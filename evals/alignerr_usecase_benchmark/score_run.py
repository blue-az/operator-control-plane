#!/usr/bin/env python3
"""Deterministic keyword scorer for Alignerr-derived benchmark runs.

The scorer is intentionally simple and auditable. It is a first-pass triage, not
an LLM judge.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CHECKS = {
    "aub1_code_preference": [
        ("prefers_a", [r"PREFERENCE:\s*A", r"A Preferred|Response A"]),
        ("narrow_localized", [r"narrow|localized|less invasive|mergeable"]),
        ("workaround_risk", [r"reset[- ]?index|rebuild[- ]?index|workaround|semantics"]),
        ("todo_detected", [r"TODO"]),
        ("verification_gap", [r"verification gap|unverified|without verification|not prove|no real verification"]),
    ],
    "aub2_dispute_rederivation": [
        ("dispute_is_claim", [r"claim[^.]{0,40}not[^.]{0,40}verdict|not a verdict|claim, not"]),
        ("rederive_file_set", [r"re-derive|rederive|independent.*file|file set"]),
        ("recompute_arithmetic", [r"arithmetic|re-sum|resum|recompute|sum"]),
        ("decompose_subclaims", [r"subclaims|sub-claims|each proposed|individually|separately"]),
        ("literal_rules", [r"literal|rule text|exclusion|query"]),
        ("claim_evidence_workflow", [r"claim/evidence|evidence|ledger|review"]),
        ("hold_clarification", [r"hold|clarification|ambiguous"]),
    ],
    "aub3_mujoco_verification": [
        ("closed_form", [r"closed[- ]form"]),
        ("mj_forward", [r"mj_forward"]),
        ("not_mj_step", [r"not mj_step|mj_step.*dynamics|never mj_step"]),
        ("support_equals_weight", [r"support.*weight|force.*weight"]),
        ("self_contact", [r"self[- ]contact|grandparent"]),
        ("gpu_cpu_crossover", [r"1379|744|23x|68\.3|3\.0|GPU.*slower|crossover"]),
        ("throughput_not_convergence", [r"throughput.*not convergence|not convergence|scope"]),
        ("mjx_distinction", [r"MJX|Gym-MuJoCo|GPU physics"]),
    ],
}


def passed(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, re.IGNORECASE | re.DOTALL) for p in patterns)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir", type=Path)
    args = parser.parse_args()

    manifest = json.loads((args.run_dir / "manifest.json").read_text())
    rows = []
    totals: dict[str, dict[str, float]] = {}
    for item in manifest["results"]:
        text = (args.run_dir / item["stdout_path"]).read_text(errors="replace")
        checks = CHECKS[item["task"]]
        got = {name: passed(text, pats) for name, pats in checks}
        score = sum(got.values())
        max_score = len(checks)
        row = {**item, "score": score, "max_score": max_score, "checks": got}
        rows.append(row)
        totals.setdefault(item["label"], {"score": 0, "max_score": 0, "elapsed_s": 0})
        totals[item["label"]]["score"] += score
        totals[item["label"]]["max_score"] += max_score
        totals[item["label"]]["elapsed_s"] += item["elapsed_s"]

    report = {"run_dir": str(args.run_dir), "rows": rows, "totals": totals}
    (args.run_dir / "scores.json").write_text(json.dumps(report, indent=2))

    print("# Alignerr use-case benchmark scores")
    print()
    print("| model | task | score | elapsed_s |")
    print("|---|---|---:|---:|")
    for row in rows:
        print(f"| {row['label']} | {row['task']} | {row['score']}/{row['max_score']} | {row['elapsed_s']} |")
    print()
    print("| model | total | elapsed_s |")
    print("|---|---:|---:|")
    for label, total in sorted(totals.items(), key=lambda kv: (-kv[1]["score"], kv[1]["elapsed_s"])):
        print(f"| {label} | {int(total['score'])}/{int(total['max_score'])} | {round(total['elapsed_s'], 3)} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
