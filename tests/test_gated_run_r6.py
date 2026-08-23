#!/usr/bin/env python3
import unittest
import tempfile
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import gated_runner
from gated_runner import OutcomeRecord

class TestGatedRunnerR6(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.artifact = self.root / "artifact.txt"
        self.artifact.write_text("initial content")
        
        self.cell = gated_runner.Cell(
            cell_id="test-task",
            objective="test obj",
            brief="test brief",
            workspace=str(self.root),
            gate=gated_runner.Gate(command=["echo", "ok"], expect="ok")
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_run_invocation_produces_outcome_record(self):
        """Assert a completed invocation produces an OutcomeRecord."""
        def action():
            return 1, "success"
        
        record = gated_runner.run_invocation(
            cell=self.cell,
            harness="test-harness",
            model="test-model",
            action_callback=action,
            artifact_path=self.artifact
        )
        self.assertIsInstance(record, OutcomeRecord)

    def test_outcome_record_has_all_fields(self):
        """Assert the outcome record contains every required field."""
        def action():
            return 5, "success"
        
        record = gated_runner.run_invocation(
            cell=self.cell,
            harness="test-harness",
            model="test-model",
            action_callback=action,
            artifact_path=self.artifact
        )
        
        # Check all fields’ presence and basic values
        self.assertEqual(record.task_id, "test-task")
        self.assertEqual(record.harness, "test-harness")
        self.assertEqual(record.model, "test-model")
        self.assertEqual(record.declared_artifact, str(self.artifact))
        self.assertIsInstance(record.wall_clock, float)
        self.assertEqual(record.tool_call_count, 5)
        self.assertEqual(record.exit_cause, "success")
        self.assertIsInstance(record.gate_verdict, str)
        self.assertIsInstance(record.artifact_hash_changed, bool)
        self.assertIsInstance(record.timestamp, float)

    def test_timeout_exit_cause_captured(self):
        """Assert that a timed-out invocation produces exit_cause: timeout."""
        def action():
            return 0, "timeout"
        
        record = gated_runner.run_invocation(
            cell=self.cell,
            harness="test-harness",
            model="test-model",
            action_callback=action,
            artifact_path=self.artifact
        )
        self.assertEqual(record.exit_cause, "timeout")

    def test_persistence_to_disk(self):
        """Assert that outcome records are persisted to disk when storage_dir is provided."""
        storage_dir = self.root / "outcomes"
        def action():
            return 1, "success"
        
        record = gated_runner.run_invocation(
            cell=self.cell,
            harness="test-harness",
            model="test-model",
            action_callback=action,
            artifact_path=self.artifact,
            storage_dir=storage_dir
        )
        
        # Verify file exists
        files = list(storage_dir.glob("outcome-*.json"))
        self.assertEqual(len(files), 1)
        
        # Verify content
        with open(files[0], "r") as f:
            data = json.load(f)
            self.assertEqual(data["task_id"], "test-task")
            self.assertEqual(data["exit_cause"], "success")

if __name__ == "__main__":
    unittest.main()
