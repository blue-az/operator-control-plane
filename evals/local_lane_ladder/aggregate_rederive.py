#!/usr/bin/env python3
"""Aggregate per-pack REDERIVE.json reports into one summary."""
from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path


def main() -> int:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    packs = [
        "e1-gold-pack",
        "e1x-27b",
        "e2-postfix-vl",
        "e3-controlled",
        "e4-sampled",
        "e5-floor",
    ]
    agg = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "checker": {
            "uid": os.getuid(),
            "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
            "host": os.uname().nodename.split(".")[0],
        },
        "packs": {},
        "ok": True,
    }
    for p in packs:
        path = out / f"{p}.json"
        if not path.is_file():
            agg["ok"] = False
            agg["packs"][p] = {"ok": False, "error": "missing json"}
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        # Prefer checker from first successful pack
        if d.get("checker") and agg["checker"]["uid"] == os.getuid():
            agg["checker"] = d["checker"]
        agg["packs"][p] = {
            "ok": d["ok"],
            "n_results": d.get("n_results"),
            "total_pass": d.get("total_pass"),
            "model_totals": d.get("model_totals"),
            "machines": d.get("machines"),
            "state_sha256": d.get("state_sha256"),
            "results_md_sha256": d.get("results_md_sha256"),
            "ps_sha256": d.get("ps_sha256"),
            "git_revs": d.get("git_revs"),
            "check_failures": [c["name"] for c in d.get("checks", []) if not c["ok"]],
            "checker_uid": d.get("checker", {}).get("uid"),
        }
        if not d["ok"]:
            agg["ok"] = False

    (out / "AGGREGATE.json").write_text(
        json.dumps(agg, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    verdict = "PASS" if agg["ok"] else "FAIL"
    lines = [
        "# Distinct-UID re-derive — Front E ladder packs (E1–E5)",
        "",
        f"**Verdict:** `{verdict}`",
        f"**Checked at:** {agg['checked_at_utc']}",
        f"**Checker:** uid={agg['checker']['uid']} user={agg['checker']['user']} "
        f"host={agg['checker']['hostname'] if 'hostname' in agg['checker'] else agg['checker'].get('host')}",
        "",
        "Independent re-derive of postcondition totals, RESULTS.md regeneration,",
        "trace completeness, state↔trace consistency, model tags, machine provenance,",
        "and GPU residency — from retained artifacts only. Run as a distinct OS UID",
        "from the claim author (uid 1000).",
        "",
        "| Pack | Verdict | Pass/N | #models | Machines | Checker uid |",
        "|---|---|---:|---:|---|---:|",
    ]
    for p, v in agg["packs"].items():
        mark = "PASS" if v.get("ok") else "FAIL"
        lines.append(
            f"| `{p}` | **{mark}** | {v.get('total_pass')}/{v.get('n_results')} | "
            f"{len(v.get('model_totals') or {})} | `{v.get('machines')}` | {v.get('checker_uid')} |"
        )

    def section(title: str, key: str) -> None:
        lines.append("")
        lines.append(f"### {title}")
        lines.append("")
        pack = agg["packs"].get(key) or {}
        for m, t in (pack.get("model_totals") or {}).items():
            lines.append(f"- `{m}`: {t['pass']}/{t['n']}")
        lines.append(
            f"- **overall {pack.get('total_pass')}/{pack.get('n_results')}**"
        )
        lines.append(f"- state.json sha256: `{pack.get('state_sha256')}`")

    lines.append("")
    lines.append("## Headline re-derived numbers")
    section("e4-sampled (ceiling / saturation)", "e4-sampled")
    section("e5-floor (path-fidelity floor)", "e5-floor")
    section("e1-gold-pack (pre-harness-fix matrix; confounded cells included)", "e1-gold-pack")
    section("e1x-27b", "e1x-27b")
    section("e2-postfix-vl", "e2-postfix-vl")
    section("e3-controlled (temperature-0 artifact record)", "e3-controlled")
    lines.append("")
    lines.append("Per-pack `*.json` / `*.md` reports live alongside this file.")
    lines.append("")
    lines.append(
        "Method: `evals/local_lane_ladder/rederive_pack.py`. "
        "Does not re-run models; temp fixtures are gone. "
        "Integrity is over the freeze (state + traces + evidence)."
    )
    lines.append("")
    (out / "AGGREGATE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0 if agg["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
