#!/usr/bin/env python3
"""Unit tests for task_lint.py -- LOCAL_LANE_CONTRACT.md R1-R6."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from task_lint import (  # noqa: E402
    check_r1_exact_paths,
    check_r2_anchored_edits,
    check_r3_one_tool_call_per_step,
    check_r4_success_criterion,
    check_r5_closed_vocabulary,
    check_r6_bounded_scope,
    lint,
)


# ---------------------------------------------------------------------------
# Evidence prompts from LOCAL_LANE_CONTRACT_SPEC.md's Evidence section /
# eval-ladder L0-L2 examples. These are the acceptance-criterion-1 cases.
# ---------------------------------------------------------------------------

L0_GOAL_SHAPED = (
    "Please change my alias file. Add 200 for sudo nvidia-smi -pl 200 to it."
)

L1_FILE_NAMED = (
    "Add an alias 200 for sudo nvidia-smi -pl 200 to my alias file, "
    "in bash/.bash_aliases."
)

L2_PLAN_SHAPED = (
    "1. In bash/.bash_aliases, after the line "
    "\"alias nv='nvidia-smi'\", add a new line "
    "\"alias 200='sudo nvidia-smi -pl 200'\".\n"
    "2. Verify the file now contains the line "
    "\"alias 200='sudo nvidia-smi -pl 200'\".\n"
    "Only touch bash/.bash_aliases."
)


class EvidencePromptTests(unittest.TestCase):
    """Acceptance criterion 1: the evidence prompts land in the right buckets."""

    def test_l0_goal_shaped_prompt_is_goal_shaped(self):
        result = lint(L0_GOAL_SHAPED)
        self.assertEqual(result.overall, "goal-shaped")

    def test_l1_file_named_prompt_is_at_least_semi_shaped(self):
        result = lint(L1_FILE_NAMED)
        self.assertIn(result.overall, ("semi-shaped", "plan-shaped"))
        # R1 in particular must pass now that a path is named -- this is
        # the axis that separates L0 from L1.
        r1 = next(r for r in result.rules if r.rule == "R1")
        self.assertEqual(r1.verdict, "PASS")

    def test_l2_plan_shaped_prompt_is_plan_shaped(self):
        result = lint(L2_PLAN_SHAPED)
        self.assertEqual(result.overall, "plan-shaped")


# ---------------------------------------------------------------------------
# R1 -- exact paths
# ---------------------------------------------------------------------------

class R1Tests(unittest.TestCase):
    PASS_CASES = [
        "Edit bash/.bash_aliases to add a new line.",
        "Update `core/tool_registry.py` to register the tool.",
        "Change config.yaml key debug to true.",
        "Modify README.md at line 10.",
        "Patch operator-control-plane/operator near line 500.",
        "Read data/bundle.json and report the count.",
        "In charter/gate.py, replace the year check.",
        "Append a line to notes.txt.",
        "Edit tests/test_tools.py to add a test.",
        "Create a new file scripts/deploy.sh.",
    ]
    FAIL_CASES = [
        "Please change my alias file.",
        "Update the config appropriately.",
        "Fix the bug in the file.",
        "Edit the settings.",
        "Add a new alias to my dotfiles.",
        "Change the readme.",
        "Update my configuration.",
        "Patch the script.",
        "Modify the registry.",
        "Fix the file that handles auth.",
    ]

    def test_pass_cases(self):
        for text in self.PASS_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r1_exact_paths(text).verdict, "PASS")

    def test_fail_cases(self):
        for text in self.FAIL_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r1_exact_paths(text).verdict, "FAIL")


# ---------------------------------------------------------------------------
# R2 -- anchored edits
# ---------------------------------------------------------------------------

class R2Tests(unittest.TestCase):
    PASS_CASES = [
        "Replace the line \"alias nv='nvidia-smi'\" with the same line plus a new alias.",
        "Add a new alias after the line `alias nv='nvidia-smi'`.",
        "Insert the following after the line containing `import os`.",
        "Append at end of file a new function foo().",
        "Patch the anchor 'def old_function():' to rename it.",
        "Change \"debug\": false to \"debug\": true.",
        "Update the block after the line `# CONFIG START`.",
        "Insert a new key at the end of the file.",
        "Replace the text \"TODO: fix this\" with the implementation.",
        "Read the file and report its contents.",  # no edit-verb -> vacuous PASS
    ]
    FAIL_CASES = [
        "Add a new alias to the file.",
        "Change the function appropriately.",
        "Replace the old value with the new one.",
        "Update the config.",
        "Insert a new line somewhere reasonable.",
        "Patch the bug.",
        "Modify the registry to add the tool.",
        "Append the new setting.",
        "Edit the function to fix it.",
        "Remove the old alias.",
    ]

    def test_pass_cases(self):
        for text in self.PASS_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r2_anchored_edits(text).verdict, "PASS")

    def test_fail_cases(self):
        for text in self.FAIL_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r2_anchored_edits(text).verdict, "FAIL")


# ---------------------------------------------------------------------------
# R3 -- one tool call per step
# ---------------------------------------------------------------------------

class R3Tests(unittest.TestCase):
    PASS_CASES = [
        "1. Open the file.\n2. Add the line.\n3. Save it.",
        "- Open the file\n- Add the line\n- Save it",
        "Run the tests.",  # single action, no ambiguity
        "Check the output.",
        "1. Read config.yaml\n2. Verify the key exists",
        "* Step one\n* Step two",
        "Append the line.",
        "Create the file.",
        "1) First step\n2) Second step",
        "Delete the temp directory.",
    ]
    WARN_CASES = [
        "Add the alias and verify it works.",
        "Change the config and update the README to match, then run the tests.",
        "Patch the file and create a backup and check the output.",
        "Insert the new function and remove the old one.",
        "Update the registry, append the changelog entry, and verify the build.",
    ]

    def test_pass_cases(self):
        for text in self.PASS_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r3_one_tool_call_per_step(text).verdict, "PASS")

    def test_warn_cases(self):
        for text in self.WARN_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r3_one_tool_call_per_step(text).verdict, "WARN")


# ---------------------------------------------------------------------------
# R4 -- explicit success criterion
# ---------------------------------------------------------------------------

class R4Tests(unittest.TestCase):
    PASS_CASES = [
        "Add the line. The file should now contain the new alias.",
        "Run the command. It should exit 0.",
        "Patch the function, then verify the change.",
        "The test suite should now contain a passing case for this input.",
        "Confirm that the output matches the expected value.",
        "After editing, verify the config parses cleanly.",
        "The command should return a non-empty list.",
        "Check that `pytest` exits with exit code 0.",
        "The build should output 'success' on the last line.",
        "Edit the file; it now contains the corrected value.",
    ]
    FAIL_CASES = [
        "Add a new alias to bash/.bash_aliases.",
        "Update core/tool_registry.py to register the tool.",
        "Fix the bug in charter/gate.py.",
        "Change the year range in PPR_Agent.pbc.md.",
        "Edit README.md to correct the command.",
        "Patch tests/test_tools.py.",
        "Insert the new function in core/agentic_engine.py.",
        "Remove the deprecated flag from ppr.",
        "Append the entry to CHANGELOG.md.",
        "Modify desk/index.html to add the badge.",
    ]

    def test_pass_cases(self):
        for text in self.PASS_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r4_success_criterion(text).verdict, "PASS")

    def test_fail_cases(self):
        for text in self.FAIL_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r4_success_criterion(text).verdict, "FAIL")


# ---------------------------------------------------------------------------
# R5 -- imperative, closed vocabulary
# ---------------------------------------------------------------------------

class R5Tests(unittest.TestCase):
    PASS_CASES = [
        "Add the line after the anchor.",
        "Replace the value with 200.",
        "Run pytest and check the exit code.",
        "Insert the function before the class definition.",
        "Delete the temp directory.",
        "Update the README to match the new flag name.",
        "Append the entry to the changelog.",
        "Patch the config to set debug to true.",
        "Verify the output contains the expected string.",
        "Create scripts/deploy.sh with the given contents.",
    ]
    FAIL_CASES = [
        "Figure out where the bug is and fix it.",
        "Update the config appropriately.",
        "Add aliases as needed.",
        "Somehow make the tests pass.",
        "Fix the imports, error handling, etc.",
        "Handle this however you think is best.",
        "Clean up the file as needed.",
        "The exact approach is up to you.",
        "Refactor appropriately for readability.",
        "Do whatever is needed to fix the bug, etc.",
    ]

    def test_pass_cases(self):
        for text in self.PASS_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r5_closed_vocabulary(text).verdict, "PASS")

    def test_fail_cases(self):
        for text in self.FAIL_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r5_closed_vocabulary(text).verdict, "FAIL")


# ---------------------------------------------------------------------------
# R6 -- bounded scope
# ---------------------------------------------------------------------------

class R6Tests(unittest.TestCase):
    PASS_CASES = [
        "Edit bash/.bash_aliases. Only touch this file.",
        "Update core/tool_registry.py and tests/test_tools.py. Only modify the files listed.",
        "Patch charter/gate.py. Do not touch any other files.",
        "Edit README.md. No other files should change.",
        "Modify desk/index.html only.",
        "Edit a.py.",  # single unique path
        "Edit a.py and b.py and c.py.",  # all unique
        "Update config.yaml. Only the files listed may change.",
        "Patch charter/gate.py near line 30.",
        "Create scripts/deploy.sh.",
    ]
    WARN_CASES = [
        "Edit a.py, then edit a.py again for a different section.",
        "Fix the config.",  # no path, no clause
        "Update the registry appropriately.",
        "Patch the same file (config.yaml) twice for two different keys, editing config.yaml both times.",
        "Do the necessary changes.",
    ]

    def test_pass_cases(self):
        for text in self.PASS_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r6_bounded_scope(text).verdict, "PASS")

    def test_warn_cases(self):
        for text in self.WARN_CASES:
            with self.subTest(text=text):
                self.assertEqual(check_r6_bounded_scope(text).verdict, "WARN")


# ---------------------------------------------------------------------------
# Overall verdict logic
# ---------------------------------------------------------------------------

class OverallVerdictTests(unittest.TestCase):
    def test_r1_fail_forces_goal_shaped_even_if_other_rules_pass(self):
        text = "Run the tests. Verify they exit 0."  # R1 fails: no path
        result = lint(text)
        r1 = next(r for r in result.rules if r.rule == "R1")
        self.assertEqual(r1.verdict, "FAIL")
        self.assertEqual(result.overall, "goal-shaped")

    def test_all_pass_is_plan_shaped(self):
        result = lint(L2_PLAN_SHAPED)
        self.assertTrue(all(r.verdict == "PASS" for r in result.rules))
        self.assertEqual(result.overall, "plan-shaped")

    def test_exit_codes(self):
        self.assertEqual(lint(L2_PLAN_SHAPED).exit_code(), 0)
        self.assertEqual(lint(L1_FILE_NAMED).exit_code(), 1)
        self.assertEqual(lint(L0_GOAL_SHAPED).exit_code(), 2)


if __name__ == "__main__":
    unittest.main()
