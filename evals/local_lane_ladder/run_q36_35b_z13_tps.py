#!/usr/bin/env python3
"""z13 decode tok/s for qwen3.6:35b vs gemma4:26b.

Same meter as desktop_sweep.py / q36-35b-spill-tps: eval_count/eval_duration,
think off, 128 tokens. No nvidia-smi (this is RADV/UMA).
"""
from __future__ import annotations

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
PACK = HERE / "fixtures" / "q36-35b-z13-tps"
MODELS = ["qwen3.6:35b", "gemma4:26b"]
CTXS = [16384, 32768]


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


def power_state() -> dict:
    def read(path: str) -> str:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except Exception:
            return "?"

    return {
        "ac0_online": read("/sys/class/power_supply/AC0/online"),
        "bat0_status": read("/sys/class/power_supply/BAT0/status"),
        "governor": read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"),
        "powerprofile": subprocess.run(
            ["powerprofilesctl", "get"], capture_output=True, text=True
        ).stdout.strip()
        or "?",
    }


def main() -> int:
    PACK.mkdir(parents=True, exist_ok=True)
    (PACK / "traces").mkdir(exist_ok=True)
    (PACK / "evidence").mkdir(exist_ok=True)
    ps = power_state()
    (PACK / "evidence" / "power_state.json").write_text(
        json.dumps(ps, indent=2) + "\n", encoding="utf-8"
    )
    print(f"power_state {ps}", flush=True)
    rows: list[dict] = []
    for model in MODELS:
        for ctx in CTXS:
            unload(model)
            for trial in range(1, 4):
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
                    "done_reason": d.get("done_reason"),
                    "placement": placement(line),
                    "ps": line,
                    "power_state": ps,
                    "think_chars": len(d.get("thinking") or ""),
                    "recorded_utc": datetime.now(timezone.utc).isoformat(),
                    "error": d.get("error"),
                }
                rows.append(rec)
                tag = f"{model.replace(':', '-')}__c{ctx}__t{trial}.json"
                (PACK / "traces" / tag).write_text(json.dumps(rec, indent=2), encoding="utf-8")
                print(
                    f"[{model} ctx={ctx} t{trial}] {rec['tok_s']} tok/s "
                    f"{rec['placement']} gen={ev} load={rec['load_s']}s err={rec['error']}",
                    flush=True,
                )
            unload(model)
    (PACK / "state.json").write_text(json.dumps({"results": rows}, indent=2), encoding="utf-8")
    lines = [
        "# q36-35b z13 tok/s",
        "",
        "Same meter as desktop_sweep / q36-35b-spill-tps. Trial 1 cold; 2–3 warm.",
        f"Power: {ps}",
        "",
        "| model | ctx | t | cold | tok/s | gen | place | load s |",
        "|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for rec in rows:
        lines.append(
            f"| `{rec['model']}` | {rec['num_ctx']} | {rec['trial']} | "
            f"{int(rec['cold'])} | {rec['tok_s']} | {rec['eval_count']} | "
            f"{rec['placement']} | {rec['load_s']} |"
        )
    warm: dict[tuple[str, int], list[float]] = {}
    for rec in rows:
        if not rec["cold"] and rec["tok_s"] is not None:
            warm.setdefault((rec["model"], rec["num_ctx"]), []).append(rec["tok_s"])
    lines += ["", "| model | ctx | place (last) | warm mean tok/s |", "|---|---:|---|---:|"]
    last_place = {(r["model"], r["num_ctx"]): r["placement"] for r in rows}
    for key, vals in warm.items():
        mean = round(sum(vals) / len(vals), 1)
        lines.append(f"| `{key[0]}` | {key[1]} | {last_place[key]} | **{mean}** |")
    (PACK / "RESULTS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Z13_TPS_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
