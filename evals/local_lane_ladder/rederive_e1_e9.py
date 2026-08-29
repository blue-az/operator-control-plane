#!/usr/bin/env python3
"""Distinct-UID re-derive span: Front E packs e1 through e9 (plus e1x).

Discovers pack roots (including e6 on/off sub-packs), runs rederive_pack on each,
writes an aggregate report. Exit 0 only if every pack PASSes.

Usage:
  python3 rederive_e1_e9.py [--out DIR] [--expected-machine desktop]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rederive_pack import rederive_pack, render_md

# Logical span for Front E freeze integrity (e0 excluded: harness-repro only).
SPAN: list[tuple[str, str]] = [
    ("e1-gold-pack", "fixtures/e1-gold-pack"),
    ("e1x-27b", "fixtures/e1x-27b"),
    ("e2-postfix-vl", "fixtures/e2-postfix-vl"),
    ("e3-controlled", "fixtures/e3-controlled"),
    ("e4-sampled", "fixtures/e4-sampled"),
    ("e5-floor", "fixtures/e5-floor"),
    ("e6-think-ab/on", "fixtures/e6-think-ab/on"),
    ("e6-think-ab/off", "fixtures/e6-think-ab/off"),
    ("e7-unused-fixtures", "fixtures/e7-unused-fixtures"),
    ("e8-ceiling", "fixtures/e8-ceiling"),
    ("e9-ceiling-continued", "fixtures/e9-ceiling-continued"),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Directory for per-pack JSON/MD + AGGREGATE (default: under .operator evidence)",
    )
    ap.add_argument("--expected-machine", default="desktop")
    args = ap.parse_args()

    ladder = Path(__file__).resolve().parent
    out = args.out
    if out is None:
        out = (
            ladder.parents[1]
            / ".operator"
            / "evidence"
            / "front-e1-gold-pack"
            / "rederive-e1-e9"
        )
    out = out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    reports: dict[str, dict] = {}
    all_ok = True
    for name, rel in SPAN:
        pack = ladder / rel
        safe = name.replace("/", "__")
        report = rederive_pack(pack, expected_machine=args.expected_machine)
        report["span_name"] = name
        reports[name] = report
        (out / f"{safe}.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (out / f"{safe}.md").write_text(render_md(report), encoding="utf-8")
        mark = "PASS" if report["ok"] else "FAIL"
        print(f"{mark} {name}  {report.get('total_pass')}/{report.get('n_results')}")
        if not report["ok"]:
            all_ok = False
            for c in report.get("checks", []):
                if not c["ok"]:
                    print(f"  - {c['name']}: {c['detail'][:160]}")

    agg = {
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "checker": {
            "uid": os.getuid(),
            "user": os.environ.get("USER") or os.environ.get("LOGNAME") or "unknown",
            "host": os.uname().nodename.split(".")[0],
        },
        "span": "e1-e9 (+e1x; e6 as on/off)",
        "ok": all_ok,
        "packs": {
            name: {
                "ok": r["ok"],
                "n_results": r.get("n_results"),
                "total_pass": r.get("total_pass"),
                "model_totals": r.get("model_totals"),
                "machines": r.get("machines"),
                "state_sha256": r.get("state_sha256"),
                "results_md_sha256": r.get("results_md_sha256"),
                "ps_sha256": r.get("ps_sha256"),
                "git_revs": r.get("git_revs"),
                "check_failures": [c["name"] for c in r.get("checks", []) if not c["ok"]],
            }
            for name, r in reports.items()
        },
    }
    (out / "AGGREGATE.json").write_text(
        json.dumps(agg, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# Distinct-UID re-derive — Front E span e1–e9",
        "",
        f"**Verdict:** `{'PASS' if all_ok else 'FAIL'}`",
        f"**Checked at:** {agg['checked_at_utc']}",
        f"**Checker:** uid={agg['checker']['uid']} user={agg['checker']['user']} "
        f"host={agg['checker']['host']}",
        "",
        "Independent re-derive of postcondition totals, RESULTS.md, traces, machine",
        "provenance, and GPU residency (where evidence exists) across the Front E ladder.",
        "",
        "| Pack | Verdict | Pass/N | #models | Machines |",
        "|---|---|---:|---:|---|",
    ]
    for name, v in agg["packs"].items():
        mark = "PASS" if v["ok"] else "FAIL"
        lines.append(
            f"| `{name}` | **{mark}** | {v['total_pass']}/{v['n_results']} | "
            f"{len(v.get('model_totals') or {})} | `{v.get('machines')}` |"
        )
    # Headline seats from e9
    e9 = reports.get("e9-ceiling-continued") or {}
    if e9.get("model_totals"):
        lines += ["", "## E9 ceiling battery (re-derived totals)", ""]
        for m, t in e9["model_totals"].items():
            lines.append(f"- `{m}`: {t['pass']}/{t['n']}")
        lines.append(f"- **overall {e9.get('total_pass')}/{e9.get('n_results')}**")
    lines += ["", f"Artifacts: `{out}`", ""]
    md = "\n".join(lines) + "\n"
    (out / "AGGREGATE.md").write_text(md, encoding="utf-8")
    print(md)
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
