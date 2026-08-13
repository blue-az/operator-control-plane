"""Deterministic postcondition grading for the local-lane eval ladder.

No LLM judging, per LOCAL_LANE_CONTRACT_SPEC.md Deliverable 3 -- every
postcondition type here is a grep, a regex, an AST query, an exit-code check, a
file-scope comparison, or a substring check against the model's own final text.
Nothing consults a model about whether an answer is good.

Composition: a postcondition may be a single check, or `type: all_of` with a
`checks:` list. Composed results keep every sub-check's outcome so a partially
correct answer is visible rather than collapsing to one boolean -- a task that
edits the right line but also clobbers an unrelated file should not look
identical to one that did nothing.

Scope (`type: files_unchanged`) exists because LOCAL_LANE_CONTRACT R6 ("the task
enumerates every file that may be touched") was stated but never graded: a model
that made the required edit *and* rewrote README.md and scripts/deploy.sh scored
exactly the same as one that stayed in bounds. It needs the pre-run manifest from
fixtures.build_fixture. The Alignerr acceptance rule is the same idea in the
source domain -- "find all matching files: no omissions and no extras".
"""

from __future__ import annotations

import ast
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_EXEC_TIMEOUT = 30


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str


@dataclass
class GradeResult:
    passed: bool
    detail: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def score(self) -> float:
        """Fraction of sub-checks passed. 1.0/0.0 for a single uncomposed check.

        Reported alongside pass/fail, never instead of it: the postcondition is
        still the gate. This only makes "failed one of four" distinguishable
        from "failed all four".
        """
        if not self.checks:
            return 1.0 if self.passed else 0.0
        return sum(1 for c in self.checks if c.passed) / len(self.checks)


def grade(
    postcondition: dict,
    fixture_root: Path,
    model_output: str,
    manifest: dict[str, str] | None = None,
) -> GradeResult:
    kind = postcondition["type"]
    if kind == "all_of":
        return _grade_all_of(postcondition, fixture_root, model_output, manifest)
    if kind == "grep":
        return _grade_grep(postcondition, fixture_root)
    if kind == "regex":
        return _grade_regex(postcondition, fixture_root)
    if kind == "python_symbol":
        return _grade_python_symbol(postcondition, fixture_root)
    if kind == "files_unchanged":
        return _grade_files_unchanged(postcondition, fixture_root, manifest)
    if kind == "exec":
        return _grade_exec(postcondition, fixture_root)
    if kind == "output_contains":
        return _grade_output_contains(postcondition, model_output)
    raise ValueError(f"unknown postcondition type: {kind!r}")


def _grade_all_of(
    postcondition: dict,
    fixture_root: Path,
    model_output: str,
    manifest: dict[str, str] | None,
) -> GradeResult:
    checks: list[CheckResult] = []
    for sub in postcondition["checks"]:
        result = grade(sub, fixture_root, model_output, manifest)
        # A nested all_of contributes its own sub-checks rather than one opaque
        # row, so the report shows leaves and not intermediate nodes.
        if result.checks:
            checks.extend(result.checks)
        else:
            checks.append(
                CheckResult(sub.get("name") or sub["type"], result.passed, result.detail)
            )
    failed = [c for c in checks if not c.passed]
    if failed:
        return GradeResult(
            False,
            f"{len(failed)}/{len(checks)} checks failed: "
            + "; ".join(f"{c.name}: {c.detail}" for c in failed[:3]),
            checks,
        )
    return GradeResult(True, f"all {len(checks)} checks passed", checks)


def _grade_grep(postcondition: dict, fixture_root: Path) -> GradeResult:
    target = fixture_root / postcondition["file"]
    if not target.is_file():
        return GradeResult(False, f"file does not exist: {postcondition['file']}")
    text = target.read_text(encoding="utf-8", errors="replace")
    pattern = postcondition["pattern"]
    if pattern not in text:
        return GradeResult(False, f"pattern not found: {pattern!r}")
    must_not = postcondition.get("must_not_contain")
    if must_not and must_not in text:
        return GradeResult(False, f"stale content still present: {must_not!r}")
    # Occurrence counting is what makes an ambiguous-anchor fixture gradeable:
    # "changed exactly the one occurrence under the named section" is a count
    # assertion, not a substring assertion.
    expect_count = postcondition.get("count")
    if expect_count is not None:
        actual = text.count(pattern)
        if actual != expect_count:
            return GradeResult(
                False, f"expected {expect_count} occurrence(s) of {pattern!r}, found {actual}"
            )
        return GradeResult(True, f"found exactly {expect_count} occurrence(s) of {pattern!r}")
    return GradeResult(True, f"pattern found: {pattern!r}")


