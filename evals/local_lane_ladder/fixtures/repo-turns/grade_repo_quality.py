#!/usr/bin/env python3
"""Quality grade for repo-turns, same shape as the z13 A/B/C pack.

z13 (`~/.dotfiles/machines/z13-amd/ollama/characterization/`):
  A = 31b n=1 greedy
  B = 26b n=1 greedy
  C = 26b best-of-5 @ T=0.7
  one programmatic grader, no LLM judge.

Here the writers are the same three conditions on the 30 retained cells
(n=3 @ T=0.8, not greedy n=1 / bo5). Score is a constraint fraction:

  required   — postcondition already passed
  scoped     — every write landed on the declared target file
  clean_write — no failed patch/write

Not Elo. Not a seat.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
TASKS = HERE / "tasks"
TRACES = HERE / "traces"
OUT = HERE / "QUALITY.md"

WRITE = {"patch_file", "write_file"}


def declared_file(task: dict) -> str:
    pc = task["postcondition"]
    if pc.get("type") == "all_of":
        return pc["checks"][0]["file"]
    return pc["file"]


def score_trace(trace: dict, target: str) -> tuple[float, dict[str, bool]]:
    calls = trace.get("trajectory", {}).get("tool_calls", [])
    writes = [c for c in calls if c["tool"] in WRITE]
    checks = {
        "required": bool(trace.get("passed")),
        "scoped": all((c.get("path") or "") == target for c in writes) and bool(writes),
        "clean_write": all(c.get("ok") for c in writes) and bool(writes),
    }
    return sum(checks.values()) / len(checks), checks


def main() -> int:
    tasks = {
        yaml.safe_load(p.read_text())["task_id"]: yaml.safe_load(p.read_text())
        for p in TASKS.glob("*.yaml")
    }
    bag: dict[tuple[str, str], list] = defaultdict(list)
    for path in sorted(TRACES.glob("*.json")):
        t = json.loads(path.read_text())
        tid, model = t["task_id"], t["model"]
        target = declared_file(tasks[tid])
        sc, detail = score_trace(t, target)
        bag[(model, tid)].append(
            {"trial": t["trial"], "score": sc, "checks": detail, "n_calls": t["trajectory"]["n_calls"]}
        )

    models = ["gemma4:26b", "gemma4:31b"]
    tids = sorted(tasks)

    def mean(model: str, tid: str) -> float:
        xs = bag[(model, tid)]
        return sum(x["score"] for x in xs) / len(xs)

    def best(model: str, tid: str) -> float:
        return max(x["score"] for x in bag[(model, tid)])

    lines = [
        "# repo-turns quality — A / B / C",
        "",
        "Same instrument as the z13 characterization pack",
        "(`machines/z13-amd/ollama/characterization/RESULTS.md`): one programmatic",
        "grader, three writers, no LLM judge.",
        "",
        "| | writer | here | z13 (29 tasks) |",
        "|---|---|---|---|",
        "| **A** | `gemma4:31b` n=1 | mean of n=3 @ T=0.8 | **0.96** greedy |",
        "| **B** | `gemma4:26b` n=1 | mean of n=3 @ T=0.8 | 0.93 greedy |",
        "| **C** | `gemma4:26b` best-of-N | best of n=3 | 0.95 best-of-5 |",
        "",
        "Checks per cell (each 0/1, score = mean): `required` (postcondition),",
        "`scoped` (writes only the declared file), `clean_write` (no failed patch).",
        "",
        "| task | A 31b mean | B 26b mean | C 26b best-of-3 |",
        "|---|---:|---:|---:|",
    ]
    a_all, b_all, c_all = [], [], []
    for tid in tids:
        a, b, c = mean("gemma4:31b", tid), mean("gemma4:26b", tid), best("gemma4:26b", tid)
        a_all.append(a)
        b_all.append(b)
        c_all.append(c)
        lines.append(f"| `{tid}` | {a:.2f} | {b:.2f} | {c:.2f} |")
    lines += [
        f"| **overall** | **{sum(a_all)/len(a_all):.2f}** | "
        f"**{sum(b_all)/len(b_all):.2f}** | **{sum(c_all)/len(c_all):.2f}** |",
        "",
        "## Where they separate",
        "",
    ]
    for tid in tids:
        for model in models:
            bad = [x for x in bag[(model, tid)] if x["score"] < 1.0]
            if not bad:
                continue
            lines.append(f"- `{tid}` `{model}`: " + "; ".join(
                f"t{x['trial']} {x['score']:.2f} { {k for k,v in x['checks'].items() if not v} }"
                for x in bad
            ))
    if not any(x["score"] < 1.0 for xs in bag.values() for x in xs):
        lines.append("- none — every cell 1.00")
    lines += [
        "",
        "## Read against z13",
        "",
        "On z13, 31b won because **codegen** and **longctx** did not saturate.",
        "This pack's `required` check saturates (30/30 pass). Quality here is",
        "scope and clean writes. 31b loses `code-stick` (`package.json` extra)",
        "and one `ollm` retry. That is FILE / TOOL, not the z13 win.",
        "",
        "Do not pool this overall with z13 0.96. Different tasks.",
        "",
    ]
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT.read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
