#!/usr/bin/env python3
"""Emit a simple static HTML board for one Operator task-id prefix.

This is not Graphify. It is a one-page status board: ladder, tasks,
claim ratios, stale next_action, recent issues, future features.
Ledger-local; regenerate whenever you want a fresh snapshot.
"""

from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]


PREFIX_DEFAULT = "pi-operator-extension"
LADDER = [
    (0, "PBC lifecycle shape"),
    (1, "Read-only orientation"),
    (2, "Claim / evidence / handoff"),
    (3, "Supervisor-review"),
    (4, "Delegate chooser"),
    (5, "Falsifiable dogfood"),
]


def load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        return data if isinstance(data, dict) else {}
    # Tiny fallback: enough for Operator task/claim records.
    out: dict = {}
    for line in text.splitlines():
        if re.match(r"^\s", line) or ":" not in line:
            continue
        key, _, val = line.partition(":")
        out[key.strip()] = val.strip().strip("'\"")
    return out


def parse_pbc_lists(pbc: Path) -> tuple[list[dict], list[dict]]:
    issues: list[dict] = []
    features: list[dict] = []
    if not pbc.exists():
        return issues, features
    section = ""
    current: dict | None = None
    bucket: list[dict] | None = None
    for raw in pbc.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.startswith("## Future Feature Candidates"):
            if current and bucket is not None:
                bucket.append(current)
            section, current, bucket = "future", None, features
            continue
        if line.startswith("## Dogfood Issue Backlog"):
            if current and bucket is not None:
                bucket.append(current)
            section, current, bucket = "issues", None, issues
            continue
        if line.startswith("## "):
            if current and bucket is not None:
                bucket.append(current)
            section, current, bucket = "", None, None
            continue
        if section not in {"future", "issues"}:
            continue
        id_match = re.match(r"\s+- id:\s+(\S+)", line)
        if id_match:
            if current and bucket is not None:
                bucket.append(current)
            current = {"id": id_match.group(1)}
            continue
        if current is None:
            continue
        m = re.match(r"\s+(name|command|description|summary|next_step):\s*(.*)$", line)
        if m:
            current[m.group(1)] = m.group(2).strip().strip('"')
    if current and bucket is not None:
        bucket.append(current)
    return issues, features


def collect(root: Path, prefix: str) -> dict:
    ledger = root / ".operator"
    tasks_dir = ledger / "tasks"
    claims_dir = ledger / "claims"
    rows = []
    for path in sorted(tasks_dir.glob("*.yaml")):
        data = load_yaml(path)
        tid = str(data.get("task_id") or path.stem)
        if not tid.startswith(prefix):
            continue
        claims = []
        for cpath in claims_dir.glob("claim-*.yaml"):
            c = load_yaml(cpath)
            if c.get("task_id") != tid:
                continue
            claims.append(
                {
                    "id": cpath.stem,
                    "verified": bool(c.get("verification_status")),
                    "text": str(c.get("text") or "")[:180],
                }
            )
        claims.sort(key=lambda x: x["id"])
        evid_dir = ledger / "evidence" / tid
        hand_dir = ledger / "handoffs" / tid
        evid = len(list(evid_dir.glob("evidence-*.yaml"))) if evid_dir.exists() else 0
        hands = len(list(hand_dir.glob("handoff-*.yaml"))) if hand_dir.exists() else 0
        next_action = str(data.get("next_action") or "")
        status = str(data.get("status") or "?")
        stale = bool(
            re.search(r"/op:handoff\s+go\b|Reload Pi|proceed to Step", next_action, re.I)
            and status in {"verified", "quarantined"}
        )
        rows.append(
            {
                "id": tid,
                "status": status,
                "next": next_action,
                "updated": str(data.get("updated_at") or ""),
                "assigned": str(data.get("assigned_harness") or ""),
                "review": str(data.get("review_harness") or ""),
                "claims": claims,
                "verified": sum(1 for c in claims if c["verified"]),
                "total": len(claims),
                "evidence": evid,
                "handoffs": hands,
                "stale": stale,
                "latest_verified": next((c["id"] for c in reversed(claims) if c["verified"]), None),
            }
        )
    issues, features = parse_pbc_lists(
        root / "owners-manual" / "pbc" / "appendix-pi-operator-extension.pbc.md"
    )
    return {
        "prefix": prefix,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tasks": rows,
        "issues": issues[-8:],
        "features": features[-10:],
    }


