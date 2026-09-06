"""POE-FUT-014 Route C local Operator PBC wrapper tests.

Positive and negative coverage for scripts/pbc_validate_operator.py.
Does not ratify proposed rules, does not claim an upstream --profile
flag, and does not execute stored verification commands.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import pbc_validate_operator
import poe_fut014_audit

FIXTURES = ROOT / "tests" / "fixtures" / "poe_fut014"
WRAPPER = ROOT / "scripts" / "pbc_validate_operator.py"


def _copy_fixtures(temp_dir: Path) -> Path:
    dest = temp_dir / "poe_fut014"
    shutil.copytree(FIXTURES, dest)
    return dest


class WrapperHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pbc_spec = poe_fut014_audit.resolve_pbc_spec()
        cls.cli_available = bool(
            cls.pbc_spec and (Path(cls.pbc_spec) / "cli" / "dist" / "bin" / "pbc.js").is_file()
        )

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="pbc_validate_operator_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.fixtures = _copy_fixtures(self.temp_dir)

    def require_cli(self) -> Path:
        if not self.cli_available:
            self.skipTest("pinned pbc-spec CLI is not available locally")
        assert self.pbc_spec is not None
        return Path(self.pbc_spec)

    def wrap(self, name: str, *, ledger: Path | None = None) -> dict:
        pbc_spec = self.require_cli()
        return pbc_validate_operator.run_wrapper(
            [self.fixtures / name],
            pbc_spec,
            ledger=ledger,
            require_pin=True,
        )

    def error_ids(self, report: dict) -> set[str]:
        return {str(row.get("checkId")) for row in report["errors"]}

    def allowlisted_ids(self, report: dict) -> set[str]:
        return {str(row.get("checkId")) for row in report["allowlisted"]}

    def allowlisted_block_types(self, report: dict) -> set[str]:
        types: set[str] = set()
        for row in report["allowlisted"]:
            if row.get("checkId") != "E004":
                continue
            block = pbc_validate_operator._block_type_from_row(row)
            if block:
                types.add(block)
        return types


class TestWrapperPinAndSurface(WrapperHelpers):
    def test_wrapper_does_not_claim_upstream_profile_flag(self) -> None:
        help_text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("**not** an upstream --profile flag", help_text)
        self.assertIn("Local Operator PBC", help_text)
        self.assertIn("does not add or claim an upstream --profile flag", help_text)
        self.assertNotIn("pbc validate --profile", help_text)
        pbc_spec = self.require_cli()
        env = os.environ.copy()
        env["NO_COLOR"] = "1"
        env["FORCE_COLOR"] = "0"
        proc = subprocess.run(
            ["node", str(pbc_spec / "cli" / "dist" / "bin" / "pbc.js"), "validate", "--help"],
            cwd=str(pbc_spec / "cli"),
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
            check=False,
        )
        combined = proc.stdout + proc.stderr
        self.assertNotIn("--profile", combined)
        self.assertFalse(poe_fut014_audit.pin_upstream(pbc_spec)["has_profile_flag"])
        self.assertEqual(
            pbc_validate_operator.PINNED_COMMIT, "ca97caf63329cee5ecf2b92dfe1120374ab90a81"
        )

    def test_pin_mismatch_fails_closed(self) -> None:
        pbc_spec = self.require_cli()
        pin = poe_fut014_audit.pin_upstream(pbc_spec)
        pin["commit"] = "0" * 40
        problems = pbc_validate_operator.validate_pin(pin, require_pin=True)
        self.assertTrue(any("upstream commit" in item for item in problems))
        self.assertEqual(pbc_validate_operator.validate_pin(pin, require_pin=False), [])

    def test_empty_commit_fails_closed_and_surfaces_git_errors(self) -> None:
        pin = {
            "commit": "",
            "spec_version": pbc_validate_operator.PINNED_SPEC_VERSION,
            "cli_package_version": pbc_validate_operator.PINNED_CLI_PACKAGE_VERSION,
            "has_profile_flag": False,
            "git_errors": ["fatal: detected dubious ownership in repository at '/tmp/pbc-spec'"],
        }
        problems = pbc_validate_operator.validate_pin(pin, require_pin=True)
        self.assertTrue(any("upstream commit (missing)" in item for item in problems))
        self.assertTrue(any("dubious ownership" in item for item in problems))
        self.assertEqual(pbc_validate_operator.validate_pin(pin, require_pin=False), [])
        self.assertNotIn("--allow-unpinned", " ".join(problems))


class TestWrapperPositive(WrapperHelpers):
    def test_portable_core_passes(self) -> None:
        report = self.wrap("poe_fut014_valid_upstream_core.pbc.md")
        self.assertTrue(report["ok"], report["fail_reasons"])
        self.assertFalse(report["ratified"])
        self.assertFalse(report["upstream_profile_flag"])
        self.assertEqual(report["errors"], [])
        self.assertEqual(report["pbc_lint_errors"], [])

    def test_yaml_valid_proposed_lifecycle_is_allowlisted_not_ratified(self) -> None:
        report = self.wrap("poe_fut014_valid_proposed_lifecycle.pbc.md")
        self.assertTrue(report["ok"], report["fail_reasons"])
        self.assertFalse(report["ratified"])
        self.assertIn("E004", self.allowlisted_ids(report))
        self.assertEqual(self.error_ids(report), set())
        self.assertEqual(
            self.allowlisted_block_types(report),
            {"proposed-rules", "proposed-behavior", "proposed-outcomes"},
        )
        reasons = " ".join(str(row.get("allowlist_reason") or "") for row in report["allowlisted"])
        self.assertIn("not ratification", reasons)
        self.assertTrue(report["allowlisted"], "allowlisted rows must remain in the report")

    def test_local_trust_verified_is_warning_not_error(self) -> None:
        report = self.wrap("poe_fut014_valid_local_trust.pbc.md")
        self.assertTrue(report["ok"], report["fail_reasons"])
        self.assertEqual(self.error_ids(report), set())
        warning_ids = {str(row.get("checkId")) for row in report["warnings"]}
        self.assertIn("W013", warning_ids)

    def test_measured_confidence_is_allowlisted_without_relabel(self) -> None:
        report = self.wrap("poe_fut014_invalid_provenance_confidence.pbc.md")
        self.assertTrue(report["ok"], report["fail_reasons"])
        self.assertIn("E011", self.allowlisted_ids(report))
        self.assertNotIn("E011", self.error_ids(report))
        for row in report["allowlisted"]:
            if row.get("checkId") == "E011":
                self.assertEqual(row.get("confidence_value"), "measured")
                reason = str(row.get("allowlist_reason") or "")
                self.assertIn("measured", reason)
                self.assertIn("not relabeled", reason.lower())
                self.assertIn("not UID-isolated verification", reason)
        serialized = json.dumps(report)
        self.assertIn("measured", serialized)
        self.assertNotIn("confidence: verified", serialized)


class TestWrapperNegative(WrapperHelpers):
    def test_invalid_yaml_still_e005(self) -> None:
        report = self.wrap("poe_fut014_invalid_yaml.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E005", self.error_ids(report))

    def test_missing_frontmatter_still_e001(self) -> None:
        report = self.wrap("poe_fut014_invalid_frontmatter_missing.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E001", self.error_ids(report))

    def test_missing_id_still_e002(self) -> None:
        report = self.wrap("poe_fut014_invalid_frontmatter_no_id.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E002", self.error_ids(report))

    def test_missing_title_still_e003(self) -> None:
        report = self.wrap("poe_fut014_invalid_frontmatter_no_title.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E003", self.error_ids(report))

    def test_broken_frontmatter_still_fails(self) -> None:
        report = self.wrap("poe_fut014_invalid_frontmatter_broken.pbc.md")
        self.assertFalse(report["ok"])
        self.assertTrue(self.error_ids(report) & {"E001", "E005"})

    def test_unclosed_block_still_e005(self) -> None:
        report = self.wrap("poe_fut014_invalid_unclosed.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E005", self.error_ids(report))

    def test_unknown_non_lifecycle_block_still_e004(self) -> None:
        report = self.wrap("poe_fut014_invalid_unknown_block.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E004", self.error_ids(report))
        self.assertNotIn("E004", self.allowlisted_ids(report))
        messages = " ".join(str(row.get("message") or "") for row in report["errors"])
        self.assertIn("not-a-block", messages)

    def test_malformed_proposed_yaml_is_not_allowlisted_away(self) -> None:
        report = self.wrap("poe_fut014_invalid_malformed_proposed_yaml.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E005", self.error_ids(report))
        self.assertNotIn("E005", self.allowlisted_ids(report))

    def test_unknown_confidence_established_still_e011(self) -> None:
        report = self.wrap("poe_fut014_invalid_unknown_confidence.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E011", self.error_ids(report))
        self.assertNotIn("E011", self.allowlisted_ids(report))
        messages = " ".join(str(row.get("message") or "") for row in report["errors"])
        self.assertIn("established", messages)
        dispositions = {row.get("disposition") for row in report["allowlisted"]}
        self.assertNotIn("error", dispositions)

    def test_missing_confidence_still_e011(self) -> None:
        report = self.wrap("poe_fut014_invalid_missing_confidence.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E011", self.error_ids(report))
        self.assertNotIn("E011", self.allowlisted_ids(report))
        messages = " ".join(str(row.get("message") or "") for row in report["errors"])
        self.assertIn("missing", messages.lower())

    def test_proposed_plus_unknown_keeps_unknown_e004(self) -> None:
        report = self.wrap("poe_fut014_invalid_proposed_plus_unknown.pbc.md")
        self.assertFalse(report["ok"])
        self.assertIn("E004", self.allowlisted_ids(report))
        self.assertIn("E004", self.error_ids(report))
        self.assertEqual(
            self.allowlisted_block_types(report),
            {"proposed-rules", "proposed-behavior", "proposed-outcomes"},
        )
        error_messages = " ".join(str(row.get("message") or "") for row in report["errors"])
        self.assertIn("not-a-block", error_messages)

    def test_rules_trust_proposed_still_fails_pbc_lint(self) -> None:
        report = self.wrap("poe_fut014_invalid_rules_trust_proposed.pbc.md")
        self.assertFalse(report["ok"])
        self.assertTrue(any("trust: proposed" in err for err in report["pbc_lint_errors"]))
        self.assertEqual(self.error_ids(report), set())


class TestWrapperCli(WrapperHelpers):
    def test_main_json_on_proposed_fixture(self) -> None:
        pbc_spec = self.require_cli()
        out = self.temp_dir / "wrapper.json"
        rc = pbc_validate_operator.main(
            [
                "--pbc-spec",
                str(pbc_spec),
                "--format",
                "json",
                "--out",
                str(out),
                str(self.fixtures / "poe_fut014_valid_proposed_lifecycle.pbc.md"),
            ]
        )
        self.assertEqual(rc, 0)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["wrapper"], "pbc_validate_operator")
        self.assertEqual(payload["route"], "C")
        self.assertFalse(payload["ratified"])
        self.assertFalse(payload["upstream_profile_flag"])
        self.assertTrue(payload["ok"])

    def test_main_fails_on_unknown_block(self) -> None:
        pbc_spec = self.require_cli()
        rc = pbc_validate_operator.main(
            [
                "--pbc-spec",
                str(pbc_spec),
                "--format",
                "json",
                str(self.fixtures / "poe_fut014_invalid_unknown_block.pbc.md"),
            ]
        )
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
