#!/usr/bin/env python3
"""Deterministic local-lane task-prompt linter.

Checks a task prompt against LOCAL_LANE_CONTRACT.md rules R1-R6 and reports
an overall verdict: plan-shaped, semi-shaped, or goal-shaped. No LLM calls --
this is regex/heuristic scoring, not natural-language understanding. Bias
toward WARN over FAIL when a rule's signal is ambiguous (see
LOCAL_LANE_CONTRACT_SPEC.md, Deliverable 2).

CLI:
    task_lint.py <file|->  [--json]

Exit codes: 0 = plan-shaped, 1 = semi-shaped, 2 = goal-shaped.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Shared patterns
# ---------------------------------------------------------------------------

# A path-like token: at least one path separator, or a bare filename with a
# recognized extension. Deliberately permissive -- false positives here are
# safer than false negatives (a stray match just makes R1 pass a bit early;
# a missed real path makes R1 fail a task that should have passed).
_PATH_WITH_SEP_RE = re.compile(r"`?([\w.\-]+(?:/[\w.\-]+)+)`?")
_KNOWN_EXTENSIONS = (
    "py", "md", "yaml", "yml", "json", "ini", "toml", "cfg", "txt", "sh",
    "js", "ts", "jsx", "tsx", "html", "css", "ipynb", "rs", "go", "rb",
    "java", "c", "cpp", "h", "hpp", "sql", "csv",
)
_BARE_FILENAME_RE = re.compile(
    r"`?\b[\w\-]+\.(?:" + "|".join(_KNOWN_EXTENSIONS) + r")\b`?"
)

_EDIT_VERBS = (
    "add", "change", "replace", "insert", "patch", "update", "modify",
    "append", "remove", "delete", "edit", "set",
)
_EDIT_VERB_RE = re.compile(
    r"\b(?:" + "|".join(_EDIT_VERBS) + r")\b", re.IGNORECASE
)

_QUOTED_ANCHOR_RE = re.compile(r"[\"'`]([^\"'`]{3,})[\"'`]")
_ANCHOR_CLAUSE_RE = re.compile(
    r"\bafter (?:the )?line\b|\bappend at end\b|\bat the end of the file\b",
    re.IGNORECASE,
)

_NUMBERED_STEP_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+\S", re.MULTILINE)

_VERIFY_PHRASE_RE = re.compile(
    r"\bshould (?:now )?contain\b|\bnow contains\b|\bverify\b|\bverifies\b|"
    r"\bexit(?:s)? (?:code )?0\b|\bshould exit\b|\bshould return\b|"
    r"\bshould output\b|\bconfirm that\b",
    re.IGNORECASE,
)

_BAN_LIST = (
    "figure out", "appropriately", "as needed", "somehow", "etc.", "etc",
    "as you see fit", "however you", "your choice", "up to you",
)

_BOUND_CLAUSE_RE = re.compile(
    r"\bonly touch\b|\bonly modify\b|\bonly the files? listed\b|"
    r"\bdo not touch any other\b|\bno other files?\b",
    re.IGNORECASE,
)

_VAGUE_REF_RE = re.compile(
    r"\bmy [\w\s]{1,20}\bfile\b|\bthe config\b|\bthe file\b", re.IGNORECASE
)

Verdict = str  # "PASS" | "FAIL" | "WARN"


@dataclass
class RuleResult:
    rule: str
    verdict: Verdict
    detail: str


@dataclass
class LintResult:
    rules: list[RuleResult] = field(default_factory=list)
    overall: str = "goal-shaped"

    def as_dict(self) -> dict:
        return {
            "overall": self.overall,
            "rules": [
                {"rule": r.rule, "verdict": r.verdict, "detail": r.detail}
                for r in self.rules
            ],
        }

    def exit_code(self) -> int:
        return {"plan-shaped": 0, "semi-shaped": 1, "goal-shaped": 2}[self.overall]


def _find_paths(text: str) -> list[str]:
    found = [m.group(1) for m in _PATH_WITH_SEP_RE.finditer(text)]
    found += [m.group(0).strip("`") for m in _BARE_FILENAME_RE.finditer(text)]
    return found


def check_r1_exact_paths(text: str) -> RuleResult:
    """R1 -- Exact paths. PASS if at least one path-like token is present."""
    paths = _find_paths(text)
    if paths:
        return RuleResult("R1", "PASS", f"path token(s) found: {paths}")
    vague = _VAGUE_REF_RE.search(text)
    if vague:
        return RuleResult(
            "R1", "FAIL", f"vague file reference with no path: {vague.group(0)!r}"
        )
    return RuleResult("R1", "FAIL", "no path-like token found")


def check_r2_anchored_edits(text: str) -> RuleResult:
    """R2 -- Anchored edits. Only applies when an edit-verb is present."""
    if not _EDIT_VERB_RE.search(text):
        return RuleResult("R2", "PASS", "no edit-verb present; rule not triggered")
    if _QUOTED_ANCHOR_RE.search(text):
        return RuleResult("R2", "PASS", "quoted verbatim anchor present")
    if _ANCHOR_CLAUSE_RE.search(text):
        return RuleResult("R2", "PASS", "anchor clause present (after line / append at end)")
    return RuleResult("R2", "FAIL", "edit-verb present but no anchor found")


def check_r3_one_tool_call_per_step(text: str) -> RuleResult:
    """R3 -- One tool call per step. Numbered/bulleted steps PASS; a single
    sentence naming 2+ distinct action verbs WARNs; otherwise PASS."""
    if _NUMBERED_STEP_RE.search(text):
        return RuleResult("R3", "PASS", "numbered/bulleted steps present")
    verbs_found = sorted(set(m.group(0).lower() for m in _EDIT_VERB_RE.finditer(text)))
    action_words = set(verbs_found) | set(
        w.lower() for w in ("run", "verify", "check", "create") if re.search(rf"\b{w}\b", text, re.IGNORECASE)
    )
    if len(action_words) >= 2:
        return RuleResult(
            "R3", "WARN", f"single-sentence task names multiple actions: {sorted(action_words)}"
        )
    return RuleResult("R3", "PASS", "single action, no step-splitting ambiguity")


def check_r4_success_criterion(text: str) -> RuleResult:
    """R4 -- Explicit success criterion."""
    m = _VERIFY_PHRASE_RE.search(text)
    if m:
        return RuleResult("R4", "PASS", f"verification clause present: {m.group(0)!r}")
    return RuleResult("R4", "FAIL", "no machine-checkable postcondition found")


def check_r5_closed_vocabulary(text: str) -> RuleResult:
    """R5 -- Imperative, closed vocabulary. FAIL if any ban-list token is present."""
    lowered = text.lower()
    hits = [tok for tok in _BAN_LIST if tok in lowered]
    if hits:
        return RuleResult("R5", "FAIL", f"ban-list token(s) present: {hits}")
    return RuleResult("R5", "PASS", "no ban-list tokens found")


def check_r6_bounded_scope(text: str) -> RuleResult:
    """R6 -- Bounded scope. Explicit bounding clause, or every mentioned
    path unique, PASS; otherwise WARN."""
    if _BOUND_CLAUSE_RE.search(text):
        return RuleResult("R6", "PASS", "explicit scope-bounding clause present")
    paths = _find_paths(text)
    if paths and len(paths) == len(set(paths)):
        return RuleResult("R6", "PASS", "all mentioned paths are unique, no bounding clause needed")
    if not paths:
        return RuleResult("R6", "WARN", "no paths and no explicit bounding clause")
    return RuleResult("R6", "WARN", f"duplicate path mentions with no bounding clause: {paths}")


_CHECKS = [
    check_r1_exact_paths,
    check_r2_anchored_edits,
    check_r3_one_tool_call_per_step,
    check_r4_success_criterion,
    check_r5_closed_vocabulary,
    check_r6_bounded_scope,
]


def lint(text: str) -> LintResult:
    result = LintResult()
    result.rules = [check(text) for check in _CHECKS]

    r1 = result.rules[0]
    if r1.verdict == "FAIL":
        result.overall = "goal-shaped"
    elif all(r.verdict == "PASS" for r in result.rules):
        result.overall = "plan-shaped"
    else:
        result.overall = "semi-shaped"
    return result


def _read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, encoding="utf-8") as f:
        return f.read()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Local-lane task-prompt linter (R1-R6).")
    parser.add_argument("path", help="Task prompt file, or - for stdin.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    args = parser.parse_args(argv)

    text = _read_input(args.path)
    result = lint(text)

    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        for r in result.rules:
            print(f"{r.rule}: {r.verdict:5s} -- {r.detail}")
        print(f"\nOverall: {result.overall}")

    return result.exit_code()


if __name__ == "__main__":
    sys.exit(main())
