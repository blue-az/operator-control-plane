#!/usr/bin/env python3
"""Fail-closed verification for the decode-vs-wall-clock and ctx-split claims.

Exits non-zero if any claim fails to reproduce. Re-runs live measurements for
the decode claims; re-derives the token-economy claim from committed traces.
"""
import json, glob, os, pathlib, statistics, subprocess, sys, time

FIX = pathlib.Path(__file__).resolve().parent
SPLIT = FIX.parent / "gemma4-26b-ctx-default-split"
BASE, PINNED = "gemma4:26b", "gemma4-26b-e9pin-ctx16384-t0p8:latest"
PROMPT = pathlib.Path.home() / (
    "Python/project-phoenix/docs/domain_runs/"
    "GEMMA4-CTX8192-3090-VS-Z13-001/prompt.txt")
fails = []

def check(name, ok, detail):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}", flush=True)
    if not ok:
        fails.append(name)

# C1 -- gemma4:26b default context is 262144 (the mechanism).
out = subprocess.run(["ollama", "show", BASE], capture_output=True, text=True).stdout
ctx = next((l.split()[-1] for l in out.splitlines() if "context length" in l), None)
check("C1 default context is 262144", ctx == "262144", f"ollama show reports {ctx}")

# C2/C3 -- interleaved decode: pinned is single-card and materially faster.
def probe(m):
    pl = json.dumps({"model": m, "prompt": PROMPT.read_text(), "stream": False,
                     "keep_alive": "5m",
                     "options": {"num_predict": 128, "temperature": 0}})
    d = None
    for _ in range(2):
        r = subprocess.run(["curl", "-s", "http://localhost:11434/api/generate",
                            "-d", pl], capture_output=True, text=True, timeout=300)
        d = json.loads(r.stdout)
    return d["eval_count"] / (d["eval_duration"] / 1e9)

def unload(m):
    subprocess.run(["curl", "-s", "http://localhost:11434/api/generate", "-d",
                    json.dumps({"model": m, "keep_alive": 0})],
                   capture_output=True, timeout=60)

def busy_gpus():
    r = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                        "--format=csv,noheader,nounits"], capture_output=True, text=True)
    return [int(x) for x in r.stdout.split()if x.strip().isdigit()]

if not PROMPT.is_file():
    check("C2/C3 decode probe", False, f"contract prompt missing at {PROMPT}")
else:
    res, cards = {BASE: [], PINNED: []}, {}
    for rep in range(3):
        for m in ([BASE, PINNED] if rep % 2 == 0 else [PINNED, BASE]):
            unload(BASE); unload(PINNED); time.sleep(3)
            res[m].append(probe(m))
            cards[m] = busy_gpus()
    b, p = res[BASE], res[PINNED]
    check("C2 pinned decode exceeds base, non-overlapping",
          min(p) > max(b),
          f"base {statistics.mean(b):.1f} (max {max(b):.1f}) vs "
          f"pinned {statistics.mean(p):.1f} (min {min(p):.1f})")
    check("C3 base spans two cards, pinned occupies one",
          sum(1 for v in cards[BASE] if v > 2000) >= 2
          and sum(1 for v in cards[PINNED] if v > 2000) == 1,
          f"base {cards[BASE]} MiB vs pinned {cards[PINNED]} MiB")

# C4 -- token economy: faster decoder, slower wall clock, more tokens.
agg = {}
for f in glob.glob(str(FIX / "traces" / "*.json")):
    d = json.load(open(f))
    m = d.get("model") or d.get("base_model")
    a = agg.setdefault(m, {"w": [], "t": []})
    a["w"].append(d.get("wall_clock_s"))
    a["t"].append((d.get("trajectory") or {}).get("completion_tokens"))
def mean(x):
    x = [v for v in x if isinstance(v, (int, float))]
    return statistics.mean(x) if x else None
g, q = agg.get("gemma4:26b"), agg.get("qwen3.8:27b")
if not g or not q:
    check("C4 token economy", False, "traces missing for one or both models")
else:
    gw, qw, gt, qt = mean(g["w"]), mean(q["w"]), mean(g["t"]), mean(q["t"])
    check("C4 gemma4:26b slower on wall clock than qwen3.8:27b",
          gw > qw, f"{gw:.1f}s vs {qw:.1f}s")
    check("C4 gemma4:26b emits materially more tokens",
          gt > 2 * qt, f"{gt:.0f} vs {qt:.0f} output tokens ({gt/qt:.1f}x)")

print()
if fails:
    print(f"VERIFICATION FAILED: {len(fails)} claim(s) did not reproduce: {fails}")
    sys.exit(1)
print("VERIFICATION PASSED: all claims reproduced.")
