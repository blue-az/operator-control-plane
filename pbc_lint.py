#!/usr/bin/env python3
"""Lint Product Behavior Contracts. Fail-closed on four invariants.

See docs/PROPOSAL_LIFECYCLE.md §4. Parser over fenced blocks, not a semantic
checker. Invariant 2 (proposed blocks reachable from a frozen claim) runs only
when --ledger is given; CI without a ledger still checks 1, 3, and 4.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

FENCE_RE = re.compile(r"^```pbc:([^\n`]+)\n(.*?)```", re.MULTILINE | re.DOTALL)
ID_RE = re.compile(r"^(?:-\s+)?id:\s*(\S+)", re.MULTILINE)
STATUS_RE = re.compile(r"^status:\s*(\S+)", re.MULTILINE)
TRUST_PROPOSED_RE = re.compile(r"^\s*trust:\s*proposed\s*$", re.MULTILINE)
PROPOSED_KINDS = {"proposed-rules", "proposed-behavior", "proposed-outcomes"}
RATIFIED_KIND = "rules"


def _iter_pbc_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.pbc.md")))
    return files


def _blocks(text: str) -> list[tuple[str, str]]:
    return [(m.group(1).strip(), m.group(2)) for m in FENCE_RE.finditer(text)]


def _ids(body: str) -> set[str]:
    return {m.group(1).rstrip(",") for m in ID_RE.finditer(body)}


def _ledger_mentions(ledger: Path) -> set[str]:
    names: set[str] = set()
    claims_dir = ledger / "claims"
    if not claims_dir.is_dir():
        return names
    for path in claims_dir.glob("*.yaml"):
        text = path.read_text(encoding="utf-8")
        names.update(re.findall(r"[\w./-]+\.pbc\.md", text))
    evidence_root = ledger / "evidence"
    if evidence_root.is_dir():
        for path in evidence_root.rglob("*.yaml"):
            text = path.read_text(encoding="utf-8")
            names.update(re.findall(r"[\w./-]+\.pbc\.md", text))
    return {Path(name).name for name in names}


def lint_file(path: Path, ledger_names: set[str] | None) -> list[str]:
    text = path.read_text(encoding="utf-8")
    blocks = _blocks(text)
    errors: list[str] = []
    status_match = STATUS_RE.search(text.split("---", 2)[1] if text.startswith("---") else text)
    status = status_match.group(1) if status_match else None
    rules_bodies = [body for kind, body in blocks if kind == RATIFIED_KIND]
    proposed_ids: set[str] = set()
    ratified_ids: set[str] = set()
    has_proposed = False
    for kind, body in blocks:
        ids = _ids(body)
        if kind == RATIFIED_KIND:
            ratified_ids |= ids
            if TRUST_PROPOSED_RE.search(body):
                errors.append(f"{path}: pbc:rules carries trust: proposed")
        if kind in PROPOSED_KINDS:
            has_proposed = True
            proposed_ids |= ids
    overlap = proposed_ids & ratified_ids
    if overlap:
        errors.append(f"{path}: rule IDs in both proposed and ratified fences: {sorted(overlap)}")
    if status == "active" and not rules_bodies:
        errors.append(f"{path}: status: active has no pbc:rules block")
    if has_proposed and ledger_names is not None and path.name not in ledger_names:
        errors.append(f"{path}: pbc:proposed-* is not reachable from a frozen claim")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint PBC fences (PROPOSAL_LIFECYCLE.md §4).")
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[Path("owners-manual/pbc")],
        help="PBC files or directories (default: owners-manual/pbc).",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Optional .operator dir. Enables invariant 2 (proposed blocks need a claim).",
    )
    args = parser.parse_args(argv)
    ledger_names = _ledger_mentions(args.ledger) if args.ledger else None
    errors: list[str] = []
    files = _iter_pbc_files(args.paths)
    if not files:
        print("Error: no PBC files found.", file=sys.stderr)
        return 1
    for path in files:
        errors.extend(lint_file(path, ledger_names))
    for err in errors:
        print(err, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
