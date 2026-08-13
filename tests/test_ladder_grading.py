"""Grader and trajectory capabilities added for the ceiling battery.

The existing three fixtures saturated at 14B and above (62/63 in e4-sampled,
126/126 in e7), and the grader is why: one literal-substring check per task caps
every fixture at a one-line edit. These tests cover the additions that lift that
cap -- composed checks, regex, AST symbol lookup, occurrence counting, scope
enforcement -- plus the trajectory parse.

Scope enforcement is the one that closes a real hole rather than adding reach:
LOCAL_LANE_CONTRACT R6 says "the task enumerates every file that may be touched",
but nothing ever checked it, so a model that made the required edit *and*
clobbered README.md scored identically to one that stayed in bounds.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "evals" / "local_lane_ladder"))

import fixtures  # noqa: E402
import grading  # noqa: E402
import runner  # noqa: E402


class GraderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / "src").mkdir()
        (self.root / "notes.md").write_text("alpha\nbeta\nalpha\nalpha\n", encoding="utf-8")
        (self.root / "src" / "m.py").write_text(
            "def square(n: int) -> int:\n    return n * n\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _g(self, pc, manifest=None):
        return grading.grade(pc, self.root, "", manifest)

    # --- composition ---------------------------------------------------

    def test_all_of_passes_when_every_check_passes(self) -> None:
        r = self._g({
            "type": "all_of",
            "checks": [
                {"type": "grep", "file": "notes.md", "pattern": "beta"},
                {"type": "python_symbol", "file": "src/m.py", "symbol": "square"},
            ],
        })
        self.assertTrue(r.passed)
        self.assertEqual(len(r.checks), 2)
        self.assertEqual(r.score, 1.0)

    def test_all_of_reports_partial_credit(self) -> None:
        """A partially-correct answer must be distinguishable from a total miss;
        that distinction is the whole reason for composing checks."""
        r = self._g({
            "type": "all_of",
            "checks": [
                {"type": "grep", "file": "notes.md", "pattern": "beta"},
                {"type": "grep", "file": "notes.md", "pattern": "gamma"},
            ],
        })
        self.assertFalse(r.passed)
        self.assertEqual(r.score, 0.5)
        self.assertIn("1/2 checks failed", r.detail)

    # --- reach ---------------------------------------------------------

    def test_python_symbol_survives_type_annotations(self) -> None:
        """`grep "def square(n):"` fails on an annotated signature that is the
        same function -- the false negative AST lookup exists to remove."""
        self.assertTrue(self._g({
            "type": "python_symbol", "file": "src/m.py", "symbol": "square", "args": ["n"],
        }).passed)

    def test_python_symbol_reports_unparseable_file(self) -> None:
        (self.root / "src" / "bad.py").write_text("def broken(\n", encoding="utf-8")
        r = self._g({"type": "python_symbol", "file": "src/bad.py", "symbol": "broken"})
        self.assertFalse(r.passed)
        self.assertIn("does not parse", r.detail)

    def test_regex_and_forbidden_regex(self) -> None:
        self.assertTrue(self._g({
            "type": "regex", "file": "src/m.py", "pattern": r"def\s+square\s*\(",
        }).passed)
        r = self._g({
            "type": "regex", "file": "src/m.py",
            "pattern": r"def\s+square", "must_not_match": r"return\s+n\s*\*\s*n",
        })
        self.assertFalse(r.passed)
        self.assertIn("forbidden regex matched", r.detail)

    def test_grep_occurrence_count(self) -> None:
        """Ambiguous-anchor fixtures need 'changed exactly one of three', which
        is a count assertion rather than a substring assertion."""
        self.assertTrue(self._g({
            "type": "grep", "file": "notes.md", "pattern": "alpha", "count": 3,
        }).passed)
        r = self._g({"type": "grep", "file": "notes.md", "pattern": "alpha", "count": 1})
        self.assertFalse(r.passed)
        self.assertIn("expected 1 occurrence", r.detail)

    # --- scope (R6) ----------------------------------------------------

    def test_scope_clean_when_only_allowed_file_changed(self) -> None:
        manifest = fixtures.hash_tree(self.root)
        (self.root / "notes.md").write_text("edited\n", encoding="utf-8")
        self.assertTrue(
            self._g({"type": "files_unchanged", "allowed": ["notes.md"]}, manifest).passed
        )

    def test_scope_detects_modification_creation_and_deletion(self) -> None:
        manifest = fixtures.hash_tree(self.root)
        (self.root / "src" / "m.py").write_text("clobbered\n", encoding="utf-8")
        (self.root / "extra.txt").write_text("new\n", encoding="utf-8")
        (self.root / "notes.md").unlink()
        r = self._g({"type": "files_unchanged", "allowed": []}, manifest)
        self.assertFalse(r.passed)
        self.assertIn("modified out of scope", r.detail)
        self.assertIn("created out of scope", r.detail)
        self.assertIn("deleted out of scope", r.detail)

    def test_scope_fails_closed_without_a_manifest(self) -> None:
        """Silently skipping the check would make an unenforced run look
        identical to an enforced one -- the same ambiguity that hid the
        trace-retention gap."""
        r = self._g({"type": "files_unchanged", "allowed": []}, None)
        self.assertFalse(r.passed)
        self.assertIn("requires a fixture manifest", r.detail)

    def test_rewrite_with_identical_content_is_not_a_violation(self) -> None:
        """R6 is about the resulting tree, not write syscalls."""
        manifest = fixtures.hash_tree(self.root)
        (self.root / "src" / "m.py").write_text(
            "def square(n: int) -> int:\n    return n * n\n", encoding="utf-8"
        )
        self.assertTrue(self._g({"type": "files_unchanged", "allowed": []}, manifest).passed)

    # --- fixture building ----------------------------------------------

    def test_build_fixture_supports_executable_mode(self) -> None:
        root = fixtures.build_fixture(
            {"bin/go.sh": {"content": "#!/bin/sh\ntrue\n", "mode": 0o755}}, prefix="modes"
        )
        try:
            import os
            import stat
            self.assertTrue(os.access(root / "bin/go.sh", os.X_OK))
            self.assertEqual(stat.S_IMODE((root / "bin/go.sh").stat().st_mode), 0o755)
            self.assertEqual((root / "README.md").read_text().count("\n") > 0, True)
        finally:
            fixtures.cleanup_fixture(root)

    def test_exec_timeout_is_configurable(self) -> None:
        r = self._g({"type": "exec", "command": "sleep 5", "timeout": 1})
        self.assertFalse(r.passed)
        self.assertIn("timed out after 1s", r.detail)


class TrajectoryParseTest(unittest.TestCase):
    SUCCESS = (
        "Routing task to: m (lane_1_local_repair)\n"
        "[tokens] prompt=10 completion=84 think_chars=0 done_reason=stop\n"
        "[Model requests tool call: read_file]\n"
        'Arguments: {\n  "tool": "read_file",\n  "path": "a.txt"\n}\n'
        "[Tool Output]\nhello\n"
        "[Model requests tool call: patch_file]\n"
        'Arguments: {\n  "tool": "patch_file",\n  "path": "a.txt"\n}\n'
        "[Tool Output]\nSuccessfully patched a.txt.\n"
    )

    def test_orders_and_counts_calls(self) -> None:
        t = runner.parse_trajectory(self.SUCCESS)
        self.assertEqual([c["tool"] for c in t["tool_calls"]], ["read_file", "patch_file"])
        self.assertEqual([c["path"] for c in t["tool_calls"]], ["a.txt", "a.txt"])
        self.assertEqual(t["n_calls"], 2)
        self.assertEqual(t["n_failed_calls"], 0)
        self.assertEqual(t["completion_tokens"], 84)

    def test_retains_failed_calls_rather_than_dropping_them(self) -> None:
        """The Alignerr rule is that discarded candidates are named with a
        reason, not silently omitted. A wrong-path attempt is exactly that."""
        s = (
            "[Model requests tool call: patch_file]\n"
            'Arguments: {"tool": "patch_file", "path": ".bash_aliases"}\n'
            "[Tool Output]\nError: File not found: .bash_aliases\n"
        )
        t = runner.parse_trajectory(s)
        self.assertEqual(t["n_failed_calls"], 1)
        self.assertFalse(t["tool_calls"][0]["ok"])
        self.assertIn("File not found", t["tool_calls"][0]["error"])

    def test_flags_the_two_harness_terminations(self) -> None:
        self.assertTrue(runner.parse_trajectory(
            "[Stopped: model repeated an already-handled tool call 'read_file: a']"
        )["stopped_repeat"])
        self.assertTrue(runner.parse_trajectory(
            "[No tool dispatched: response carried tool-shaped JSON]"
        )["no_dispatch"])

    def test_tolerates_prose_only_output(self) -> None:
        """A trajectory parse must never be able to fail a cell the
        postcondition already graded."""
        t = runner.parse_trajectory("The file already contains that line.")
        self.assertEqual(t["n_calls"], 0)
        self.assertEqual(t["tool_calls"], [])


if __name__ == "__main__":
    unittest.main()
