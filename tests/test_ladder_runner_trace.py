"""Trace retention for the local-lane ladder runner (GOLD_STANDARD.md rule 4).

The pre-890d595 confound was that 88 negatives could not be distinguished from
harness truncation because no output was kept. So the property under test is
not "traces exist" but "traces exist *for failures and timeouts too*" -- a
harness that only retains output for passes reproduces the original defect.

These tests stub the opr subprocess, so they run without a model or a GPU.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "evals" / "local_lane_ladder"))

import runner  # noqa: E402


def _alias_add_task() -> dict:
    tasks = runner.load_tasks(["alias-add"])
    assert tasks, "alias-add task definition not found"
    return tasks[0]


class LadderRunnerTraceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.trace_dir = Path(self._tmp.name) / "traces"
        self.task = _alias_add_task()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _run(self, trace_dir: Path | None) -> dict:
        return runner.run_trial(
            self.task, "L2", "fake-model:1b", 1,
            ledger_dir=REPO_ROOT, use_ledger=False, trace_dir=trace_dir,
        )

    def _sole_trace(self) -> dict:
        files = sorted(self.trace_dir.glob("*.json"))
        self.assertEqual(len(files), 1, f"expected exactly one trace, got {files}")
        return json.loads(files[0].read_text(encoding="utf-8"))

    def test_failing_cell_still_retains_stdout(self) -> None:
        """A graded FAIL must keep the model output that explains the failure."""
        fake = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="model rambled and edited nothing", stderr="warn: x",
        )
        with mock.patch.object(runner.subprocess, "run", return_value=fake):
            record = self._run(self.trace_dir)

        self.assertFalse(record["passed"], "fixture was untouched, so grading must fail")
        trace = self._sole_trace()
        self.assertFalse(trace["passed"])
        self.assertFalse(trace["timed_out"])
        self.assertEqual(trace["stdout"], "model rambled and edited nothing")
        self.assertEqual(trace["stderr"], "warn: x")
        self.assertEqual(trace["cell_key"], "alias-add|L2|fake-model:1b|1")
        # opr-era argv asserted --eval-auto-confirm. pi has no such flag; the
        # invariants that matter under this backend are the JSON event stream
        # the trajectory parser consumes and non-interactive execution.
        self.assertIn("--mode", trace["argv"])
        self.assertIn("json", trace["argv"])
        self.assertIn("--print", trace["argv"])
        self.assertTrue(trace["prompt"].strip(), "prompt must be recorded for reproducibility")

    def test_timeout_retains_partial_output(self) -> None:
        """Partial output from a killed cell is the most diagnostic trace there is."""
        timeout_exc = subprocess.TimeoutExpired(
            cmd=["opr"], timeout=runner.MAX_WALL_CLOCK_SECONDS,
            output=b"got halfway then stalled", stderr=b"",
        )
        with mock.patch.object(runner.subprocess, "run", side_effect=timeout_exc):
            record = self._run(self.trace_dir)

        self.assertFalse(record["passed"])
        self.assertIsNone(record["returncode"])
        trace = self._sole_trace()
        self.assertTrue(trace["timed_out"])
        self.assertEqual(trace["stdout"], "got halfway then stalled")
        self.assertEqual(trace["timeout_limit_s"], runner.MAX_WALL_CLOCK_SECONDS)

    def test_passing_cell_retains_tool_activity(self) -> None:
        tool_log = "[Model requests tool call: patch_file]\n[Tool Output]\nSuccessfully patched."
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout=tool_log, stderr="")
        with mock.patch.object(runner.subprocess, "run", return_value=fake):
            self._run(self.trace_dir)
        self.assertIn("tool call", self._sole_trace()["stdout"])

    def test_no_trace_dir_is_a_no_op(self) -> None:
        """Default behaviour must be byte-identical to the pre-change runner."""
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="x", stderr="")
        with mock.patch.object(runner.subprocess, "run", return_value=fake):
            record = self._run(None)
        self.assertNotIn("trace", record)
        self.assertFalse(self.trace_dir.exists())

    def test_trace_write_failure_propagates(self) -> None:
        """Fails closed: main() must be able to abort rather than record an
        untraced cell, which state.json could not distinguish afterwards."""
        blocker = Path(self._tmp.name) / "blocked"
        blocker.write_text("not a directory", encoding="utf-8")
        fake = subprocess.CompletedProcess(args=[], returncode=0, stdout="x", stderr="")
        with mock.patch.object(runner.subprocess, "run", return_value=fake):
            with self.assertRaises(OSError):
                self._run(blocker / "traces")


if __name__ == "__main__":
    unittest.main()
