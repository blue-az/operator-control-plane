#!/usr/bin/env python3
"""Generate the Operator-wide dashboard hub."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timezone
from html import escape
from pathlib import Path

import yaml
from operator_project_board import extra_nav_links

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / ".operator" / "tasks"
CLAIMS = ROOT / ".operator" / "claims"
OUT = ROOT / "docs" / "boards" / "operator.html"


def verified_claim_ids() -> set[str]:
    # Task records list claim IDs; the verification state lives on the claim record.
    ids = set()
    for path in CLAIMS.glob("*.yaml"):
        try:
            claim = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        if claim.get("verification_status") is True:
            ids.add(str(claim.get("claim_id") or path.stem))
    return ids


def main() -> None:
    verified_ids = verified_claim_ids()
    groups = defaultdict(list)
    for path in TASKS.glob("*.yaml"):
        try:
            task = yaml.safe_load(path.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        tid = str(task.get("task_id") or path.stem)
        family = tid.split("-", 1)[0]
        groups[family].append(task | {"task_id": tid})

    def summarize(items: list[dict]) -> tuple[int, str]:
        statuses = defaultdict(int)
        verified = 0
        for task in items:
            statuses[str(task.get("status") or "unknown")] += 1
            verified += sum(1 for c in task.get("claims") or [] if str(c) in verified_ids)
        return verified, ", ".join(f"{n} {s}" for s, n in sorted(statuses.items()))

    rows = []
    singles = []
    for family in sorted(groups):
        items = groups[family]
        if len(items) == 1:
            # A one-task "family" is just a task whose ID prefix is unique; fold it below.
            singles.append(items[0])
            continue
        verified, status = summarize(items)
        link = ""
        if family == "pi":
            link = ' <a href="pi-operator-extension.html">open board</a>'
        elif (OUT.parent / f"{family}.html").exists():
            link = f' <a href="{escape(family)}.html">open board</a>'
        rows.append(
            f"<tr><td><strong>{escape(family)}</strong></td><td>{len(items)}</td><td>{verified}</td><td>{escape(status)}</td><td>{link}</td></tr>"
        )
    if singles:
        verified, status = summarize(singles)
        listing = "".join(
            f"<li><code>{escape(t['task_id'])}</code> · {escape(str(t.get('status') or 'unknown'))}</li>"
            for t in sorted(singles, key=lambda t: t["task_id"])
        )
        rows.append(
            f"<tr><td><details><summary><strong>other</strong> ({len(singles)} one-task prefixes)</summary>"
            f"<ul>{listing}</ul></details></td><td>{len(singles)}</td><td>{verified}</td><td>{escape(status)}</td><td></td></tr>"
        )
    total = sum(map(len, groups.values()))
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Operator Dashboard Hub</title><style>
body{{margin:0;background:#0f1419;color:#e8eef4;font:15px/1.45 system-ui,sans-serif}}main{{max-width:1100px;margin:auto;padding:32px}}nav a,a{{color:#59c2ff;text-decoration:none;margin-right:14px}}h1{{margin-bottom:4px}}.sub{{color:#9aa8b4}}.kpis{{display:flex;gap:12px;flex-wrap:wrap}}.kpi,section{{background:#1a222c;border-radius:12px;padding:16px}}.kpi b{{display:block;font-size:24px}}table{{width:100%;border-collapse:collapse;margin-top:20px}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #33404c}}th{{color:#9aa8b4}}td{{vertical-align:top}}summary{{cursor:pointer}}details ul{{margin:8px 0 0;padding-left:18px;color:#9aa8b4}}
</style></head><body><main><nav><a href="pi-operator-extension.html">Pi extension board</a>{extra_nav_links()}</nav>
<h1>Operator Dashboard Hub</h1><p class="sub">Whole-ledger view · snapshot {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} · family summaries, not a verification authority</p>
<div class="kpis"><div class="kpi"><b>{total}</b>tasks</div><div class="kpi"><b>{len(groups) - len(singles)}</b>families</div><div class="kpi"><b>{len(singles)}</b>one-off tasks</div><div class="kpi"><b>{sum(1 for g in groups.values() for t in g if t.get('status') == 'verified')}</b>verified tasks</div></div>
<section><table><thead><tr><th>FAMILY</th><th>TASKS</th><th>VERIFIED CLAIMS</th><th>STATUS BREAKDOWN</th><th>LINK</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section></main></body></html>"""
    OUT.write_text(html)
    print(
        f"Wrote {OUT} ({total} tasks, {len(groups) - len(singles)} families, {len(singles)} one-off tasks)"
    )


if __name__ == "__main__":
    main()
