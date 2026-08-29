"""Alignerr trajectory scoring and the failure taxonomy.

The scorer never gates a cell -- the deterministic postcondition does. These
tests pin that separation, the rule mappings, and the not-applicable semantics
that keep a task author's choices from being scored as a model's behaviour.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "evals" / "local_lane_ladder"))

from trajectory_score import classify_failure, score_trajectory


def traj(calls, **kw):
    base = {
        "tool_calls": calls,
        "n_calls": len(calls),
        "n_failed_calls": sum(1 for c in calls if not c.get("ok", True)),
        "stopped_repeat": False,
        "no_dispatch": False,
    }
    base.update(kw)
    return base


def call(tool, path, ok=True):
    return {"tool": tool, "path": path, "ok": ok, "error": None}


SINGLE = {"files": {"a.py": "x"}}
MULTI = {"files": {"a.py": "x", "b.py": "y", "tests/t.py": "z"}, "state_changes": 5}


class TrajectoryScoreTest(unittest.TestCase):
    def test_read_before_write_is_satisfied(self) -> None:
        s = score_trajectory(traj([call("read_file", "a.py"), call("patch_file", "a.py")]), SINGLE)
        self.assertIs(s.rules["read_before_write"], True)

    def test_blind_patch_is_flagged(self) -> None:
        """Batch 5's anti-anchoring rule: derive from the source rather than
        from what you assume is there."""
        s = score_trajectory(traj([call("patch_file", "a.py")]), SINGLE)
        self.assertIs(s.rules["read_before_write"], False)
        self.assertIn("patched without reading", s.notes[0])

    def test_multi_source_task_requires_reading_every_source(self) -> None:
        partial = traj([call("read_file", "a.py"), call("patch_file", "a.py")])
        self.assertIs(score_trajectory(partial, MULTI).rules["all_sources_read"], False)
        full = traj([
            call("read_file", "a.py"), call("read_file", "b.py"),
            call("patch_file", "a.py"), call("patch_file", "b.py"),
        ])
        self.assertIs(score_trajectory(full, MULTI).rules["all_sources_read"], True)

    def test_single_source_task_does_not_score_that_rule(self) -> None:
        """A rule that cannot apply must be None, not False -- otherwise the
        task author's choice is charged to the model."""
        s = score_trajectory(traj([call("read_file", "a.py"), call("patch_file", "a.py")]), SINGLE)
        self.assertIsNone(s.rules["all_sources_read"])
        self.assertIsNone(s.rules["min_steps"])

    def test_repeat_guard_stop_is_a_violation(self) -> None:
        s = score_trajectory(traj([call("read_file", "a.py")], stopped_repeat=True), SINGLE)
        self.assertIs(s.rules["no_blind_repeat"], False)

    def test_score_is_fraction_of_applicable_rules(self) -> None:
        s = score_trajectory(traj([call("patch_file", "a.py")], stopped_repeat=True), SINGLE)
        # applicable: read_before_write (F), no_blind_repeat (F), single_action (T)
        self.assertEqual(s.applicable, 3)
        self.assertEqual(s.satisfied, 1)
        self.assertAlmostEqual(s.score, 1 / 3, places=2)

    def test_perfect_multi_file_trajectory_scores_one(self) -> None:
        s = score_trajectory(traj([
            call("read_file", "a.py"), call("read_file", "b.py"),
            call("patch_file", "a.py"), call("patch_file", "b.py"),
            call("run_command", None),
        ]), MULTI)
        self.assertEqual(s.score, 1.0)
        self.assertEqual(s.notes, [])


class FailureTaxonomyTest(unittest.TestCase):
    def test_infra_is_read_from_stdout_not_from_grader_detail(self) -> None:
        """Regression. An early version matched "connection" against the
        grader's detail, which quotes fixture content -- so all 19
        ambiguous-anchor failures were misfiled as INFRA because that fixture's
        runbook says "Drain connections." They are ordinary model failures.
        """
        rec = {"detail": "regex did not match: '## Production\\n1. Drain connections.'",
               "returncode": 0}
        self.assertEqual(classify_failure(rec, traj([]), stdout="model output"), "MODEL_FAILURE")

    def test_genuine_infra_is_detected(self) -> None:
        rec = {"detail": "pattern not found", "returncode": 0}
        self.assertEqual(
            classify_failure(rec, traj([]), stdout="Ollama API Error: connection refused"),
            "INFRA",
        )

    def test_timeout_and_protocol(self) -> None:
        self.assertEqual(
            classify_failure({"detail": "timed out after 600s", "returncode": None}, traj([])),
            "TIMEOUT",
        )
        self.assertEqual(
            classify_failure({"detail": "pattern not found", "returncode": 0},
                             traj([], no_dispatch=True)),
            "HARNESS_PROTOCOL",
        )


if __name__ == "__main__":
    unittest.main()