def render(data: dict) -> str:
    tasks = data["tasks"]
    verified_tasks = sum(1 for t in tasks if t["status"] == "verified")
    stale = sum(1 for t in tasks if t["stale"])
    vclaims = sum(t["verified"] for t in tasks)
    tclaims = sum(t["total"] for t in tasks)

    def esc(s: object) -> str:
        return html.escape(str(s or ""), quote=True)

    cards = []
    for t in tasks:
        pct = int(100 * t["verified"] / t["total"]) if t["total"] else 0
        cards.append(
            f"""
<article class="card status-{esc(t['status'])}{' stale' if t['stale'] else ''}">
  <header>
    <h2><a href="{esc(t['id'])}-resolution.html">{esc(t['id'])}</a></h2>
    <span class="pill">{esc(t['status'])}</span>
  </header>
  <div class="bar"><i style="width:{pct}%"></i></div>
  <p class="meta">{t['verified']}/{t['total']} claims verified · {t['evidence']} evidence · {t['handoffs']} handoffs</p>
  <p class="next">{'STALE · ' if t['stale'] else ''}{esc(t['next'][:220] or '(no next_action)')}</p>
  <p class="meta">latest verified: {esc(t['latest_verified'] or 'none')} · updated {esc(t['updated'][:19])}</p>
</article>"""
        )

    issues = "".join(
        f"<li><strong>{esc(i.get('id'))}</strong> {esc(i.get('summary') or i.get('name') or '')}</li>"
        for i in data["issues"]
    ) or "<li>No PBC issues parsed.</li>"
    features = "".join(
        f"<li><strong>{esc(f.get('id'))}</strong> {esc(f.get('command') or '')} — {esc(f.get('name') or '')}</li>"
        for f in data["features"]
    ) or "<li>No future features parsed.</li>"

    payload = json.dumps(data, indent=2)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Operator board · {esc(data['prefix'])}</title>
