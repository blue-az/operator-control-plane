from __future__ import annotations

import array
import json
import os
import select
import shutil
import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
import sys
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
BROKER_BIN = REPO_ROOT / "operator-broker"
OPERATOR_BIN = REPO_ROOT / "operator"


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

        # Generate mock registry
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "registrations": [
                        {
                            "repository_path": str(self.temp_dir),
                            "ledger_id": "ledger-test",
                            "socket_path": str(self.socket_path),
                        }
                    ],
                }
            )
        )

        # Set up test environment variables
        self.test_env = os.environ.copy()
        self.test_env["OPERATOR_REGISTRY_PATH"] = str(self.registry_path)

        # Set up policy config for broker
        # Assign roles: current UID gets both builder and verifier roles for tests
        uid = os.getuid()
        self.bootstrap_config_path.write_text(
            json.dumps(
                {
                    "policy_id": "standalone-policy",
                    "policy_generation": 1,
                    "ledgers": ["ledger-test"],
                    "roles": {str(uid): ["builder", "verifier"]},
                }
            )
        )

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
            self.assertEqual(os.read(read_fd, 1), b"1")
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

    def run_operator(self, *args: str, stdin_data: str | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(OPERATOR_BIN)] + list(args),
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
        conn.execute("UPDATE authority_events SET actor_uid = actor_uid + 1 WHERE record_type = 'claim'")
        conn.commit()
        conn.close()


    def test_enrollment_resolution(self) -> None:
        # Check that resolve_enrollment correctly resolves inside the workspace
        import authority_client
        
        # Test direct resolution using import and custom environment
        os.environ["OPERATOR_REGISTRY_PATH"] = str(self.registry_path)
        try:
            enrollment = authority_client.resolve_enrollment(self.temp_dir)
            self.assertIsNotNone(enrollment)
            self.assertEqual(enrollment[0], "ledger-test")
            self.assertEqual(enrollment[1], str(self.socket_path))
        finally:
            del os.environ["OPERATOR_REGISTRY_PATH"]

    def test_claim_add_routing(self) -> None:
        # 1. Create a task locally
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0, res.stderr)

        # 2. Add a claim; should route through broker and project locally
        res = self.run_operator("claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim")
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("Registered claim 'claim-0001' on task 'task-1' via authority broker.", res.stdout)

        # 3. Verify YAML projection was created
        claim_yaml_path = self.temp_dir / ".operator" / "claims" / "claim-0001.yaml"
        self.assertTrue(claim_yaml_path.exists())
        
        with open(claim_yaml_path) as f:
            claim_data = yaml.safe_load(f)
            self.assertEqual(claim_data["claim_id"], "claim-0001")
            self.assertEqual(claim_data["text"], "Test claim")
            self.assertEqual(claim_data["verification_status"], "unverified")

    def test_evidence_attach_routing(self) -> None:
        # 1. Setup task and claim
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator("claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim")
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
        self.assertIn("Registered evidence 'evidence-0001' on task 'task-1' via authority broker.", res.stdout)

        # Verify YAML projection
        ev_yaml_path = self.temp_dir / ".operator" / "evidence" / "task-1" / "evidence-0001.yaml"
        self.assertTrue(ev_yaml_path.exists())
        with open(ev_yaml_path) as f:
            ev_data = yaml.safe_load(f)
            self.assertEqual(ev_data["evidence_id"], "evidence-0001")
            self.assertEqual(ev_data["path_or_url"], str(ev_file))

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
        self.assertIn("Registered evidence 'evidence-0002' on task 'task-1' via authority broker.", res.stdout)

        # Check claim verification status projection is updated
        claim_yaml_path = self.temp_dir / ".operator" / "claims" / "claim-0001.yaml"
        with open(claim_yaml_path) as f:
            claim_data = yaml.safe_load(f)
            self.assertEqual(claim_data["verification_status"], "verified")

    def test_task_transition_routing(self) -> None:
        # 1. Setup task, claim, and verify the claim
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator("claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim")
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
        self.assertIn("Task status transitions to 'verified' or 'complete' are restricted", res.stderr + res.stdout)

    def test_fail_closed_if_broker_unavailable(self) -> None:
        # 1. Setup task
        res = self.run_operator("task-create", "--id", "task-1", "--objective", "Test objective")
        self.assertEqual(res.returncode, 0)

        # 2. Stop the broker
        self.stop_broker_server()

        # 3. Attempt claim-add; should fail closed
        res = self.run_operator("claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Fail claim")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Broker dispatch failed", res.stderr + res.stdout)

        # Verify no claim-0001 YAML file was written
        claim_yaml_path = self.temp_dir / ".operator" / "claims" / "claim-0001.yaml"
        self.assertFalse(claim_yaml_path.exists())

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
        res = self.run_operator("claim-add", "--task", "task-1", "--type", "deployment_state", "--text", "Test claim")
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


if __name__ == "__main__":
    unittest.main()
