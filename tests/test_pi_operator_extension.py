"""Verification path for the project-local pi Operator extension.

The extension itself is TypeScript under ``.pi/extensions/operator/``. Its
assertions live in ``selftest.ts`` so they can run against pi's real extension
loader; this module is the hook that puts them in ``python3 -m pytest tests/``.

The selftest builds a throwaway ledger with the real ``operator`` binary and
never makes a network or model call. It skips (rather than fails) when node is
too old to strip TypeScript types or when pi is not installed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SELFTEST = REPO_ROOT / ".pi" / "extensions" / "operator" / "selftest.ts"
EXTENSION_DIR = SELFTEST.parent


def _strip_ts_comments(text: str) -> str:
    """Drop // and /* */ comments so prose about a flag is not read as code."""
    out = []
    i = 0
    n = len(text)
    while i < n:
        two = text[i : i + 2]
        if two == "//":
            i = text.find("\n", i)
            if i == -1:
                break
        elif two == "/*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _node_supports_type_stripping(node: str) -> bool:
    """Node gained --experimental-strip-types in 22.6."""
    try:
        raw = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    if not raw.startswith("v"):
        return False
    try:
        major, minor = (int(part) for part in raw[1:].split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (22, 6)


class PiOperatorExtensionLayoutTest(unittest.TestCase):
    """Layout invariants that hold with or without node installed."""

    def test_only_index_is_auto_discovered(self):
        # pi discovers .pi/extensions/*.ts and .pi/extensions/*/index.ts. The
        # helper modules must stay inside the subdirectory so they are imported
        # by index.ts rather than loaded as extensions in their own right.
        names = sorted(p.name for p in EXTENSION_DIR.glob("*.ts"))
        self.assertEqual(names, ["core.ts", "index.ts", "render.ts", "selftest.ts"])
        self.assertFalse(
            list((EXTENSION_DIR.parent).glob("*.ts")),
            "loose .ts files in .pi/extensions/ would each load as an extension",
        )

    def test_no_lifecycle_flags_anywhere_in_the_extension(self):
        # POE-RUL-113: --status, --verified-by and --verdict are omitted
        # entirely, not validated. The only permitted mentions are the guard
        # that rejects them and the prose explaining why.
        offenders = []
        for path in sorted(EXTENSION_DIR.glob("*.ts")):
            if path.name in {"core.ts", "selftest.ts"}:
                continue
            text = _strip_ts_comments(path.read_text(encoding="utf-8"))
            for flag in ("--status", "--verified-by", "--verdict"):
                if flag in text:
                    offenders.append(f"{path.name}: {flag}")
        self.assertEqual(offenders, [])

    def test_allowlist_is_read_only_plus_confirmed_writes(self):
        text = (EXTENSION_DIR / "core.ts").read_text(encoding="utf-8")
        self.assertIn('"doctor"', text)
        self.assertIn('"claim-show"', text)
        self.assertIn('"review-delegate"', text)
        self.assertIn(
            "export const READ_ONLY_SUBCOMMANDS = [\n"
            '\t"doctor",\n'
            '\t"task-list",\n'
            '\t"task-show",\n'
            '\t"claim-list",\n'
            '\t"claim-show",\n'
            '\t"session-list",\n'
            "] as const;",
            text,
        )
        self.assertIn(
            "export const CONFIRMED_WRITE_SUBCOMMANDS = [\n"
            '\t"task-use",\n'
            '\t"claim-add",\n'
            '\t"evidence-attach",\n'
            '\t"handoff-add",\n'
            '\t"review-delegate",\n'
            '\t"task-create",\n'
            '\t"session-start",\n'
            '\t"brief",\n'
            '\t"export-brief",\n'
            "] as const;",
            text,
        )
        self.assertIn(
            '"claim-add": ["--task", "--type", "--text", "--by", "--gate", '
            '"--verify-cmd", "--layer"]',
            text,
        )
        self.assertIn(
            '"evidence-attach": ["--task", "--claim", "--type", "--by", '
            '"--notes", "--verify-cmd", "--hash"]',
            text,
        )
        self.assertIn(
            '"handoff-add": ["--task", "--by", "--changed", "--verified", '
            '"--claimed", "--open", "--assumptions", "--next-action"]',
            text,
        )
        self.assertIn('"claim-show": ["--id"]', text)
        self.assertIn(
            '"review-delegate": ["--task", "--reviewer", "--mode", '
            '"--review-user", "--verify-cmd"]',
            text,
        )
        self.assertIn(
            'export const FORBIDDEN_FLAGS = ["--status", "--verified-by", '
            '"--verified_by", "--verdict"]',
            text,
        )
        review_flags = (
            '"review-delegate": ["--task", "--reviewer", "--mode", '
            '"--review-user", "--verify-cmd"]'
        )
        self.assertIn(review_flags, text)
        self.assertNotIn("--status", review_flags)
        self.assertNotIn("--verified-by", review_flags)
        self.assertNotIn("--model", review_flags)
        self.assertIn(
            '"task-create": ["--id", "--objective", "--assign", "--review"]',
            text,
        )
        self.assertIn('"session-start": ["--task", "--harness"]', text)
        self.assertIn('brief: ["--for", "--task"]', text)
        self.assertIn('"export-brief": ["--for", "--task"]', text)
        session_flags = '"session-start": ["--task", "--harness"]'
        self.assertNotIn("--force", session_flags)
        self.assertNotIn("--status", session_flags)
        self.assertNotIn("--verified-by", session_flags)
        create_flags = '"task-create": ["--id", "--objective", "--assign", "--review"]'
        self.assertNotIn("--status", create_flags)
        self.assertIn("ADAPTER_INVOKE_SCRIPT", text)
        self.assertIn("ha.Role.IMPLEMENTER", text)
        self.assertNotIn("ha.Role.JUDGE", text)

    def test_operator_commands_only(self):
        text = (EXTENSION_DIR / "index.ts").read_text(encoding="utf-8")
        registered = sorted(
            line.split('"')[1] for line in text.splitlines() if "pi.registerCommand(" in line
        )
        self.assertEqual(
            registered,
            [
                "op:claim",
                "op:delegate",
                "op:doctor",
                "op:evidence",
                "op:handoff",
                "op:next-steps",
                "op:roadmap",
                "op:status",
                "op:supervisor-review",
                "op:tasks",
                "op:use",
            ],
        )
        self.assertNotIn("pi.registerTool(", text)
        self.assertIn('pi.registerCommand("op:delegate"', text)
        self.assertIn('pi.registerCommand("op:supervisor-review"', text)
        self.assertIn('pi.registerCommand("op:roadmap"', text)
        self.assertIn('pi.registerCommand("op:next-steps"', text)
        self.assertNotIn('pi.registerCommand("pbc:define"', text)
        self.assertNotIn('pi.registerCommand("pbc:feature"', text)

    def test_delegate_targets_do_not_override_routing(self):
        text = (EXTENSION_DIR / "targets.json").read_text(encoding="utf-8")
        self.assertNotIn("assigned_harness", text)
        self.assertNotIn("review_harness", text)
        self.assertIn('"carrier_id": "agy"', text)
        self.assertIn('"harness_id": "gemini-agy"', text)


class PiOperatorExtensionSelftest(unittest.TestCase):
    """Run the TypeScript selftest (loader + handler behavior)."""

    def test_selftest_passes(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        if not _node_supports_type_stripping(node):
            self.skipTest("node is older than 22.6 (no --experimental-strip-types)")
        # selftest.ts discovers pi via PI_PACKAGE_DIR or a `pi` on PATH; the
        # module contract is to skip Tiers B/C (not fail) when pi is absent.
        pi_present = bool(os.environ.get("PI_PACKAGE_DIR") or shutil.which("pi"))
        result = subprocess.run(
            [node, "--experimental-strip-types", str(SELFTEST)],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, 0, output)
        self.assertIn("0 failed", output)
        if pi_present:
            self.assertNotIn("skipped: Tier B", output)
            self.assertNotIn("skipped: Tier C", output)


if __name__ == "__main__":
    unittest.main()
