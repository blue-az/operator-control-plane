from __future__ import annotations

import grp
import json
import os
import pwd
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import authority_admin  # noqa: E402
import authority_broker  # noqa: E402


class TestAuthorityUpgrade(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="operator-upgrade-test.")).resolve()
        os.chmod(self.root, 0o700)
        self.layout = authority_admin.InstallLayout.under(self.root)
        self.source = self.root / "release"
        self.source.mkdir(mode=0o700)

        # Copy source assets from the real repository root
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(REPO_ROOT / name, self.source / name)
            os.chmod(self.source / name, 0o700 if name == "operator-admin" else 0o600)

        self.inputs = self.root / "inputs"
        self.inputs.mkdir(mode=0o700)

        # Identity
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

        # Install initial deployment
        self.install()

        # Start preflight mock
        self.preflight_patcher = mock.patch(
            "authority_admin.privilege_preflight",
            return_value={"boundary_ready": True, "checks": []},
        )
        self.mock_preflight = self.preflight_patcher.start()

        self.stop_patcher = mock.patch("authority_admin.stop_service")
        self.start_patcher = mock.patch("authority_admin.start_service")
        self.stop_patcher.start()
        self.start_patcher.start()

    def tearDown(self) -> None:
        self.preflight_patcher.stop()
        self.stop_patcher.stop()
        self.start_patcher.stop()
        shutil.rmtree(self.root)

    def write_policy(
        self, name: str, generation: int, previous: str | None
    ) -> tuple[Path, authority_admin.PolicyDocument]:
        value = {
            "policy_schema_version": 1,
            "policy_id": self.policy_id,
            "ledger_id": self.ledger_id,
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
        path = self.inputs / name
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
        return path, authority_admin.parse_policy_object(value)

    def install(self) -> None:
        path, policy = self.write_policy("generation-1.json", 1, None)
        authority_admin.install_deployment(
            self.layout,
            self.source,
            path,
            self.identity,
            validate_accounts=False,
        )

    def make_candidate_release(self, modifier=None) -> Path:
        temp_candidate = Path(tempfile.mkdtemp(dir=self.root))
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(self.source / name, temp_candidate / name)

        if modifier:
            modifier(temp_candidate)

        # Calculate digest
        assets = authority_admin.read_source_assets(temp_candidate, self.layout, self.identity)
        hashes = authority_admin.hash_source_assets(assets)
        digest = authority_admin.compute_release_digest(hashes)

        # Rename directory to match digest
        candidate_dir = self.layout.releases_root / digest
        candidate_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(temp_candidate), str(candidate_dir))
        return candidate_dir

    def test_upgrade_success(self) -> None:
        def modify_code(dir_path: Path):
            # Make a minor change to operator-admin code to change its hash
            op_path = dir_path / "operator-admin"
            content = op_path.read_bytes()
            op_path.write_bytes(content + b"\n# Modified for test upgrade")

        candidate_dir = self.make_candidate_release(modify_code)
        new_digest = candidate_dir.name

        # Mock start/stop/health
        health_probe_mock = mock.Mock(return_value=True)
        stop_mock = mock.Mock()
        start_mock = mock.Mock()

        result = authority_admin.upgrade_deployment(
            self.layout,
            candidate_dir,
            self.identity.admin_uid,
            self.identity.admin_gid,
            validate_accounts=False,
            health_probe=health_probe_mock,
            service_stop=stop_mock,
            service_start=start_mock,
        )

        self.assertTrue(result["ok"])
        self.assertEqual(result["new_release_digest"], new_digest)
        self.assertEqual(result["action"], "upgrade")
        self.assertFalse(result["idempotent_replay"])

        # Check files on disk match candidate
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            installed_data = (self.layout.install_root / name).read_bytes()
            candidate_data = (candidate_dir / name).read_bytes()
            self.assertEqual(installed_data, candidate_data)

        # Check manifest matches new hashes
        manifest, _ = authority_admin.load_manifest(
            self.layout, self.identity.admin_uid, self.identity.admin_gid, validate_binding=False
        )
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            dest_path = str(self.layout.install_root / name)
            entry = manifest["assets"][dest_path]
            candidate_hash = authority_admin.sha256_bytes((candidate_dir / name).read_bytes())
            self.assertEqual(entry["sha256"], candidate_hash)

        # Check journal is terminal (completed)
        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "completed")

        # Check history contains completed entry
        history_lines = self.layout.upgrade_history_path.read_text().splitlines()
        self.assertEqual(len(history_lines), 1)
        history_record = json.loads(history_lines[0])
        self.assertEqual(history_record["state"], "completed")
        self.assertEqual(history_record["new_release_digest"], new_digest)

    def test_upgrade_already_up_to_date(self) -> None:
        candidate_dir = self.make_candidate_release()
        result = authority_admin.upgrade_deployment(
            self.layout,
            candidate_dir,
            self.identity.admin_uid,
            self.identity.admin_gid,
            validate_accounts=False,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["idempotent_replay"])

    def test_upgrade_competing_rejection(self) -> None:
        # Setup an active upgrade journal for Candidate A
        candidate_a = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Candidate A")
        )
        candidate_b = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Candidate B")
        )

        current_assets = {
            name: (self.layout.install_root / name).read_bytes()
            for name in authority_admin.INSTALLED_SOURCE_ASSETS
        }
        current_hashes = authority_admin.hash_source_assets(current_assets)
        old_digest = authority_admin.compute_release_digest(current_hashes)

        idempotency_key = authority_admin.upgrade_idempotency_key(old_digest, candidate_a.name)
        journal = {
            "upgrade_journal_schema_version": 1,
            "idempotency_key": idempotency_key,
            "old_release_digest": old_digest,
            "new_release_digest": candidate_a.name,
            "state": "prepared",
            "started_at": "2026-07-15T22:29:17+02:00",
            "completed_at": None,
            "admin_uid": self.identity.admin_uid,
        }
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        # Try to upgrade to Candidate B
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_b,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
            )
        self.assertEqual(ctx.exception.code, "upgrade_in_progress")

    def test_upgrade_schema_rejection(self) -> None:
        def modify_schema(dir_path: Path):
            # Change STORE_SCHEMA_VERSION to 2 in authority_broker.py
            broker_path = dir_path / "authority_broker.py"
            content = broker_path.read_bytes()
            modified = content.replace(b"STORE_SCHEMA_VERSION = 1", b"STORE_SCHEMA_VERSION = 2")
            broker_path.write_bytes(modified)

        candidate_dir = self.make_candidate_release(modify_schema)

        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
            )
        self.assertEqual(ctx.exception.code, "schema_incompatible_upgrade")

    def test_upgrade_registry_independence(self) -> None:
        registry_path = self.root / "operator-control-plane-registry.json"
        if registry_path.exists():
            os.remove(registry_path)

        def modify_code(dir_path: Path):
            (dir_path / "operator-admin").write_bytes(b"# Registry Independence Test")

        candidate_dir = self.make_candidate_release(modify_code)
        result = authority_admin.upgrade_deployment(
            self.layout,
            candidate_dir,
            self.identity.admin_uid,
            self.identity.admin_gid,
            validate_accounts=False,
            health_probe=lambda *args, **kwargs: True,
        )
        self.assertTrue(result["ok"])

    def test_upgrade_idempotent_completion_history(self) -> None:
        def modify_code(dir_path: Path):
            (dir_path / "operator-admin").write_bytes(b"# Idempotent replay test")

        candidate_dir = self.make_candidate_release(modify_code)

        health_probe_mock = mock.Mock(return_value=True)

        # First run: completes
        result1 = authority_admin.upgrade_deployment(
            self.layout,
            candidate_dir,
            self.identity.admin_uid,
            self.identity.admin_gid,
            validate_accounts=False,
            health_probe=health_probe_mock,
        )
        self.assertTrue(result1["ok"])
        self.assertFalse(result1["idempotent_replay"])

        # Second run: should return idempotent_replay immediately
        result2 = authority_admin.upgrade_deployment(
            self.layout,
            candidate_dir,
            self.identity.admin_uid,
            self.identity.admin_gid,
            validate_accounts=False,
            health_probe=health_probe_mock,
        )
        self.assertTrue(result2["ok"])
        self.assertTrue(result2["idempotent_replay"])

        # Verify history log has exactly 1 entry
        history_lines = self.layout.upgrade_history_path.read_text().splitlines()
        self.assertEqual(len(history_lines), 1)

    def test_fault_service_stop_failure(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Service stop fail")
        )

        def failing_stop(lay):
            raise authority_admin.AdminError("service_stop_failed", "stop failed")

        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                service_stop=failing_stop,
            )
        self.assertEqual(ctx.exception.code, "service_stop_failed")

        # Files on disk should be original files (not changed)
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            installed = (self.layout.install_root / name).read_bytes()
            original = (self.source / name).read_bytes()
            self.assertEqual(installed, original)

    def test_fault_activation_failure_and_recovery(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Activation fail")
        )

        original_activate = authority_admin.activate_release_assets
        fail_flag = True

        def failing_activate(layout, identity, assets):
            nonlocal fail_flag
            if fail_flag:
                fail_flag = False
                raise RuntimeError("Disk full halfway")
            return original_activate(layout, identity, assets)

        # First run raises RuntimeError
        with mock.patch("authority_admin.activate_release_assets", side_effect=failing_activate):
            with self.assertRaises(RuntimeError):
                authority_admin.upgrade_deployment(
                    self.layout,
                    candidate_dir,
                    self.identity.admin_uid,
                    self.identity.admin_gid,
                    validate_accounts=False,
                    health_probe=lambda *args, **kwargs: True,
                    service_stop=mock.Mock(),
                    service_start=mock.Mock(),
                )

        # Journal state is left at "service_stopped"
        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "service_stopped")

        # Second run (resume) completes successfully
        with mock.patch("authority_admin.activate_release_assets", side_effect=failing_activate):
            result = authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=lambda *args, **kwargs: True,
                service_stop=mock.Mock(),
                service_start=mock.Mock(),
            )
        self.assertTrue(result["ok"])
        self.assertFalse(result["idempotent_replay"])

        # Check journal is completed
        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "completed")

    def test_fault_health_probe_failure_rollback(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Health probe fail")
        )
        new_digest = candidate_dir.name

        health_probes = []

        def custom_health_probe(lay, uid, gid, expected_digest=None):
            health_probes.append(expected_digest)
            if expected_digest == new_digest:
                return False  # Candidate is unhealthy
            return True  # Rollback is healthy

        # Verify that upgrade raises upgrade_health_check_failed
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=custom_health_probe,
                service_stop=mock.Mock(),
                service_start=mock.Mock(),
            )
        self.assertEqual(ctx.exception.code, "upgrade_health_check_failed")

        # Files on disk should be original files (rolled back)
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            installed = (self.layout.install_root / name).read_bytes()
            original = (self.source / name).read_bytes()
            self.assertEqual(installed, original)

        # Manifest assets should match original hashes
        manifest, _ = authority_admin.load_manifest(
            self.layout, self.identity.admin_uid, self.identity.admin_gid, validate_binding=False
        )
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            dest_path = str(self.layout.install_root / name)
            original = (self.source / name).read_bytes()
            self.assertEqual(
                manifest["assets"][dest_path]["sha256"], authority_admin.sha256_bytes(original)
            )

        # Journal is rolled_back
        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "rolled_back")

        # History contains rolled_back entry
        history_lines = self.layout.upgrade_history_path.read_text().splitlines()
        history_record = json.loads(history_lines[0])
        self.assertEqual(history_record["state"], "rolled_back")

    def test_fault_rollback_unhealthy(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Rollback unhealthy")
        )

        def custom_health_probe(lay, uid, gid, expected_digest=None):
            return False  # Both candidate and rollback unhealthy

        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=custom_health_probe,
                service_stop=mock.Mock(),
                service_start=mock.Mock(),
            )
        self.assertEqual(ctx.exception.code, "rollback_unhealthy")

    def test_fault_manifest_publication_crash_and_recovery(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Publication crash")
        )

        original_write_protected = authority_admin.write_protected_file
        crash_flag = True

        def crashing_write_protected(path, data, mode, uid, gid, lay, identity, replace=False):
            nonlocal crash_flag
            if path == self.layout.manifest_path and crash_flag:
                # Write the manifest file successfully
                original_write_protected(path, data, mode, uid, gid, lay, identity, replace=replace)
                # But crash before writing the journal completed state
                crash_flag = False
                raise RuntimeError("Crash after manifest write")
            return original_write_protected(
                path, data, mode, uid, gid, lay, identity, replace=replace
            )

        with mock.patch(
            "authority_admin.write_protected_file", side_effect=crashing_write_protected
        ):
            with self.assertRaises(RuntimeError):
                authority_admin.upgrade_deployment(
                    self.layout,
                    candidate_dir,
                    self.identity.admin_uid,
                    self.identity.admin_gid,
                    validate_accounts=False,
                    health_probe=lambda *args, **kwargs: True,
                    service_stop=mock.Mock(),
                    service_start=mock.Mock(),
                )

        # Journal is still at "health_verified"
        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "health_verified")

        # Second run (resume) completes successfully
        result = authority_admin.upgrade_deployment(
            self.layout,
            candidate_dir,
            self.identity.admin_uid,
            self.identity.admin_gid,
            validate_accounts=False,
            health_probe=lambda *args, **kwargs: True,
            service_stop=mock.Mock(),
            service_start=mock.Mock(),
        )
        self.assertTrue(result["ok"])

        # Journal is completed
        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "completed")

    def test_fault_interrupted_rollback_recovery(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Interrupted rollback")
        )
        new_digest = candidate_dir.name

        original_write_protected = authority_admin.write_protected_file
        crash_flag = True

        def crashing_write_protected(path, data, mode, uid, gid, lay, identity, replace=False):
            nonlocal crash_flag
            if path == self.layout.manifest_path and crash_flag:
                # Write restored manifest assets, then crash before writing rolled_back state to journal
                original_write_protected(path, data, mode, uid, gid, lay, identity, replace=replace)
                crash_flag = False
                raise RuntimeError("Crash during rollback manifest write")
            return original_write_protected(
                path, data, mode, uid, gid, lay, identity, replace=replace
            )

        def health_probe_candidate_unhealthy(lay, uid, gid, expected_digest=None):
            if expected_digest == new_digest:
                return False  # Candidate is unhealthy
            return True  # Rollback is healthy

        with mock.patch(
            "authority_admin.write_protected_file", side_effect=crashing_write_protected
        ):
            with self.assertRaises(RuntimeError):
                authority_admin.upgrade_deployment(
                    self.layout,
                    candidate_dir,
                    self.identity.admin_uid,
                    self.identity.admin_gid,
                    validate_accounts=False,
                    health_probe=health_probe_candidate_unhealthy,
                    service_stop=mock.Mock(),
                    service_start=mock.Mock(),
                )

        # Journal state is at "rolling_back" because we crashed during rollback manifest write
        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "rolling_back")

        # Second run: health check for candidate (new_digest) fails again,
        # rollback runs again idempotently, and journal becomes "rolled_back"
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=health_probe_candidate_unhealthy,
                service_stop=mock.Mock(),
                service_start=mock.Mock(),
            )
        self.assertEqual(ctx.exception.code, "upgrade_health_check_failed")

        journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(journal["state"], "rolled_back")

    @mock.patch("authority_admin.probe_service_active", return_value=True)
    @mock.patch("authority_admin.probe_socket_health", return_value=True)
    def test_real_default_health_probe(self, mock_socket, mock_service) -> None:
        # Test default_health_probe Happy Path (no expected digest)
        res = authority_admin.default_health_probe(
            self.layout, self.identity.admin_uid, self.identity.admin_gid, validate_binding=False
        )
        self.assertTrue(res)

        # Test default_health_probe fails if files on disk are modified
        op_path = self.layout.install_root / "operator-admin"
        content = op_path.read_bytes()
        op_path.write_bytes(content + b"\n# Tampered")
        res = authority_admin.default_health_probe(
            self.layout, self.identity.admin_uid, self.identity.admin_gid, validate_binding=False
        )
        self.assertFalse(res)

        # Restore
        op_path.write_bytes(content)

        # Test default_health_probe with candidate expected_digest
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# Health check digest test")
        )
        new_digest = candidate_dir.name

        # Prepare candidate manifest metadata
        authority_admin.prepare_release(candidate_dir, self.layout, self.identity)

        # Activate candidate assets on disk manually (simulating activation state)
        authority_admin.activate_release_assets(
            self.layout,
            self.identity,
            {
                name: (candidate_dir / name).read_bytes()
                for name in authority_admin.INSTALLED_SOURCE_ASSETS
            },
        )

        # Manifest is still the old one. We test health_probe with expected_digest=new_digest
        res = authority_admin.default_health_probe(
            self.layout,
            self.identity.admin_uid,
            self.identity.admin_gid,
            expected_digest=new_digest,
            validate_binding=False,
        )
        self.assertTrue(res)

    def test_fault_rolling_back_crash_and_recovery(self) -> None:
        # 1. Prepare a candidate release
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# rollingback crash")
        )
        new_digest = candidate_dir.name

        # Calculate old digest (before upgrade)
        current_assets = {
            name: (self.layout.install_root / name).read_bytes()
            for name in authority_admin.INSTALLED_SOURCE_ASSETS
        }
        current_hashes = authority_admin.hash_source_assets(current_assets)
        old_digest = authority_admin.compute_release_digest(current_hashes)

        # Backup the old assets to releases root (as done by upgrade_deployment)
        archive_dir = self.layout.releases_root / old_digest
        authority_admin.ensure_directory(
            archive_dir,
            0o700,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(self.layout.install_root / name, archive_dir / name)

        # 2. Write a rolling_back state to the journal manually, simulating a crash during rollback
        idempotency_key = authority_admin.upgrade_idempotency_key(old_digest, new_digest)
        journal = {
            "upgrade_journal_schema_version": 1,
            "idempotency_key": idempotency_key,
            "old_release_digest": old_digest,
            "new_release_digest": new_digest,
            "state": "rolling_back",
            "started_at": "2026-07-15T22:29:17+02:00",
            "completed_at": None,
            "admin_uid": self.identity.admin_uid,
        }
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        # Tamper with the installed files on disk to simulate mixed/corrupt state
        tampered_bytes = b"# Tampered mixed code"
        (self.layout.install_root / "operator-admin").write_bytes(tampered_bytes)

        # Verify recovery:
        # Mock service_start and verify that when it is called, the files are completely restored
        # to their old/original version (no tampered_bytes left!).
        def custom_start(lay):
            # Check that the files are fully restored when the service starts
            for name in authority_admin.INSTALLED_SOURCE_ASSETS:
                installed = (self.layout.install_root / name).read_bytes()
                original = (archive_dir / name).read_bytes()
                self.assertEqual(installed, original)
                self.assertNotEqual(installed, tampered_bytes)

        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=lambda *args, **kwargs: True,  # Rollback health check passes
                service_stop=mock.Mock(),
                service_start=custom_start,
            )
        self.assertEqual(ctx.exception.code, "upgrade_health_check_failed")

        # Check journal is terminal "rolled_back"
        recovered_journal = authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(recovered_journal["state"], "rolled_back")

    def test_terminal_history_crash_windows(self) -> None:
        # Test Window 1: Crash between completed state write and history write
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# completed history crash")
        )
        new_digest = candidate_dir.name

        # Prepare the archive backup manually so we can simulate completed state
        current_assets = {
            name: (self.layout.install_root / name).read_bytes()
            for name in authority_admin.INSTALLED_SOURCE_ASSETS
        }
        current_hashes = authority_admin.hash_source_assets(current_assets)
        old_digest = authority_admin.compute_release_digest(current_hashes)
        archive_dir = self.layout.releases_root / old_digest
        authority_admin.ensure_directory(
            archive_dir,
            0o700,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(self.layout.install_root / name, archive_dir / name)

        # Write completed journal manually but keep history empty
        idempotency_key = authority_admin.upgrade_idempotency_key(old_digest, new_digest)
        journal = {
            "upgrade_journal_schema_version": 1,
            "idempotency_key": idempotency_key,
            "old_release_digest": old_digest,
            "new_release_digest": new_digest,
            "state": "completed",
            "started_at": "2026-07-15T22:29:17+02:00",
            "completed_at": "2026-07-15T22:29:18+02:00",
            "admin_uid": self.identity.admin_uid,
        }
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        history_file = self.layout.upgrade_history_path
        if history_file.exists():
            os.remove(history_file)

        # Copy candidate files to simulate completed code activation on disk
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(candidate_dir / name, self.layout.install_root / name)

        # Update manifest to match candidate files
        new_entries = {
            str(self.layout.install_root / name): {
                "sha256": authority_admin.sha256_bytes((candidate_dir / name).read_bytes()),
                "mode": mode,
                "uid": self.identity.admin_uid,
                "gid": self.identity.admin_gid,
            }
            for name, mode in authority_admin.INSTALLED_SOURCE_ASSETS.items()
        }
        manifest_val, _ = authority_admin.load_manifest(
            self.layout, self.identity.admin_uid, self.identity.admin_gid, validate_binding=False
        )
        updated_assets = dict(manifest_val["assets"])
        updated_assets.update(new_entries)
        authority_admin.write_protected_file(
            self.layout.manifest_path,
            authority_admin.json_bytes({**manifest_val, "assets": updated_assets}),
            0o600,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
            replace=True,
        )

        # Run upgrade (idempotent replay)
        result = authority_admin.upgrade_deployment(
            self.layout,
            candidate_dir,
            self.identity.admin_uid,
            self.identity.admin_gid,
            validate_accounts=False,
            health_probe=lambda *args, **kwargs: True,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["idempotent_replay"])

        # History must contain the completed record now!
        history_lines = history_file.read_text().splitlines()
        self.assertEqual(len(history_lines), 1)
        self.assertEqual(json.loads(history_lines[0])["state"], "completed")

        # Test Window 2: Crash between rolled_back state write and history write
        # Remove history file and journal
        os.remove(history_file)

        # Restore original assets to simulate rolled_back code activation on disk
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(archive_dir / name, self.layout.install_root / name)

        # Restore manifest back to original assets
        original_entries = {
            str(self.layout.install_root / name): {
                "sha256": authority_admin.sha256_bytes((archive_dir / name).read_bytes()),
                "mode": mode,
                "uid": self.identity.admin_uid,
                "gid": self.identity.admin_gid,
            }
            for name, mode in authority_admin.INSTALLED_SOURCE_ASSETS.items()
        }
        manifest_val, _ = authority_admin.load_manifest(
            self.layout, self.identity.admin_uid, self.identity.admin_gid, validate_binding=False
        )
        updated_assets = dict(manifest_val["assets"])
        updated_assets.update(original_entries)
        authority_admin.write_protected_file(
            self.layout.manifest_path,
            authority_admin.json_bytes({**manifest_val, "assets": updated_assets}),
            0o600,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
            replace=True,
        )

        # Write rolled_back journal manually
        journal["state"] = "rolled_back"
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        # Replaying should raise upgrade_health_check_failed and reconcile the history!
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=lambda *args, **kwargs: True,
            )
        self.assertEqual(ctx.exception.code, "upgrade_health_check_failed")

        history_lines = history_file.read_text().splitlines()
        self.assertEqual(len(history_lines), 1)
        self.assertEqual(json.loads(history_lines[0])["state"], "rolled_back")

    def test_completed_journal_inconsistent_state(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# inconsistent completed")
        )
        new_digest = candidate_dir.name

        current_assets = {
            name: (self.layout.install_root / name).read_bytes()
            for name in authority_admin.INSTALLED_SOURCE_ASSETS
        }
        current_hashes = authority_admin.hash_source_assets(current_assets)
        old_digest = authority_admin.compute_release_digest(current_hashes)

        # Write completed journal manually but do NOT copy candidate files to install_root (inconsistent state!)
        idempotency_key = authority_admin.upgrade_idempotency_key(old_digest, new_digest)
        journal = {
            "upgrade_journal_schema_version": 1,
            "idempotency_key": idempotency_key,
            "old_release_digest": old_digest,
            "new_release_digest": new_digest,
            "state": "completed",
            "started_at": "2026-07-15T22:29:17+02:00",
            "completed_at": "2026-07-15T22:29:18+02:00",
            "admin_uid": self.identity.admin_uid,
        }
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        # Replaying should raise AdminError("invalid_admin_state")
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
            )
        self.assertEqual(ctx.exception.code, "invalid_admin_state")

    def test_stop_before_replace_call_order(self) -> None:
        # Test that service_stop is called before files are activated during recovery from service_stopped and rolling_back.
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# recovery stop ordering")
        )
        new_digest = candidate_dir.name

        current_assets = {
            name: (self.layout.install_root / name).read_bytes()
            for name in authority_admin.INSTALLED_SOURCE_ASSETS
        }
        current_hashes = authority_admin.hash_source_assets(current_assets)
        old_digest = authority_admin.compute_release_digest(current_hashes)

        # Setup backup archive
        archive_dir = self.layout.releases_root / old_digest
        authority_admin.ensure_directory(
            archive_dir,
            0o700,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(self.layout.install_root / name, archive_dir / name)

        idempotency_key = authority_admin.upgrade_idempotency_key(old_digest, new_digest)
        journal = {
            "upgrade_journal_schema_version": 1,
            "idempotency_key": idempotency_key,
            "old_release_digest": old_digest,
            "new_release_digest": new_digest,
            "state": "service_stopped",
            "started_at": "2026-07-15T22:29:17+02:00",
            "completed_at": None,
            "admin_uid": self.identity.admin_uid,
        }
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        call_sequence = []

        def mock_service_stop(lay):
            call_sequence.append("service_stop")

        # Mock activate_release_assets to trace when file replacement occurs
        original_activate = authority_admin.activate_release_assets

        def mock_activate(*args, **kwargs):
            call_sequence.append("activate_assets")
            return original_activate(*args, **kwargs)

        with mock.patch("authority_admin.activate_release_assets", side_effect=mock_activate):
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=lambda *args, **kwargs: True,
                service_stop=mock_service_stop,
                service_start=mock.Mock(),
            )

        # Verify that service_stopped recovery stopped service first
        self.assertIn("service_stop", call_sequence)
        self.assertIn("activate_assets", call_sequence)
        self.assertTrue(
            call_sequence.index("service_stop") < call_sequence.index("activate_assets")
        )

        # Test same stop-before-replace call order for rolling_back recovery
        call_sequence.clear()
        journal["state"] = "rolling_back"
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        with mock.patch("authority_admin.activate_release_assets", side_effect=mock_activate):
            with self.assertRaises(authority_admin.AdminError):
                authority_admin.upgrade_deployment(
                    self.layout,
                    candidate_dir,
                    self.identity.admin_uid,
                    self.identity.admin_gid,
                    validate_accounts=False,
                    health_probe=lambda *args, **kwargs: False,  # triggers rollback health failure/raise
                    service_stop=mock_service_stop,
                    service_start=mock.Mock(),
                )

        self.assertIn("service_stop", call_sequence)
        self.assertIn("activate_assets", call_sequence)
        self.assertTrue(
            call_sequence.index("service_stop") < call_sequence.index("activate_assets")
        )

    def test_malformed_and_unknown_journals(self) -> None:
        # 1. Test malformed journal (not a JSON dict)
        with open(self.layout.upgrade_journal_path, "w") as f:
            f.write("malformed data")
        os.chmod(self.layout.upgrade_journal_path, 0o600)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "corrupt_upgrade_journal")

        # 2. Test unknown state
        old_dg = "a" * 64
        new_dg = "b" * 64
        idemp_k = authority_admin.upgrade_idempotency_key(old_dg, new_dg)
        journal = {
            "upgrade_journal_schema_version": 1,
            "idempotency_key": idemp_k,
            "old_release_digest": old_dg,
            "new_release_digest": new_dg,
            "state": "unknown_state",
            "started_at": "2026-07-15T22:29:17+02:00",
            "admin_uid": self.identity.admin_uid,
        }
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "corrupt_upgrade_journal")

        # 3. Test missing required fields (e.g. started_at)
        del journal["started_at"]
        journal["state"] = "prepared"
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "corrupt_upgrade_journal")

        # 4. Test wrong schema version
        journal["started_at"] = "2026-07-15T22:29:17+02:00"
        journal["upgrade_journal_schema_version"] = 99
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "corrupt_upgrade_journal")

        # 5. Test wrong administrator UID
        journal["upgrade_journal_schema_version"] = 1
        journal["admin_uid"] = self.identity.admin_uid + 10
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.load_upgrade_journal(self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "corrupt_upgrade_journal")

    def test_rolled_back_replay_semantics(self) -> None:
        candidate_dir = self.make_candidate_release(
            lambda d: (d / "operator-admin").write_bytes(b"# rolled back replay semantics")
        )
        new_digest = candidate_dir.name

        current_assets = {
            name: (self.layout.install_root / name).read_bytes()
            for name in authority_admin.INSTALLED_SOURCE_ASSETS
        }
        current_hashes = authority_admin.hash_source_assets(current_assets)
        old_digest = authority_admin.compute_release_digest(current_hashes)

        # Backup the old assets
        archive_dir = self.layout.releases_root / old_digest
        authority_admin.ensure_directory(
            archive_dir,
            0o700,
            self.identity.admin_uid,
            self.identity.admin_gid,
            self.layout,
            self.identity,
        )
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(self.layout.install_root / name, archive_dir / name)

        idempotency_key = authority_admin.upgrade_idempotency_key(old_digest, new_digest)
        journal = {
            "upgrade_journal_schema_version": 1,
            "idempotency_key": idempotency_key,
            "old_release_digest": old_digest,
            "new_release_digest": new_digest,
            "state": "rolled_back",
            "started_at": "2026-07-15T22:29:17+02:00",
            "completed_at": "2026-07-15T22:29:18+02:00",
            "admin_uid": self.identity.admin_uid,
        }
        authority_admin.write_upgrade_journal(self.layout, self.identity, journal)

        # Case A: Rollback is healthy on replay
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=lambda *args, **kwargs: True,
            )
        self.assertEqual(ctx.exception.code, "upgrade_health_check_failed")

        # Case B: Rollback is unhealthy on replay
        with self.assertRaises(authority_admin.AdminError) as ctx:
            authority_admin.upgrade_deployment(
                self.layout,
                candidate_dir,
                self.identity.admin_uid,
                self.identity.admin_gid,
                validate_accounts=False,
                health_probe=lambda *args, **kwargs: False,
            )
        self.assertEqual(ctx.exception.code, "rollback_unhealthy")


if __name__ == "__main__":
    unittest.main()