def _grade_regex(postcondition: dict, fixture_root: Path) -> GradeResult:
    """Literal substring grading pushes task authors toward trivially anchorable
    edits, because any whitespace or quote-style variation fails a semantically
    correct answer. Regex lets a fixture accept the real answer space."""
    target = fixture_root / postcondition["file"]
    if not target.is_file():
        return GradeResult(False, f"file does not exist: {postcondition['file']}")
    text = target.read_text(encoding="utf-8", errors="replace")
    pattern = postcondition["pattern"]
    flags = re.MULTILINE | (re.DOTALL if postcondition.get("dotall") else 0)
    if not re.search(pattern, text, flags):
        return GradeResult(False, f"regex did not match: {pattern!r}")
    must_not = postcondition.get("must_not_match")
    if must_not and re.search(must_not, text, flags):
        return GradeResult(False, f"forbidden regex matched: {must_not!r}")
    return GradeResult(True, f"regex matched: {pattern!r}")


def _grade_python_symbol(postcondition: dict, fixture_root: Path) -> GradeResult:
    """Assert a function exists with a given signature, structurally.

    `grep "def square(n):"` fails on `def square(n: int) -> int:` which is the
    same function. Parsing removes that whole class of false negative.
    """
    target = fixture_root / postcondition["file"]
    if not target.is_file():
        return GradeResult(False, f"file does not exist: {postcondition['file']}")
    try:
        tree = ast.parse(target.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return GradeResult(False, f"file does not parse: {exc.msg} (line {exc.lineno})")
    name = postcondition["symbol"]
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            expected_args = postcondition.get("args")
            if expected_args is None:
                return GradeResult(True, f"function {name!r} defined")
            actual = [a.arg for a in node.args.args]
            if actual != list(expected_args):
                return GradeResult(
                    False, f"function {name!r} has args {actual}, expected {list(expected_args)}"
                )
            return GradeResult(True, f"function {name!r} defined with args {actual}")
    return GradeResult(False, f"function {name!r} not defined in {postcondition['file']}")


def _grade_files_unchanged(
    postcondition: dict, fixture_root: Path, manifest: dict[str, str] | None
) -> GradeResult:
    """Enforce R6: nothing outside the declared set may be modified or created.

    Fails closed when no manifest was supplied -- silently skipping a scope check
    would make an unenforced run indistinguishable from an enforced one, which is
    the exact ambiguity that let the trace-retention gap go unnoticed.
    """
    if manifest is None:
        return GradeResult(False, "scope check requires a fixture manifest, none supplied")
    from fixtures import hash_tree  # local import; fixtures imports nothing from here

    allowed = set(postcondition.get("allowed", []))
    after = hash_tree(fixture_root)
    modified = sorted(
        p for p, h in after.items() if p in manifest and manifest[p] != h and p not in allowed
    )
    created = sorted(p for p in after if p not in manifest and p not in allowed)
    deleted = sorted(p for p in manifest if p not in after and p not in allowed)
    problems = []
    if modified:
        problems.append(f"modified out of scope: {modified}")
    if created:
        problems.append(f"created out of scope: {created}")
    if deleted:
        problems.append(f"deleted out of scope: {deleted}")
    if problems:
        return GradeResult(False, "; ".join(problems))
    return GradeResult(True, f"no writes outside {sorted(allowed)}")


def _grade_exec(postcondition: dict, fixture_root: Path) -> GradeResult:
    timeout = postcondition.get("timeout", DEFAULT_EXEC_TIMEOUT)
    try:
        completed = subprocess.run(
            postcondition["command"],
            shell=True,
            cwd=fixture_root,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return GradeResult(False, f"postcondition command timed out after {timeout}s")
    if completed.returncode != 0:
        return GradeResult(
            False,
            f"postcondition command exited {completed.returncode}: "
            f"{completed.stderr.strip()[:400]}",
        )
    return GradeResult(True, "postcondition command exited 0")


def _grade_output_contains(postcondition: dict, model_output: str) -> GradeResult:
    value = postcondition["value"]
    if value not in model_output:
        return GradeResult(False, f"expected value not found in model output: {value!r}")
    return GradeResult(True, f"value found in model output: {value!r}")
