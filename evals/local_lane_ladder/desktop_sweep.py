#!/usr/bin/env python3
"""
Desktop throughput sweep — deliberately mirrors Z13_BENCHMARK.md's method so
the two machines can be compared like-for-like.

Method (copied from the z13 run, do not drift):
  ctx 16384, temperature 0.8, 128-token generation, each model loaded cold and
  unloaded after. Decode rate excludes load time and prompt eval -- it is
  eval_count / eval_duration, not tokens/wall-clock.

WHY THIS EXISTS AND WHEN IT EXPIRES
-----------------------------------
z13 has a full per-model table; the desktop -- the machine everything actually
runs on -- has only scattered one-offs. This is the single-3090 baseline.

A second RTX 3090 is installed but not powered (wrong cord; replacement due
2026-08-18). On the day it comes up, every tok/s and placement figure measured
here becomes historical: two discrete 24 GB pools are not one 48 GB pool, and
ollama splitting layers across them pays PCIe on every token that crosses.
Re-run this script after the upgrade and diff, rather than trusting that a
number labelled "desktop" still means the same machine.

The z13 lesson applies double here: read tok/s, not the placement percentage.
On z13 the percentage was misleading because memory is unified. On a dual-card
desktop it will mislead for the opposite reason -- `ollama ps` reports one
aggregate figure over two independent pools.
"""

import json
import subprocess
import sys
import time

import requests

NUM_CTX = 16384
TEMPERATURE = 0.8
GEN_TOKENS = 128
PROMPT = "Write a short paragraph explaining what a hash table is."

# Text field only. qwen3-vl:30b is a vision grader — GOLD_STANDARD.md
# "Out of field". Pass it on the CLI if you really want a decode number.
MODELS = [
    "gemma4:26b", "gemma4:31b", "gemma4:12b",
    "qwen3.8:27b", "qwen3.6:27b", "qwen3:32b",
    "gemma3:27b", "qwen2.5-coder:14b", "granite4:latest",
]


def unload(model):
    try:
        requests.post("http://localhost:11434/api/generate",
                      json={"model": model, "keep_alive": 0}, timeout=120)
    except Exception:
        pass
    time.sleep(3)


def placement():
    """PROCESSOR column from `ollama ps`, e.g. '100% GPU' or '16%/84% CPU/GPU'."""
    try:
        out = subprocess.run(["ollama", "ps"], capture_output=True, text=True,
                             timeout=30).stdout.splitlines()
        if len(out) < 2:
            return "?"
        cols = out[1].split()
        for i, c in enumerate(cols):
            if c.endswith("%") or "%/" in c:
                return " ".join(cols[i:i + 2])
        return "?"
    except Exception:
        return "?"


def bench(model):
    unload(model)  # force a cold load so load_duration is real
    r = requests.post("http://localhost:11434/api/generate", json={
        "model": model, "prompt": PROMPT, "stream": False, "think": False,
        "options": {"num_ctx": NUM_CTX, "temperature": TEMPERATURE,
                    "num_predict": GEN_TOKENS},
        "keep_alive": "2m"}, timeout=1800).json()
    # An ollama error comes back as HTTP 200 with an {"error": ...} body, so it
    # is NOT caught by the exception handler in main(). Without this the record
    # reads eval_count 0 / tok_s None / placement "?" and looks like a model
    # that generated nothing -- which is what a real OOM looked like on z13
    # (qwen3.8:27b, "radv/amdgpu: Not enough memory for command submission").
    # A capacity failure must never be reported as a throughput measurement.
    if isinstance(r, dict) and r.get("error"):
        return {"model": model, "tok_s": None, "error": r["error"],
                "failed": "api_error"}
    place = placement()
    ev, ed = r.get("eval_count") or 0, r.get("eval_duration") or 0
    rec = {
        "model": model,
        "tok_s": round(ev / (ed / 1e9), 1) if ed else None,
        "eval_count": ev,
        "load_s": round((r.get("load_duration") or 0) / 1e9, 1),
        "prompt_eval_count": r.get("prompt_eval_count"),
        "placement": place,
        "done_reason": r.get("done_reason"),
    }
    unload(model)
    return rec


def main():
    models = sys.argv[1:] or MODELS
    rows = []
    print(f"ctx={NUM_CTX} temp={TEMPERATURE} gen={GEN_TOKENS}, cold load each\n")
    for m in models:
        try:
            rec = bench(m)
        except Exception as e:
            print(f"[{m}] ERROR {type(e).__name__}: {e}", flush=True)
            rows.append({"model": m, "error": str(e)})
            continue
        rows.append(rec)
        if rec.get("failed"):
            print(f"[{rec['model']:20s}] FAILED -- {rec['error'][:96]}", flush=True)
            continue
        print(f"[{rec['model']:20s}] {str(rec['tok_s']):>6s} tok/s  "
              f"load {rec['load_s']:5.1f}s  {rec['placement']:18s} "
              f"gen={rec['eval_count']}", flush=True)

    dest = f"/home/blueaz/handoffs/desktop_sweep_{time.strftime('%Y%m%d_%H%M%S')}.json"
    with open(dest, "w") as fh:
        json.dump({"num_ctx": NUM_CTX, "temperature": TEMPERATURE,
                   "gen_tokens": GEN_TOKENS, "gpus": "1x RTX 3090 320W",
                   "captured": time.strftime("%Y-%m-%dT%H:%M:%S"),
                   "rows": rows}, fh, indent=2)
    print(f"\nraw -> {dest}")


if __name__ == "__main__":
    main()
