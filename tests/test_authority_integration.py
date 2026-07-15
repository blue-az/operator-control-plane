from __future__ import annotations

import array
import hashlib
import json
import os
import select
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
BROKER_BIN = REPO_ROOT / "operator-broker"
OPERATOR_BIN = REPO_ROOT / "operator"

import authority_broker  # noqa: E402


class TestAuthorityIntegration(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)

        # Initialize the operator workspace
        res = subprocess.run([str(OPERATOR_BIN), "init"], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)

        self.processes: list[subprocess.Popen[str]] = []
        self.store_path = self.temp_dir / "authority.sqlite3"
        self.content_dir = self.temp_dir / "content"
        self.socket_path = self.temp_dir / "broker.sock"
        self.bootstrap_config_path = self.temp_dir / "bootstrap.json"
        self.registry_path = self.temp_dir / "registry.json"
        self.ledger_id = "ledger-test"

        uid = os.getuid()
        policy_document = {
            "policy_id": "standalone-policy",
            "policy_generation": 1,
            "ledgers": ["ledger-test"],
            "roles": {str(uid): ["builder", "verifier"]},
        }
        policy_sha256 = hashlib.sha256(
            json.dumps(
                policy_document,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest()
        repository_stat = self.temp_dir.lstat()
        operator_stat = (self.temp_dir / ".operator").lstat()
        ledger_stat = (self.temp_dir / ".operator" / "ledger.sqlite3").lstat()
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "registrations": [
                        {
                            "repository_path": str(self.temp_dir),
                            "ledger_id": "ledger-test",
                            "socket_path": str(self.socket_path),
                            "repository_identity": {
                                "repository_path": str(self.temp_dir),
                                "repository_device": repository_stat.st_dev,
                                "repository_inode": repository_stat.st_ino,
                                "operator_device": operator_stat.st_dev,
                                "operator_inode": operator_stat.st_ino,
                                "ledger_device": ledger_stat.st_dev,
                                "ledger_inode": ledger_stat.st_ino,
                            },
                            "anchor_records": [],
                            "legacy_anchor_sha256": hashlib.sha256(b"[]").hexdigest(),
                            "policy_binding": {
                                "id": "standalone-policy",
                                "generation": 1,
                                "sha256": policy_sha256,
                            },
                            "first_broker_sequence": 1,
                            "enrollment_receipt_hash": "0" * 64,
                        }
                    ],
                }
            )
        )

        # Build a test-only CLI copy with a compiled-in temporary registry. Production
        # code has no environment-variable registry selector.
        self.cli_dir = self.temp_dir / "cli"
        self.cli_dir.mkdir()
        for filename in ("operator", "authority_client.py", "authority_projection.py"):
            shutil.copy2(REPO_ROOT / filename, self.cli_dir / filename)
        client_path = self.cli_dir / "authority_client.py"
        client_source = client_path.read_text()
        client_source = client_source.replace(
            'REGISTRY_PATH = Path("/etc/operator-control-plane-registry.json")',
            f"REGISTRY_PATH = Path({str(self.registry_path)!r})",
        )
        client_source = client_source.replace(
            "REGISTRY_OWNER_UID = 0", f"REGISTRY_OWNER_UID = {os.getuid()}"
        )
        client_source = client_source.replace(
            "REQUIRE_TRUSTED_ANCESTORS = True", "REQUIRE_TRUSTED_ANCESTORS = False"
        )
        client_path.write_text(client_source)
        self.operator_bin = self.cli_dir / "operator"

        self.test_env = os.environ.copy()

        # Set up policy config for broker
        # Assign roles: current UID gets both builder and verifier roles for tests
        self.bootstrap_config_path.write_text(json.dumps(policy_document))

        # Bootstrap broker store
        res = subprocess.run(
            [
                str(BROKER_BIN),
                "bootstrap-fixture",
                "--store",
                str(self.store_path),
                "--content-dir",
                str(self.content_dir),
                "--bootstrap-config",
                str(self.bootstrap_config_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)

        registry = json.loads(self.registry_path.read_text())
        registration = registry["registrations"][0]
        enrollment_request = {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": self.ledger_id,
            "operation_key": "integration-fixture-enrollment",
            "operation": {
                "kind": "ledger.enroll",
                "repository_identity": registration["repository_identity"],
                "anchor_records": [],
                "legacy_anchor_sha256": registration["legacy_anchor_sha256"],
            },
            "expected": [],
            "blob": None,
        }
        fixture_broker = authority_broker.AuthorityBroker(
            authority_broker.AuthorityStore(self.store_path, self.content_dir)
        )
        enrollment_response, committed = fixture_broker.handle(
            enrollment_request,
            authority_broker.PeerCredentials(os.getpid(), 0, 0),
        )
        self.assertTrue(committed)
        registration["enrollment_receipt_hash"] = enrollment_response["receipt"]["receipt_hash"]
        self.registry_path.write_text(json.dumps(registry))

        # Start broker server
        self.start_broker_server()

    def start_broker_server(self) -> None:
        read_fd, write_fd = os.pipe()
        process = subprocess.Popen(
            [
                str(BROKER_BIN),
                "serve",
                "--store",
                str(self.store_path),
                "--content-dir",
                str(self.content_dir),
                "--socket",
                str(self.socket_path),
                "--ready-fd",
                str(write_fd),
            ],
            env=self.test_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            pass_fds=(write_fd,),
        )
        self.processes.append(process)
        os.close(write_fd)
        ready, _, _ = select.select([read_fd], [], [], 5)
        try:
            self.assertTrue(ready, "broker did not signal readiness")
            ready_byte = os.read(read_fd, 1)
            if ready_byte != b"1":
                stdout, stderr = process.communicate(timeout=2)
                self.fail(f"broker exited before readiness: {stdout}{stderr}")
        finally:
            os.close(read_fd)

    def stop_broker_server(self) -> None:
        for process in reversed(self.processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        self.processes.clear()

    def tearDown(self) -> None:
        self.stop_broker_server()
        os.chdir(self.old_cwd)
        shutil.rmtree(self.temp_dir)

    def run_operator(
        self, *args: str, stdin_data: str | None = None
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(self.operator_bin)] + list(args),
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=self.test_env,
        )

    def mock_claim_author_uid(self) -> None:
        import sqlite3

        conn = sqlite3.connect(str(self.store_path))
        conn.execute("DROP TRIGGER IF EXISTS authority_events_no_update")
        conn.execute(
            "UPDATE authority_events SET actor_uid = actor_uid + 1 WHERE record_type = 'claim'"
        )
        conn.commit()
        conn.close()

    def test_enrollment_resolution(self) -> None:
        registry = json.loads(self.registry_path.read_text())
        registry["registrations"].insert(
            0,
            {
                "repository_path": str(self.temp_dir / "deleted-repository"),
                "ledger_id": "stale-ledger",
                "socket_path": str(self.temp_dir / "stale.sock"),
            },
        )
        self.registry_path.write_text(json.dumps(registry))

        nested = self.temp_dir / "nested" / "worktree"
        (nested / ".operator").mkdir(parents=True)
        os.chdir(nested)
        try:
            res = self.run_operator("doctor")
        finally:
            os.chdir(self.temp_dir)
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("policy_authority: external_broker", res.stdout)

        fake_registry = self.temp_dir / "agent-selected-registry.json"
        fake_registry.write_text('{"schema_version": 1, "registrations": []}')
        self.test_env["OPERATOR_REGISTRY_PATH"] = str(fake_registry)
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("policy_authority: external_broker", res.stdout)

    def test_claim_add_routing(self) -> None:
        # 1. Create a task locally
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0, res.stderr)

        # 2. Add a claim; should route through broker and project locally
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim"
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn(
            "Registered claim 'claim-0001' on task 'task-1' via authority broker.", res.stdout
        )

        # 3. Verify YAML projection was created
        claim_yaml_path = self.temp_dir / ".operator" / "claims" / "claim-0001.yaml"
        self.assertTrue(claim_yaml_path.exists())

        with open(claim_yaml_path) as f:
            claim_data = yaml.safe_load(f)
            self.assertEqual(claim_data["claim_id"], "claim-0001")
            self.assertEqual(claim_data["text"], "Test claim")
            self.assertFalse(claim_data["verification_status"])

    def test_evidence_attach_routing(self) -> None:
        # 1. Setup task and claim
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim"
        )
        self.assertEqual(res.returncode, 0)

        # Create local evidence file
        ev_file = self.temp_dir / "evidence.txt"
        ev_file.write_text("Hello verification evidence")

        # 2. Attach draft status-free evidence
        res = self.run_operator(
            "evidence-attach",
            str(ev_file),
            "--task",
            "task-1",
            "--claim",
            "claim-0001",
            "--type",
            "run_log",
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn(
            "Registered evidence 'evidence-0001' on task 'task-1' via authority broker.", res.stdout
        )

        # Verify YAML projection
        ev_yaml_path = self.temp_dir / ".operator" / "evidence" / "task-1" / "evidence-0001.yaml"
        self.assertTrue(ev_yaml_path.exists())
        with open(ev_yaml_path) as f:
            ev_data = yaml.safe_load(f)
            self.assertEqual(ev_data["evidence_id"], "evidence-0001")
            self.assertEqual(ev_data["path_or_url"], str(ev_file))

        journal_path = self.temp_dir / ".operator" / "client_journal.sqlite3"
        journal_before = journal_path.read_bytes()
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertEqual(journal_path.read_bytes(), journal_before)

        # 3. Attach status-bearing evidence (verifying claim)
        ev_file2 = self.temp_dir / "evidence2.txt"
        ev_file2.write_text("Verifier results")
        self.mock_claim_author_uid()
        res = self.run_operator(
            "evidence-attach",
            str(ev_file2),
            "--task",
            "task-1",
            "--claim",
            "claim-0001",
            "--type",
            "run_log",
            "--status",
            "verified",
            "--verified-by",
            "verifier-actor",
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn(
            "Registered evidence 'evidence-0002' on task 'task-1' via authority broker.", res.stdout
        )

        # Check claim verification status projection is updated
        claim_yaml_path = self.temp_dir / ".operator" / "claims" / "claim-0001.yaml"
        with open(claim_yaml_path) as f:
            claim_data = yaml.safe_load(f)
            self.assertTrue(claim_data["verification_status"])

    def test_task_transition_routing(self) -> None:
        # 1. Setup task, claim, and verify the claim
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim"
        )
        self.assertEqual(res.returncode, 0)

        ev_file = self.temp_dir / "evidence.txt"
        ev_file.write_text("Hello verification")
        self.mock_claim_author_uid()
        res = self.run_operator(
            "evidence-attach",
            str(ev_file),
            "--task",
            "task-1",
            "--claim",
            "claim-0001",
            "--type",
            "run_log",
            "--status",
            "verified",
            "--verified-by",
            "verifier-actor",
        )
        self.assertEqual(res.returncode, 0)

        # 2. Transition task to status 'verified'
        res = self.run_operator(
            "task-transition",
            "--task",
            "task-1",
            "--status",
            "verified",
            "--claim",
            "claim-0001",
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("Successfully transitioned task 'task-1' to status 'verified'.", res.stdout)

        # Verify task status in YAML projection
        task_yaml_path = self.temp_dir / ".operator" / "tasks" / "task-1.yaml"
        with open(task_yaml_path) as f:
            task_data = yaml.safe_load(f)
            self.assertEqual(task_data["status"], "verified")

        # 3. Transition task to status 'complete' (claim not allowed for complete transition)
        res = self.run_operator(
            "task-transition",
            "--task",
            "task-1",
            "--status",
            "complete",
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("Successfully transitioned task 'task-1' to status 'complete'.", res.stdout)

        with open(task_yaml_path) as f:
            task_data = yaml.safe_load(f)
            self.assertEqual(task_data["status"], "complete")

    def test_session_end_rejection(self) -> None:
        # 1. Setup task and start session
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator("session-start", "--task", "task-1", "--harness", "gemini-agy")
        self.assertEqual(res.returncode, 0, res.stderr)

        # 2. Attempt to run session-end with verified status; should be rejected
        res = self.run_operator(
            "session-end",
            "usage-0001",
            "--outcome",
            "useful",
            "--cost",
            "0.05",
            "--status",
            "verified",
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn(
            "Task status transitions to 'verified' or 'complete' are restricted",
            res.stderr + res.stdout,
        )

    def test_fail_closed_if_broker_unavailable(self) -> None:
        # 1. Setup task
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)

        # 2. Stop the broker
        self.stop_broker_server()

        # 3. Attempt claim-add; should fail closed
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Fail claim"
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot determine expected state", res.stderr + res.stdout)

        # Verify no claim-0001 YAML file was written
        claim_yaml_path = self.temp_dir / ".operator" / "claims" / "claim-0001.yaml"
        self.assertFalse(claim_yaml_path.exists())

    def test_retry_after_outage_creates_no_duplicate_commit(self) -> None:
        # A failed attempt while the broker is down must not poison a later,
        # successful retry with a stale operation-key collision: compile_expected
        # must fail closed (not silently default to version=0) before any local
        # journal row is ever written for the doomed attempt.
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)

        self.stop_broker_server()
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Retry claim"
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("cannot determine expected state", res.stderr + res.stdout)

        self.start_broker_server()
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Retry claim"
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)

        conn = sqlite3.connect(str(self.store_path))
        try:
            (commit_count,) = conn.execute(
                "SELECT COUNT(*) FROM authority_commits WHERE operation = 'claim.create'"
            ).fetchone()
        finally:
            conn.close()
        self.assertEqual(commit_count, 1)

    def test_doctor_reports(self) -> None:
        # 1. Check current status
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("status: current", res.stdout)
        self.assertIn("verification_authority: uid_isolated", res.stdout)
        self.assertIn("policy_authority: external_broker", res.stdout)

        # 2. Setup task and claim
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim"
        )
        self.assertEqual(res.returncode, 0)

        # 3. Verify status remains current after reconciliation
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("status: current", res.stdout)

        # 4. Introduce local divergence (modify claim YAML manually)
        claim_yaml_path = self.temp_dir / ".operator" / "claims" / "claim-0001.yaml"
        with open(claim_yaml_path, "r") as f:
            claim_data = yaml.safe_load(f)
        claim_data["text"] = "Forged/altered claim text"
        with open(claim_yaml_path, "w") as f:
            yaml.safe_dump(claim_data, f)

        # Verify doctor reports divergent_or_forged_local
        res = self.run_operator("doctor")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("status: divergent_or_forged_local", res.stdout)

        # Restore
        claim_data["text"] = "Test claim"
        with open(claim_yaml_path, "w") as f:
            yaml.safe_dump(claim_data, f)

        # 5. Broker unavailable check
        self.stop_broker_server()
        res = self.run_operator("doctor")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("status: broker_unavailable", res.stdout)

    def test_authority_security_fail_closed(self) -> None:
        # Check that resolve_enrollment fails closed on unsafe registry permissions
        os.chmod(str(self.registry_path), 0o777)  # unsafe group/other writable

        # Attempt running doctor
        res = self.run_operator("doctor")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("authority registry file is unsafe", res.stderr + res.stdout)

    def test_read_only_doctor(self) -> None:
        # Delete client_journal if it exists
        journal_path = self.temp_dir / ".operator" / "client_journal.sqlite3"
        if journal_path.exists():
            journal_path.unlink()

        # Run doctor
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)

        # Verify client_journal database file was NOT created
        self.assertFalse(journal_path.exists())

    def test_doctor_rejects_post_enrollment_local_write_without_mutating(self) -> None:
        res = self.run_operator(
            "task-create", "--id", "legacy-task", "--objective", "Legacy local task"
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)

        import sqlite3

        db_path = self.temp_dir / ".operator" / "ledger.sqlite3"
        before = db_path.read_bytes()
        conn = sqlite3.connect(db_path)
        table_before = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'authority_projection_events'"
        ).fetchone()
        conn.close()
        self.assertIsNone(table_before)

        res = self.run_operator("doctor")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("status: divergent_or_forged_local", res.stdout)
        self.assertIn("Local forged record found: task legacy-task", res.stdout)
        self.assertEqual(db_path.read_bytes(), before)

        conn = sqlite3.connect(db_path)
        table_after = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'authority_projection_events'"
        ).fetchone()
        conn.close()
        self.assertIsNone(table_after)

    def test_definitive_replay_rejection_discards_prepared_transaction(self) -> None:
        import sqlite3

        import authority_projection

        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "claim-add",
            "--task",
            "task-1",
            "--type",
            "deployment_state",
            "--text",
            "Test claim",
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)

        operation_key = "op-rejected-replay"
        request = {
            "action": "commit",
            "ledger_id": self.ledger_id,
            "operation_key": operation_key,
            "operation": {
                "kind": "claim.create",
                "task_id": "task-1",
                "claim_id": "claim-9999",
                "claim_type": "deployment_state",
                "text": "Stale request",
            },
            "expected": [
                {
                    "record_type": "task",
                    "record_id": "task-1",
                    "version": 0,
                    "event_hash": None,
                },
                {
                    "record_type": "claim",
                    "record_id": "claim-9999",
                    "version": 0,
                    "event_hash": None,
                },
            ],
            "blob": None,
        }
        journal_path = self.temp_dir / ".operator" / "client_journal.sqlite3"
        conn = authority_projection.ensure_journal(str(self.temp_dir / ".operator"))
        authority_projection.prepare_transaction(conn, operation_key, request)
        conn.close()

        res = self.run_operator("authority-reconcile")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        conn = sqlite3.connect(journal_path)
        remaining = conn.execute(
            "SELECT COUNT(*) FROM transaction_journal WHERE operation_key = ?",
            (operation_key,),
        ).fetchone()[0]
        conn.close()
        self.assertEqual(remaining, 0)

    def test_projection_helpers_preserve_contracts(self) -> None:
        import math

        import authority_broker
        import authority_client
        import authority_projection

        value = {"unicode": "\u03c4", "nested": {"answer": 42}}
        self.assertEqual(
            authority_client.canonical_json(value), authority_broker.canonical_json(value)
        )
        with self.assertRaises(ValueError):
            authority_client.canonical_json({"invalid": math.nan})

        projection = self.temp_dir / "mode-preserved.yaml"
        projection.write_text("old: value\n")
        os.chmod(projection, 0o640)
        authority_projection.save_yaml({"new": "value"}, str(projection))
        self.assertEqual(projection.stat().st_mode & 0o777, 0o640)

        def handoff_record(task_id: str) -> dict:
            return {
                "record_type": "handoff",
                "record_id": "handoff-0001",
                "version": 1,
                "event_hash": "1" * 64,
                "payload": {"task_id": task_id, "handoff_id": "handoff-0001"},
                "authority": {
                    "actor_uid": os.getuid(),
                    "policy": {"id": "policy", "generation": 1, "sha256": "2" * 64},
                },
            }

        _, first_path, _ = authority_projection.normalize_record(
            str(self.temp_dir / ".operator"), handoff_record("task-1")
        )
        _, second_path, _ = authority_projection.normalize_record(
            str(self.temp_dir / ".operator"), handoff_record("task-2")
        )
        self.assertNotEqual(first_path, second_path)
        self.assertTrue(first_path.endswith("handoffs/task-1/handoff-0001.yaml"))

    def test_lost_evidence_response_recovery(self) -> None:
        import hashlib
        import json

        import authority_projection

        # 1. Setup task and claim
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim"
        )
        self.assertEqual(res.returncode, 0)

        # 2. Add a prepared evidence request with path_or_url in the journal
        ev_file = self.temp_dir / "evidence_lost.txt"
        ev_file.write_text("Lost response content")

        h = hashlib.sha256()
        h.update(b"Lost response content")
        file_hash = h.hexdigest()
        size_bytes = len(b"Lost response content")

        expected = [
            authority_projection.get_expected_item(
                str(self.temp_dir / ".operator"), "task", "task-1"
            ),
            authority_projection.get_expected_item(
                str(self.temp_dir / ".operator"), "claim", "claim-0001"
            ),
            {
                "record_type": "evidence",
                "record_id": "evidence-0001",
                "version": 0,
                "event_hash": None,
            },
        ]

        request = {
            "action": "commit",
            "ledger_id": self.ledger_id,
            "operation_key": "op-evidence-attach-evidence-0001",
            "operation": {
                "kind": "evidence.attach_draft",
                "task_id": "task-1",
                "claim_id": "claim-0001",
                "evidence_id": "evidence-0001",
                "evidence_type": "run_log",
            },
            "expected": expected,
            "blob": {
                "sha256": file_hash,
                "size_bytes": size_bytes,
            },
        }

        conn_journal = authority_projection.ensure_journal(str(self.temp_dir / ".operator"))
        authority_projection.prepare_transaction(
            conn_journal,
            "op-evidence-attach-evidence-0001",
            request,
            evidence_path=str(ev_file),
        )
        conn_journal.close()

        # The broker commits, but the client loses the response before updating its journal.
        import authority_client

        committed = authority_client.AuthorityClient(str(self.socket_path)).send_request(
            request, evidence_path=str(ev_file)
        )
        self.assertTrue(committed["ok"])

        # 3. Reconcile
        res = self.run_operator("authority-reconcile")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)

        # 4. Check that it successfully recovered, committed, and projected!
        ev_yaml_path = self.temp_dir / ".operator" / "evidence" / "task-1" / "evidence-0001.yaml"
        self.assertTrue(ev_yaml_path.exists())

    def test_reconcile_rejects_higher_local_forgery(self) -> None:
        import json
        import sqlite3

        # 1. Setup task and claim
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim"
        )
        self.assertEqual(res.returncode, 0)

        # 2. Tamper: manually insert a higher version 2 (forgery) in local ledger_events
        db_path = self.temp_dir / ".operator" / "ledger.sqlite3"
        conn_ledger = sqlite3.connect(str(db_path))
        # Find version 1 claim event to copy structure
        row = conn_ledger.execute(
            "SELECT * FROM ledger_events WHERE record_type = 'claim' AND record_id = 'claim-0001'"
        ).fetchone()
        self.assertIsNotNone(row)

        # Drop triggers temporarily to allow insert
        conn_ledger.execute("DROP TRIGGER IF EXISTS ledger_events_no_update")
        conn_ledger.execute("DROP TRIGGER IF EXISTS ledger_events_no_delete")

        # Insert forged version 2
        payload = json.loads(row[5])
        payload["text"] = "Forged/tampered version 2 claim text"
        conn_ledger.execute(
            """
            INSERT INTO ledger_events (
                event_id, record_type, record_id, version, event_type, payload_json,
                actor_uid, actor_name, created_at, source_command, previous_event_hash,
                event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "evt-claim-forged-v2",
                "claim",
                "claim-0001",
                2,  # version 2 (which is not committed on the broker!)
                "claim.create",
                json.dumps(payload),
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                "forged_hash_v2",
            ),
        )

        # Recreate triggers
        conn_ledger.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS ledger_events_no_update
            BEFORE UPDATE ON ledger_events
            BEGIN
                SELECT RAISE(ABORT, 'ledger_events is append-only');
            END;

            CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete
            BEFORE DELETE ON ledger_events
            BEGIN
                SELECT RAISE(ABORT, 'ledger_events is append-only');
            END;
        """
        )
        conn_ledger.commit()
        conn_ledger.close()

        # The forged row remains forensic evidence and doctor continues to fail closed.
        conn_ledger = sqlite3.connect(str(db_path))
        max_ver = conn_ledger.execute(
            "SELECT MAX(version) FROM ledger_events WHERE record_type = 'claim' AND record_id = 'claim-0001'"
        ).fetchone()[0]
        conn_ledger.close()
        self.assertEqual(max_ver, 2)
        res = self.run_operator("doctor")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("status: divergent_or_forged_local", res.stdout)

    def test_migration_and_anchor_records(self) -> None:
        import hashlib

        import authority_client

        def test_canonical_json(value: object) -> str:
            return json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            )

        def test_event_hash(
            record_type: str,
            record_id: str,
            version: int,
            event_type: str,
            payload_json: str,
            actor_uid: int | None,
            actor_name: str | None,
            created_at: str,
            source_command: str | None,
            previous_event_hash: str | None,
        ) -> str:
            hash_fields = {
                "hash_format": "operator-ledger-event-v1",
                "record_type": record_type,
                "record_id": record_id,
                "version": version,
                "event_type": event_type,
                "payload_json": payload_json,
                "actor_uid": actor_uid,
                "actor_name": actor_name,
                "created_at": created_at,
                "source_command": source_command,
                "previous_event_hash": previous_event_hash,
            }
            return hashlib.sha256(test_canonical_json(hash_fields).encode("utf-8")).hexdigest()

        # 1. Create a legacy task-legacy record
        legacy_yaml = {
            "task_id": "task-legacy",
            "objective": "Legacy task",
            "status": "proposed",
            "claim_ids": [],
            "evidence_ids": [],
            "verified_claim_ids": [],
            "policy_authority": "local_policy",
            "verification_authority": None,
        }

        payload_json = test_canonical_json(legacy_yaml)
        event_hash = test_event_hash(
            record_type="task",
            record_id="task-legacy",
            version=1,
            event_type="record_created",
            payload_json=payload_json,
            actor_uid=1000,
            actor_name="blueaz",
            created_at="2026-07-14T16:00:00Z",
            source_command="task-create",
            previous_event_hash=None,
        )

        db_path = self.temp_dir / ".operator" / "ledger.sqlite3"
        conn_ledger = sqlite3.connect(str(db_path))
        conn_ledger.execute(
            """
            INSERT INTO ledger_events (
                event_id, record_type, record_id, version, event_type, payload_json,
                actor_uid, actor_name, created_at, source_command, event_hash
            ) VALUES (?, 'task', 'task-legacy', 1, 'record_created', ?, 1000, 'blueaz', '2026-07-14T16:00:00Z', 'task-create', ?)
        """,
            (event_hash, payload_json, event_hash),
        )
        conn_ledger.commit()
        conn_ledger.close()

        # Write legacy task YAML
        tasks_dir = self.temp_dir / ".operator" / "tasks"
        tasks_dir.mkdir(exist_ok=True)
        with open(tasks_dir / "task-legacy.yaml", "w") as f:
            yaml.safe_dump(legacy_yaml, f)

        # Replace the synthetic Issue #6 registration with an explicit migration.
        import authority_admin

        self.registry_path.write_text(json.dumps({"schema_version": 1, "registrations": []}))

        def committed_enrollment(_socket_path: Path, request: object) -> dict:
            assert isinstance(request, dict)
            return {
                "ok": True,
                "receipt": {
                    "ledger_id": request["ledger_id"],
                    "operation": "ledger.enroll",
                    "operation_key": request["operation_key"],
                    "commit_sequence": 1,
                    "policy": {
                        "id": "standalone-policy",
                        "generation": 1,
                        "sha256": hashlib.sha256(
                            json.dumps(
                                {
                                    "policy_id": "standalone-policy",
                                    "policy_generation": 1,
                                    "ledgers": ["ledger-test"],
                                    "roles": {str(os.getuid()): ["builder", "verifier"]},
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        ).hexdigest(),
                    },
                    "receipt_hash": "3" * 64,
                },
            }

        res = authority_admin.enroll_repository(
            self.registry_path,
            self.temp_dir,
            self.ledger_id,
            self.socket_path,
            registry_owner_uid=os.getuid(),
            registry_owner_gid=os.getgid(),
            registry_anchor=self.temp_dir,
            request_sender=committed_enrollment,
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["anchor_records_count"], 1)

        # 2. Verify doctor reports current status (acknowledges legacy record)
        res_doc = self.run_operator("doctor")
        self.assertEqual(res_doc.returncode, 0, res_doc.stderr + res_doc.stdout)
        self.assertIn("status: current", res_doc.stdout)

        # 3. Create a local-only forged claim (without broker or registry enrollment)
        forged_yaml = {
            "claim_id": "claim-forged",
            "task_id": "task-legacy",
            "type": "deployment_state",
            "text": "Forged claim",
            "verification_status": "proposed",
            "policy_authority": "local_policy",
            "verification_authority": None,
        }
        payload_json_forged = test_canonical_json(forged_yaml)
        event_hash_forged = test_event_hash(
            record_type="claim",
            record_id="claim-forged",
            version=1,
            event_type="record_created",
            payload_json=payload_json_forged,
            actor_uid=1000,
            actor_name="blueaz",
            created_at="2026-07-14T16:05:00Z",
            source_command="claim-add",
            previous_event_hash=None,
        )

        conn_ledger = sqlite3.connect(str(db_path))
        conn_ledger.execute(
            """
            INSERT INTO ledger_events (
                event_id, record_type, record_id, version, event_type, payload_json,
                actor_uid, actor_name, created_at, source_command, event_hash
            ) VALUES (?, 'claim', 'claim-forged', 1, 'record_created', ?, 1000, 'blueaz', '2026-07-14T16:05:00Z', 'claim-add', ?)
        """,
            (event_hash_forged, payload_json_forged, event_hash_forged),
        )
        conn_ledger.commit()
        conn_ledger.close()

        # Write forged claim YAML
        claims_dir = self.temp_dir / ".operator" / "claims"
        claims_dir.mkdir(exist_ok=True)
        with open(claims_dir / "claim-forged.yaml", "w") as f:
            yaml.safe_dump(forged_yaml, f)

        # Verify doctor reports divergent_or_forged_local
        res_doc = self.run_operator("doctor")
        self.assertNotEqual(res_doc.returncode, 0)
        self.assertIn("status: divergent_or_forged_local", res_doc.stdout)
        self.assertIn("Local forged record found: claim claim-forged", res_doc.stdout)

        # Clean up the forged claim from database and disk
        conn_ledger = sqlite3.connect(str(db_path))
        conn_ledger.execute("DROP TRIGGER IF EXISTS ledger_events_no_update")
        conn_ledger.execute("DROP TRIGGER IF EXISTS ledger_events_no_delete")
        conn_ledger.execute("DELETE FROM ledger_events WHERE record_id = 'claim-forged'")
        conn_ledger.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS ledger_events_no_update BEFORE UPDATE ON ledger_events BEGIN SELECT RAISE(ABORT, 'ledger_events is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete BEFORE DELETE ON ledger_events BEGIN SELECT RAISE(ABORT, 'ledger_events is append-only'); END;
            """
        )
        conn_ledger.commit()
        conn_ledger.close()
        (claims_dir / "claim-forged.yaml").unlink()

        # Verify doctor is current again
        res_doc = self.run_operator("doctor")
        self.assertEqual(res_doc.returncode, 0)

        # 4. Mutate the legacy record locally to version 2 (exceeding anchor version)
        legacy_yaml_v2 = dict(legacy_yaml)
        legacy_yaml_v2["status"] = "complete"
        payload_json_v2 = test_canonical_json(legacy_yaml_v2)
        event_hash_v2 = test_event_hash(
            record_type="task",
            record_id="task-legacy",
            version=2,
            event_type="record_updated",
            payload_json=payload_json_v2,
            actor_uid=1000,
            actor_name="blueaz",
            created_at="2026-07-14T16:10:00Z",
            source_command="task-transition",
            previous_event_hash=event_hash,
        )

        conn_ledger = sqlite3.connect(str(db_path))
        # Disable triggers temporarily to insert version 2
        conn_ledger.execute("DROP TRIGGER IF EXISTS ledger_events_no_update")
        conn_ledger.execute("DROP TRIGGER IF EXISTS ledger_events_no_delete")
        conn_ledger.execute(
            """
            INSERT INTO ledger_events (
                event_id, record_type, record_id, version, event_type, payload_json,
                actor_uid, actor_name, created_at, source_command, previous_event_hash, event_hash
            ) VALUES (?, 'task', 'task-legacy', 2, 'record_updated', ?, 1000, 'blueaz', '2026-07-14T16:10:00Z', 'task-transition', ?, ?)
        """,
            (event_hash_v2, payload_json_v2, event_hash, event_hash_v2),
        )
        # Recreate triggers
        conn_ledger.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS ledger_events_no_update BEFORE UPDATE ON ledger_events BEGIN SELECT RAISE(ABORT, 'ledger_events is append-only'); END;
            CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete BEFORE DELETE ON ledger_events BEGIN SELECT RAISE(ABORT, 'ledger_events is append-only'); END;
            """
        )
        conn_ledger.commit()
        conn_ledger.close()

        # Write mutated legacy YAML
        with open(tasks_dir / "task-legacy.yaml", "w") as f:
            yaml.safe_dump(legacy_yaml_v2, f)

        # Verify doctor reports divergent_or_forged_local because version exceeds anchor
        res_doc = self.run_operator("doctor")
        self.assertNotEqual(res_doc.returncode, 0)
        self.assertIn("status: divergent_or_forged_local", res_doc.stdout)
        self.assertIn("exceeds pre-enrollment anchor version 1", res_doc.stdout)

    def test_evidence_anchor_record_ids_are_wire_safe_and_collision_free(self) -> None:
        # Locally, evidence record IDs are task-scoped ("<task>/<leaf>") and reset per task
        # (get_next_evidence_id numbers each task's evidence independently), so two different
        # tasks can each have a local "evidence-0001". validate_local_ledger must produce
        # anchor record_ids that (a) pass the broker's record_id character class (no "/") and
        # (b) stay distinct across tasks -- stripping the task prefix instead of re-encoding it
        # would silently collide them.
        import authority_admin
        import authority_broker as broker

        def canonical(value: object) -> str:
            return json.dumps(
                value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
            )

        def event_hash(
            record_type: str,
            record_id: str,
            payload_json: str,
            created_at: str,
            source_command: str,
        ) -> str:
            hash_fields = {
                "hash_format": "operator-ledger-event-v1",
                "record_type": record_type,
                "record_id": record_id,
                "version": 1,
                "event_type": "record_created",
                "payload_json": payload_json,
                "actor_uid": 1000,
                "actor_name": "blueaz",
                "created_at": created_at,
                "source_command": source_command,
                "previous_event_hash": None,
            }
            return hashlib.sha256(canonical(hash_fields).encode("utf-8")).hexdigest()

        db_path = self.temp_dir / ".operator" / "ledger.sqlite3"
        op_dir = self.temp_dir / ".operator"
        conn_ledger = sqlite3.connect(str(db_path))
        rows = []
        for task_id in ("task-a", "task-b"):
            task_yaml = {
                "task_id": task_id,
                "objective": f"Objective for {task_id}",
                "status": "open",
                "claim_ids": [],
                "evidence_ids": ["evidence-0001"],
                "verified_claim_ids": [],
                "policy_authority": "local_policy",
                "verification_authority": None,
            }
            created_at = "2026-07-15T12:00:00Z"
            task_payload = canonical(task_yaml)
            task_hash = event_hash("task", task_id, task_payload, created_at, "task-create")
            rows.append(("task", task_id, task_payload, created_at, "task-create", task_hash))
            (op_dir / "tasks").mkdir(exist_ok=True)
            with open(op_dir / "tasks" / f"{task_id}.yaml", "w") as f:
                yaml.safe_dump(task_yaml, f)

            evidence_record_id = f"{task_id}/evidence-0001"
            evidence_yaml = {
                "evidence_id": "evidence-0001",
                "task_id": task_id,
                "claim_id": None,
                "evidence_type": "test_output",
                "policy_authority": "local_policy",
                "verification_authority": None,
            }
            evidence_payload = canonical(evidence_yaml)
            evidence_evt_hash = event_hash(
                "evidence", evidence_record_id, evidence_payload, created_at, "evidence-attach"
            )
            rows.append(
                (
                    "evidence",
                    evidence_record_id,
                    evidence_payload,
                    created_at,
                    "evidence-attach",
                    evidence_evt_hash,
                )
            )
            (op_dir / "evidence" / task_id).mkdir(parents=True, exist_ok=True)
            with open(op_dir / "evidence" / task_id / "evidence-0001.yaml", "w") as f:
                yaml.safe_dump(evidence_yaml, f)

        for record_type, record_id, payload_json, created_at, source_command, ev_hash in rows:
            conn_ledger.execute(
                """
                INSERT INTO ledger_events (
                    event_id, record_type, record_id, version, event_type, payload_json,
                    actor_uid, actor_name, created_at, source_command, event_hash
                ) VALUES (?, ?, ?, 1, 'record_created', ?, 1000, 'blueaz', ?, ?, ?)
                """,
                (
                    ev_hash,
                    record_type,
                    record_id,
                    payload_json,
                    created_at,
                    source_command,
                    ev_hash,
                ),
            )
        conn_ledger.commit()
        conn_ledger.close()

        migration = authority_admin.validate_local_ledger(self.temp_dir)
        evidence_anchors = [
            a for a in migration["anchor_records"] if a["record_type"] == "evidence"
        ]
        self.assertEqual(len(evidence_anchors), 2)
        record_ids = {a["record_id"] for a in evidence_anchors}
        self.assertEqual(record_ids, {"task-a:evidence-0001", "task-b:evidence-0001"})
        for anchor in migration["anchor_records"]:
            # Must not raise: proves the broker's own record_id validation accepts this.
            broker.require_token(anchor["record_id"], "record_id")

        # The client-computed digest must match what the broker recomputes after its own
        # (record_type, record_id) sort over the wire-safe anchors -- not the pre-transform order.
        recomputed = sorted(
            migration["anchor_records"], key=lambda item: (item["record_type"], item["record_id"])
        )
        self.assertEqual(
            migration["legacy_anchor_sha256"], broker.sha256_text(broker.canonical_json(recomputed))
        )


if __name__ == "__main__":
    unittest.main()
