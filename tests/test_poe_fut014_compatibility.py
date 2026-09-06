"""POE-FUT-014 compatibility audit tests.

Exercises YAML-valid proposed lifecycle fixtures and invalid
YAML/frontmatter against the pinned local pbc-spec CLI and Operator
pbc_lint.py. Copies fixtures into temporary directories. Does not
ratify rules, edit PBCs, or execute stored verification commands.
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

import pbc_lint

FIXTURES = ROOT / "tests" / "fixtures" / "poe_fut014"


def _copy_fixtures(temp_dir: Path) -> Path:
    dest = temp_dir / "poe_fut014"
    shutil.copytree(FIXTURES, dest)
    return dest


class PoeFut014AuditHelpers(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.pbc_spec = poe_fut014_audit.resolve_pbc_spec()
        cls.cli_available = bool(
            cls.pbc_spec and (Path(cls.pbc_spec) / "cli" / "dist" / "bin" / "pbc.js").is_file()
        )

    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp(prefix="poe_fut014_"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.fixtures = _copy_fixtures(self.temp_dir)

    def require_cli(self) -> Path:
        if not self.cli_available:
            self.skipTest("pinned pbc-spec CLI is not available locally")
        assert self.pbc_spec is not None
        return Path(self.pbc_spec)

    def validate(self, name: str) -> tuple[int, list[dict]]:
        pbc_spec = self.require_cli()
        path = self.fixtures / name
        code, payload, _stderr = poe_fut014_audit.run_upstream_validate(pbc_spec, path)
        return code, poe_fut014_audit.flatten_cli_results(payload)

    def lint(self, name: str) -> list[str]:
        return pbc_lint.lint_file(self.fixtures / name, ledger_names=None)


class TestPoeFut014PinnedUpstream(PoeFut014AuditHelpers):
    def test_pin_records_commit_and_spec_version(self) -> None:
        pbc_spec = self.require_cli()
        pin = poe_fut014_audit.pin_upstream(pbc_spec)
        self.assertTrue(pin["commit"])
        self.assertEqual(len(pin["commit"]), 40)
        self.assertEqual(pin["spec_version"], "0.6.0-draft")
        self.assertEqual(pin["cli_package_version"], "0.1.0")
        self.assertFalse(pin["has_profile_flag"])
        self.assertTrue(Path(pin["cli_bin"]).is_file())
        self.assertEqual(pin.get("git_errors") or [], [])
        self.assertTrue(pin.get("git_root"))

    def test_cli_has_no_profile_flag(self) -> None:
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
        self.assertIn("--format", combined)


class TestPoeFut014ValidProposedBlocks(PoeFut014AuditHelpers):
    def test_operator_pbc_lint_accepts_yaml_valid_proposed_lifecycle(self) -> None:
        errors = self.lint("poe_fut014_valid_proposed_lifecycle.pbc.md")
        self.assertEqual(errors, [])

    def test_upstream_cli_does_not_silently_drop_proposed_blocks(self) -> None:
        code, rows = self.validate("poe_fut014_valid_proposed_lifecycle.pbc.md")
        self.assertEqual(code, 1)
        problems = poe_fut014_audit.check_no_silent_drop(
            rows,
            ["proposed-rules", "proposed-behavior", "proposed-outcomes"],
        )
        self.assertEqual(problems, [])
        error_ids = {row["checkId"] for row in rows if row["severity"] == "error"}
        self.assertIn("E004", error_ids)

    def test_portable_core_fixture_passes_both_tools(self) -> None:
        self.assertEqual(self.lint("poe_fut014_valid_upstream_core.pbc.md"), [])
        code, rows = self.validate("poe_fut014_valid_upstream_core.pbc.md")
        self.assertEqual(code, 0)
        self.assertFalse(any(row["severity"] == "error" for row in rows))

    def test_local_trust_is_warning_not_error_on_known_blocks(self) -> None:
        self.assertEqual(self.lint("poe_fut014_valid_local_trust.pbc.md"), [])
        code, rows = self.validate("poe_fut014_valid_local_trust.pbc.md")
        self.assertEqual(code, 0)
        warning_ids = {row["checkId"] for row in rows if row["severity"] == "warning"}
        self.assertIn("W013", warning_ids)
        self.assertFalse(any(row["severity"] == "error" for row in rows))


class TestPoeFut014InvalidYamlAndFrontmatter(PoeFut014AuditHelpers):
    def test_upstream_rejects_invalid_yaml(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_yaml.pbc.md")
        self.assertEqual(code, 1)
        self.assertTrue(any(row["checkId"] == "E005" for row in rows))

    def test_upstream_rejects_missing_frontmatter(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_frontmatter_missing.pbc.md")
        self.assertEqual(code, 1)
        self.assertTrue(any(row["checkId"] == "E001" for row in rows))

    def test_upstream_rejects_missing_id(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_frontmatter_no_id.pbc.md")
        self.assertEqual(code, 1)
        self.assertTrue(any(row["checkId"] == "E002" for row in rows))

    def test_upstream_rejects_missing_title(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_frontmatter_no_title.pbc.md")
        self.assertEqual(code, 1)
        self.assertTrue(any(row["checkId"] == "E003" for row in rows))

    def test_upstream_rejects_broken_frontmatter(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_frontmatter_broken.pbc.md")
        self.assertEqual(code, 1)
        self.assertTrue(
            any(row["checkId"] == "E001" or "frontmatter" in row["message"].lower() for row in rows)
        )

    def test_upstream_rejects_unclosed_block(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_unclosed.pbc.md")
        self.assertEqual(code, 1)
        self.assertTrue(any(row["checkId"] == "E005" for row in rows))

    def test_unknown_non_lifecycle_block_is_not_dropped(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_unknown_block.pbc.md")
        self.assertEqual(code, 1)
        problems = poe_fut014_audit.check_no_silent_drop(rows, ["not-a-block"])
        self.assertEqual(problems, [])

    def test_measured_provenance_confidence_is_an_error(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_provenance_confidence.pbc.md")
        self.assertEqual(code, 1)
        self.assertTrue(any(row["checkId"] == "E011" for row in rows))


class TestPoeFut014OperatorLintGapsObserved(PoeFut014AuditHelpers):
    """Current pbc_lint.py behavior. Not a ruling that the gaps are acceptable."""

    def test_pbc_lint_does_not_yet_reject_invalid_yaml(self) -> None:
        self.assertEqual(self.lint("poe_fut014_invalid_yaml.pbc.md"), [])

    def test_pbc_lint_does_not_yet_require_frontmatter(self) -> None:
        self.assertEqual(self.lint("poe_fut014_invalid_frontmatter_missing.pbc.md"), [])
        self.assertEqual(self.lint("poe_fut014_invalid_frontmatter_no_id.pbc.md"), [])
        self.assertEqual(self.lint("poe_fut014_invalid_frontmatter_broken.pbc.md"), [])

    def test_pbc_lint_does_not_yet_reject_unknown_blocks(self) -> None:
        self.assertEqual(self.lint("poe_fut014_invalid_unknown_block.pbc.md"), [])

    def test_pbc_lint_invariant_one_rejects_rules_trust_proposed(self) -> None:
        errors = self.lint("poe_fut014_invalid_rules_trust_proposed.pbc.md")
        self.assertTrue(any("trust: proposed" in err for err in errors))

    def test_upstream_does_not_fail_closed_on_rules_trust_proposed(self) -> None:
        code, rows = self.validate("poe_fut014_invalid_rules_trust_proposed.pbc.md")
        self.assertEqual(code, 0)
        self.assertTrue(any(row["checkId"] == "W013" for row in rows))


class TestPoeFut014AuditMatrix(PoeFut014AuditHelpers):
    def test_full_manifest_in_temp_dir(self) -> None:
        pbc_spec = self.require_cli()
        report = poe_fut014_audit.run_audit(self.fixtures, pbc_spec)
        self.assertFalse(report["ratified"])
        self.assertFalse(report["route_chosen"])
        self.assertEqual(report["fail_closed_violations"], [])
        self.assertTrue(all(row["ok"] for row in report["results"]))
        self.assertEqual(len(report["results"]), 12)

    def test_script_main_writes_json_without_touching_ledger(self) -> None:
        pbc_spec = self.require_cli()
        out = self.temp_dir / "poe_fut014_report.json"
        rc = poe_fut014_audit.main(
            [
                "--fixtures",
                str(self.fixtures),
                "--pbc-spec",
                str(pbc_spec),
                "--format",
                "json",
                "--out",
                str(out),
            ]
        )
        self.assertEqual(rc, 0)
        payload = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(payload["audit"], "POE-FUT-014")
        self.assertFalse(payload["ratified"])


def _init_temp_git_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init"],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=operator-test@example.invalid",
            "-c",
            "user.name=operator-test",
            "commit",
            "--allow-empty",
            "-m",
            "pin-root",
        ],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    )
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(path),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return commit


def _install_spy_git(bin_dir: Path, log_path: Path, *, mode: str, expected_root: str) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    git = bin_dir / "git"
    git.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        f"log = Path({str(log_path)!r})\n"
        "prev = log.read_text(encoding='utf-8') if log.is_file() else ''\n"
        "log.write_text(prev + ' '.join(sys.argv[1:]) + '\\n', encoding='utf-8')\n"
        "args = sys.argv[1:]\n"
        "if 'config' in args or '--global' in args:\n"
        "    print('forbidden git config', file=sys.stderr)\n"
        "    sys.exit(128)\n"
        "safe = None\n"
        "cmd = []\n"
        "skip = False\n"
        "for a in args:\n"
        "    if skip:\n"
        "        if a.startswith('safe.directory='):\n"
        "            safe = a.split('=', 1)[1]\n"
        "        skip = False\n"
        "        continue\n"
        "    if a == '-c':\n"
        "        skip = True\n"
        "        continue\n"
        "    cmd.append(a)\n"
        "if safe in {'*', ''} or (isinstance(safe, str) and safe.endswith('/*')):\n"
        "    print('wildcard/empty safe.directory refused', file=sys.stderr)\n"
        "    sys.exit(128)\n"
        f"expected = {expected_root!r}\n"
        f"mode = {mode!r}\n"
        "if mode == 'always_fail' or safe != expected:\n"
        "    print('fatal: detected dubious ownership in repository at %r' % expected, file=sys.stderr)\n"
        "    sys.exit(128)\n"
        "if cmd[:1] == ['rev-parse'] and '--abbrev-ref' not in cmd:\n"
        "    print('aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')\n"
        "elif '--abbrev-ref' in cmd:\n"
        "    print('main')\n"
        "elif cmd[:1] == ['describe']:\n"
        "    print('v0-0-gaaaaaaa')\n"
        "elif cmd[:1] == ['log']:\n"
        "    print('subject' if '%s' in ' '.join(cmd) else '2026-01-01T00:00:00+00:00')\n"
        "elif cmd[:1] == ['status']:\n"
        "    sys.exit(0)\n"
        "else:\n"
        "    print('unhandled', cmd, file=sys.stderr)\n"
        "    sys.exit(1)\n",
        encoding="utf-8",
    )
    git.chmod(0o755)
    return git


class TestGitScopedSafeDirectory(PoeFut014AuditHelpers):
    """Provenance lookup under Git dubious-ownership. Does not change global Git trust."""

    def _with_path(self, bin_dir: Path) -> None:
        old = os.environ.get("PATH", "")
        os.environ["PATH"] = str(bin_dir) + os.pathsep + old

        def restore() -> None:
            os.environ["PATH"] = old

        self.addCleanup(restore)

    def test_resolved_git_root_requires_dot_git(self) -> None:
        missing = self.temp_dir / "not-a-repo"
        missing.mkdir()
        self.assertIsNone(poe_fut014_audit.resolved_git_root(missing))
        result = poe_fut014_audit._git(missing, "rev-parse", "HEAD")
        self.assertNotEqual(result["returncode"], 0)
        self.assertEqual(result["argv"], [])
        self.assertIn("not a git repository at expected root", result["stderr"])

    def test_scoped_safe_directory_rejects_wildcard(self) -> None:
        self.assertIsNone(poe_fut014_audit.scoped_safe_directory_value(Path("*")))
        self.assertIsNone(poe_fut014_audit.scoped_safe_directory_value(Path("/tmp/repo/*")))

    def test_source_has_no_global_or_wildcard_trust(self) -> None:
        source = (ROOT / "scripts" / "poe_fut014_audit.py").read_text(encoding="utf-8")
        self.assertNotIn("git config --global", source)
        self.assertNotIn("safe.directory=*", source)
        self.assertNotIn(
            "safe.directory=*", (ROOT / "scripts" / "pbc_validate_operator.py").read_text()
        )
        self.assertNotIn("--allow-unpinned", source)

    def test_spy_git_uses_exact_root_and_not_wildcard(self) -> None:
        repo = self.temp_dir / "pbc-spec"
        repo.mkdir()
        (repo / ".git").mkdir()
        log = self.temp_dir / "git-argv.log"
        bin_dir = self.temp_dir / "bin"
        _install_spy_git(bin_dir, log, mode="scoped_ok", expected_root=str(repo.resolve()))
        self._with_path(bin_dir)
        pin = poe_fut014_audit.pin_upstream(repo)
        self.assertEqual(pin["commit"], "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")
        self.assertEqual(pin.get("git_errors") or [], [])
        self.assertTrue(pin["working_tree_clean"])
        recorded = log.read_text(encoding="utf-8")
        self.assertIn(f"-c safe.directory={repo.resolve()}", recorded)
        self.assertNotIn("safe.directory=*", recorded)
        self.assertNotIn("--global", recorded)
        self.assertNotIn(" config ", f" {recorded} ")

    def test_git_failure_is_fail_closed_not_clean_tree(self) -> None:
        repo = self.temp_dir / "pbc-spec"
        repo.mkdir()
        (repo / ".git").mkdir()
        log = self.temp_dir / "git-argv.log"
        bin_dir = self.temp_dir / "bin"
        _install_spy_git(bin_dir, log, mode="always_fail", expected_root=str(repo.resolve()))
        self._with_path(bin_dir)
        pin = poe_fut014_audit.pin_upstream(repo)
        self.assertEqual(pin["commit"], "")
        self.assertFalse(pin["working_tree_clean"])
        self.assertTrue(pin.get("git_errors"))
        self.assertTrue(any("dubious ownership" in err for err in pin["git_errors"]))
        problems = pbc_validate_operator.validate_pin(
            {
                **pin,
                "spec_version": pbc_validate_operator.PINNED_SPEC_VERSION,
                "cli_package_version": pbc_validate_operator.PINNED_CLI_PACKAGE_VERSION,
            },
            require_pin=True,
        )
        self.assertTrue(any("upstream commit (missing)" in item for item in problems))
        self.assertTrue(any("dubious ownership" in item for item in problems))

    def test_real_git_assume_different_owner_reads_commit_with_scope(self) -> None:
        repo = self.temp_dir / "owned-repo"
        commit = _init_temp_git_repo(repo)
        old = os.environ.get("GIT_TEST_ASSUME_DIFFERENT_OWNER")
        os.environ["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"

        def restore() -> None:
            if old is None:
                os.environ.pop("GIT_TEST_ASSUME_DIFFERENT_OWNER", None)
            else:
                os.environ["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = old

        self.addCleanup(restore)
        naked = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(naked.returncode, 0, naked.stderr)
        self.assertIn("dubious ownership", naked.stderr)
        pin = poe_fut014_audit.pin_upstream(repo)
        self.assertEqual(pin["commit"], commit)
        self.assertEqual(pin.get("git_errors") or [], [])
        self.assertTrue(pin["working_tree_clean"])

    def test_live_pbc_spec_assume_different_owner_matches_pin(self) -> None:
        pbc_spec = self.require_cli()
        old = os.environ.get("GIT_TEST_ASSUME_DIFFERENT_OWNER")
        os.environ["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = "1"

        def restore() -> None:
            if old is None:
                os.environ.pop("GIT_TEST_ASSUME_DIFFERENT_OWNER", None)
            else:
                os.environ["GIT_TEST_ASSUME_DIFFERENT_OWNER"] = old

        self.addCleanup(restore)
        pin = poe_fut014_audit.pin_upstream(pbc_spec)
        self.assertTrue(pin["commit"])
        self.assertEqual(len(pin["commit"]), 40)
        self.assertEqual(pin.get("git_errors") or [], [])


if __name__ == "__main__":
    unittest.main()