<style>
  :root {{ --bg:#0f1419; --card:#1a222c; --ink:#e8eef4; --muted:#9aa8b4; --ok:#3dd68c; --warn:#f5c542; --bad:#f07178; --run:#59c2ff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.45 ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--ink); }}
  header.top {{ padding:28px 32px 12px; }}
  .nav {{ color:var(--muted); margin-bottom:10px; }}
  .nav a, .card h2 a {{ color:var(--run); text-decoration:none; }}
  .nav a:hover, .card h2 a:hover {{ text-decoration:underline; }}
  h1 {{ margin:0 0 6px; font-size:28px; font-weight:650; }}
  .sub {{ color:var(--muted); }}
  .kpis {{ display:flex; gap:12px; flex-wrap:wrap; padding:0 32px 20px; }}
  .kpi {{ background:var(--card); padding:12px 16px; border-radius:12px; min-width:120px; }}
  .kpi b {{ display:block; font-size:22px; }}
  .ladder {{ display:flex; gap:8px; padding:0 32px 24px; flex-wrap:wrap; }}
  .step {{ flex:1; min-width:110px; background:var(--card); border-radius:12px; padding:10px 12px; }}
  .step span {{ display:block; color:var(--muted); font-size:12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; padding:0 32px 32px; }}
  .card {{ background:var(--card); border-radius:14px; padding:14px 16px; border-left:4px solid #445; }}
  .status-verified {{ border-left-color:var(--ok); }}
  .status-assigned, .status-new {{ border-left-color:var(--warn); }}
  .status-running {{ border-left-color:var(--run); }}
  .status-quarantined {{ border-left-color:var(--bad); }}
  .card.stale {{ outline:1px dashed var(--warn); }}
  .card header {{ display:flex; justify-content:space-between; gap:8px; align-items:start; }}
  .card h2 {{ margin:0; font-size:14px; font-weight:650; word-break:break-all; }}
  .pill {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; background:#0003; padding:3px 8px; border-radius:999px; }}
  .bar {{ height:6px; background:#0004; border-radius:99px; margin:10px 0 8px; overflow:hidden; }}
  .bar i {{ display:block; height:100%; background:var(--ok); }}
  .meta {{ color:var(--muted); font-size:12px; margin:0 0 8px; }}
  .next {{ margin:0 0 8px; font-size:13px; }}
  section.lists {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; padding:0 32px 48px; }}
  @media (max-width:800px) {{ section.lists {{ grid-template-columns:1fr; }} }}
  ul {{ margin:8px 0 0; padding-left:18px; color:var(--muted); }}
  li {{ margin:0 0 8px; }}
</style>
</head>
<body>
<header class="top">
  <nav class="nav"><a href="pi-operator-extension.html">Project</a> · <a href="pi-operator-extension-issues.html">Issues</a> · <a href="pi-operator-extension-graph.html">Map</a></nav>
  <h1>{esc(data['prefix'])}</h1>
  <p class="sub">Simple Operator board · snapshot {esc(data['generated_at'])} · not Graphify, not a knowledge graph</p>
</header>
<div class="kpis">
  <div class="kpi"><b>{len(tasks)}</b>tasks</div>
  <div class="kpi"><b>{verified_tasks}</b>verified tasks</div>
  <div class="kpi"><b>{vclaims}/{tclaims}</b>claims verified</div>
  <div class="kpi"><b>{stale}</b>stale next_action</div>
</div>
<div class="ladder">
  {''.join(f'<div class="step"><span>Step {n}</span>{esc(name)}</div>' for n,name in LADDER)}
</div>
<div class="grid">
{''.join(cards)}
</div>
<section class="lists">
  <div>
    <h3>Recent PBC issues</h3>
    <ul>{issues}</ul>
  </div>
  <div>
    <h3>Recent future features</h3>
    <ul>{features}</ul>
  </div>
</section>
<script type="application/json" id="board-data">{payload}</script>
</body>
</html>
"""


def collect_issues(root: Path, prefix: str) -> dict:
    issues, _features = parse_pbc_lists(
        root / "owners-manual" / "pbc" / "appendix-pi-operator-extension.pbc.md"
    )
    ledger = root / ".operator"
    mentions: dict[str, list[dict]] = {}
    for cpath in (ledger / "claims").glob("claim-*.yaml"):
        c = load_yaml(cpath)
        blob = f"{c.get('text','')} {c.get('task_id','')} {cpath.stem}"
        for issue in issues:
            iid = issue.get("id") or ""
            if iid and iid in blob:
                mentions.setdefault(iid, []).append(
                    {
                        "id": cpath.stem,
                        "task": c.get("task_id"),
                        "verified": bool(c.get("verification_status")),
                    }
                )
    rows = []
    for issue in issues:
        iid = str(issue.get("id") or "")
        hits = mentions.get(iid, [])
        verified_hits = [h for h in hits if h["verified"]]
        if verified_hits:
            state = "addressed"
        elif hits:
            state = "in-ledger"
        else:
            state = "open"
        source = str(issue.get("source") or "")
        task_hint = None
        m = re.search(r"(pi-operator-extension[-\w]*)", source)
        if m:
            task_hint = m.group(1)
        rows.append(
            {
                "id": iid,
                "state": state,
                "source": source,
                "summary": str(issue.get("summary") or ""),
                "next_step": str(issue.get("next_step") or ""),
                "task_hint": task_hint,
                "claims": hits,
            }
        )
    return {
        "prefix": prefix,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "issues": rows,
    }


def render_issues(data: dict) -> str:
    def esc(s: object) -> str:
        return html.escape(str(s or ""), quote=True)

    issues = data["issues"]
    by = {k: sum(1 for i in issues if i["state"] == k) for k in ("open", "in-ledger", "addressed")}
    cards = []
    for i in issues:
        claims = i["claims"]
        claim_bits = ", ".join(
            f"{c['id']}{' ✓' if c['verified'] else ''}" for c in claims[:6]
        ) or "no matching claims"
        cards.append(
            f"""
<article class="card state-{esc(i['state'])}">
  <header>
    <h2>{esc(i['id'])}</h2>
    <span class="pill">{esc(i['state'])}</span>
  </header>
  <p class="next">{esc(i['summary'][:280])}</p>
  <p class="meta">source: {esc(i['source'][:160])}</p>
  <p class="meta">next: {esc(i['next_step'][:220])}</p>
  <p class="meta">task hint: {esc(i['task_hint'] or 'none')} · claims: {esc(claim_bits)}</p>
</article>"""
        )
    payload = json.dumps(data, indent=2)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Issue board · {esc(data['prefix'])}</title>
<style>
  :root {{ --bg:#0f1419; --card:#1a222c; --ink:#e8eef4; --muted:#9aa8b4; --ok:#3dd68c; --warn:#f5c542; --bad:#f07178; --run:#59c2ff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.45 ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--ink); }}
  header.top {{ padding:28px 32px 12px; }}
  .nav {{ color:var(--muted); margin-bottom:10px; }}
  .nav a {{ color:var(--run); text-decoration:none; }}
  .nav a:hover {{ text-decoration:underline; }}
  h1 {{ margin:0 0 6px; font-size:28px; font-weight:650; }}
  .sub {{ color:var(--muted); }}
  .kpis {{ display:flex; gap:12px; flex-wrap:wrap; padding:0 32px 20px; }}
  .kpi {{ background:var(--card); padding:12px 16px; border-radius:12px; min-width:120px; }}
  .kpi b {{ display:block; font-size:22px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(320px,1fr)); gap:14px; padding:0 32px 48px; }}
  .card {{ background:var(--card); border-radius:14px; padding:14px 16px; border-left:4px solid #445; }}
  .state-open {{ border-left-color:var(--bad); }}
  .state-in-ledger {{ border-left-color:var(--warn); }}
  .state-addressed {{ border-left-color:var(--ok); }}
  .card header {{ display:flex; justify-content:space-between; gap:8px; align-items:start; }}
  .card h2 {{ margin:0; font-size:14px; font-weight:650; }}
  .pill {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; background:#0003; padding:3px 8px; border-radius:999px; }}
  .meta {{ color:var(--muted); font-size:12px; margin:0 0 8px; }}
  .next {{ margin:0 0 8px; font-size:13px; }}
</style>
</head>
<body>
<header class="top">
  <nav class="nav"><a href="pi-operator-extension.html">Project</a> · <a href="pi-operator-extension-issues.html">Issues</a> · <a href="pi-operator-extension-graph.html">Map</a></nav>
  <h1>{esc(data['prefix'])} issues</h1>
  <p class="sub">Issue backlog catalog · snapshot {esc(data['generated_at'])} · PBC dogfood backlog + ledger mentions</p>
</header>
<div class="kpis">
  <div class="kpi"><b>{len(issues)}</b>issues</div>
  <div class="kpi"><b>{by['open']}</b>open (no claim mention)</div>
  <div class="kpi"><b>{by['in-ledger']}</b>in ledger, unverified</div>
  <div class="kpi"><b>{by['addressed']}</b>addressed (verified claim)</div>
</div>
<div class="grid">
{''.join(cards)}
</div>
<script type="application/json" id="board-data">{payload}</script>
</body>
</html>
"""


def collect_resolution(root: Path, task_id: str) -> dict:
    ledger = root / ".operator"
    task_path = ledger / "tasks" / f"{task_id}.yaml"
    task = load_yaml(task_path) if task_path.exists() else {}
    events: list[dict] = []
    claims = []
    for cpath in sorted((ledger / "claims").glob("claim-*.yaml")):
        c = load_yaml(cpath)
        if c.get("task_id") != task_id:
            continue
        claims.append(c)
        events.append(
            {
                "kind": "claim",
                "id": cpath.stem,
                "at": str(c.get("made_at") or ""),
                "actor": str(c.get("made_by") or ""),
                "text": str(c.get("text") or "")[:240],
                "status": "verified" if c.get("verification_status") else ("withdrawn" if c.get("verdict") else "unverified"),
                "lane": "builder",
            }
        )
    evid_dir = ledger / "evidence" / task_id
    if evid_dir.exists():
        for epath in sorted(evid_dir.glob("evidence-*.yaml")):
            e = load_yaml(epath)
            actor = str(e.get("produced_by") or "")
            uid = None
            ex = e.get("executor")
            if isinstance(ex, dict):
                uid = ex.get("uid")
            verifier = actor == "operator-verifier" or uid == 966
            events.append(
                {
                    "kind": "verify" if verifier else "evidence",
                    "id": epath.stem,
                    "at": str(e.get("produced_at") or ""),
                    "actor": actor,
                    "text": f"{e.get('evidence_type') or e.get('type') or 'artifact'} for {e.get('claim_id') or 'task'}",
                    "status": "verifier" if verifier else "builder",
                    "lane": "verifier" if verifier else "builder",
                    "claim": e.get("claim_id"),
                }
            )
    hand_dir = ledger / "handoffs" / task_id
    if hand_dir.exists():
        for hpath in sorted(hand_dir.glob("handoff-*.yaml")):
            h = load_yaml(hpath)
            events.append(
                {
                    "kind": "handoff",
                    "id": h.get("handoff_id") or hpath.stem,
                    "at": str(h.get("created_at") or ""),
                    "actor": str(h.get("by") or ""),
                    "text": str(h.get("next_action") or h.get("what_changed") or "")[:240],
                    "status": "continuity",
                    "lane": "builder",
                }
            )
    rd = ledger / "review_delegations"
    if rd.exists():
        for rpath in sorted(rd.glob("review-claim-*.yaml")):
            r = load_yaml(rpath)
            if r.get("task_id") != task_id:
                continue
            events.append(
                {
                    "kind": "review",
                    "id": r.get("delegation_id") or rpath.stem,
                    "at": str(r.get("created_at") or ""),
                    "actor": str(r.get("reviewer") or ""),
                    "text": f"{r.get('mode')} review of {r.get('claim_id')} as {r.get('review_user') or 'n/a'}",
                    "status": str(r.get("mode") or ""),
                    "lane": "reviewer",
                    "claim": r.get("claim_id"),
                }
            )
    events.sort(key=lambda x: (x.get("at") or "", x.get("id") or ""))
    return {
        "task_id": task_id,
        "status": str(task.get("status") or "?"),
        "objective": str(task.get("objective") or ""),
        "next": str(task.get("next_action") or ""),
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "events": events,
        "claims": [
            {
                "id": c.get("claim_id"),
                "verified": bool(c.get("verification_status")),
                "verdict": str(c.get("verdict") or "")[:160],
            }
            for c in claims
        ],
    }


def render_resolution(data: dict) -> str:
    def esc(s: object) -> str:
        return html.escape(str(s or ""), quote=True)

    events = data["events"]
    counts = {}
    for e in events:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    rows = []
    for e in events:
        rows.append(
            f"""
<div class="ev lane-{esc(e['lane'])} kind-{esc(e['kind'])}">
  <div class="when">{esc((e['at'] or '')[:19].replace('T',' '))}</div>
  <div class="kind">{esc(e['kind'])}</div>
  <div class="body">
    <strong>{esc(e['id'])}</strong>
    <span class="actor">{esc(e['actor'])}</span>
    <p>{esc(e['text'])}</p>
  </div>
</div>"""
        )
    payload = json.dumps(data, indent=2)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Resolution ledger · {esc(data['task_id'])}</title>
<style>
  :root {{ --bg:#0f1419; --card:#1a222c; --ink:#e8eef4; --muted:#9aa8b4; --ok:#3dd68c; --warn:#f5c542; --bad:#f07178; --run:#59c2ff; --hand:#c3a6ff; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; font:15px/1.45 ui-sans-serif,system-ui,sans-serif; background:var(--bg); color:var(--ink); }}
  header.top {{ padding:28px 32px 8px; }}
  .nav {{ color:var(--muted); margin-bottom:10px; }}
  .nav a {{ color:var(--run); text-decoration:none; }}
  .nav a:hover {{ text-decoration:underline; }}
  h1 {{ margin:0 0 6px; font-size:24px; font-weight:650; word-break:break-all; }}
  .sub,.obj {{ color:var(--muted); max-width:80ch; }}
  .flow {{ display:flex; gap:8px; flex-wrap:wrap; padding:16px 32px; }}
  .flow span {{ background:var(--card); padding:8px 12px; border-radius:999px; font-size:13px; }}
  .kpis {{ display:flex; gap:12px; flex-wrap:wrap; padding:0 32px 16px; }}
  .kpi {{ background:var(--card); padding:12px 16px; border-radius:12px; min-width:110px; }}
  .kpi b {{ display:block; font-size:22px; }}
  .timeline {{ padding:0 32px 48px; display:flex; flex-direction:column; gap:8px; }}
  .ev {{ display:grid; grid-template-columns:150px 90px 1fr; gap:12px; background:var(--card); border-radius:12px; padding:10px 14px; border-left:4px solid #445; }}
  .kind-claim {{ border-left-color:var(--warn); }}
  .kind-evidence {{ border-left-color:var(--run); }}
  .kind-review {{ border-left-color:#ffa657; }}
  .kind-verify {{ border-left-color:var(--ok); }}
  .kind-handoff {{ border-left-color:var(--hand); }}
  .when,.kind {{ color:var(--muted); font-size:12px; padding-top:3px; }}
  .kind {{ text-transform:uppercase; letter-spacing:.04em; font-weight:650; }}
  .actor {{ color:var(--muted); font-size:12px; margin-left:8px; }}
  .body p {{ margin:4px 0 0; font-size:13px; color:var(--muted); }}
  @media (max-width:800px) {{ .ev {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<header class="top">
  <nav class="nav"><a href="pi-operator-extension.html">Project</a> · <a href="pi-operator-extension-issues.html">Issues</a> · <a href="pi-operator-extension-graph.html">Map</a></nav>
  <h1>{esc(data['task_id'])}</h1>
  <p class="sub">Issue-resolution ledger · {esc(data['status'])} · snapshot {esc(data['generated_at'])}</p>
  <p class="obj">{esc(data['objective'][:400])}</p>
</header>
<div class="flow">
  <span>1 task</span><span>2 claim</span><span>3 evidence</span><span>4 review bundle</span><span>5 verifier UID evidence</span><span>6 handoff</span>
</div>
<div class="kpis">
  <div class="kpi"><b>{counts.get('claim',0)}</b>claims</div>
  <div class="kpi"><b>{counts.get('evidence',0)}</b>builder evidence</div>
  <div class="kpi"><b>{counts.get('review',0)}</b>reviews</div>
  <div class="kpi"><b>{counts.get('verify',0)}</b>verifier evidence</div>
  <div class="kpi"><b>{counts.get('handoff',0)}</b>handoffs</div>
</div>
<div class="timeline">
{''.join(rows)}
</div>
<script type="application/json" id="board-data">{payload}</script>
</body>
</html>
"""


def task_family(tid: str, prefix: str) -> str:
    rest = tid[len(prefix) :].lstrip("-") if tid.startswith(prefix) else tid
    if rest.startswith("step"):
        return "ladder " + rest.split("-")[0]
    if rest.startswith("pbc"):
        return "spec"
    if "cross-project" in rest:
        return "cross-project"
    if rest in {"next-steps", "project-dashboard", "workflow-guidance", "target-ux-cleanup"} or rest.startswith("target-ux"):
        return "follow-on"
    return "other"


def write_graph_html(root: Path, prefix: str, out: Path) -> None:
    project = collect(root, prefix)
    issues = collect_issues(root, prefix)
    families: dict[str, list[dict]] = {}
    order = ["spec", "ladder step1", "ladder step2", "ladder step3", "ladder step4", "ladder step5", "follow-on", "cross-project", "other"]
    for t in project["tasks"]:
        families.setdefault(task_family(t["id"], prefix), []).append(t)
    for key in families:
        if key not in order:
            order.append(key)

    def esc(s: object) -> str:
        return html.escape(str(s or ""), quote=True)

    cols = []
    for fam in order:
        items = families.get(fam) or []
        if not items:
            continue
        cards = []
        for t in items:
            short = t["id"].replace(prefix + "-", "")
            chips = "".join(
                f'<span class="chip {"ok" if c["verified"] else "no"}">{esc(c["id"])}</span>'
                for c in t["claims"]
            )
            cards.append(
                f'<a class="node status-{esc(t["status"])}" href="{esc(t["id"])}-resolution.html"><strong>{esc(short)}</strong><em>{esc(t["status"])} · {t["verified"]}/{t["total"]}</em>{chips}</a>'
            )
        cols.append(f'<section><h2>{esc(fam)}</h2>{"".join(cards)}</section>')
    iss = "".join(
        f'<span class="chip {esc(i["state"])}">{esc(i["id"])}</span>' for i in issues["issues"]
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Project map · {esc(prefix)}</title>
<style>
  body {{ margin:0; background:#0f1419; color:#e8eef4; font:14px/1.4 ui-sans-serif,system-ui; }}
  nav {{ padding:16px 24px 0; }}
  nav a {{ color:#59c2ff; text-decoration:none; margin-right:12px; }}
  h1 {{ margin:8px 24px 4px; font-size:24px; }}
  .sub {{ margin:0 24px 16px; color:#9aa8b4; }}
  .cols {{ display:flex; gap:14px; overflow-x:auto; padding:0 24px 24px; align-items:flex-start; }}
  section {{ min-width:220px; background:#1a222c; border-radius:14px; padding:12px; }}
  h2 {{ margin:0 0 10px; font-size:13px; color:#9aa8b4; text-transform:uppercase; letter-spacing:.04em; }}
  .node {{ display:block; background:#10161c; border-radius:10px; padding:10px; margin:0 0 8px; color:inherit; text-decoration:none; border-left:4px solid #445; }}
  .status-verified {{ border-left-color:#3dd68c; }}
  .status-assigned,.status-new {{ border-left-color:#f5c542; }}
  .status-running {{ border-left-color:#59c2ff; }}
  .status-quarantined {{ border-left-color:#f07178; }}
  .node strong {{ display:block; }}
  .node em {{ color:#9aa8b4; font-style:normal; font-size:12px; }}
  .chip {{ display:inline-block; margin:6px 4px 0 0; padding:2px 6px; border-radius:999px; background:#0004; font-size:11px; }}
  .chip.ok,.chip.addressed {{ color:#3dd68c; }}
  .chip.no,.chip.open {{ color:#f07178; }}
  .issues {{ margin:0 24px 40px; }}
</style>
</head>
<body>
<nav><a href="pi-operator-extension.html">Project</a> <a href="pi-operator-extension-issues.html">Issues</a></nav>
<h1>{esc(prefix)}</h1>
<p class="sub">Whole-project map · click a task for its resolution ledger · not Obsidian, not floating dots</p>
<div class="cols">{''.join(cols)}</div>
<div class="issues"><h2>Issues</h2>{iss}</div>
</body></html>
""",
        encoding="utf-8",
    )


def write_obsidian(root: Path, prefix: str, out: Path) -> int:
    project = collect(root, prefix)
    issues = collect_issues(root, prefix)
    out.mkdir(parents=True, exist_ok=True)
    count = 0

    def w(name: str, body: str) -> None:
        nonlocal count
        (out / f"{name}.md").write_text(body.strip() + "\n", encoding="utf-8")
        count += 1

    task_links = "\n".join(f"- [[{t['id']}]] `{t['status']}` {t['verified']}/{t['total']}" for t in project["tasks"])
    issue_links = "\n".join(f"- [[{i['id']}]] `{i['state']}`" for i in issues["issues"])
    w(
        "00-project",
        f"""# {prefix}\n\nOperator project map. Open this folder as an Obsidian vault and use Graph view.\n\nHTML: [[pi-operator-extension]] boards are separate.\n\n## Tasks\n{task_links}\n\n## Issues\n{issue_links}\n""",
    )
    for t in project["tasks"]:
        resolution = collect_resolution(root, t["id"])
        claim_links = "\n".join(
            f"- [[{c['id']}]]" for c in t["claims"]
        ) or "- (none)"
        event_links = "\n".join(
            f"- {e['kind']}: `{e['id']}` {e.get('actor','')}" for e in resolution["events"][:40]
        )
        issue_hits = [i for i in issues["issues"] if i.get("task_hint") == t["id"] or t["id"] in (i.get("source") or "")]
        iss = "\n".join(f"- [[{i['id']}]]" for i in issue_hits) or "- (none named)"
        w(
            t["id"],
            f"""# {t['id']}\n\nstatus: `{t['status']}`\n\nback to [[00-project]]\n\n## Claims\n{claim_links}\n\n## Related issues\n{iss}\n\n## Ledger events\n{event_links}\n\n## Next\n{t['next']}\n""",
        )
        for c in t["claims"]:
            w(
                c["id"],
                f"""# {c['id']}\n\ntask: [[{t['id']}]]\nverified: `{c['verified']}`\n\n{c['text']}\n\n[[00-project]]\n""",
            )
    for i in issues["issues"]:
        claim_links = "\n".join(f"- [[{c['id']}]] on [[{c['task']}]]" for c in i["claims"]) or "- (no claims)"
        task = f"[[{i['task_hint']}]]" if i.get("task_hint") else "(none)"
        w(
            i["id"],
            f"""# {i['id']}\n\nstate: `{i['state']}`\nsource: {i['source']}\ntask hint: {task}\n\n{i['summary']}\n\n## Next step\n{i['next_step']}\n\n## Claims\n{claim_links}\n\n[[00-project]]\n""",
        )
    w(
        "README",
        f"""# Obsidian Operator map\n\nOpen **this folder** as an Obsidian vault.\n\n1. Obsidian → Open folder as vault → `docs/boards/obsidian`\n2. Open [[00-project]]\n3. Open Graph view\n\nThis is a generated wiki-link map of the Operator ledger, not Graphify.\nRegenerate with:\n\n```bash\npython3 scripts/operator_project_board.py --view obsidian\n```\n""",
    )
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", default=PREFIX_DEFAULT)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--view", choices=["project", "issues", "resolution", "obsidian", "graph"], default="project")
    parser.add_argument("--task", default="pi-operator-extension-step5-dogfood")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
    )
    args = parser.parse_args()
    if args.view == "obsidian":
        out = args.output or Path("docs/boards/obsidian")
        n = write_obsidian(args.root, args.prefix, out)
        print(f"Wrote Obsidian vault {out} ({n} notes)")
        return 0
    if args.view == "graph":
        out = args.output or Path("docs/boards/pi-operator-extension-graph.html")
        write_graph_html(args.root, args.prefix, out)
        print(f"Wrote graph {out}")
        return 0
    if args.view == "issues":
        data = collect_issues(args.root, args.prefix)
        out = args.output or Path("docs/boards/pi-operator-extension-issues.html")
        html_text = render_issues(data)
        label = f"{len(data['issues'])} issues"
    elif args.view == "resolution":
        data = collect_resolution(args.root, args.task)
        out = args.output or Path(f"docs/boards/{args.task}-resolution.html")
        html_text = render_resolution(data)
        label = f"{len(data['events'])} ledger events"
    else:
        data = collect(args.root, args.prefix)
        out = args.output or Path("docs/boards/pi-operator-extension.html")
        html_text = render(data)
        label = f"{len(data['tasks'])} tasks"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_text, encoding="utf-8")
    print(f"Wrote {out} ({label})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
