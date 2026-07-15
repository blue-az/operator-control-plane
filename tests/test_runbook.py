from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import authority_admin  # noqa: E402

RUNBOOK_PATH = REPO_ROOT / "OPERATIONS_RUNBOOK.md"
OPERATOR_BIN = str(REPO_ROOT / "operator")


def choices_from_usage(usage: str) -> set[str]:
    match = re.search(r"\{([a-zA-Z0-9_,-]+)\}", usage)
    if not match:
        raise AssertionError(f"could not find subcommand choices in usage text: {usage!r}")
    return set(match.group(1).split(","))


class TestRunbookMatchesCli(unittest.TestCase):
    """Keeps OPERATIONS_RUNBOOK.md from silently drifting away from the real CLIs."""

    def setUp(self) -> None:
        self.text = RUNBOOK_PATH.read_text(encoding="utf-8")

    def test_runbook_exists_and_is_nonempty(self) -> None:
        self.assertTrue(RUNBOOK_PATH.is_file())
        self.assertGreater(len(self.text), 500)

    def test_runbook_covers_required_procedures(self) -> None:
        required_headings = (
            "install",
            "service",
            "collect privilege evidence",
            "preflight",
            "enroll",
            "reconcil",
            "outage",
            "rotation",
            "revocation",
            "rollback-rejection",
            "recovery",
        )
        lowered = self.text.lower()
        missing = [heading for heading in required_headings if heading not in lowered]
        self.assertFalse(missing, f"runbook is missing coverage of: {missing}")

    def test_operator_admin_commands_are_real(self) -> None:
        valid = choices_from_usage(authority_admin.build_parser().format_usage())
        mentioned = set(re.findall(r"`operator-admin ([a-z][a-z0-9-]*)`", self.text))
        mentioned |= set(re.findall(r'operator-admin"\s+([a-z][a-z0-9-]*)', self.text))
        self.assertTrue(mentioned, "expected at least one operator-admin command in the runbook")
        unknown = mentioned - valid
        self.assertFalse(
            unknown, f"runbook references operator-admin commands that do not exist: {unknown}"
        )

    def test_repo_cli_commands_are_real(self) -> None:
        completed = subprocess.run(
            [OPERATOR_BIN, "--help"], capture_output=True, text=True, check=True
        )
        valid = choices_from_usage(completed.stdout)
        # Only treat "operator <word>" as an invocation when "operator" opens a code line or
        # an inline code span -- otherwise ordinary prose quoting error text (e.g. "operator
        # path is group/other writable") gets misread as a bogus subcommand.
        mentioned = set(re.findall(r"(?:^|`)operator\s+([a-z][a-z0-9-]*)", self.text, re.MULTILINE))
        self.assertTrue(mentioned, "expected at least one repo CLI command in the runbook")
        unknown = mentioned - valid
        self.assertFalse(unknown, f"runbook references unknown operator commands: {unknown}")


if __name__ == "__main__":
    unittest.main()
