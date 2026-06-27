#!/usr/bin/env python3
"""
Integration test suite for the Operator Control Plane CLI.
Validates the full spine of commands using a temporary workspace.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

OPERATOR_BIN = str(Path(__file__).resolve().parents[1] / "operator")


class TestOperatorCLI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        shutil.rmtree(self.temp_dir)

    def run_operator(
        self, *args: str, stdin_data: str | None = None, env: dict | None = None
    ) -> subprocess.CompletedProcess[str]:
        cmd = [OPERATOR_BIN] + list(args)
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        return subprocess.run(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=run_env,
        )

    def test_init_creates_structure(self) -> None:
        res = self.run_operator("init")
        self.assertEqual(res.returncode, 0, f"init failed: {res.stderr}")
        self.assertIn("Initialized empty Operator Control Plane repository", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"
        self.assertTrue(op_path.exists())
        self.assertTrue((op_path / "harnesses").exists())
        self.assertTrue((op_path / "tasks").exists())
        self.assertTrue((op_path / "claims").exists())
        self.assertTrue((op_path / "evidence").exists())
        self.assertTrue((op_path / "usage").exists())
        self.assertTrue((op_path / "briefs").exists())

        # Verify default harnesses
        self.assertTrue((op_path / "harnesses" / "codex.yaml").exists())
        self.assertTrue((op_path / "harnesses" / "claude.yaml").exists())

    def test_task_lifecycle_and_quarantine_flow(self) -> None:
        # 1. Initialize
        self.run_operator("init")

        # 2. Create Task
        res = self.run_operator(
            "task-create",
            "--objective",
            "Audit the PROX-HIL-002 real-data claim",
            "--id",
            "prox-hil-002-audit",
            "--assign",
            "codex",
            "--review",
            "claude",
            "--assumption",
            "Session 3 physical-capture provenance is undocumented.",
        )
        self.assertEqual(res.returncode, 0, f"task-create failed: {res.stderr}")
        self.assertIn("Task 'prox-hil-002-audit' created successfully", res.stdout)

        # Verify files on disk
        op_path = Path(self.temp_dir) / ".operator"
        task_file = op_path / "tasks" / "prox-hil-002-audit.yaml"
        self.assertTrue(task_file.exists())

        # 3. Show Task (Active defaults)
        res = self.run_operator("task-show")
        self.assertEqual(res.returncode, 0, f"task-show failed: {res.stderr}")
        self.assertIn("Task ID:          prox-hil-002-audit", res.stdout)
        self.assertIn(
            "Objective:        Audit the PROX-HIL-002 real-data claim", res.stdout
        )
        self.assertIn("Status:           assigned", res.stdout)
        self.assertIn(
            "Session 3 physical-capture provenance is undocumented.", res.stdout
        )

        # 4. Add Claim
        res = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "PROX-HIL-002 validates real sensor data.",
            "--gate",
            "data provenance chain",
        )
        self.assertEqual(res.returncode, 0, f"claim-add failed: {res.stderr}")
        self.assertIn("Registered claim 'claim-0001'", res.stdout)
        self.assertTrue((op_path / "claims" / "claim-0001.yaml").exists())

        # 5. Show Claim (Initial)
        res = self.run_operator("claim-show", "claim-0001")
        self.assertEqual(res.returncode, 0, f"claim-show failed: {res.stderr}")
        self.assertIn("Claim ID:            claim-0001", res.stdout)
        self.assertIn("Verification status: UNVERIFIED", res.stdout)
        self.assertIn("Required Gate:       data provenance chain", res.stdout)

        # Create dummy evidence file
        evidence_file = Path(self.temp_dir) / "manifest.json"
        evidence_file.write_text('{"session": 3, "source": "replay"}')

        # 6. Attach Evidence and Quarantine Claim
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            "--status",
            "quarantined",
            "--verified-by",
            "claude",
            "--verdict",
            "Session 3 is database replay with undocumented provenance, not real-data evidence.",
            str(evidence_file),
        )
        self.assertEqual(res.returncode, 0, f"evidence-attach failed: {res.stderr}")
        self.assertIn("Attached evidence 'evidence-0001'", res.stdout)

        evidence_record_path = (
            op_path / "evidence" / "prox-hil-002-audit" / "evidence-0001.yaml"
        )
        evidence_record = yaml.safe_load(evidence_record_path.read_text())
        expected_hash = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
        self.assertEqual(evidence_record.get("hash"), expected_hash)

        # 7. Verify Claim status has updated to quarantined
        res = self.run_operator("claim-show", "claim-0001")
        self.assertIn("Verification status: QUARANTINED", res.stdout)
        self.assertIn(
            "Verdict:             Session 3 is database replay with undocumented provenance",
            res.stdout,
        )

        # 8. Verify Task status has updated to quarantined
        res = self.run_operator("task-show")
        self.assertIn("Status:           quarantined", res.stdout)

        # 9. Generate and verify Brief
        res = self.run_operator("brief", "--for", "codex")
        self.assertEqual(res.returncode, 0, f"brief failed: {res.stderr}")
        self.assertIn("Target Harness:** Codex", res.stdout)
        self.assertIn("claim-0001", res.stdout)
        self.assertIn("quarantined", res.stdout)

        # 10. Record Usage
        stdin_usage = "/status\nOllama running: gemma4:26b\nContext: 8k/16k"
        res = self.run_operator(
            "usage-add",
            "--harness",
            "codex",
            "--model",
            "gemma4:26b",
            "--cost",
            "0.05",
            "--outcome",
            "useful",
            stdin_data=stdin_usage,
        )
        self.assertEqual(res.returncode, 0, f"usage-add failed: {res.stderr}")
        self.assertIn("Usage record 'usage-0001' successfully added", res.stdout)

        # 11. Run Usage Summary
        res = self.run_operator("usage-summary", "--by-task")
        self.assertEqual(res.returncode, 0, f"usage-summary failed: {res.stderr}")
        self.assertIn("Total Estimated Cost: $0.0500 USD", res.stdout)
        self.assertIn("useful: 1", res.stdout)
        self.assertIn("SUMMARY BY TASK", res.stdout)
        self.assertIn("Task ID:      prox-hil-002-audit", res.stdout)

        res = self.run_operator("usage-summary", "--by-harness")
        self.assertEqual(
            res.returncode, 0, f"usage-summary --by-harness failed: {res.stderr}"
        )
        self.assertIn("SUMMARY BY HARNESS", res.stdout)
        self.assertIn("Harness ID:   codex", res.stdout)

        res = self.run_operator("usage-summary", "--by-model")
        self.assertEqual(
            res.returncode, 0, f"usage-summary --by-model failed: {res.stderr}"
        )
        self.assertIn("SUMMARY BY MODEL", res.stdout)
        self.assertIn("Model ID:     gemma4:26b", res.stdout)

        # 12. Add Handoff
        res = self.run_operator(
            "handoff-add",
            "--changed",
            "Audit notes documented",
            "--verified",
            "Session 3 data is database replay",
            "--claimed",
            "None",
            "--open",
            "Provenance is undocumented",
            "--assumptions",
            "None",
            "--next-action",
            "Replay proximity data on physical bench",
        )
        self.assertEqual(res.returncode, 0, f"handoff-add failed: {res.stderr}")
        self.assertIn("Successfully recorded handoff 'handoff-0001'", res.stdout)

        handoff_file = op_path / "handoffs" / "prox-hil-002-audit" / "handoff-0001.yaml"
        handoff_record = yaml.safe_load(handoff_file.read_text())
        self.assertEqual(
            handoff_record.get("what_verified"), "Session 3 data is database replay"
        )
        self.assertEqual(
            handoff_record.get("next_action"), "Replay proximity data on physical bench"
        )

        # 13. Add Handoff from YAML file
        yaml_handoff_file = Path(self.temp_dir) / "handoff.yaml"
        yaml_handoff_file.write_text(
            "what_changed: Added file-loaded handoff\n"
            "what_verified: YAML handoff parsing works\n"
            "next_action: Review file-loaded handoff\n"
        )
        res = self.run_operator("handoff-add", "--file", str(yaml_handoff_file))
        self.assertEqual(res.returncode, 0, f"handoff-add --file failed: {res.stderr}")
        self.assertIn("Successfully recorded handoff 'handoff-0002'", res.stdout)

        # 14. Add Handoff from stdin YAML
        stdin_handoff = (
            "what_changed: Added stdin handoff\n"
            "what_verified: Stdin handoff parsing works\n"
            "next_action: Review stdin handoff\n"
        )
        res = self.run_operator("handoff-add", "--file", "-", stdin_data=stdin_handoff)
        self.assertEqual(
            res.returncode, 0, f"handoff-add --file - failed: {res.stderr}"
        )
        self.assertIn("Successfully recorded handoff 'handoff-0003'", res.stdout)

        # 15. Reject invalid and empty handoff payloads
        res = self.run_operator(
            "handoff-add", "--file", "-", stdin_data="- not\n- a mapping\n"
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("must be a YAML mapping/object", res.stderr)

        res = self.run_operator("handoff-add", "--file", "-", stdin_data="{}\n")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Handoff is empty", res.stderr)

        # Verify that task-show includes the handoff and updated next action
        res = self.run_operator("task-show")
        self.assertEqual(
            res.returncode, 0, f"task-show with handoffs failed: {res.stderr}"
        )
        self.assertIn("Handoffs:", res.stdout)
        self.assertIn("handoffs/prox-hil-002-audit/handoff-0001.yaml", res.stdout)
        self.assertIn("handoffs/prox-hil-002-audit/handoff-0002.yaml", res.stdout)
        self.assertIn("handoffs/prox-hil-002-audit/handoff-0003.yaml", res.stdout)
        self.assertIn("Next Action:      Review stdin handoff", res.stdout)

        # 16. Generate and verify brief using handoff state
        res = self.run_operator("brief", "--for", "claude")
        self.assertEqual(res.returncode, 0, f"brief with handoffs failed: {res.stderr}")
        self.assertIn("Latest Harness Handoff Closeout", res.stdout)
        self.assertIn("Added stdin handoff", res.stdout)
        self.assertIn("Recommended Next Action:** `Review stdin handoff`", res.stdout)

    def test_doctor_next_action_warning_respects_task_status(self) -> None:
        # The next_action-mismatch warning is operational guidance for in-flight
        # work. Once a task is verified/complete, its next_action has
        # legitimately moved past the last handoff, so doctor must stay silent.
        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Next-action status guard",
            "--id",
            "next-action-task",
        )

        res = self.run_operator(
            "handoff-add",
            "--changed",
            "Work logged",
            "--next-action",
            "Replay proximity data on physical bench",
        )
        self.assertEqual(res.returncode, 0, f"handoff-add failed: {res.stderr}")

        op_path = Path(self.temp_dir) / ".operator"
        task_file = op_path / "tasks" / "next-action-task.yaml"

        # Task has since moved its own next_action away from the handoff's.
        task_data = yaml.safe_load(task_file.read_text())
        task_data["next_action"] = "Ship the paper"
        task_data["status"] = "running"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)

        # In-flight: the divergence is worth flagging.
        res = self.run_operator("doctor")
        self.assertIn("next_action differs", res.stdout)

        # Terminal statuses: the divergence is expected, so doctor stays silent.
        for terminal_status in ("verified", "complete"):
            task_data["status"] = terminal_status
            with open(task_file, "w") as f:
                yaml.safe_dump(task_data, f)
            res = self.run_operator("doctor")
            self.assertNotIn(
                "next_action differs",
                res.stdout,
                f"doctor must not warn on next_action for a '{terminal_status}' task",
            )

    def test_doctor_diagnostic_rules(self) -> None:
        import yaml

        self.run_operator("init")

        self.run_operator(
            "task-create",
            "--objective",
            "Test task for doctor",
            "--id",
            "doctor-test-task",
        )

        res = self.run_operator(
            "claim-add", "--type", "real_data", "--text", "Doctor claim test."
        )
        self.assertEqual(res.returncode, 0)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("has no required_gate defined", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"
        claim_file = op_path / "claims" / "claim-0001.yaml"

        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["required_gate"] = "test gate"
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

        claim_data["evidence_refs"] = [
            "evidence/doctor-test-task/missing-evidence.yaml"
        ]
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("evidence reference points to missing file", res.stdout)

        claim_data["evidence_refs"] = []
        claim_data["verification_outcome"] = "quarantined"
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        task_file = op_path / "tasks" / "doctor-test-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        task_data["status"] = "verified"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("while claims are quarantined: claim-0001", res.stdout)

        # Inverse rule: a task may not be quarantined while a claim under it is
        # still marked verified. This is the mirror of the check above and
        # guards against quarantining a task without retracting its claims.
        claim_data["verification_outcome"] = "verified"
        claim_data["verification_status"] = True
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        task_data["status"] = "quarantined"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "is quarantined while claims are still marked verified: claim-0001",
            res.stdout,
        )

        # Retracting the claim verdict to match the quarantined task clears the
        # inconsistency entirely (task quarantined + claim quarantined is valid).
        claim_data["verification_outcome"] = "quarantined"
        claim_data["verification_status"] = False
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertNotIn("still marked verified", res.stdout)

        claim_data["verification_outcome"] = None
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        task_data["status"] = "assigned"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)

        self.run_operator(
            "handoff-add", "--changed", "test changed", "--next-action", "Action A"
        )
        task_data = yaml.safe_load(task_file.read_text())
        task_data["next_action"] = "Action B"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "next_action differs from the latest handoff recommended next action",
            res.stdout,
        )

    def test_supervision_credit_layer_fr12(self) -> None:
        """FR-12: supervision_credit claims must name a layer or be flagged ambiguous."""
        import yaml

        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Supervision layer enforcement",
            "--id",
            "fr12-task",
        )

        # A supervision_credit claim with no --layer is accepted but warns.
        res = self.run_operator(
            "claim-add",
            "--type",
            "supervision_credit",
            "--text",
            "Claude supervised this work.",
            "--gate",
            "explicit supervision layer",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("has no --layer", res.stderr)

        op_path = Path(self.temp_dir) / ".operator"
        claim_file = op_path / "claims" / "claim-0001.yaml"
        claim_data = yaml.safe_load(claim_file.read_text())
        self.assertIsNone(claim_data.get("supervision_layer"))

        # doctor flags the ambiguous credit, and claim-show surfaces it.
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("supervision_credit with no named layer", res.stdout)

        res = self.run_operator("claim-show", "claim-0001")
        self.assertIn("Supervision Layer:   AMBIGUOUS (no layer)", res.stdout)

        # Naming the layer clears the flag and is shown verbatim.
        claim_data["supervision_layer"] = "end_to_end"
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertNotIn("no named layer", res.stdout)

        res = self.run_operator("claim-show", "claim-0001")
        self.assertIn("Supervision Layer:   end_to_end", res.stdout)

        # The --layer choice set is enforced at the CLI boundary.
        res = self.run_operator(
            "claim-add",
            "--type",
            "supervision_credit",
            "--text",
            "Bad layer value.",
            "--gate",
            "explicit supervision layer",
            "--layer",
            "not_a_layer",
        )
        self.assertNotEqual(res.returncode, 0)

        # A supervision_credit claim created with a valid --layer stores it directly.
        res = self.run_operator(
            "claim-add",
            "--type",
            "supervision_credit",
            "--text",
            "Codex supervised execution.",
            "--gate",
            "explicit supervision layer",
            "--layer",
            "execution",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("has no --layer", res.stderr)
        claim2 = yaml.safe_load((op_path / "claims" / "claim-0002.yaml").read_text())
        self.assertEqual(claim2.get("supervision_layer"), "execution")

    def test_session_start(self) -> None:
        import yaml

        self.run_operator("init")

        self.run_operator(
            "task-create",
            "--objective",
            "Verify session start flow",
            "--id",
            "session-test-task",
            "--assign",
            "claude",
        )

        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0, f"session-start failed: {res.stderr}")
        self.assertIn("SESSION INITIALIZED: session-test-task", res.stdout)
        self.assertIn("Usage placeholder recorded: usage-0001", res.stdout)
        self.assertIn("Paste instructions:", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"

        # Verify export brief exists
        brief_file = op_path / "briefs" / "session-test-task.claude.export.md"
        self.assertTrue(brief_file.exists())
        self.assertIn("Verify session start flow", brief_file.read_text())

        # Verify usage placeholder file exists
        import datetime

        utc_now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{utc_now_date}.yaml"
        self.assertTrue(usage_file.exists())

        usage_records = yaml.safe_load(usage_file.read_text())
        self.assertEqual(len(usage_records), 1)
        rec = usage_records[0]
        self.assertEqual(rec.get("usage_id"), "usage-0001")
        self.assertEqual(rec.get("task_id"), "session-test-task")
        self.assertEqual(rec.get("harness_id"), "claude")
        self.assertEqual(rec.get("outcome"), "unknown")
        self.assertIsNone(rec.get("ended_at"))

        # Verify task status is updated to running
        task_file = op_path / "tasks" / "session-test-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

    def test_session_lifecycle(self) -> None:
        import datetime

        import yaml

        self.run_operator("init")

        # 1. Create task
        self.run_operator(
            "task-create",
            "--objective",
            "Verify session lifecycle flow",
            "--id",
            "lifecycle-test-task",
            "--assign",
            "claude",
        )

        # 2. Start session
        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage placeholder recorded: usage-0001", res.stdout)

        # Verify task is running
        op_path = Path(self.temp_dir) / ".operator"
        task_file = op_path / "tasks" / "lifecycle-test-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

        # 3. Duplicate session-start fails without --force
        res2 = self.run_operator("session-start", "--harness", "claude")
        self.assertNotEqual(res2.returncode, 0)
        self.assertIn("is already running. Use --force to override.", res2.stderr)

        # 4. Duplicate session-start succeeds with --force
        res3 = self.run_operator("session-start", "--harness", "claude", "--force")
        self.assertEqual(res3.returncode, 0)
        self.assertIn("Usage placeholder recorded: usage-0002", res3.stdout)

        # 5. End session (using --usage alias)
        # We end usage-0001
        res4 = self.run_operator(
            "session-end",
            "--usage",
            "usage-0001",
            "--outcome",
            "useful",
            "--cost",
            "0.05",
            stdin_data="/status Notes on run",
        )
        self.assertEqual(res4.returncode, 0, res4.stderr)
        self.assertIn("Successfully closed usage session 'usage-0001'", res4.stdout)

        # Verify usage record update
        utc_now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{utc_now_date}.yaml"
        usage_records = yaml.safe_load(usage_file.read_text())

        rec1 = next(r for r in usage_records if r["usage_id"] == "usage-0001")
        self.assertEqual(rec1.get("outcome"), "useful")
        self.assertEqual(rec1.get("cost_estimate_usd"), 0.05)
        self.assertIsNotNone(rec1.get("ended_at"))
        self.assertEqual(rec1.get("raw_payload"), "/status Notes on run")

        # 6. Re-ending usage-0001 fails without --force
        res5 = self.run_operator(
            "session-end", "usage-0001", "--outcome", "useful", "--cost", "0.05"
        )
        self.assertNotEqual(res5.returncode, 0)
        self.assertIn("is already closed", res5.stderr)

        # 7. Re-ending usage-0001 succeeds with --force
        res6 = self.run_operator(
            "session-end",
            "usage-0001",
            "--outcome",
            "partial",
            "--cost",
            "0.10",
            "--force",
        )
        self.assertEqual(res6.returncode, 0, res6.stderr)

        # Verify task remains running because forced usage-0002 is still open.
        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

        res_doctor = self.run_operator("doctor")
        self.assertEqual(res_doctor.returncode, 0, res_doctor.stdout)

        # 8. Close the forced duplicate and verify the task defaults back to assigned.
        res7 = self.run_operator(
            "session-end", "usage-0002", "--outcome", "partial", "--cost", "0.00"
        )
        self.assertEqual(res7.returncode, 0, res7.stderr)

        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "assigned")

        # 9. Start again to test explicit status closeout
        res8 = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res8.returncode, 0)
        self.assertIn("Usage placeholder recorded: usage-0003", res8.stdout)

        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

        # End and set status to complete
        res9 = self.run_operator(
            "session-end",
            "usage-0003",
            "--outcome",
            "useful",
            "--cost",
            "0.12",
            "--status",
            "complete",
        )
        self.assertEqual(res9.returncode, 0, res9.stderr)

        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "complete")

    def test_session_list_open_and_filters(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Verify session-list reporting",
            "--id",
            "session-list-task",
            "--assign",
            "claude",
        )

        # No sessions yet.
        res = self.run_operator("session-list")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions found in ledger.", res.stdout)

        # Start a session -> one open session.
        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)

        # session-list shows usage-0001 marked open while the session is active.
        res = self.run_operator("session-list")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("open", res.stdout)

        # --open surfaces the active session (the core blind spot this command fixes).
        res = self.run_operator("session-list", "--open")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("open", res.stdout)
        self.assertNotIn("closed", res.stdout)

        # Close it.
        res = self.run_operator(
            "session-end", "usage-0001", "--outcome", "useful", "--cost", "0.05"
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # --open now matches nothing; plain list shows the closed session.
        res = self.run_operator("session-list", "--open")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions matched the filters.", res.stdout)

        res = self.run_operator("session-list")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("closed", res.stdout)

        # Open a second session: --open must discriminate the live one from the closed one.
        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("session-list", "--open")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0002", res.stdout)
        self.assertNotIn("usage-0001", res.stdout)

        # --task filter: matching task returns both, unknown task returns none.
        res = self.run_operator("session-list", "--task", "session-list-task")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("usage-0002", res.stdout)

        res = self.run_operator("session-list", "--task", "nonexistent-task")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions matched the filters.", res.stdout)

        # --harness filter: claude matches, codex does not.
        res = self.run_operator("session-list", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)

        res = self.run_operator("session-list", "--harness", "codex")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions matched the filters.", res.stdout)

    def test_usage_add_file_payload_fidelity(self) -> None:
        import datetime

        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Verify usage payload fidelity",
            "--id",
            "payload-fidelity-task",
            "--assign",
            "copilot",
        )

        # Payload contains a "$0.00" that a shell would mangle to "bash.00" via
        # $0 expansion. The --file capture path must store it verbatim.
        payload = "Copilot Chat session.\nEstimated cost: $0.00 (Copilot flat rate subscription)."
        payload_file = Path(self.temp_dir) / "usage_payload.txt"
        payload_file.write_text(payload)

        res = self.run_operator(
            "usage-add",
            "--harness",
            "copilot",
            "--model",
            "copilot-chat",
            "--cost",
            "0.0",
            "--outcome",
            "useful",
            "--file",
            str(payload_file),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Usage record 'usage-0001' successfully added", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"
        utc_now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{utc_now_date}.yaml"
        records = yaml.safe_load(usage_file.read_text())
        rec = records[0]

        # Regression guard for the stored "bash.00" corruption.
        self.assertEqual(rec.get("raw_payload"), payload)
        self.assertIn("$0.00", rec.get("raw_payload"))
        self.assertNotIn("bash.00", rec.get("raw_payload"))

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_usage_autoimport_and_annotation(self) -> None:
        import datetime

        self.run_operator("init")

        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        op_path = Path(self.temp_dir) / ".operator"

        # Copy the pricing.yaml table so that pricing rate lookup succeeds in test environment.
        # Sourced from tests/fixtures/ (not the gitignored runtime .operator/ ledger) so the
        # suite is self-contained on a clean clone.
        shutil.copy(fixtures_dir / "pricing.yaml", op_path / "pricing.yaml")

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{today}.yaml"

        def adjust_start_time(usage_id, new_start):
            data = yaml.safe_load(usage_file.read_text())
            for r in data:
                if r.get("usage_id") == usage_id:
                    r["started_at"] = new_start
            usage_file.write_text(yaml.safe_dump(data))

        # 1. Claude import testing
        res = self.run_operator(
            "task-create",
            "--objective",
            "Test Claude import",
            "--id",
            "claude-task",
            "--repo",
            str(Path(self.temp_dir) / "project-phoenix"),
            "--assign",
            "claude",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator(
            "session-start", "--task", "claude-task", "--harness", "claude"
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        adjust_start_time("usage-0001", "2026-05-29T06:00:00Z")

        env_claude = {"OPERATOR_TEST_CLAUDE_DIR": str(fixtures_dir / "claude")}
        res = self.run_operator(
            "usage-import",
            "--harness",
            "claude",
            "--task",
            "claude-task",
            env=env_claude,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Successfully imported usage record", res.stdout)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0001")
        self.assertEqual(rec["harness_id"], "claude")
        self.assertEqual(rec["model"], "claude-opus-4-8")
        self.assertEqual(rec["metering"], "tokens")
        self.assertEqual(rec["tokens_in"], 3272)
        self.assertEqual(rec["tokens_out"], 2839)
        self.assertEqual(rec["tokens_cache_read"], 9105)
        self.assertEqual(rec["tokens_cache_write"], 12958)
        self.assertEqual(rec["activity"]["tool_calls"], 3)
        self.assertEqual(rec["activity"]["turns"], 2)
        self.assertEqual(rec["field_sources"]["tokens_in"], "auto")
        self.assertAlmostEqual(rec["cost_estimate_usd"], 0.5186, places=4)

        # 2. Codex import testing
        res = self.run_operator(
            "task-create",
            "--objective",
            "Test Codex import",
            "--id",
            "codex-task",
            "--repo",
            str(Path(self.temp_dir) / "project-phoenix"),
            "--assign",
            "codex",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator(
            "session-start", "--task", "codex-task", "--harness", "codex"
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        adjust_start_time("usage-0002", "2026-05-29T06:00:00Z")

        env_codex = {"OPERATOR_TEST_CODEX_DIR": str(fixtures_dir / "codex")}
        res = self.run_operator(
            "usage-import", "--harness", "codex", "--task", "codex-task", env=env_codex
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0002")
        self.assertEqual(rec["harness_id"], "codex")
        self.assertEqual(rec["model"], "gpt-5.5")
        self.assertEqual(rec["metering"], "tokens")
        self.assertEqual(rec["tokens_in"], 11000)
        self.assertEqual(rec["tokens_cache_read"], 4000)
        self.assertEqual(rec["tokens_out"], 800)
        self.assertEqual(rec["activity"]["turns"], 2)
        self.assertEqual(rec["activity"]["tool_calls"], 1)
        self.assertEqual(rec["cost_estimate_usd"], 0.0)

        # 3. Gemini-Agy import testing
        res = self.run_operator(
            "task-create",
            "--objective",
            "Test Gemini-Agy import",
            "--id",
            "agy-task",
            "--assign",
            "gemini-agy",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator(
            "session-start", "--task", "agy-task", "--harness", "gemini-agy"
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        adjust_start_time("usage-0003", "2026-05-29T06:00:00Z")

        env_gemini = {"OPERATOR_TEST_GEMINI_DIR": str(fixtures_dir / "gemini")}
        res = self.run_operator(
            "usage-import",
            "--harness",
            "gemini-agy",
            "--task",
            "agy-task",
            "--session-id",
            "agy-test-brain",
            env=env_gemini,
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["harness_id"], "gemini-agy")
        self.assertEqual(rec["model"], "configured-gemini-model")
        self.assertEqual(rec["metering"], "activity")
        self.assertEqual(rec["tokens_in"], None)
        self.assertEqual(rec["cost_estimate_usd"], None)
        self.assertEqual(rec["activity"]["turns"], 2)
        self.assertEqual(rec["activity"]["tool_calls"], 3)
        self.assertEqual(rec["activity"]["quota_events"], 2)

        # 4. Idempotency test
        res = self.run_operator(
            "usage-import",
            "--harness",
            "gemini-agy",
            "--task",
            "agy-task",
            "--session-id",
            "agy-test-brain",
            env=env_gemini,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        records = yaml.safe_load(usage_file.read_text())
        self.assertEqual(len(records), 3)

        # 5. Manual override / usage-annotate
        res = self.run_operator(
            "usage-annotate",
            "usage-0003",
            "--cost",
            "1.50",
            "--active-start",
            "2026-05-29T12:00:00Z",
            "--active-end",
            "2026-05-29T12:05:00Z",
            "--quota-events",
            "5",
            "--note",
            "Annotated notes",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["cost_estimate_usd"], 1.50)
        self.assertEqual(rec["activity"]["active_s"], 300)
        self.assertEqual(rec["activity"]["quota_events"], 5)
        self.assertEqual(rec["field_sources"]["cost_estimate_usd"], "manual")
        self.assertEqual(rec["field_sources"]["active_s"], "manual")
        self.assertEqual(rec["field_sources"]["quota_events"], "manual")
        self.assertEqual(rec["auto_values"]["quota_events"], 2)
        self.assertEqual(rec["raw_payload"], "Annotated notes")

        # 6. Usage summary --metering test
        res = self.run_operator("usage-summary", "--metering", "--by-harness")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("TOKENS-METERED", res.stdout)
        self.assertIn("ACTIVITY-METERED", res.stdout)
        self.assertIn("Harness ID:   claude", res.stdout)
        self.assertIn("Harness ID:   gemini-agy", res.stdout)
        self.assertIn("Turns:", res.stdout)
        self.assertIn("not cross-comparable", res.stdout)

        # 7. Doctor warnings/errors tests
        res = self.run_operator("doctor")
        self.assertIn("manual/auto divergence on quota_events", res.stdout)

    def test_verified_by_guard_integrity(self) -> None:
        import yaml

        self.run_operator("init")

        # Create task: assign=codex, review=claude
        res = self.run_operator(
            "task-create",
            "--objective",
            "Verify the guard",
            "--id",
            "guard-task",
            "--assign",
            "codex",
            "--review",
            "claude",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # Add claim
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "A test claim",
            "--gate",
            "test-gate",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        evidence_file = Path(self.temp_dir) / "test_evidence.txt"
        evidence_file.write_text("dummy evidence content")

        # 4. missing --verified-by rejected: evidence-attach --status verified (no --verified-by) -> exits non-zero, claim unchanged
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            str(evidence_file),
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn(
            "Error: --verified-by is required when setting --status", res.stderr
        )

        claim_file = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim_data = yaml.safe_load(claim_file.read_text())
        self.assertFalse(claim_data.get("verification_status"))
        self.assertIsNone(claim_data.get("verified_by"))

        # Helper helper function to set claim status/verified-by
        def update_claim(status_val, verifier):
            # We overwrite by running evidence-attach again
            return self.run_operator(
                "evidence-attach",
                "--claim",
                "claim-0001",
                "--type",
                "test_output",
                "--status",
                status_val,
                "--verified-by",
                verifier,
                str(evidence_file),
            )

        # 1. self-verify blocked by doctor: verified_by == made_by (codex) -> doctor exits 1 with Error
        res = update_claim("verified", "codex")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "[Error] claim claim-0001 is self-verified by 'codex'", res.stdout
        )

        # 3. wrong verifier warns: --verified-by gemini-agy (not review_harness claude) -> doctor warns, exits 1
        res = update_claim("verified", "gemini-agy")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "[Warning] claim claim-0001 verified by 'gemini-agy', not the task's review harness 'claude'",
            res.stdout,
        )
        self.assertNotIn("[Error] claim claim-0001 is self-verified", res.stdout)

        # 2. reviewer verify clean: --verified-by claude -> doctor clean (exit 0)
        res = update_claim("verified", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

        # 5. legacy is Info, not failure: hand-write a claim with verification_status: true and no verified_by -> doctor prints Info and exits 0
        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["verification_status"] = True
        claim_data["verification_outcome"] = "verified"
        if "verified_by" in claim_data:
            del claim_data["verified_by"]
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn(
            "[Info] Claim claim-0001 has unknown verifier (legacy claim)", res.stdout
        )

    def test_executor_identity_binding(self) -> None:
        import yaml

        self.run_operator("init")

        # 1. executor stamped: any write records executor.uid / executor.user
        res = self.run_operator(
            "task-create", "--objective", "Test executor", "--id", "exec-task"
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        task_file = Path(self.temp_dir) / ".operator" / "tasks" / "exec-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        self.assertIn("executor", task_data)
        self.assertIn("uid", task_data["executor"])
        self.assertIn("user", task_data["executor"])

        # 2. derive + match: identity map with mode: enforced
        identity_file = Path(self.temp_dir) / ".operator" / "identity.yaml"
        identity_file.write_text(
            "mode: enforced\n" "uids:\n" "  1001: gemini-agy\n" "  1002: claude\n"
        )

        # Create a claim under the task
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "Test claim",
            "--gate",
            "test-gate",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        claim_file = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        evidence_file = Path(self.temp_dir) / "test_ev.txt"
        evidence_file.write_text("ev content")

        # Simulated uid 1002 setting status verified using test override and sentinel
        env_claude = {"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"}
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence_file),
            env=env_claude,
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # Check claim verifier and executor block
        claim_data = yaml.safe_load(claim_file.read_text())
        self.assertEqual(claim_data.get("verified_by"), "claude")
        self.assertEqual(claim_data.get("executor", {}).get("uid"), 1002)

        # Doctor error when mapping is enforced but override active flag is on
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("contains write made with test-override active", res.stdout)

        # Hand-modify both claim and evidence to clear test_override_active for testing doctor mismatch checks
        claim_data["executor"]["test_override_active"] = False
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        ev_file = (
            Path(self.temp_dir)
            / ".operator"
            / "evidence"
            / "exec-task"
            / "evidence-0001.yaml"
        )
        ev_data = yaml.safe_load(ev_file.read_text())
        ev_data["executor"]["test_override_active"] = False
        with open(ev_file, "w") as f:
            yaml.safe_dump(ev_data, f)

        # Now doctor should be clean
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

        # 3. mismatch rejected: simulated uid 1001 trying to verify as claude -> error
        env_gemini = {"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"}
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence_file),
            env=env_gemini,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("does not match the executing identity", res.stderr)

        # 4. unknown uid fails closed: uid not in map -> error
        env_unknown = {"OPERATOR_TEST_UID": "9999", "OPERATOR_TEST_SENTINEL": "1"}
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence_file),
            env=env_unknown,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("is not a known identity", res.stderr)

        # 5. doctor impersonation catch: hand-write a mismatch -> Error
        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["verified_by"] = "claude"
        claim_data["verification_status"] = True
        claim_data["verification_outcome"] = "verified"
        claim_data["executor"] = {"uid": 1001, "user": "gemini-agy"}
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("verification identity mismatch", res.stdout)

        # 6. single_user honesty: mode: single_user -> warning, exit 0
        identity_file.write_text(
            "mode: single_user\n" "uids:\n" "  1001: gemini-agy\n" "  1002: claude\n"
        )
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn(
            "verification is NOT identity-enforced (single-user mode)", res.stdout
        )

        # 7. test-hook guard: a ledger write made under OPERATOR_TEST_UID without the test sentinel -> doctor Error
        env_spoof = {"OPERATOR_TEST_UID": "1002"}
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "Spoof claim",
            "--gate",
            "test-gate",
            env=env_spoof,
        )
        self.assertEqual(res.returncode, 0)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "contains write with unauthorized test-override attempt", res.stdout
        )

    def test_doctor_flags_enforcement_downgrade(self) -> None:
        # A configured identity map left in single_user mode silently accepts claims that
        # enforced mode would reject as impersonation. doctor must surface that relaxation
        # (warn-only: it stays exit 0, but the downgrade is no longer invisible).
        import yaml

        self.run_operator("init")
        self.run_operator(
            "task-create", "--objective", "Downgrade check", "--id", "dg-task"
        )
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "a claim",
            "--gate",
            "test-gate",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # Attach evidence + a clean verification (single_user is the default mode here).
        evidence_file = Path(self.temp_dir) / "ev.txt"
        evidence_file.write_text("evidence")
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence_file),
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # Configure an identity map but leave enforcement relaxed to single_user.
        identity_file = Path(self.temp_dir) / ".operator" / "identity.yaml"
        identity_file.write_text(
            "mode: single_user\nuids:\n  1001: gemini-agy\n  1002: claude\n"
        )

        claim_file = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"

        def set_executor(uid: int, user: str) -> None:
            data = yaml.safe_load(claim_file.read_text())
            data["executor"] = {"uid": uid, "user": user}
            claim_file.write_text(yaml.safe_dump(data))

        # Mismatch: executor maps to gemini-agy (uid 1001) but verified_by is claude.
        # enforced mode would reject this; single_user accepts it -> doctor must warn, exit 0.
        set_executor(1001, "gemini-agy")
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("would be REJECTED under enforced mode", res.stdout)
        self.assertIn("enforcement appears relaxed to single_user", res.stdout)

        # Control: executor maps to claude (uid 1002), matching verified_by -> no downgrade warning.
        set_executor(1002, "claude")
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertNotIn("would be REJECTED under enforced mode", res.stdout)

    def test_status_requires_claim(self) -> None:
        # A bare evidence-attach with --status but no --claim must fail closed: status is only ever
        # recorded on a claim, so without one it would silently drop, leaving the operator thinking
        # trust advanced when it did not.
        self.run_operator("init")
        self.run_operator("task-create", "--objective", "gate", "--id", "g-task")
        evidence = Path(self.temp_dir) / "ev.txt"
        evidence.write_text("evidence")

        res = self.run_operator(
            "evidence-attach",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
        )
        self.assertNotEqual(
            res.returncode, 0, "bare --status with no --claim should fail closed"
        )
        self.assertIn("--status requires --claim", res.stderr)

        # Control: the same write WITH a claim succeeds.
        self.run_operator(
            "claim-add", "--type", "test_passes", "--text", "a claim", "--gate", "g"
        )
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
        )
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_usage_lane_tagging(self) -> None:
        import datetime

        import yaml

        self.run_operator("init")
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        op_path = Path(self.temp_dir) / ".operator"
        shutil.copy(fixtures_dir / "pricing.yaml", op_path / "pricing.yaml")

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{today}.yaml"

        # 1. session-start with lane/class
        res = self.run_operator(
            "task-create", "--objective", "tagging", "--id", "t-tagging"
        )
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "session-start",
            "--task",
            "t-tagging",
            "--harness",
            "claude",
            "--lane",
            "frontier_author",
            "--class",
            "bounded",
        )
        self.assertEqual(res.returncode, 0)

        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0001")
        self.assertEqual(rec["lane"], "frontier_author")
        self.assertEqual(rec["task_class"], "bounded")
        self.assertEqual(rec.get("field_sources", {}).get("lane"), "manual")
        self.assertEqual(rec.get("field_sources", {}).get("task_class"), "manual")

        # End usage-0001 so it's not left open
        res = self.run_operator(
            "session-end",
            "usage-0001",
            "--outcome",
            "useful",
            "--cost",
            "0.0",
            "--status",
            "complete",
        )
        self.assertEqual(res.returncode, 0)

        # 2. usage-add with lane/class
        payload_file = Path(self.temp_dir) / "payload.txt"
        payload_file.write_text("dummy usage payload")
        res = self.run_operator(
            "usage-add",
            "--harness",
            "gemini-agy",
            "--task",
            "t-tagging",
            "--lane",
            "local",
            "--class",
            "bounded",
            "--cost",
            "0.0",
            "--file",
            str(payload_file),
        )
        self.assertEqual(res.returncode, 0)

        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0002")
        self.assertEqual(rec["lane"], "local")
        self.assertEqual(rec["task_class"], "bounded")

        # 3. usage-import heuristics
        # Create a task for claude-import
        res = self.run_operator(
            "task-create", "--objective", "claude-imp", "--id", "claude-task"
        )
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "session-start", "--task", "claude-task", "--harness", "claude"
        )
        self.assertEqual(res.returncode, 0)

        # Update started_at of usage-0003 so that autoimport matches it
        data = yaml.safe_load(usage_file.read_text())
        for r in data:
            if r["usage_id"] == "usage-0003":
                r["started_at"] = "2026-05-29T06:00:00Z"
        usage_file.write_text(yaml.safe_dump(data))

        env_claude = {"OPERATOR_TEST_CLAUDE_DIR": str(fixtures_dir / "claude")}
        res = self.run_operator(
            "usage-import",
            "--harness",
            "claude",
            "--task",
            "claude-task",
            env=env_claude,
        )
        self.assertEqual(res.returncode, 0)

        # Set task status to complete to avoid doctor consistency warning (since session is closed)
        task_file = op_path / "tasks" / "claude-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        task_data["status"] = "complete"
        task_file.write_text(yaml.safe_dump(task_data))

        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["lane"], "frontier_driver")
        self.assertEqual(rec["task_class"], "unknown")
        self.assertEqual(rec.get("field_sources", {}).get("lane"), "auto")
        self.assertEqual(rec.get("field_sources", {}).get("task_class"), "auto")

        # 4. usage-annotate override
        res = self.run_operator(
            "usage-annotate", "usage-0003", "--lane", "local", "--class", "hard"
        )
        self.assertEqual(res.returncode, 0)
        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["lane"], "local")
        self.assertEqual(rec["task_class"], "hard")
        self.assertEqual(rec.get("field_sources", {}).get("lane"), "manual")
        self.assertEqual(rec.get("field_sources", {}).get("task_class"), "manual")

        # 5. usage-summary --by-lane
        # Let's add another frontier_driver + bounded record to verify avoidable rollup and offload audit
        res = self.run_operator(
            "usage-add",
            "--harness",
            "codex",
            "--task",
            "t-tagging",
            "--lane",
            "frontier_driver",
            "--class",
            "bounded",
            "--cost",
            "1.50",
            "--file",
            str(payload_file),
        )
        self.assertEqual(res.returncode, 0)

        res = self.run_operator("usage-summary", "--by-lane")
        self.assertEqual(res.returncode, 0)
        self.assertIn("SUMMARY BY LANE × TASK_CLASS", res.stdout)
        self.assertIn("Lane:         frontier_author", res.stdout)
        self.assertIn("Task Class:   bounded", res.stdout)
        self.assertIn("Lane:         frontier_driver", res.stdout)
        self.assertIn("Avoidable Rollup Cost:", res.stdout)

        # 6. usage-summary --offload-audit
        # usage-0001 (frontier_author, bounded, cost 0.0) -> avoidable
        # usage-0002 (local, bounded, cost 0.0) -> ignored (starts with local)
        # usage-0003 (local, hard, cost 0.5186) -> ignored
        # usage-0004 (frontier_driver, bounded, cost 1.50) -> avoidable
        # Total frontier spend: usage-0001 ($0.0) + usage-0004 ($1.5) = $1.50
        # Avoidable spend: usage-0001 ($0.0) + usage-0004 ($1.5) = $1.50 (100.0%)
        res = self.run_operator("usage-summary", "--offload-audit")
        self.assertEqual(res.returncode, 0)
        self.assertIn("100.0% of frontier spend went to bounded work", res.stdout)

        # 7. doctor advisory check
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0)
        self.assertIn("is an offload candidate", res.stdout)


if __name__ == "__main__":
    unittest.main()
