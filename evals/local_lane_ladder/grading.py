"""Deterministic postcondition grading for the local-lane eval ladder.

No LLM judging, per LOCAL_LANE_CONTRACT_SPEC.md Deliverable 3 -- every
postcondition type here is a grep, an exit-code check, or a substring check
against the model's own final text, nothing else.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GradeResult:
    passed: bool
    detail: str


def grade(postcondition: dict, fixture_root: Path, model_output: str) -> GradeResult:
    kind = postcondition["type"]
    if kind == "grep":
        return _grade_grep(postcondition, fixture_root)
    if kind == "exec":
        return _grade_exec(postcondition, fixture_root)
    if kind == "output_contains":
        return _grade_output_contains(postcondition, model_output)
    raise ValueError(f"unknown postcondition type: {kind!r}")


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
    return GradeResult(True, f"pattern found: {pattern!r}")


def _grade_exec(postcondition: dict, fixture_root: Path) -> GradeResult:
    try:
        completed = subprocess.run(
            postcondition["command"],
            shell=True,
            cwd=fixture_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return GradeResult(False, "postcondition command timed out")
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
