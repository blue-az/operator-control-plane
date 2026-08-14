#!/usr/bin/env python3
"""E12 analysis — does feeding a repeated tool result back change outcomes?

E10 measured +11.1 pts on engaged cells at p=0.32, ~4x underpowered against an
11.3% noise floor. E12 targets only the 9 classes where the repeat path actually
engages, at n=24 per arm, with arms interleaved per class so drift cannot
accumulate between them.

Reports per-class deltas, the aggregate, a Fisher exact test, and separately the
MECHANISM (did repeat-stops actually fall) -- because E10 established the
mechanism works while leaving the outcome unproven, and conflating the two is
the easy mistake here.
"""
from __future__ import annotations
import glob, json, sys
from math import comb
from pathlib import Path

X = Path(sys.argv[1] if len(sys.argv) > 1
         else "evals/local_lane_ladder/fixtures/e12-repeat-conclusive")

def load(arm):
    cells = {}
    for f in glob.glob(str(X / arm / "state_*.json")):
        for r in json.load(open(f))["results"]:
            cells[(r["task_id"], r["model"], r["trial"])] = r
    return cells

def fisher(a, b, c, d):
    n = a + b + c + d
    if min(a + b, c + d, a + c, b + d) == 0:
        return 1.0
    def p(x):
        return comb(a + b, x) * comb(c + d, a + c - x) / comb(n, a + c)
    obs = p(a)
    lo, hi = max(0, a + c - (c + d)), min(a + b, a + c)
    return min(1.0, sum(p(x) for x in range(lo, hi + 1) if p(x) <= obs * 1.000001))

stop, fb = load("stop"), load("feedback")
classes = sorted({(t, m) for t, m, _ in stop} & {(t, m) for t, m, _ in fb})
print(f"classes with data in both arms: {len(classes)}/9\n")
print(f"{'class':<46}{'stop':>9}{'feedback':>11}{'delta':>9}")
print("-" * 75)
sa = sb = na = nb = 0
for t, m in classes:
    a = [r for (tt, mm, _), r in stop.items() if (tt, mm) == (t, m)]
    b = [r for (tt, mm, _), r in fb.items() if (tt, mm) == (t, m)]
    pa, pb = sum(r["passed"] for r in a), sum(r["passed"] for r in b)
    sa += pa; na += len(a); sb += pb; nb += len(b)
    d = 100 * pb / len(b) - 100 * pa / len(a)
    print(f"{t+' x '+m:<46}{f'{pa}/{len(a)}':>9}{f'{pb}/{len(b)}':>11}{d:>+8.1f}")
print("-" * 75)
print(f"{'AGGREGATE':<46}{f'{sa}/{na}':>9}{f'{sb}/{nb}':>11}"
      f"{100*sb/nb - 100*sa/na:>+8.1f}")
print(f"\nFisher exact two-sided p = {fisher(sa, na-sa, sb, nb-sb):.4f}")
print("Noise floor (e10 drift probe): 11.3% of cells flip between invocations.")

def mech(cells):
    st = sum(1 for r in cells.values()
             if json.load(open(r["trace"]))["trajectory"]["stopped_repeat"]) if cells else 0
    return st

print("\nMECHANISM — did the repeat path actually change behaviour?")
for name, cells in (("stop", stop), ("feedback", fb)):
    tr = [json.load(open(r["trace"])) for r in cells.values() if r.get("trace")]
    st = sum(t["trajectory"]["stopped_repeat"] for t in tr)
    fbk = sum("Repeat fed back" in t["stdout"] for t in tr)
    ed = sum(sum(1 for c in t["trajectory"]["tool_calls"]
                 if c["tool"] in ("patch_file", "write_file", "run_command")) for t in tr)
    print(f"  {name:<9} repeat-stops {st:>3}/{len(tr):<4} fed-back {fbk:>3}  state-changing calls {ed}")
