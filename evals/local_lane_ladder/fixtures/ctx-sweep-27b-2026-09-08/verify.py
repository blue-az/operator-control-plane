#!/usr/bin/env python3
"""Fail-closed re-derivation of the 2026-09-08 single-card and context-depth claims.

Scope: this verifies that the registered claims match the COMMITTED measurements.
It does NOT re-run the models -- a live re-measurement is ~25 minutes and requires
the solo daemon. A reviewer wanting reproduction must run hw_standard.py per
GOLD_STANDARD.md 2b.2. Exits non-zero on any claim that does not re-derive.
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
RANK = HERE.parent / "singlecard-rank-2026-09-08" / "results.json"
SWEEP = HERE / "results.json"
fails = []

def check(name, cond, detail):
    print(f"{'PASS' if cond else 'FAIL'}  {name}: {detail}")
    if not cond: fails.append(name)

def rows(p):
    d = json.load(open(p))
    return {r["config"]: r for r in d["rows"] if r.get("status") == "ok"}, d

sw, swd = rows(SWEEP)
rk, rkd = rows(RANK)

check("all sweep rows ok", len(sw) == 8, f"{len(sw)}/8 ok")
check("all rank rows ok", len(rk) == 8, f"{len(rk)}/8 ok")

d131 = sw.get("dual|qwen3.8:27b|ctx131072|x1"); s131 = sw.get("solo|qwen3.8:27b|ctx131072|x1")
if d131 and s131:
    ratio = d131["decode_tok_s_median"] / s131["decode_tok_s_median"]
    check("C1 5.5x at ctx131072", 5.3 <= ratio <= 5.7,
          f"dual {d131['decode_tok_s_median']} / solo {s131['decode_tok_s_median']} = {ratio:.2f}x")
else:
    check("C1 5.5x at ctx131072", False, "rows missing")

# C2: the same comparison at benchmark depth, across BOTH runs of that config
deltas = []
for src, tag in ((sw, "sweep"), (rk, "rank")):
    d = src.get("dual|qwen3.8:27b|ctx16384|x1"); s = src.get("solo|qwen3.8:27b|ctx16384|x1")
    if d and s:
        deltas.append((tag, (s["decode_tok_s_median"] / d["decode_tok_s_median"] - 1) * 100))
check("C2 ctx16384 delta is small and negative", len(deltas) == 2 and all(-13 <= v <= -7 for _, v in deltas),
      ", ".join(f"{t} {v:+.1f}%" for t, v in deltas))

pre = [sw[f"solo|qwen3.8:27b|ctx{c}|x1"]["prompt_s_median"] / sw[f"solo|qwen3.8:27b|ctx{c}|x1"]["prompt_tok"] * 1000
       for c in (16384, 32768, 65536) if f"solo|qwen3.8:27b|ctx{c}|x1" in sw]
check("C3 solo prefill flat 16k-64k", len(pre) == 3 and (max(pre) - min(pre)) < 0.02,
      " / ".join(f"{v:.3f}" for v in pre) + " ms/tok, spread %.3f" % (max(pre) - min(pre)))

if s131 and d131:
    short = d131["vram_mib_total"] - s131["vram_mib_total"]
    ms_res = 1000 / s131["decode_tok_s_median"]
    ms_full = 1000 / sw["solo|qwen3.8:27b|ctx65536|x1"]["decode_tok_s_median"]
    layers_est = round(66 * short / d131["vram_mib_total"])
    per_layer = (ms_res - ms_full) / layers_est if layers_est else None
    check("C4 spill cost per layer (INFERRED, not measured)", per_layer is not None and 4.0 <= per_layer <= 7.0,
          f"shortfall {short} MiB -> ~{layers_est} layers, {per_layer:.1f} ms/layer")

check("C5 placement not captured on solo arm (the instrument gap)",
      all(r.get("layers") is None for k, r in sw.items() if k.startswith("solo")),
      "every solo row records layers: None")

print()
if fails:
    print(f"FAILED: {len(fails)} claim(s) did not re-derive: {', '.join(fails)}")
    sys.exit(1)
print("All registered claims re-derive from the committed fixtures.")
