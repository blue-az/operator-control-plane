from __future__ import annotations

import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import authority_admin  # noqa: E402
import authority_broker  # noqa: E402


@unittest.skipUnless(os.geteuid() == 0, "requires root for a real broker UID drop")
class TestAuthorityAdminRootBoundary(unittest.TestCase):
    def setUp(self) -> None:
        self.root_stage: Path | None = None
        self.mounted: list[Path] = []
        self.root = Path(tempfile.mkdtemp(prefix="operator-admin-root.")).resolve()
        os.chmod(self.root, 0o755)
        (self.root / "var/lib").mkdir(parents=True, mode=0o755)
        os.chmod(self.root / "var", 0o755)
        os.chmod(self.root / "var/lib", 0o755)
        self.layout = authority_admin.InstallLayout.under(self.root)
        self.source = self.root / "release"
        self.source.mkdir(mode=0o700)
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(REPO_ROOT / name, self.source / name)
            os.chmod(self.source / name, 0o700 if name == "operator-admin" else 0o600)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir(mode=0o700)
        broker_account = pwd.getpwnam("nobody")
        socket_gid = 0 if broker_account.pw_gid != 0 else 1
        self.identity = authority_admin.DeploymentIdentity(
            0,
            0,
            broker_account.pw_name,
            broker_account.pw_uid,
            broker_account.pw_gid,
            "root",
            socket_gid,
        )
        self.policy_value = {
            "policy_schema_version": 1,
            "policy_id": "root-boundary-policy",
            "ledger_id": "root-boundary-ledger",
            "policy_generation": 1,
            "previous_policy_sha256": None,
            "mode": "enforced",
            "uid_names": {"200001": "fixture-builder", "200002": "fixture-verifier"},
            "roles": {"200001": ["builder"], "200002": ["verifier"]},
        }
        self.policy_file = self.inputs / "policy.json"
        self.policy_file.write_text(json.dumps(self.policy_value) + "\n", encoding="ascii")
        os.chmod(self.policy_file, 0o600)

    def tearDown(self) -> None:
        for path in reversed(self.mounted):
            subprocess.run(["/usr/bin/umount", str(path)], check=False)
        shutil.rmtree(self.root)
        if self.root_stage is not None:
            shutil.rmtree(self.root_stage)

    def test_every_sqlite_open_follows_real_uid_drop_and_store_is_broker_owned(self) -> None:
        traced_connect = authority_broker.AuthorityStore.connect

        def connect(store, *args, **kwargs):
            trace_path = self.layout.state_root / "sqlite-open-uids"
            with trace_path.open("a", encoding="ascii") as stream:
                stream.write(f"{os.geteuid()}\n")
                stream.flush()
                os.fsync(stream.fileno())
            return traced_connect(store, *args, **kwargs)

        with mock.patch.object(authority_broker.AuthorityStore, "connect", new=connect):
            result = authority_admin.install_deployment(
                self.layout,
                self.source,
                self.policy_file,
                self.identity,
                validate_accounts=False,
            )
        observed = {
            int(value)
            for value in (self.layout.state_root / "sqlite-open-uids")
            .read_text(encoding="ascii")
            .splitlines()
        }
        self.assertEqual(observed, {self.identity.broker_uid})
        self.assertEqual(result["store_created_by_uid"], self.identity.broker_uid)
        database = self.layout.database_path.stat()
        self.assertEqual(database.st_uid, self.identity.broker_uid)
        self.assertEqual(database.st_gid, self.identity.broker_gid)
        self.assertEqual(stat.S_IMODE(database.st_mode), 0o600)
        state = self.layout.state_root.stat()
        self.assertEqual(
            (state.st_uid, state.st_gid),
            (
                self.identity.broker_uid,
                self.identity.broker_gid,
            ),
        )

        identity_result = authority_admin.run_as_broker(
            self.identity,
            lambda: {
                "uid": os.geteuid(),
                "gid": os.getegid(),
                "groups": os.getgroups(),
            },
        )
        self.assertEqual(identity_result["uid"], self.identity.broker_uid)
        self.assertEqual(identity_result["gid"], self.identity.broker_gid)
        self.assertEqual(identity_result["groups"], [])

    def test_broker_uid_cannot_administer_or_read_root_policy(self) -> None:
        authority_admin.install_deployment(
            self.layout,
            self.source,
            self.policy_file,
            self.identity,
            validate_accounts=False,
        )

        def broker_attempt() -> dict:
            authority_admin.load_manifest(self.layout, 0, 0, validate_binding=False)
            return {"unexpected": True}

        with self.assertRaises(authority_admin.AdminError):
            authority_admin.run_as_broker(self.identity, broker_attempt)
        self.assertEqual(self.layout.config_root.stat().st_uid, 0)
        self.assertEqual(stat.S_IMODE(self.layout.config_root.stat().st_mode), 0o700)

    def test_wrong_store_owner_and_parent_owner_fail_before_sqlite(self) -> None:
        authority_admin.install_deployment(
            self.layout,
            self.source,
            self.policy_file,
            self.identity,
            validate_accounts=False,
        )
        os.chown(self.layout.database_path, 0, 0)
        with self.assertRaisesRegex(authority_admin.AdminError, "store file"):
            authority_admin.audit_deployment(self.layout, 0, 0, validate_binding=False)
        os.chown(
            self.layout.database_path,
            self.identity.broker_uid,
            self.identity.broker_gid,
        )
        os.chown(self.layout.state_root, 0, 0)
        with self.assertRaisesRegex(authority_admin.AdminError, "directory owner"):
            authority_admin.audit_deployment(self.layout, 0, 0, validate_binding=False)

    def test_root_owned_wrapper_ignores_hostile_environment_and_cwd(self) -> None:
        user_namespace = os.environ.get("OPERATOR_USERNS_ROOT") == "1"
        if user_namespace:
            chroot = self.root / "wrapper-chroot"
            for path in (
                chroot / "usr/bin",
                chroot / "usr/lib",
                chroot / "usr/lib64",
                chroot / "lib64",
                chroot / "opt/operator",
                chroot / "hostile",
            ):
                path.mkdir(parents=True, exist_ok=True, mode=0o755)
            for source, target in (
                (Path("/lib64"), chroot / "lib64"),
                (Path("/usr/lib"), chroot / "usr/lib"),
                (Path("/usr/lib64"), chroot / "usr/lib64"),
            ):
                subprocess.run(
                    ["/usr/bin/mount", "--bind", str(source), str(target)],
                    check=True,
                )
                self.mounted.append(target)
            shutil.copyfile(Path("/usr/bin/python3").resolve(), chroot / "usr/bin/python3")
            os.chmod(chroot / "usr/bin/python3", 0o755)
            staged = chroot / "opt/operator"
            hostile = chroot / "hostile"
            command = [
                "/usr/bin/chroot",
                str(chroot),
                "/opt/operator/operator-admin",
            ]
            hostile_environment = {
                "PATH": "/hostile",
                "PYTHONPATH": "/hostile",
                "PYTHONHOME": "/hostile",
                "HOME": "/hostile",
            }
        else:
            self.root_stage = Path(
                tempfile.mkdtemp(prefix="operator-admin-stage.", dir="/root")
            ).resolve()
            staged = self.root_stage
            os.chmod(staged, 0o755)
            hostile = self.root / "hostile"
            hostile.mkdir(mode=0o777)
            command = [str(staged / "operator-admin")]
            hostile_environment = {
                "PATH": str(hostile),
                "PYTHONPATH": str(hostile),
                "PYTHONHOME": str(hostile),
                "HOME": str(hostile),
            }
        wrapper = staged / "operator-admin"
        shutil.copyfile(REPO_ROOT / "operator-admin", wrapper)
        os.chmod(wrapper, 0o755)
        (staged / "authority_admin.py").write_text(
            "import json, os\n"
            "def main():\n"
            "    print(json.dumps({'cwd': os.getcwd(), 'environment': dict(os.environ)}))\n"
            "    return 0\n",
            encoding="ascii",
        )
        os.chmod(staged / "authority_admin.py", 0o644)
        (staged / "authority_broker.py").write_text("", encoding="ascii")
        os.chmod(staged / "authority_broker.py", 0o644)
        (hostile / "authority_admin.py").write_text(
            "raise RuntimeError('hostile import executed')\n", encoding="ascii"
        )
        completed = subprocess.run(
            command,
            cwd="/",
            env=hostile_environment,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["cwd"], "/")
        self.assertEqual(result["environment"], {"LANG": "C"})

        os.chmod(staged / "authority_admin.py", 0o666)
        rejected = subprocess.run(
            command,
            cwd="/",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("unsafe privileged code path", rejected.stderr)

        os.chmod(staged / "authority_admin.py", 0o644)
        os.chmod(staged / "authority_broker.py", 0o666)
        rejected = subprocess.run(
            command,
            cwd="/",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("unsafe privileged code path", rejected.stderr)


if __name__ == "__main__":
    unittest.main()
