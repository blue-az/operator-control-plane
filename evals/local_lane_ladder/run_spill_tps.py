#!/usr/bin/env python3
"""Decode tok/s with placement, to see if a few-percent CPU spill is a killer.

Same meter as desktop_sweep.py: eval_count/eval_duration, think off, 128 tokens.
Not a ladder. Not Elo. Not a seat claim.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

API = "http://127.0.0.1:11434/api/generate"
PROMPT = "Write a short paragraph explaining what a hash table is."
TEMP = 0.8
GEN = 128
HERE = Path(__file__).resolve().parent


def unload(model: str) -> None:
    try:
        requests.post(API, json={"model": model, "keep_alive": 0}, timeout=120)
    except Exception:
        pass
    time.sleep(2)


def ps_line() -> str:
    out = subprocess.run(["ollama", "ps"], capture_output=True, text=True, timeout=30).stdout
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[1] if len(lines) > 1 else ""


def placement(line: str) -> str:
    parts = line.split()
    for i, p in enumerate(parts):
        if "%" in p:
            return " ".join(parts[i : i + 2])
    return "?"


def smi() -> str:
    return subprocess.check_output(
        ["nvidia-smi", "--query-gpu=memory.used,memory.total,utilization.gpu,power.draw",
         "--format=csv,noheader"],
        text=True,
    ).strip()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["qwen3.6:35b", "qwen3.6:27b", "gemma4:26b"])
    ap.add_argument("--ctx", nargs="+", type=int, default=[16384, 32768])
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--pack", default=str(HERE / "fixtures" / "q36-35b-spill-tps"))
    args = ap.parse_args()
    pack = Path(args.pack)
    pack.mkdir(parents=True, exist_ok=True)
    (pack / "traces").mkdir(exist_ok=True)
    (pack / "evidence").mkdir(exist_ok=True)
    rows: list[dict] = []
    print(f"spill-tps models={args.models} ctx={args.ctx} n={args.trials} gen={GEN} think=off", flush=True)
    for model in args.models:
        for ctx in args.ctx:
            unload(model)
            for trial in range(1, args.trials + 1):
                print(f"[{model} ctx={ctx} t{trial}] running...", flush=True)
                r = requests.post(
                    API,
                    json={
                        "model": model,
                        "prompt": PROMPT,
                        "stream": False,
                        "think": False,
                        "keep_alive": "3m",
                        "options": {"num_ctx": ctx, "temperature": TEMP, "num_predict": GEN},
                    },
                    timeout=1800,
                )
                r.raise_for_status()
                d = r.json()
                line = ps_line()
                ev, ed = d.get("eval_count") or 0, d.get("eval_duration") or 0
                rec = {
                    "model": model,
                    "num_ctx": ctx,
                    "trial": trial,
                    "cold": trial == 1,
                    "tok_s": round(ev / (ed / 1e9), 1) if ed else None,
                    "eval_count": ev,
                    "eval_duration_s": round(ed / 1e9, 3) if ed else None,
                    "load_s": round((d.get("load_duration") or 0) / 1e9, 1),
                    "prompt_eval_count": d.get("prompt_eval_count"),
                    "done_reason": d.get("done_reason"),
                    "placement": placement(line),
                    "ps": line,
                    "smi": smi(),
                    "think_chars": len(d.get("thinking") or ""),
                    "recorded_utc": datetime.now(timezone.utc).isoformat(),
                }
                rows.append(rec)
                (pack / "traces" / f"{model.replace(':', '-')}__c{ctx}__t{trial}.json").write_text(
                    json.dumps(rec, indent=2), encoding="utf-8"
                )
                print(
                    f"[{model} ctx={ctx} t{trial}] {rec['tok_s']} tok/s "
                    f"{rec['placement']} gen={ev} load={rec['load_s']}s",
                    flush=True,
                )
            unload(model)

    (pack / "state.json").write_text(json.dumps({"results": rows}, indent=2), encoding="utf-8")
    write_results(rows, pack)
    return 0


def write_results(rows: list[dict], pack: Path) -> None:
    lines = [
        "# spill tok/s",
        "",
        "Same meter as `desktop_sweep.py`: `eval_count/eval_duration`, think off, 128 tokens.",
        "Trial 1 is cold load; 2–3 are warm. Not Elo. Not a seat.",
        "",
        "| model | ctx | t | cold | tok/s | gen | place | load s | smi |",
        "|---|---:|---:|:---:|---:|---:|---|---:|---|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['model']}` | {r['num_ctx']} | {r['trial']} | {int(r['cold'])} | "
            f"{r['tok_s']} | {r['eval_count']} | {r['placement']} | {r['load_s']} | {r['smi']} |"
        )
    # warm means
    from collections import defaultdict

    bag: dict[tuple, list] = defaultdict(list)
    for r in rows:
        if r["tok_s"] is not None and not r["cold"]:
            bag[(r["model"], r["num_ctx"], r["placement"])].append(r["tok_s"])
    lines += ["", "## Warm mean (trials 2–3)", "",
              "| model | ctx | place | n | mean tok/s |",
              "|---|---:|---|---:|---:|"]
    for key in sorted(bag):
        vals = bag[key]
        model, ctx, place = key
        lines.append(f"| `{model}` | {ctx} | {place} | {len(vals)} | {sum(vals)/len(vals):.1f} |")
    (pack / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {pack / 'RESULTS.md'}", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
