#!/usr/bin/env python3
"""Evaluate the falsifiable artifact gate for the Pi Operator dogfood task."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys
import yaml


def load(path: Path) -> dict:
    value = yaml.safe_load(path.read_text())
    return value if isinstance(value, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("task", help="task id")
    parser.add_argument("--ledger", default=".operator", type=Path)
    args = parser.parse_args()
    root = args.ledger
    task_path = root / "tasks" / f"{args.task}.yaml"
    checks: list[tuple[str, bool]] = [("task record exists", task_path.is_file())]
    task = load(task_path) if task_path.is_file() else {}
    claim_paths = [root / "claims" / f"{cid}.yaml" for cid in task.get("claims", [])]
    claims = [load(path) for path in claim_paths if path.is_file()]
    checks.append(("claim with verify_cmd", any(str(c.get("verify_cmd", "")).strip() for c in claims)))
    evidence_dir = root / "evidence" / args.task
    evidence = [load(path) for path in evidence_dir.glob("*.yaml")] if evidence_dir.is_dir() else []
    checks.append(("run_log evidence", any(e.get("evidence_type") == "run_log" for e in evidence)))
    delegation_dir = root / "review_delegations"
    bundles = [load(path) for path in delegation_dir.glob("*.yaml")] if delegation_dir.is_dir() else []
    checks.append(("review delegation bundle", any(b.get("task_id") == args.task for b in bundles)))
    handoff_dir = root / "handoffs" / args.task
    checks.append(("handoff", handoff_dir.is_dir() and any(handoff_dir.glob("*.yaml"))))
    trusted = False
    for claim in claims:
        author = (claim.get("author_executor") or {}).get("uid")
        verifier = (claim.get("verification_executor") or {}).get("uid")
        if claim.get("verification_status") is True and claim.get("verification_authority") == "uid_isolated" and author != verifier:
            trusted = True
    advisory = any("advisory" in str(c.get("verdict", "")).lower() for c in claims)
    checks.append(("distinct verifier or explicit advisory outcome", trusted or advisory))
    failed = [name for name, ok in checks if not ok]
    for name, ok in checks:
        print(f"{'PASS' if ok else 'FAIL'}: {name}")
    if failed:
        print(f"DOGFOOD GATE: FAIL ({len(failed)} unmet)")
        return 1
    print("DOGFOOD GATE: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
