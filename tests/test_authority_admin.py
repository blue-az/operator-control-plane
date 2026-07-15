from __future__ import annotations

import grp
import json
import os
import pwd
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import authority_admin  # noqa: E402
import authority_broker  # noqa: E402
import socket_permission_helper  # noqa: E402


class TestAuthorityAdmin(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="operator-admin-test.")).resolve()
        os.chmod(self.root, 0o700)
        self.layout = authority_admin.InstallLayout.under(self.root)
        self.source = self.root / "release"
        self.source.mkdir(mode=0o700)
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(REPO_ROOT / name, self.source / name)
            os.chmod(self.source / name, 0o700 if name == "operator-admin" else 0o600)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir(mode=0o700)
        account = pwd.getpwuid(os.getuid())
        group = grp.getgrgid(os.getgid())
        self.identity = authority_admin.DeploymentIdentity(
            os.getuid(),
            os.getgid(),
            account.pw_name,
            os.getuid(),
            os.getgid(),
            group.gr_name,
            os.getgid(),
        )
        self.ledger_id = "ledger-test"
        self.policy_id = "policy-test"
        self.builder_uid = os.getuid() + 40000
        self.verifier_uid = os.getuid() + 40001

    def tearDown(self) -> None:
        shutil.rmtree(self.root)

    def policy_object(
        self,
        generation: int,
        previous: str | None,
        *,
        ledger_id: str | None = None,
        policy_id: str | None = None,
    ) -> dict:
        return {
            "policy_schema_version": 1,
            "policy_id": policy_id or self.policy_id,
            "ledger_id": ledger_id or self.ledger_id,
            "policy_generation": generation,
            "previous_policy_sha256": previous,
            "mode": "enforced",
            "uid_names": {
                str(self.builder_uid): "fixture-builder",
                str(self.verifier_uid): "fixture-verifier",
            },
            "roles": {
                str(self.builder_uid): ["builder"],
                str(self.verifier_uid): ["verifier"],
            },
        }

    def write_policy(
        self,
        name: str,
        generation: int,
        previous: str | None,
        **changes: object,
    ) -> tuple[Path, authority_admin.PolicyDocument]:
        value = self.policy_object(generation, previous)
        value.update(changes)
        path = self.inputs / name
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
        return path, authority_admin.parse_policy_object(value)

    def install(self) -> tuple[dict, authority_admin.PolicyDocument, Path]:
        path, policy = self.write_policy("generation-1.json", 1, None)
        result = authority_admin.install_deployment(
            self.layout,
            self.source,
            path,
            self.identity,
            validate_accounts=False,
        )
        return result, policy, path

    def make_evidence(
        self,
        policy: authority_admin.PolicyDocument,
        *,
        collected_at: int | None = None,
        ledger_id: str | None = None,
        policy_id: str | None = None,
        policy_generation: int | None = None,
        policy_sha256: str | None = None,
        statuses: dict[str, str] | None = None,
    ) -> dict:
        checks = {
            check_id: {
                "status": (statuses or {}).get(check_id, "pass"),
                "evidence": {"synthetic": True},
            }
            for check_id in authority_admin.EVIDENCE_CHECK_IDS
        }
        return {
            "evidence_schema_version": authority_admin.EVIDENCE_SCHEMA_VERSION,
            "ledger_id": ledger_id if ledger_id is not None else policy.ledger_id,
            "policy_id": policy_id if policy_id is not None else policy.policy_id,
            "policy_generation": (
                policy_generation if policy_generation is not None else policy.generation
            ),
            "policy_sha256": policy_sha256 if policy_sha256 is not None else policy.sha256,
            "collected_at": collected_at if collected_at is not None else int(time.time()),
            "checks": checks,
        }

    def write_evidence(self, evidence: dict) -> None:
        authority_admin.write_protected_file(
            self.layout.evidence_path,
            authority_admin.json_bytes(evidence),
            0o600,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
            replace=True,
        )

    def inspect(self) -> dict:
        return authority_admin.run_store_action(
            self.layout,
            self.identity,
            lambda: authority_admin.inspect_store(self.layout),
        )

    def claim_request(self, operation_key: str, task_id: str, claim_id: str) -> dict:
        return authority_broker.normalize_request(
            {
                "protocol_version": 1,
                "action": "commit",
                "ledger_id": self.ledger_id,
                "operation_key": operation_key,
                "operation": {
                    "kind": "claim.create",
                    "task_id": task_id,
                    "claim_id": claim_id,
                    "claim_type": "test_passes",
                    "text": "fixture claim",
                },
                "expected": [
                    {
                        "record_type": "task",
                        "record_id": task_id,
                        "version": 0,
                        "event_hash": None,
                    },
                    {
                        "record_type": "claim",
                        "record_id": claim_id,
                        "version": 0,
                        "event_hash": None,
                    },
                ],
            }
        )

    def commit_claim(self, operation_key: str, task_id: str, claim_id: str) -> tuple[dict, dict]:
        request = self.claim_request(operation_key, task_id, claim_id)
        store = authority_broker.AuthorityStore(self.layout.database_path, self.layout.content_root)
        receipt, _ = store.commit(
            request,
            authority_broker.PeerCredentials(12345, self.builder_uid, self.builder_uid),
            authority_broker.digest_request(request),
            [],
        )
        return receipt, request

    def test_install_rotate_revoke_and_audit(self) -> None:
        result, first, _ = self.install()
        self.assertEqual(result["event"]["event_type"], "enroll")
        self.assertEqual(result["store_created_by_uid"], self.identity.broker_uid)
        self.assertFalse(result["service_started"])
        unit = self.layout.unit_path.read_text(encoding="ascii")
        self.assertIn("ExecStart=/usr/bin/python3 -I ", unit)
        self.assertIn("ExecStartPre=/usr/bin/python3 -I ", unit)
        self.assertIn("ExecStartPost=/usr/bin/python3 -I ", unit)
        self.assertNotIn("/usr/bin/chmod", unit)
        self.assertIn("WorkingDirectory=/", unit)
        self.assertIn("UnsetEnvironment=PYTHONPATH PYTHONHOME PYTHONUSERBASE", unit)

        second_path, second = self.write_policy("generation-2.json", 2, first.sha256)
        rotated = authority_admin.rotate_deployment(
            self.layout,
            second_path,
            os.getuid(),
            os.getgid(),
            validate_accounts=False,
        )
        self.assertEqual(rotated["event"]["event_type"], "rotate")
        revoked = authority_admin.revoke_deployment(
            self.layout,
            self.ledger_id,
            second.sha256,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        self.assertEqual(revoked["event"]["event_type"], "revoke")
        audit = authority_admin.audit_deployment(
            self.layout, os.getuid(), os.getgid(), validate_binding=False
        )
        self.assertTrue(audit["ok"])
        self.assertEqual(audit["policy_generations"], 2)
        self.assertEqual(audit["current"]["state"], "revoked")

    def test_policy_schema_rejects_unknown_malformed_and_advisory(self) -> None:
        base = self.policy_object(1, None)
        cases = [
            {**base, "unknown": True},
            {**base, "mode": "single_user"},
            {**base, "previous_policy_sha256": "0" * 64},
            {**base, "policy_generation": 0},
        ]
        duplicate = json.loads(json.dumps(base))
        duplicate["roles"][str(self.builder_uid)] = ["builder", "builder"]
        cases.append(duplicate)
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(authority_admin.AdminError):
                    authority_admin.parse_policy_object(value)

    def test_broker_commits_bind_policy_selected_inside_transaction(self) -> None:
        _, first, _ = self.install()
        before, _ = self.commit_claim("before", "task-0001", "claim-0001")
        second_path, second = self.write_policy("generation-2.json", 2, first.sha256)
        authority_admin.rotate_deployment(
            self.layout,
            second_path,
            os.getuid(),
            os.getgid(),
            validate_accounts=False,
        )
        after, _ = self.commit_claim("after", "task-0002", "claim-0002")
        self.assertEqual(before["policy"]["generation"], 1)
        self.assertEqual(before["policy"]["sha256"], first.sha256)
        self.assertEqual(after["policy"]["generation"], 2)
        self.assertEqual(after["policy"]["sha256"], second.sha256)

    def test_broker_commit_racing_rotation_binds_one_complete_generation(self) -> None:
        _, first, _ = self.install()
        second_path, second = self.write_policy("generation-2.json", 2, first.sha256)
        barrier = threading.Barrier(2)

        def rotate() -> dict:
            barrier.wait()
            return authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
            )

        def commit() -> tuple[dict, dict]:
            barrier.wait()
            return self.commit_claim("racing", "task-0001", "claim-0001")

        with ThreadPoolExecutor(max_workers=2) as executor:
            rotation = executor.submit(rotate)
            committed = executor.submit(commit)
            rotation.result(timeout=10)
            receipt, _ = committed.result(timeout=10)
        expected = {1: first.sha256, 2: second.sha256}
        self.assertIn(receipt["policy"]["generation"], expected)
        self.assertEqual(receipt["policy"]["sha256"], expected[receipt["policy"]["generation"]])
        conn = sqlite3.connect(self.layout.database_path)
        try:
            generations = {
                row[0]
                for row in conn.execute(
                    "SELECT policy_generation FROM authority_events " "WHERE commit_sequence = ?",
                    (receipt["commit_sequence"],),
                )
            }
        finally:
            conn.close()
        self.assertEqual(generations, {receipt["policy"]["generation"]})

    def test_store_symlink_hardlink_mode_and_parent_fail_closed(self) -> None:
        self.install()
        hardlink = self.root / "database-link"
        os.link(self.layout.database_path, hardlink)
        with self.assertRaisesRegex(authority_admin.AdminError, "store file"):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )
        hardlink.unlink()

        os.chmod(self.layout.database_path, 0o640)
        with self.assertRaisesRegex(authority_admin.AdminError, "store file"):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )
        os.chmod(self.layout.database_path, 0o600)

        sidecar_target = self.root / "sidecar-target"
        sidecar_target.write_bytes(b"not sqlite")
        wal = Path(str(self.layout.database_path) + "-wal")
        retained_wal = self.root / "retained-wal"
        had_wal = wal.exists()
        if had_wal:
            wal.rename(retained_wal)
        wal.symlink_to(sidecar_target)
        with self.assertRaises(authority_admin.AdminError):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )
        wal.unlink()
        if had_wal:
            retained_wal.rename(wal)

        retained = self.root / "retained.sqlite3"
        self.layout.database_path.rename(retained)
        self.layout.database_path.symlink_to(retained)
        with self.assertRaises(authority_admin.AdminError):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )
        self.layout.database_path.unlink()
        retained.rename(self.layout.database_path)

        os.chmod(self.layout.state_root.parent, 0o770)
        with self.assertRaisesRegex(authority_admin.AdminError, "writable"):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )

    def test_policy_hardlink_and_config_symlink_fail_closed(self) -> None:
        _, policy, _ = self.install()
        archive = authority_admin.policy_path(self.layout, policy)
        hardlink = self.root / "policy-link"
        os.link(archive, hardlink)
        with self.assertRaisesRegex(authority_admin.AdminError, "protected file"):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )
        hardlink.unlink()

        retained = self.root / "retained-config"
        self.layout.config_root.rename(retained)
        self.layout.config_root.symlink_to(retained, target_is_directory=True)
        with self.assertRaises(authority_admin.AdminError):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )

    def test_store_inode_substitution_between_parent_and_child_fails(self) -> None:
        self.install()
        original = self.layout.database_path
        replacement = self.root / "replacement.sqlite3"
        shutil.copyfile(original, replacement)
        os.chmod(replacement, 0o600)

        real_run = authority_admin.run_as_broker

        def substitute(identity: authority_admin.DeploymentIdentity, callback):
            old = self.root / "old.sqlite3"
            original.rename(old)
            replacement.rename(original)
            try:
                return real_run(identity, callback)
            finally:
                if original.exists():
                    original.unlink()
                old.rename(original)

        with mock.patch.object(authority_admin, "run_as_broker", side_effect=substitute):
            with self.assertRaisesRegex(authority_admin.AdminError, "database changed"):
                authority_admin.run_store_action(
                    self.layout,
                    self.identity,
                    lambda: authority_admin.inspect_store(self.layout),
                )

    def test_store_substitution_during_callback_fails_postcheck(self) -> None:
        self.install()
        original = self.layout.database_path
        replacement = self.root / "replacement.sqlite3"
        shutil.copyfile(original, replacement)
        os.chmod(replacement, 0o600)
        retained = self.root / "retained.sqlite3"

        def substitute_during_callback() -> dict:
            result = authority_admin.inspect_store(self.layout)
            original.rename(retained)
            replacement.rename(original)
            return result

        try:
            with self.assertRaisesRegex(authority_admin.AdminError, "database changed"):
                authority_admin.run_store_action(
                    self.layout, self.identity, substitute_during_callback
                )
        finally:
            if original.exists():
                original.unlink()
            retained.rename(original)

    def test_sidecar_substitution_during_callback_fails_postcheck(self) -> None:
        self.install()
        sidecar = Path(str(self.layout.database_path) + "-wal")
        retained = sidecar.with_name(sidecar.name + ".retained")
        replacement = sidecar.with_name(sidecar.name + ".replacement")
        replacement.write_bytes(b"replacement")
        os.chmod(replacement, 0o600)

        def substitute() -> dict:
            sidecar.rename(retained)
            replacement.rename(sidecar)
            return {"ok": True}

        try:
            with self.assertRaisesRegex(authority_admin.AdminError, "sidecar changed"):
                authority_admin.run_store_action(self.layout, self.identity, substitute)
        finally:
            sidecar.unlink(missing_ok=True)
            replacement.unlink(missing_ok=True)
            retained.unlink(missing_ok=True)

    def test_database_initialization_is_inside_broker_guard(self) -> None:
        authority_admin.ensure_layout(self.layout, self.identity)
        observed = []
        real_connect = authority_broker.AuthorityStore.connect

        def connect(store, *args, **kwargs):
            observed.append(os.geteuid())
            return real_connect(store, *args, **kwargs)

        def broker_guard(identity, callback):
            self.assertFalse(self.layout.database_path.exists())
            with mock.patch.object(authority_admin.os, "geteuid", return_value=identity.broker_uid):
                return callback()

        with (
            mock.patch.object(authority_admin, "run_as_broker", side_effect=broker_guard),
            mock.patch.object(authority_broker.AuthorityStore, "connect", new=connect),
        ):
            authority_admin.initialize_store_as_broker(self.layout, self.identity)
        self.assertEqual(observed, [self.identity.broker_uid])

    def test_exact_reinstall_is_read_only_and_changed_reinstall_fails(self) -> None:
        first_result, _, policy_path = self.install()
        before = self.inspect()
        database_inode = self.layout.database_path.stat().st_ino
        database_mtime = self.layout.database_path.stat().st_mtime_ns
        replay = authority_admin.install_deployment(
            self.layout,
            self.source,
            policy_path,
            self.identity,
            validate_accounts=False,
        )
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(before, self.inspect())
        self.assertEqual(database_inode, self.layout.database_path.stat().st_ino)
        self.assertEqual(database_mtime, self.layout.database_path.stat().st_mtime_ns)
        self.assertEqual(first_result["policy"], replay["policy"])

        source_admin = self.source / "authority_admin.py"
        source_admin.write_bytes(source_admin.read_bytes() + b"\n")
        with self.assertRaisesRegex(authority_admin.AdminError, "asset"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(before, self.inspect())

    def test_completed_install_rejects_pending_files_and_unsafe_lock(self) -> None:
        _, _, policy_path = self.install()
        manifest = json.loads(self.layout.manifest_path.read_text(encoding="ascii"))
        targets = [
            Path(next(iter(manifest["assets"]))),
            self.layout.active_path,
            self.layout.manifest_path,
        ]
        for target in targets:
            with self.subTest(target=target):
                pending = target.parent / f".{target.name}.pending"
                pending.write_bytes(b"foreign\n")
                os.chmod(pending, 0o600)
                with self.assertRaisesRegex(authority_admin.AdminError, "pending file"):
                    authority_admin.audit_deployment(
                        self.layout, os.getuid(), os.getgid(), validate_binding=False
                    )
                pending.unlink()

        os.chmod(self.layout.lock_path, 0o644)
        with self.assertRaisesRegex(authority_admin.AdminError, "metadata differs"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(stat.S_IMODE(self.layout.lock_path.stat().st_mode), 0o644)

    def test_install_recovers_exact_commit_before_manifest(self) -> None:
        policy_path, policy = self.write_policy("generation-1.json", 1, None)

        def crash(_event: dict) -> None:
            raise RuntimeError("crash before manifest")

        with self.assertRaisesRegex(RuntimeError, "before manifest"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
                after_activation=crash,
            )
        self.assertFalse(self.layout.manifest_path.exists())
        self.assertEqual(len(self.inspect()["policy_events"]), 1)
        recovered = authority_admin.install_deployment(
            self.layout,
            self.source,
            policy_path,
            self.identity,
            validate_accounts=False,
        )
        self.assertFalse(recovered["idempotent_replay"])
        self.assertEqual(recovered["policy"]["sha256"], policy.sha256)
        self.assertTrue(
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )["ok"]
        )

    def test_install_recovers_exact_policy_pending(self) -> None:
        policy_path, policy = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        for root in (self.layout.policies_root, self.layout.revocations_root):
            authority_admin.ensure_directory(
                root / policy.ledger_id,
                0o700,
                self.identity.admin_uid,
                self.identity.admin_gid,
                self.layout,
                self.identity,
            )
        target = authority_admin.policy_path(self.layout, policy)
        pending = target.parent / f".{target.name}.pending"
        pending.write_bytes((policy.canonical_json + "\n").encode("ascii"))
        os.chmod(pending, 0o600)
        result = authority_admin.install_deployment(
            self.layout,
            self.source,
            policy_path,
            self.identity,
            validate_accounts=False,
        )
        self.assertTrue(result["audit"]["ok"])
        self.assertFalse(pending.exists())
        self.assertEqual(target.read_bytes(), (policy.canonical_json + "\n").encode("ascii"))

    def test_install_recovers_exact_active_and_manifest_pending(self) -> None:
        policy_path, policy = self.write_policy("generation-1.json", 1, None)

        def crash(_event: dict) -> None:
            raise RuntimeError("crash after activation")

        with self.assertRaises(RuntimeError):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
                after_activation=crash,
            )
        event = self.inspect()["policy_events"][-1]
        active_pending = self.layout.active_path.parent / f".{self.layout.active_path.name}.pending"
        active_pending.write_bytes(authority_admin.json_bytes(authority_admin.active_index(event)))
        os.chmod(active_pending, 0o600)
        source_assets = authority_admin.read_source_assets(self.source, self.layout, self.identity)
        payloads = authority_admin.expected_asset_payloads(
            self.layout, self.identity, source_assets
        )
        asset_entries = {
            str(path): {
                "sha256": authority_admin.sha256_bytes(data),
                "mode": mode,
                "uid": self.identity.admin_uid,
                "gid": self.identity.admin_gid,
            }
            for path, (data, mode) in payloads.items()
        }
        manifest_pending = self.layout.manifest_path.parent / (
            f".{self.layout.manifest_path.name}.pending"
        )
        manifest_pending.write_bytes(
            authority_admin.json_bytes(
                authority_admin.install_manifest(self.layout, self.identity, policy, asset_entries)
            )
        )
        os.chmod(manifest_pending, 0o600)
        result = authority_admin.install_deployment(
            self.layout,
            self.source,
            policy_path,
            self.identity,
            validate_accounts=False,
        )
        self.assertTrue(result["audit"]["ok"])
        self.assertFalse(active_pending.exists())
        self.assertFalse(manifest_pending.exists())

    def test_install_recovery_rejects_divergent_active_index(self) -> None:
        policy_path, _ = self.write_policy("generation-1.json", 1, None)

        def crash(_event: dict) -> None:
            raise RuntimeError("crash before manifest")

        with self.assertRaises(RuntimeError):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
                after_activation=crash,
            )
        event = self.inspect()["policy_events"][-1]
        authority_admin.write_protected_file(
            self.layout.active_path,
            authority_admin.json_bytes(authority_admin.active_index(event)),
            0o600,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        self.layout.active_path.write_bytes(b"{}\n")
        with self.assertRaisesRegex(authority_admin.AdminError, "active index differs"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(self.layout.active_path.read_bytes(), b"{}\n")
        self.assertFalse(self.layout.manifest_path.exists())

    def test_empty_store_recovery_rejects_any_active_index(self) -> None:
        policy_path, policy = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        for root in (self.layout.policies_root, self.layout.revocations_root):
            authority_admin.ensure_directory(
                root / policy.ledger_id,
                0o700,
                self.identity.admin_uid,
                self.identity.admin_gid,
                self.layout,
                self.identity,
            )
        authority_admin.write_protected_file(
            authority_admin.policy_path(self.layout, policy),
            (policy.canonical_json + "\n").encode("ascii"),
            0o600,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        authority_admin.initialize_store_as_broker(self.layout, self.identity)
        authority_admin.write_protected_file(
            self.layout.active_path,
            b"{}\n",
            0o600,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        with self.assertRaisesRegex(authority_admin.AdminError, "has an active index"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(self.layout.active_path.read_bytes(), b"{}\n")
        self.assertFalse(self.layout.manifest_path.exists())

    def test_fresh_install_rejects_active_index_without_database(self) -> None:
        policy_path, _ = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        authority_admin.write_protected_file(
            self.layout.active_path,
            b"{}\n",
            0o600,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        with self.assertRaisesRegex(authority_admin.AdminError, "without an authority database"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(self.layout.active_path.read_bytes(), b"{}\n")
        self.assertFalse(self.layout.database_path.exists())
        self.assertFalse(self.layout.manifest_path.exists())

    def test_fresh_install_rejects_rollback_journal_without_mutation(self) -> None:
        policy_path, _ = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        journal = Path(str(self.layout.database_path) + "-journal")
        journal.write_bytes(b"foreign journal")
        os.chmod(journal, 0o600)
        with self.assertRaisesRegex(authority_admin.AdminError, "sidecar"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(journal.read_bytes(), b"foreign journal")
        self.assertFalse(self.layout.database_path.exists())
        self.assertFalse(self.layout.manifest_path.exists())

    def test_install_preflight_rejects_unsafe_socket_before_mutation(self) -> None:
        policy_path, _ = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        self.layout.socket_path.write_bytes(b"not a socket")
        os.chmod(self.layout.socket_path, 0o600)
        with self.assertRaisesRegex(authority_admin.AdminError, "socket metadata"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(self.layout.socket_path.read_bytes(), b"not a socket")
        self.assertFalse(self.layout.database_path.exists())
        self.assertFalse(self.layout.manifest_path.exists())

    def test_install_preflight_rejects_unsafe_lock_before_mutation(self) -> None:
        policy_path, _ = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        self.layout.lock_path.write_bytes(b"")
        os.chmod(self.layout.lock_path, 0o644)
        shutil.rmtree(self.layout.install_root)
        with self.assertRaisesRegex(authority_admin.AdminError, "metadata differs"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertFalse(self.layout.install_root.exists())
        self.assertEqual(self.layout.lock_path.read_bytes(), b"")
        self.assertEqual(stat.S_IMODE(self.layout.lock_path.stat().st_mode), 0o644)
        self.assertFalse(self.layout.database_path.exists())
        self.assertFalse(self.layout.manifest_path.exists())

    def test_install_preflight_rejects_manifest_pending_before_mutation(self) -> None:
        policy_path, _ = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        pending = self.layout.manifest_path.parent / f".{self.layout.manifest_path.name}.pending"
        pending.write_bytes(b"foreign\n")
        os.chmod(pending, 0o600)
        with self.assertRaisesRegex(authority_admin.AdminError, "unexpected pending"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(pending.read_bytes(), b"foreign\n")
        self.assertFalse(self.layout.database_path.exists())
        self.assertFalse(self.layout.active_path.exists())
        self.assertFalse(self.layout.manifest_path.exists())

    def test_different_ledger_reinstall_fails_before_store_mutation(self) -> None:
        self.install()
        before = self.inspect()
        other_path, _ = self.write_policy(
            "other.json", 1, None, ledger_id="other-ledger", policy_id="other-policy"
        )
        with self.assertRaisesRegex(authority_admin.AdminError, "identity differs"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                other_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertEqual(before, self.inspect())
        self.assertTrue(
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )["ok"]
        )

    def test_foreign_preexisting_store_is_rejected(self) -> None:
        authority_admin.ensure_layout(self.layout, self.identity)
        config_path = self.inputs / "bootstrap.json"
        config_path.write_text(
            json.dumps(
                {
                    "policy_id": "foreign-policy",
                    "policy_generation": 1,
                    "ledgers": ["foreign-ledger"],
                    "roles": {
                        str(self.builder_uid): ["builder"],
                        str(self.verifier_uid): ["verifier"],
                    },
                }
            ),
            encoding="ascii",
        )
        config = authority_broker.read_bootstrap_config(config_path)
        authority_broker.AuthorityStore(
            self.layout.database_path, self.layout.content_root
        ).initialize(config)
        path, _ = self.write_policy("generation-1.json", 1, None)
        with self.assertRaisesRegex(authority_admin.AdminError, "archive"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                path,
                self.identity,
                validate_accounts=False,
            )

    def test_foreign_archive_directory_is_rejected_and_audited(self) -> None:
        authority_admin.ensure_layout(self.layout, self.identity)
        foreign_policy_root = self.layout.policies_root / "foreign-ledger"
        authority_admin.ensure_directory(
            foreign_policy_root,
            0o700,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        path, _ = self.write_policy("generation-1.json", 1, None)
        with self.assertRaisesRegex(authority_admin.AdminError, "foreign ledger archive"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                path,
                self.identity,
                validate_accounts=False,
            )

        shutil.rmtree(foreign_policy_root)
        self.install()
        foreign_policy_root.mkdir(mode=0o700)
        with self.assertRaisesRegex(authority_admin.AdminError, "directory set"):
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )

    def test_concurrent_fresh_installs_leave_one_exact_archive(self) -> None:
        first_path, _ = self.write_policy("first.json", 1, None)
        second_path, _ = self.write_policy(
            "second.json",
            1,
            None,
            ledger_id="second-ledger",
            policy_id="second-policy",
        )
        barrier = threading.Barrier(2)

        def install(path: Path) -> tuple[str, object]:
            barrier.wait()
            try:
                return (
                    "ok",
                    authority_admin.install_deployment(
                        self.layout,
                        self.source,
                        path,
                        self.identity,
                        validate_accounts=False,
                    ),
                )
            except Exception as exc:
                return "error", exc

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = [
                future.result(timeout=10)
                for future in (
                    executor.submit(install, first_path),
                    executor.submit(install, second_path),
                )
            ]
        self.assertEqual([status for status, _ in results].count("ok"), 1)
        manifest = json.loads(self.layout.manifest_path.read_text(encoding="ascii"))
        self.assertEqual(set(os.listdir(self.layout.policies_root)), {manifest["ledger_id"]})
        self.assertEqual(set(os.listdir(self.layout.revocations_root)), {manifest["ledger_id"]})
        self.assertTrue(
            authority_admin.audit_deployment(
                self.layout, os.getuid(), os.getgid(), validate_binding=False
            )["ok"]
        )

    def test_archive_recovers_both_crash_windows(self) -> None:
        _, first, _ = self.install()
        second_path, second = self.write_policy("generation-2.json", 2, first.sha256)

        def crash_after_fsync(stage: str, _path: Path) -> None:
            if stage == "after_file_fsync":
                raise RuntimeError("crash after file fsync")

        with self.assertRaisesRegex(RuntimeError, "file fsync"):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
                archive_fault=crash_after_fsync,
            )
        self.assertTrue(
            (
                authority_admin.policy_path(self.layout, second).parent
                / f".{authority_admin.policy_path(self.layout, second).name}.pending"
            ).exists()
        )
        recovered = authority_admin.rotate_deployment(
            self.layout,
            second_path,
            os.getuid(),
            os.getgid(),
            validate_accounts=False,
        )
        self.assertEqual(recovered["event"]["event_type"], "rotate")
        archived = authority_admin.policy_path(self.layout, second)
        self.assertEqual(archived.stat().st_nlink, 1)

        third_path, third = self.write_policy("generation-3.json", 3, second.sha256)

        def crash_after_publish(stage: str, _path: Path) -> None:
            if stage == "after_publish":
                raise RuntimeError("crash after publish")

        with self.assertRaisesRegex(RuntimeError, "after publish"):
            authority_admin.rotate_deployment(
                self.layout,
                third_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
                archive_fault=crash_after_publish,
            )
        self.assertTrue(authority_admin.policy_path(self.layout, third).is_file())
        recovered = authority_admin.rotate_deployment(
            self.layout,
            third_path,
            os.getuid(),
            os.getgid(),
            validate_accounts=False,
        )
        self.assertEqual(recovered["event"]["generation"], 3)
        self.assertEqual(authority_admin.policy_path(self.layout, third).stat().st_nlink, 1)

    def test_divergent_pending_archive_fails_closed(self) -> None:
        _, first, _ = self.install()
        second_path, second = self.write_policy("generation-2.json", 2, first.sha256)

        def crash_after_fsync(stage: str, _path: Path) -> None:
            if stage == "after_file_fsync":
                raise RuntimeError("crash after file fsync")

        with self.assertRaises(RuntimeError):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
                archive_fault=crash_after_fsync,
            )
        pending = authority_admin.policy_path(self.layout, second).parent / (
            f".{authority_admin.policy_path(self.layout, second).name}.pending"
        )
        pending.write_bytes(b"{}\n")
        os.chmod(pending, 0o600)
        with self.assertRaisesRegex(authority_admin.AdminError, "pending"):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
            )
        self.assertEqual(pending.read_bytes(), b"{}\n")

    def test_pending_archive_is_not_cleaned_before_structural_preflight(self) -> None:
        _, first, _ = self.install()
        second_path, second = self.write_policy("generation-2.json", 2, first.sha256)

        def crash_after_fsync(stage: str, _path: Path) -> None:
            if stage == "after_file_fsync":
                raise RuntimeError("crash after file fsync")

        with self.assertRaises(RuntimeError):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
                archive_fault=crash_after_fsync,
            )
        pending = authority_admin.policy_path(self.layout, second).parent / (
            f".{authority_admin.policy_path(self.layout, second).name}.pending"
        )
        self.assertTrue(pending.exists())
        os.chmod(self.layout.config_root, 0o770)
        with self.assertRaises(authority_admin.AdminError):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
            )
        self.assertTrue(pending.exists())

    def test_pending_revocation_blocks_rotation_and_revoke_recovers(self) -> None:
        _, first, _ = self.install()

        def crash(_intent: dict) -> None:
            raise RuntimeError("crash after intent")

        with self.assertRaisesRegex(RuntimeError, "after intent"):
            authority_admin.revoke_deployment(
                self.layout,
                self.ledger_id,
                first.sha256,
                os.getuid(),
                os.getgid(),
                after_intent=crash,
                validate_binding=False,
            )
        second_path, _ = self.write_policy("generation-2.json", 2, first.sha256)
        with self.assertRaisesRegex(authority_admin.AdminError, "revocation archive"):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
            )
        recovered = authority_admin.revoke_deployment(
            self.layout,
            self.ledger_id,
            first.sha256,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        self.assertEqual(recovered["event"]["event_type"], "revoke")

    def test_rotation_and_revocation_recover_after_database_activation(self) -> None:
        _, first, _ = self.install()
        second_path, second = self.write_policy("generation-2.json", 2, first.sha256)

        def crash_rotation(_event: dict) -> None:
            raise RuntimeError("rotation after activation")

        with self.assertRaisesRegex(RuntimeError, "rotation after activation"):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
                after_activation=crash_rotation,
            )
        self.assertEqual(len(self.inspect()["policy_events"]), 2)
        active_pending = self.layout.active_path.parent / (
            f".{self.layout.active_path.name}.pending"
        )
        active_pending.write_bytes(
            authority_admin.json_bytes(
                authority_admin.active_index(self.inspect()["policy_events"][-1])
            )
        )
        os.chmod(active_pending, 0o600)
        rotated = authority_admin.rotate_deployment(
            self.layout,
            second_path,
            os.getuid(),
            os.getgid(),
            validate_accounts=False,
        )
        self.assertTrue(rotated["event"]["idempotent_replay"])
        self.assertFalse(active_pending.exists())
        self.assertEqual(len(self.inspect()["policy_events"]), 2)
        self.assertEqual(
            json.loads(self.layout.active_path.read_text(encoding="ascii"))["policy_sha256"],
            second.sha256,
        )

        def crash_revoke(_event: dict) -> None:
            raise RuntimeError("revoke after activation")

        with self.assertRaisesRegex(RuntimeError, "revoke after activation"):
            authority_admin.revoke_deployment(
                self.layout,
                self.ledger_id,
                second.sha256,
                os.getuid(),
                os.getgid(),
                after_activation=crash_revoke,
                validate_binding=False,
            )
        self.assertEqual(len(self.inspect()["policy_events"]), 3)
        active_pending.write_bytes(
            authority_admin.json_bytes(
                authority_admin.active_index(self.inspect()["policy_events"][-1])
            )
        )
        os.chmod(active_pending, 0o600)
        revoked = authority_admin.revoke_deployment(
            self.layout,
            self.ledger_id,
            second.sha256,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        self.assertTrue(revoked["event"]["idempotent_replay"])
        self.assertFalse(active_pending.exists())
        self.assertEqual(len(self.inspect()["policy_events"]), 3)
        self.assertEqual(
            json.loads(self.layout.active_path.read_text(encoding="ascii"))["state"],
            "revoked",
        )

    def test_activation_recovery_verifies_state_before_index_repair(self) -> None:
        _, first, _ = self.install()
        second_path, _ = self.write_policy("generation-2.json", 2, first.sha256)

        def crash(_event: dict) -> None:
            raise RuntimeError("rotation after activation")

        with self.assertRaises(RuntimeError):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
                after_activation=crash,
            )
        stale_index = self.layout.active_path.read_bytes()
        os.chmod(self.layout.unit_path, 0o666)
        with self.assertRaisesRegex(authority_admin.AdminError, "metadata"):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
            )
        self.assertEqual(self.layout.active_path.read_bytes(), stale_index)

    def test_revocation_preserves_exact_committed_retry(self) -> None:
        _, first, _ = self.install()
        receipt, request = self.commit_claim("retained", "task-0001", "claim-0001")
        authority_admin.revoke_deployment(
            self.layout,
            self.ledger_id,
            first.sha256,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        store = authority_broker.AuthorityStore(self.layout.database_path, self.layout.content_root)
        replayed, replay = store.commit(
            request,
            authority_broker.PeerCredentials(99999, self.builder_uid, self.builder_uid),
            authority_broker.digest_request(request),
            [],
        )
        self.assertTrue(replay)
        self.assertEqual(replayed, receipt)

    def test_rotation_rejects_gap_fork_wrong_ledger_and_replacement(self) -> None:
        _, first, _ = self.install()
        attempts = [
            self.write_policy("gap.json", 3, first.sha256)[0],
            self.write_policy("fork.json", 2, "f" * 64)[0],
            self.write_policy("wrong.json", 2, first.sha256, ledger_id="wrong-ledger")[0],
        ]
        for path in attempts:
            with self.subTest(path=path):
                with self.assertRaises(authority_admin.AdminError):
                    authority_admin.rotate_deployment(
                        self.layout,
                        path,
                        os.getuid(),
                        os.getgid(),
                        validate_accounts=False,
                    )
        valid_path, _ = self.write_policy("generation-2.json", 2, first.sha256)
        authority_admin.rotate_deployment(
            self.layout,
            valid_path,
            os.getuid(),
            os.getgid(),
            validate_accounts=False,
        )
        replacement = self.policy_object(2, first.sha256)
        replacement["uid_names"][str(self.builder_uid)] = "replacement-builder"
        replacement_path = self.inputs / "replacement.json"
        replacement_path.write_text(json.dumps(replacement) + "\n", encoding="ascii")
        os.chmod(replacement_path, 0o600)
        with self.assertRaises(authority_admin.AdminError):
            authority_admin.rotate_deployment(
                self.layout,
                replacement_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
            )
        self.assertEqual(len(self.inspect()["policy_events"]), 2)

    def test_preflight_always_returns_complete_catalog_without_mutation(self) -> None:
        missing = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        self.assertEqual(
            tuple(item["id"] for item in missing["checks"]),
            authority_admin.PREFLIGHT_CHECK_IDS,
        )
        self.assertFalse(missing["boundary_ready"])
        self.assertFalse(self.layout.config_root.exists())

        self.install()
        manifest_mtime = self.layout.manifest_path.stat().st_mtime_ns
        self.layout.manifest_path.write_text("{}\n", encoding="ascii")
        os.chmod(self.layout.manifest_path, 0o600)
        corrupted_mtime = self.layout.manifest_path.stat().st_mtime_ns
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        self.assertEqual(
            tuple(item["id"] for item in report["checks"]),
            authority_admin.PREFLIGHT_CHECK_IDS,
        )
        self.assertEqual(
            next(item for item in report["checks"] if item["id"] == "assets.protected_paths")[
                "status"
            ],
            "fail",
        )
        self.assertFalse(report["boundary_ready"])
        self.assertNotEqual(manifest_mtime, corrupted_mtime)
        self.assertEqual(corrupted_mtime, self.layout.manifest_path.stat().st_mtime_ns)

    def test_install_preflight_rejects_all_existing_mode_violations_before_mutation(self) -> None:
        policy_path, _ = self.write_policy("generation-1.json", 1, None)
        authority_admin.ensure_layout(self.layout, self.identity)
        shutil.rmtree(self.layout.install_root)
        os.chmod(self.layout.runtime_root, 0o750)
        with self.assertRaisesRegex(authority_admin.AdminError, "directory metadata differs"):
            authority_admin.install_deployment(
                self.layout,
                self.source,
                policy_path,
                self.identity,
                validate_accounts=False,
            )
        self.assertFalse(self.layout.install_root.exists())

    def test_preflight_reports_simultaneous_structural_violations(self) -> None:
        self.install()
        os.chmod(self.layout.runtime_root, 0o750)
        os.chmod(self.layout.database_path, 0o640)
        manifest = json.loads(self.layout.manifest_path.read_text(encoding="ascii"))
        asset = Path(next(iter(manifest["assets"])))
        pending = asset.parent / f".{asset.name}.pending"
        pending.write_bytes(b"foreign\n")
        os.chmod(pending, 0o600)
        os.chmod(self.layout.lock_path, 0o644)
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        protected = next(
            item for item in report["checks"] if item["id"] == "assets.protected_paths"
        )
        self.assertEqual(protected["status"], "fail")
        messages = [entry["error"]["message"] for entry in protected["evidence"]["violations"]]
        self.assertTrue(any("runtime" in message or "/run/" in message for message in messages))
        self.assertTrue(any("store file" in message for message in messages))
        self.assertTrue(any("pending file" in message for message in messages))
        self.assertTrue(any("lock" in message for message in messages))

    def test_normal_preflight_is_complete_and_conservative(self) -> None:
        self.install()
        before = {
            str(path.relative_to(self.root)): (
                path.lstat().st_mode,
                path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None,
            )
            for path in self.root.rglob("*")
        }
        with mock.patch.object(
            authority_broker.AuthorityStore,
            "connect",
            side_effect=AssertionError("preflight must not open SQLite"),
        ):
            report = authority_admin.privilege_preflight(
                self.layout,
                os.getuid(),
                os.getgid(),
                sudo_probe=lambda _user: ("unknown", "synthetic account"),
                validate_binding=False,
            )
        after = {
            str(path.relative_to(self.root)): (
                path.lstat().st_mode,
                path.lstat().st_mtime_ns,
                path.read_bytes() if path.is_file() else None,
            )
            for path in self.root.rglob("*")
        }
        self.assertEqual(
            tuple(item["id"] for item in report["checks"]),
            authority_admin.PREFLIGHT_CHECK_IDS,
        )
        self.assertFalse(report["boundary_ready"])
        self.assertTrue(any(item["status"] == "unknown" for item in report["checks"]))
        self.assertEqual(before, after)

    def test_preflight_trusts_fresh_bound_evidence(self) -> None:
        _, policy, _ = self.install()
        self.write_evidence(self.make_evidence(policy))
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        evidence_backed = {
            item["id"]: item["status"]
            for item in report["checks"]
            if item["id"] in authority_admin.EVIDENCE_CHECK_IDS
        }
        self.assertEqual(set(evidence_backed), set(authority_admin.EVIDENCE_CHECK_IDS))
        self.assertTrue(all(status == "pass" for status in evidence_backed.values()))

    def test_preflight_surfaces_evidence_reported_failures(self) -> None:
        _, policy, _ = self.install()
        self.write_evidence(self.make_evidence(policy, statuses={"process.control": "fail"}))
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        process_control = next(item for item in report["checks"] if item["id"] == "process.control")
        self.assertEqual(process_control["status"], "fail")
        self.assertFalse(report["boundary_ready"])

    def test_preflight_ignores_stale_evidence(self) -> None:
        _, policy, _ = self.install()
        stale_time = int(time.time()) - authority_admin.EVIDENCE_MAX_AGE_SECONDS - 3600
        self.write_evidence(self.make_evidence(policy, collected_at=stale_time))
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        evidence_backed = {
            item["id"]: item["status"]
            for item in report["checks"]
            if item["id"] in authority_admin.EVIDENCE_CHECK_IDS
        }
        self.assertTrue(all(status == "unknown" for status in evidence_backed.values()))
        self.assertFalse(report["boundary_ready"])

    def test_preflight_ignores_evidence_bound_to_different_policy(self) -> None:
        _, policy, _ = self.install()
        self.write_evidence(self.make_evidence(policy, policy_sha256="0" * 64))
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        evidence_backed = {
            item["id"]: item["status"]
            for item in report["checks"]
            if item["id"] in authority_admin.EVIDENCE_CHECK_IDS
        }
        self.assertTrue(all(status == "unknown" for status in evidence_backed.values()))
        self.assertFalse(report["boundary_ready"])

    def test_preflight_rejects_evidence_with_unsafe_ownership(self) -> None:
        _, policy, _ = self.install()
        self.write_evidence(self.make_evidence(policy))
        os.chmod(self.layout.evidence_path, 0o644)
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        self.assertEqual(
            tuple(item["id"] for item in report["checks"]),
            authority_admin.PREFLIGHT_CHECK_IDS,
        )
        protected = next(
            item for item in report["checks"] if item["id"] == "assets.protected_paths"
        )
        self.assertEqual(protected["status"], "fail")
        self.assertFalse(report["boundary_ready"])

    def test_preflight_rejects_symlinked_evidence_file(self) -> None:
        _, policy, _ = self.install()
        decoy = self.root / "decoy-evidence.json"
        decoy.write_bytes(authority_admin.json_bytes(self.make_evidence(policy)))
        os.chmod(decoy, 0o600)
        os.symlink(decoy, self.layout.evidence_path)
        report = authority_admin.privilege_preflight(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
        )
        self.assertEqual(
            tuple(item["id"] for item in report["checks"]),
            authority_admin.PREFLIGHT_CHECK_IDS,
        )
        protected = next(
            item for item in report["checks"] if item["id"] == "assets.protected_paths"
        )
        self.assertEqual(protected["status"], "fail")
        self.assertFalse(report["boundary_ready"])

    def test_load_privilege_evidence_rejects_incomplete_catalog(self) -> None:
        _, policy, _ = self.install()
        evidence = self.make_evidence(policy)
        del evidence["checks"]["process.control"]
        self.write_evidence(evidence)
        manifest, identity = authority_admin.load_manifest(
            self.layout, os.getuid(), os.getgid(), validate_binding=False
        )
        with self.assertRaisesRegex(authority_admin.AdminError, "evidence catalog"):
            authority_admin.load_privilege_evidence(self.layout, identity, policy)

    def test_collect_evidence_deployment_writes_protected_file(self) -> None:
        _, policy, _ = self.install()
        synthetic = self.make_evidence(policy)
        result = authority_admin.collect_evidence_deployment(
            self.layout,
            os.getuid(),
            os.getgid(),
            validate_binding=False,
            collector=lambda _layout, _identity, _policy: synthetic,
        )
        self.assertEqual(result["ok"], True)
        self.assertEqual(stat.S_IMODE(self.layout.evidence_path.stat().st_mode), 0o600)
        stored = json.loads(self.layout.evidence_path.read_text(encoding="utf-8"))
        self.assertEqual(stored, synthetic)

    def test_run_sudo_listing_pass_when_root_query_reports_no_privileges(self) -> None:
        # sudo -n -l -U <user> run by root exits 0 even when the target has no
        # privileges at all -- the denial is only signalled by the message text.
        completed = subprocess.CompletedProcess(
            args=["sudo"],
            returncode=0,
            stdout="User operator-builder is not allowed to run sudo on z13.\n",
            stderr="",
        )
        with mock.patch.object(authority_admin.subprocess, "run", return_value=completed):
            status, output = authority_admin.run_sudo_listing("operator-builder")
        self.assertEqual(status, "pass")
        self.assertIn("not allowed to run sudo", output)

    def test_run_sudo_listing_fail_when_root_query_reports_real_privileges(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["sudo"],
            returncode=0,
            stdout=(
                "User operator-builder may run the following commands on z13:\n"
                "    (root) NOPASSWD: /usr/local/bin/pwrcfg\n"
            ),
            stderr="",
        )
        with mock.patch.object(authority_admin.subprocess, "run", return_value=completed):
            status, _ = authority_admin.run_sudo_listing("operator-builder")
        self.assertEqual(status, "fail")

    def test_run_sudo_listing_pass_on_self_query_denial_phrasing(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["sudo"],
            returncode=1,
            stdout="",
            stderr="Sorry, user operator-builder may not run sudo on z13.\n",
        )
        with mock.patch.object(authority_admin.subprocess, "run", return_value=completed):
            status, _ = authority_admin.run_sudo_listing("operator-builder")
        self.assertEqual(status, "pass")

    def test_run_sudo_listing_unknown_on_unrecognized_failure(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["sudo"], returncode=1, stdout="", stderr="sudo: unexpected error\n"
        )
        with mock.patch.object(authority_admin.subprocess, "run", return_value=completed):
            status, _ = authority_admin.run_sudo_listing("operator-builder")
        self.assertEqual(status, "unknown")

    def test_collect_broker_account_properties_reads_shadow_directly(self) -> None:
        shadow = self.root / "shadow-locked"
        shadow.write_text(
            f"someone-else:x:1:2:3:4:5:6:\n{self.identity.broker_user}:!locked-hash:1:2:3:4:5:6:\n",
            encoding="ascii",
        )
        with mock.patch.object(authority_admin, "SHADOW_PATH", shadow):
            result = authority_admin.collect_broker_account_properties(self.identity)
        self.assertEqual(result["evidence"]["locked_status"], "pass")
        self.assertIsNone(result["evidence"]["shadow_error"])

    def test_collect_broker_account_properties_flags_unlocked_password(self) -> None:
        shadow = self.root / "shadow-unlocked"
        shadow.write_text(
            f"{self.identity.broker_user}:$6$realhash:1:2:3:4:5:6:\n", encoding="ascii"
        )
        with mock.patch.object(authority_admin, "SHADOW_PATH", shadow):
            result = authority_admin.collect_broker_account_properties(self.identity)
        self.assertEqual(result["evidence"]["locked_status"], "fail")

    def test_collect_broker_account_properties_missing_shadow_entry(self) -> None:
        shadow = self.root / "shadow-empty"
        shadow.write_text("someone-else:x:1:2:3:4:5:6:\n", encoding="ascii")
        with mock.patch.object(authority_admin, "SHADOW_PATH", shadow):
            result = authority_admin.collect_broker_account_properties(self.identity)
        self.assertEqual(result["evidence"]["locked_status"], "unknown")
        self.assertIn("not present", result["evidence"]["shadow_error"])

    def test_collect_polkit_authorization_ignores_generic_yes_return(self) -> None:
        rules_dir = self.root / "polkit-rules-generic"
        rules_dir.mkdir()
        (rules_dir / "10-example.rules").write_text(
            "polkit.addRule(function(action, subject) {\n"
            "    if (subject.isInGroup('wheel')) { return polkit.Result.YES; }\n"
            "});\n",
            encoding="utf-8",
        )
        with mock.patch.object(authority_admin, "POLKIT_RULE_DIRS", (rules_dir,)):
            result = authority_admin.collect_polkit_authorization(
                {self.builder_uid: "fixture-builder"}
            )
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["evidence"]["matches"], [])

    def test_collect_polkit_authorization_flags_wildcard_grant(self) -> None:
        rules_dir = self.root / "polkit-rules-wildcard"
        rules_dir.mkdir()
        (rules_dir / "99-broad.rules").write_text(
            'if (subject.isInGroup("unix-user:*")) { return polkit.Result.YES; }\n',
            encoding="utf-8",
        )
        with mock.patch.object(authority_admin, "POLKIT_RULE_DIRS", (rules_dir,)):
            result = authority_admin.collect_polkit_authorization(
                {self.builder_uid: "fixture-builder"}
            )
        self.assertEqual(result["status"], "fail")

    def test_collect_capabilities_setuid_helpers_does_not_trust_allowlist_by_path_alone(
        self,
    ) -> None:
        # A path matching KNOWN_SAFE_SETUID_HELPERS but not actually root-owned (as here,
        # since the test runs unprivileged) must NOT be trusted -- path matching alone is
        # not verification.
        scan_root = self.root / "opt-fixture"
        scan_root.mkdir()
        safe_path = scan_root / "chrome-sandbox"
        safe_path.write_bytes(b"\x7fELF")
        os.chmod(safe_path, 0o4755)
        unsafe_path = scan_root / "mystery-setuid-helper"
        unsafe_path.write_bytes(b"\x7fELF")
        os.chmod(unsafe_path, 0o4755)
        layout = authority_admin.InstallLayout.under(self.root / "layout-root")
        with (
            mock.patch.object(authority_admin, "CAPABILITY_SCAN_ROOTS", (scan_root,)),
            mock.patch.object(
                authority_admin, "KNOWN_SAFE_SETUID_HELPERS", frozenset({str(safe_path)})
            ),
            mock.patch.object(authority_admin, "run_probe", return_value=(0, "")),
        ):
            result = authority_admin.collect_capabilities_setuid_helpers(layout)
        self.assertEqual(result["status"], "fail")
        self.assertIn(str(unsafe_path), result["evidence"]["setuid_or_setgid_files"])
        self.assertIn(str(safe_path), result["evidence"]["setuid_or_setgid_files"])
        self.assertEqual(result["evidence"]["allowlisted"], [])

    def test_collect_capabilities_setuid_helpers_allowlists_verified_root_owned_binary(
        self,
    ) -> None:
        scan_root = self.root / "opt-fixture"
        scan_root.mkdir()
        safe_path = scan_root / "chrome-sandbox"
        layout = authority_admin.InstallLayout.under(self.root / "layout-root")
        with (
            mock.patch.object(authority_admin, "CAPABILITY_SCAN_ROOTS", (scan_root,)),
            mock.patch.object(
                authority_admin, "KNOWN_SAFE_SETUID_HELPERS", frozenset({str(safe_path)})
            ),
            mock.patch.object(authority_admin, "run_probe", return_value=(0, "")),
            mock.patch.object(
                authority_admin, "verify_allowlisted_setuid_helper", return_value=True
            ),
        ):
            (scan_root / "chrome-sandbox").write_bytes(b"\x7fELF")
            os.chmod(safe_path, 0o4755)
            result = authority_admin.collect_capabilities_setuid_helpers(layout)
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["evidence"]["setuid_or_setgid_files"], [])
        self.assertIn(str(safe_path), result["evidence"]["allowlisted"])

    def test_verify_allowlisted_setuid_helper_rejects_non_root_owner(self) -> None:
        target = self.root / "chrome-sandbox"
        target.write_bytes(b"\x7fELF")
        os.chmod(target, 0o4755)
        with mock.patch.object(authority_admin, "run_probe", return_value=(0, "")):
            self.assertFalse(authority_admin.verify_allowlisted_setuid_helper(target))

    def test_verify_allowlisted_setuid_helper_passes_root_owned_clean_rpm_verify(self) -> None:
        target = Path("/opt/example/fake-helper")
        fake_stat = os.stat_result((stat.S_IFREG | 0o4755, 1, 1, 1, 0, 0, 4, 0, 0, 0))
        with (
            mock.patch.object(Path, "lstat", return_value=fake_stat),
            mock.patch.object(authority_admin, "run_probe", return_value=(0, "")),
        ):
            self.assertTrue(authority_admin.verify_allowlisted_setuid_helper(target))

    def test_verify_allowlisted_setuid_helper_rejects_rpm_verify_discrepancy(self) -> None:
        target = Path("/opt/example/fake-helper")
        fake_stat = os.stat_result((stat.S_IFREG | 0o4755, 1, 1, 1, 0, 0, 4, 0, 0, 0))
        with (
            mock.patch.object(Path, "lstat", return_value=fake_stat),
            mock.patch.object(
                authority_admin,
                "run_probe",
                return_value=(1, "S.5....T.  c /opt/example/fake-helper"),
            ),
        ):
            self.assertFalse(authority_admin.verify_allowlisted_setuid_helper(target))

    def test_verify_allowlisted_setuid_helper_rejects_group_writable_mode(self) -> None:
        target = Path("/opt/example/fake-helper")
        fake_stat = os.stat_result((stat.S_IFREG | 0o4775, 1, 1, 1, 0, 0, 4, 0, 0, 0))
        with (
            mock.patch.object(Path, "lstat", return_value=fake_stat),
            mock.patch.object(authority_admin, "run_probe", return_value=(0, "")),
        ):
            self.assertFalse(authority_admin.verify_allowlisted_setuid_helper(target))

    def test_admin_lock_metadata_is_not_silently_repaired(self) -> None:
        _, first, _ = self.install()
        second_path, _ = self.write_policy("generation-2.json", 2, first.sha256)
        os.chmod(self.layout.lock_path, 0o644)
        with self.assertRaisesRegex(authority_admin.AdminError, "lock metadata"):
            authority_admin.rotate_deployment(
                self.layout,
                second_path,
                os.getuid(),
                os.getgid(),
                validate_accounts=False,
            )
        self.assertEqual(stat.S_IMODE(self.layout.lock_path.stat().st_mode), 0o644)

    def test_socket_permission_helper_waits_and_verifies_inode(self) -> None:
        runtime = self.root / "socket-runtime"
        runtime.mkdir(mode=0o750)
        os.chmod(runtime, 0o2750)
        path = runtime / "broker.sock"
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            server.bind(str(path))
            os.chmod(path, 0o600)
            socket_permission_helper.remove_stale_socket(path, os.getgid())
            self.assertFalse(path.exists())
            server.close()
            server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            server.bind(str(path))
            os.chmod(path, 0o600)
            before = path.stat()
            socket_permission_helper.prepare_socket(path, os.getgid(), timeout=0.1)
            after = path.stat()
            self.assertEqual((before.st_dev, before.st_ino), (after.st_dev, after.st_ino))
            self.assertEqual(stat.S_IMODE(after.st_mode), 0o660)

            hardlink = runtime / "broker-hardlink.sock"
            os.link(path, hardlink)
            with self.assertRaisesRegex(RuntimeError, "metadata differs"):
                socket_permission_helper.prepare_socket(path, os.getgid(), timeout=0.1)
            hardlink.unlink()
        finally:
            server.close()

    def test_privileged_wrapper_uses_fixed_isolated_interpreter(self) -> None:
        wrapper = (REPO_ROOT / "operator-admin").read_text(encoding="ascii")
        self.assertTrue(wrapper.startswith("#!/usr/bin/python3 -I\n"))
        self.assertIn('os.chdir("/")', wrapper)
        self.assertIn("os.environ.clear()", wrapper)
        completed = subprocess.run(
            [str(REPO_ROOT / "operator-admin"), "audit"],
            text=True,
            capture_output=True,
            check=False,
            env={
                "PATH": str(self.root),
                "PYTHONPATH": str(self.root),
                "PYTHONHOME": str(self.root),
                "HOME": str(self.root),
            },
            cwd=self.root,
        )
        if os.geteuid() != 0:
            self.assertEqual(json.loads(completed.stderr)["error"]["code"], "root_required")

    def test_identity_binding_change_fails_closed(self) -> None:
        identity = authority_admin.DeploymentIdentity(
            0, 0, "broker-name", 2000, 2001, "client-name", 3000
        )
        account = pwd.struct_passwd(("broker-name", "x", 9999, 2001, "", "/", "/sbin/nologin"))
        group = grp.struct_group(("client-name", "x", 3000, []))
        with (
            mock.patch.object(authority_admin.pwd, "getpwnam", return_value=account),
            mock.patch.object(authority_admin.grp, "getgrnam", return_value=group),
        ):
            with self.assertRaisesRegex(authority_admin.AdminError, "binding changed"):
                authority_admin.validate_identity_binding(identity)

    def test_preflight_attributes_identity_binding_failure(self) -> None:
        self.install()
        manifest = json.loads(self.layout.manifest_path.read_text(encoding="ascii"))
        manifest["broker_uid"] += 1
        self.layout.manifest_path.write_text(
            authority_broker.canonical_json(manifest) + "\n", encoding="ascii"
        )
        os.chmod(self.layout.manifest_path, 0o600)
        with mock.patch.object(authority_admin, "validate_privileged_runtime", return_value=None):
            report = authority_admin.privilege_preflight(
                self.layout, os.getuid(), os.getgid(), validate_binding=True
            )
        statuses = {item["id"]: item["status"] for item in report["checks"]}
        self.assertEqual(statuses["identity.broker_binding"], "fail")
        self.assertEqual(statuses["assets.protected_paths"], "unknown")

    def test_layout_owner_boundary_changes_only_at_state_and_runtime_roots(self) -> None:
        distinct = authority_admin.DeploymentIdentity(0, 0, "broker", 2000, 2001, "clients", 3000)
        self.assertEqual(
            authority_admin.expected_directory_owner(
                self.layout.unit_path.parent, self.layout, distinct
            ),
            0,
        )
        self.assertEqual(
            authority_admin.expected_directory_owner(
                self.layout.config_root, self.layout, distinct
            ),
            0,
        )
        self.assertEqual(
            authority_admin.expected_directory_owner(self.layout.state_root, self.layout, distinct),
            2000,
        )
        self.assertEqual(
            authority_admin.expected_directory_owner(
                self.layout.runtime_root, self.layout, distinct
            ),
            2000,
        )

    def test_enrollment_lifecycle(self) -> None:
        registry_path = self.root / "test-registry.json"
        repo_path = self.root / "test-repo"
        repo_path.mkdir()
        for arguments in (
            ("init",),
            ("task-create", "--objective", "Legacy task", "--id", "task-1"),
        ):
            completed = subprocess.run(
                [str(REPO_ROOT / "operator"), *arguments],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)

        def committed_enrollment(_socket_path: Path, request: object) -> dict:
            assert isinstance(request, dict)
            return {
                "ok": True,
                "idempotent_replay": False,
                "receipt": {
                    "ledger_id": request["ledger_id"],
                    "operation": "ledger.enroll",
                    "operation_key": request["operation_key"],
                    "commit_sequence": 1,
                    "policy": {"id": "policy-test", "generation": 1, "sha256": "1" * 64},
                    "receipt_hash": "2" * 64,
                },
            }

        res = authority_admin.enroll_repository(
            registry_path,
            repo_path,
            "ledger-test",
            Path("/tmp/socket.sock"),
            registry_owner_uid=os.getuid(),
            registry_owner_gid=os.getgid(),
            registry_anchor=self.root,
            request_sender=committed_enrollment,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["ledger_id"], "ledger-test")
        self.assertEqual(res["anchor_records_count"], 1)

        # Verify registry file is written correctly
        self.assertTrue(registry_path.exists())
        with open(registry_path, "r") as f:
            registry_data = json.load(f)
        self.assertEqual(registry_data["schema_version"], 1)
        self.assertEqual(len(registry_data["registrations"]), 1)
        reg = registry_data["registrations"][0]
        self.assertEqual(reg["ledger_id"], "ledger-test")
        self.assertEqual(len(reg["anchor_records"]), 1)
        self.assertEqual(reg["anchor_records"][0]["record_id"], "task-1")
        self.assertEqual(reg["anchor_records"][0]["version"], 1)
        self.assertEqual(reg["first_broker_sequence"], 1)
        self.assertEqual(reg["policy_binding"]["sha256"], "1" * 64)

        replay = authority_admin.enroll_repository(
            registry_path,
            repo_path,
            "ledger-test",
            Path("/tmp/socket.sock"),
            registry_owner_uid=os.getuid(),
            registry_owner_gid=os.getgid(),
            registry_anchor=self.root,
            request_sender=committed_enrollment,
        )
        self.assertTrue(replay["idempotent_replay"])


if __name__ == "__main__":
    unittest.main()
