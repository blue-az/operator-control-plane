"""Repair-task negative controls and known-good positive controls; no models."""
from __future__ import annotations

import copy
import unittest
from pathlib import Path
from unittest.mock import patch

import runner
from fixtures import build_fixture, cleanup_fixture, hash_tree
from grading import grade

TASK_IDS = ["booking-off-by-one", "ambiguous-anchor", "constant-and-callers",
            "csv-summarize-repair", "strict-log-format"]


def apply_known_fix(task: dict, root: Path) -> None:
    def replace(path, old, new):
        target = root / path
        text = target.read_text()
        assert old in text
        target.write_text(text.replace(old, new))

    if task["task_id"] == "booking-off-by-one":
        replace("src/bookings.py", "start1 <= end2 and start2 <= end1", "start1 < end2 and start2 < end1")
    elif task["task_id"] == "ambiguous-anchor":
        replace("runbook.md", "## Staging\n1. Drain connections.\n2. Run: restart the service\n",
                "## Staging\n1. Drain connections.\n2. Run: restart the service --force\n")
    elif task["task_id"] == "constant-and-callers":
        replace("src/limits.py", "MAX_RETRIES = 3", "MAX_RETRIES = 5")
        for name in ("src/fetcher.py", "docs/retry_policy.md"):
            replace(name, "up to 3 times", "up to 5 times")
    elif task["task_id"] == "csv-summarize-repair":
        (root / "src/expenses.py").write_text('''import csv
import io
from decimal import Decimal

def summarize_expenses(csv_text):
    totals = {}
    for row in csv.DictReader(io.StringIO(csv_text)):
        raw = (row.get("amount") or "").strip()
        if not raw:
            continue
        negative = raw.startswith("(") and raw.endswith(")")
        amount = Decimal(raw.strip("()").replace("$", "").replace(",", ""))
        if negative:
            amount = -amount
        category = row["category"].strip().lower()
        totals[category] = totals.get(category, Decimal(0)) + amount
    return {key: round(float(value), 2) for key, value in totals.items()}
''')
    elif task["task_id"] == "strict-log-format":
        (root / "src/logsum.py").write_text('''import re
from collections import Counter

def error_report(log_text):
    hours = Counter()
    for line in log_text.splitlines():
        match = re.fullmatch(r"\\d{4}-\\d{2}-\\d{2}T([0-2]\\d):[0-5]\\d:[0-5]\\dZ ERROR .+", line)
        if match and int(match[1]) < 24:
            hours[match[1]] += 1
    return [f"{hour}: {hours[hour]} errors" for hour in sorted(hours)]
''')


class FixtureBaselineTests(unittest.TestCase):
    def setUp(self):
        self.tasks = runner.load_tasks(TASK_IDS)

    def test_all_five_repair_tasks_declare_and_fail_baseline(self):
        self.assertEqual(len(self.tasks), 5)
        for task in self.tasks:
            with self.subTest(task=task["task_id"]):
                self.assertEqual(task.get("initial_state"), "must_fail")
                runner.validate_task_baseline(task)

    def test_known_fixes_pass_all_five_graders_without_changing_tests(self):
        for task in self.tasks:
            with self.subTest(task=task["task_id"]):
                root = build_fixture(task["files"], prefix="positive-control")
                try:
                    manifest = hash_tree(root)
                    apply_known_fix(task, root)
                    result = grade(task["postcondition"], root, "", manifest)
                    self.assertTrue(result.passed, result.detail)
                finally:
                    cleanup_fixture(root)

    def test_pre_solved_booking_is_rejected_before_pinning_or_dispatch(self):
        task = copy.deepcopy(next(t for t in self.tasks if t["task_id"] == "booking-off-by-one"))
        task["files"]["src/bookings.py"] = task["files"]["src/bookings.py"].replace("<=", "<")
        with patch.object(runner, "ensure_pinned_model") as pin, patch.object(runner, "_ledger_session_start") as ledger:
            with self.assertRaisesRegex(runner.FixtureBaselineError, "already passes"):
                runner.run_trial(task, "L2", "must-not-run", 1, Path("/unused"), True)
            pin.assert_not_called()
            ledger.assert_not_called()

    def test_unknown_policy_fails_closed(self):
        with self.assertRaisesRegex(runner.FixtureBaselineError, "unknown initial_state"):
            runner.validate_task_baseline({"task_id": "typo", "initial_state": "must_fial"})

    def test_observation_task_without_policy_is_not_forced_to_fail(self):
        with patch.object(runner, "build_fixture") as build:
            runner.validate_task_baseline({"task_id": "read-only"})
            build.assert_not_called()

    def test_baseline_tempdir_is_cleaned_on_rejection(self):
        task = {"task_id": "solved", "initial_state": "must_fail", "files": {"x": "done"},
                "postcondition": {"type": "grep", "file": "x", "pattern": "done"}}
        roots = []
        def build(*args, **kwargs):
            root = build_fixture(*args, **kwargs)
            roots.append(root)
            return root
        with patch.object(runner, "build_fixture", side_effect=build), \
                self.assertRaises(runner.FixtureBaselineError):
            runner.validate_task_baseline(task)
        self.assertTrue(roots)
        self.assertTrue(all(not root.exists() for root in roots))
