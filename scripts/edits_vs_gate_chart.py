"""Chart: runs that changed the file vs runs whose edit passed the gate.

Reads the measurement_results*/ outcome records and writes docs/edits-vs-gate.svg.

Usage: python3 scripts/edits_vs_gate_chart.py [out.svg]
"""

import glob
import json
import sys
from html import escape
from pathlib import Path

ROWS = [
    ("measurement_results", "4 local models, small edit tasks", "model writes the file"),
    ("measurement_results_raw", "gemma4 31b / 26b", "model writes the file"),
    (
        "measurement_results_harness-r3",
        "Control: harness applies the known edit",
        "no model on the write path",
    ),
]


def tally(repo: Path, subdir: str) -> dict:
    records = []
    for f in glob.glob(str(repo / subdir / "*.json")):
        try:
            r = json.loads(Path(f).read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if "gate_verdict" in r:
            records.append(r)
    return {
        "n": len(records),
        "changed": sum(1 for r in records if r.get("artifact_hash_changed")),
        "passed": sum(1 for r in records if r["gate_verdict"] == "pass"),
    }


def build(repo: Path) -> str:
    data = [(label, sub, tally(repo, d)) for d, label, sub in ROWS]
    for label, _, t in data:
        # The chart's premise: every run changed the file. Refuse to draw otherwise.
        assert t["n"] > 0 and t["changed"] == t["n"], (label, t)

    W, left, bar_w, bar_h = 760, 292, 290, 26
    top, row_gap = 112, 58
    H = top + row_gap * len(data) + 58

    out = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            'role="img" aria-labelledby="t d" '
            'font-family="ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif">'
        ),
        "<style>",
        ":root{--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--rule:#e4e3df;--pass:#2a78d6;--fail:#eb6834}",
        "@media (prefers-color-scheme: dark){:root{--surface:#1a1a19;--ink:#ffffff;--ink2:#c3c2b7;--muted:#8f8e86;--rule:#33332f;--pass:#3987e5;--fail:#d95926}}",
        ".bg{fill:var(--surface)}.t1{fill:var(--ink)}.t2{fill:var(--ink2)}.t3{fill:var(--muted)}",
        ".pass{fill:var(--pass)}.fail{fill:var(--fail)}.rule{stroke:var(--rule)}",
        "</style>",
        '<title id="t">Every run changed the file. At most a third of the changes passed the check.</title>',
        '<desc id="d">'
        + escape(
            "; ".join(
                f"{label}: {t['passed']} of {t['n']} runs passed the gate, all {t['changed']} changed the file"
                for label, _, t in data
            )
        )
        + "</desc>",
        f'<rect class="bg" width="{W}" height="{H}" rx="12"/>',
        '<text class="t1" x="24" y="38" font-size="19" font-weight="600">Every run changed the file. At most a third of the changes passed the check.</text>',
        '<text class="t2" x="24" y="62" font-size="13">Share of runs whose edit passed an independent gate (a task-specific check run after the edit).</text>',
    ]
    # Legend
    lx = left
    for cls, text in (("pass", "Passed the gate"), ("fail", "Changed the file, failed the gate")):
        out.append(f'<rect class="{cls}" x="{lx}" y="80" width="12" height="12" rx="3"/>')
        out.append(f'<text class="t2" x="{lx + 18}" y="90.5" font-size="12">{text}</text>')
        lx += 18 + len(text) * 6.6 + 22

    for i, (label, sub, t) in enumerate(data):
        y = top + i * row_gap
        if i == len(data) - 1:
            out.append(
                f'<line class="rule" x1="24" x2="{W - 24}" y1="{y - 16}" y2="{y - 16}" stroke-width="1"/>'
            )
        is_control = i == len(data) - 1
        out.append(
            f'<text class="{"t2" if is_control else "t1"}" x="24" y="{y + 11}" font-size="13" font-weight="{400 if is_control else 600}">{escape(label)}</text>'
        )
        out.append(
            f'<text class="t3" x="24" y="{y + 27}" font-size="11.5">{escape(sub)} · n = {t["n"]}</text>'
        )
        pw = round(bar_w * t["passed"] / t["n"], 1)
        fw = bar_w - pw
        gap = 2 if 0 < pw < bar_w else 0
        if pw:
            out.append(
                f'<rect class="pass" x="{left}" y="{y}" width="{pw - gap / 2}" height="{bar_h}" rx="4"/>'
            )
        if fw:
            out.append(
                f'<rect class="fail" x="{left + pw + gap / 2}" y="{y}" width="{fw - gap / 2}" height="{bar_h}" rx="4"/>'
            )
        pct = round(100 * t["passed"] / t["n"])
        out.append(
            f'<text class="t1" x="{left + bar_w + 14}" y="{y + 17.5}" font-size="13">'
            f'<tspan font-weight="600">{pct}%</tspan><tspan class="t2"> passed ({t["passed"]} of {t["n"]})</tspan></text>'
        )

    fy = H - 34
    out.append(
        f'<text class="t3" x="24" y="{fy}" font-size="11">Gate: grep for the expected text, exec the fixed Python, or load and check the JSON, '
        "run after the edit.</text>"
    )
    out.append(
        f'<text class="t3" x="24" y="{fy + 16}" font-size="11">Source: operator-control-plane measurement_results*/ '
        "(scripts/measurement_session.py, scripts/r3_grid_comparison.py)</text>"
    )
    out.append("</svg>")
    return "\n".join(out)


if __name__ == "__main__":
    repo = Path(__file__).resolve().parent.parent
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else repo / "docs" / "edits-vs-gate.svg"
    dest.write_text(build(repo))
    print(f"wrote {dest}")
