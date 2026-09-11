#!/usr/bin/env python3
"""Offline consistency checks for C1-C3; conditional arithmetic for C4.

Uses local fixtures, not live models. GAP1 records missing historical placement;
it is NOT explanatory claim C5. Does not verify placement, causality, C5-C8,
fixture provenance, or ledger status. Live runs require the corrected protocol in
docs/REVIEW_CALL_singlecard-and-ctx-depth_2026-09-08.md.
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
check("approximately fixed actual prompt, not capacity-sized input",
      len(sw) == 8 and all(r.get("prompt_tok") == (
          12837 if k in {"dual|qwen3.8:27b|ctx16384|x1", "dual|qwen3.8:27b|ctx32768|x1"}
          else 12838) for k, r in sw.items()),
      "12,837 in dual 16k/32k; 12,838 in remaining rows")

d131 = sw.get("dual|qwen3.8:27b|ctx131072|x1"); s131 = sw.get("solo|qwen3.8:27b|ctx131072|x1")
if d131 and s131:
    ratio = d131["decode_tok_s_median"] / s131["decode_tok_s_median"]
    check("C1 5.5x at ctx131072", 5.3 <= ratio <= 5.7,
          f"dual {d131['decode_tok_s_median']} / solo {s131['decode_tok_s_median']} = {ratio:.2f}x")
else:
    check("C1 5.5x at ctx131072", False, "rows missing")

# C2: solo-relative-to-dual delta at capacity 16384, across both runs.
deltas = []
for src, tag in ((sw, "sweep"), (rk, "rank")):
    d = src.get("dual|qwen3.8:27b|ctx16384|x1"); s = src.get("solo|qwen3.8:27b|ctx16384|x1")
    if d and s:
        deltas.append((tag, (s["decode_tok_s_median"] / d["decode_tok_s_median"] - 1) * 100))
check("C2 ctx16384 delta is small and negative", len(deltas) == 2 and all(-13 <= v <= -7 for _, v in deltas),
      ", ".join(f"{t} {v:+.1f}%" for t, v in deltas))

pre = [sw[f"solo|qwen3.8:27b|ctx{c}|x1"]["prompt_s_median"] / sw[f"solo|qwen3.8:27b|ctx{c}|x1"]["prompt_tok"] * 1000
       for c in (16384, 32768, 65536) if f"solo|qwen3.8:27b|ctx{c}|x1" in sw]
spread = max(pre) - min(pre) if pre else float("inf")
check("C3 prefill within rounded precision at capacities 16k-64k",
      len(pre) == 3 and all(abs(v - 0.872) < 0.002 for v in pre) and spread < 0.02,
      " / ".join(f"{v:.3f}" for v in pre) + f" ms/tok, spread {spread:.3f}")
headroom = [24576 - sw[f"solo|qwen3.8:27b|ctx{c}|x1"]["vram_mib_total"]
            for c in (16384, 65536) if f"solo|qwen3.8:27b|ctx{c}|x1" in sw]
check("C3 reported headroom (24576 MiB nominal card)",
      headroom == [5669, 2339], str(headroom))

if s131 and d131 and "solo|qwen3.8:27b|ctx65536|x1" in sw:
    short = d131["vram_mib_total"] - s131["vram_mib_total"]
    ms_res = 1000 / s131["decode_tok_s_median"]
    ms_full = 1000 / sw["solo|qwen3.8:27b|ctx65536|x1"]["decode_tok_s_median"]
    layers_est = round(66 * short / d131["vram_mib_total"])
    per_layer = (ms_res - ms_full) / layers_est if layers_est else None
    check("C4 spill cost per layer (INFERRED, not measured)", per_layer is not None and 4.0 <= per_layer <= 7.0,
          f"VRAM difference {short} MiB -> ~{layers_est} hypothetical layers, {per_layer} ms/layer")
else:
    check("C4 conditional arithmetic", False, "required rows missing")

check("GAP1 placement not captured on solo arm (NOT claim C5)",
      all(r.get("layers") is None for k, r in sw.items() if k.startswith("solo")),
      "every solo row records layers: None")

print()
if fails:
    print(f"FAILED: {len(fails)} claim(s) did not re-derive: {', '.join(fails)}")
    sys.exit(1)
print("Scoped fixture checks passed: C1-C3 consistency, C4 conditional arithmetic, GAP1.")
print("NOT VERIFIED: actual CPU-layer cost, residency explanation (C5), standards C6-C8.")
