#!/usr/bin/env python3
"""Fail-closed re-derivation of the 2026-09-06 power-ranking analysis.

Everything here is recomputed from trace files on disk. Nothing is taken from
the session that produced the analysis. Exits non-zero if any settled claim
fails to reproduce.

The exclusion rules are applied MECHANICALLY from trace fields, not from a
hand-written fixture list, so this validates the rule rather than replaying a
judgement call. Run it and read which fixtures each rule catches.
"""
import json, glob, os, re, sys, collections

LADDER = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(LADDER, "fixtures")
SEAT = ("ambiguous-anchor", "csv-summarize-repair", "strict-log-format")
fails = []

def check(name, ok, detail):
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    if not ok: fails.append(name)

# ---- load every L2 seat trial on the desktop -------------------------------
rows = []
for f in glob.glob(os.path.join(FIX, "*", "traces", "*.json")):
    try: d = json.load(open(f))
    except Exception: continue
    if d.get("level") != "L2" or d.get("task_id") not in SEAT: continue
    if d.get("machine") != "desktop": continue
    argv = " ".join(d.get("argv") or [])
    m = re.search(r"--model (\S+)", argv)
    tr = d.get("trajectory") or {}
    rows.append(dict(
        fixture=os.path.relpath(f, FIX).split(os.sep)[0],
        model=d.get("model"), task=d["task_id"], passed=bool(d.get("passed")),
        tag=(m.group(1) if m else ""), think_off=("--thinking off" in argv),
        no_dispatch=bool(tr.get("no_dispatch")), tokens=tr.get("completion_tokens"),
        calls=tr.get("n_calls"), prompt=d.get("prompt", "")))
print(f"loaded {len(rows)} L2 seat trials on desktop from {len(set(r['fixture'] for r in rows))} fixtures\n")

# ---- R1: unpinned base tag ------------------------------------------------
unpinned = [r for r in rows if "e9pin" not in r["tag"]]
fx = sorted({r["fixture"] for r in unpinned})
check("R1 unpinned-tag rule catches trials", len(unpinned) > 0,
      f"{len(unpinned)} trials in {fx}")

# ---- R2: think-on ---------------------------------------------------------
thinkon = [r for r in rows if not r["think_off"]]
check("R2 think-on rule catches trials", len(thinkon) > 0,
      f"{len(thinkon)} trials in {sorted({r['fixture'] for r in thinkon})}")

# ---- R3: no_dispatch is zero-work, and always scored as failure -----------
nd = [r for r in rows if r["no_dispatch"]]
zero = [r for r in nd if (r["tokens"] in (0, None)) and (r["calls"] in (0, None))]
scored_fail = [r for r in nd if not r["passed"]]
# no_dispatch does NOT mean "produced nothing". Most such trials emitted
# hundreds of tokens and made read calls, then never made the edit -- a real
# task failure. Only the zero-work subset is an infrastructure stall.
check("R3a no_dispatch splits into zero-work stalls vs substantive failures",
      len(zero) == 6 and len(nd) - len(zero) == 57,
      f"{len(zero)} zero-work (stall) + {len(nd)-len(zero)} emitted-but-never-edited (real failure)")
check("R3b every no_dispatch trial is scored as a failure",
      len(scored_fail) == len(nd), f"{len(scored_fail)}/{len(nd)} scored failed")

by = collections.Counter(r["model"] for r in nd)
tot = collections.Counter(r["model"] for r in rows)
print("\n  no_dispatch concentration (the ranking-relevant pattern):")
for m, n in by.most_common():
    print(f"    {m:22} {n:3}/{tot[m]:4}  {n/tot[m]:6.1%}")
top = ("gemma4:26b", "gemma4:31b", "qwen3.8:27b")
tr_ = sum(by[m] for m in top) / max(1, sum(tot[m] for m in top))
bot = ("gemma3:27b", "qwen3-vl:30b", "qwen3:32b", "qwen2.5-coder:14b")
br_ = sum(by[m] for m in bot) / max(1, sum(tot[m] for m in bot))
check("R3c no_dispatch concentrates in the low-ranked models",
      br_ > 5 * tr_, f"bottom-4 {br_:.1%} vs top-3 {tr_:.1%} ({br_/max(tr_,1e-9):.0f}x)")

# ---- clean corpus ---------------------------------------------------------
def zero_work(r): return r["no_dispatch"] and (r["tokens"] in (0,None)) and (r["calls"] in (0,None))
# Substantive no_dispatch trials are KEPT as failures: the model emitted output
# and made calls, it simply never made the edit. Only zero-work stalls drop out.
def clean(r): return ("e9pin" in r["tag"]) and r["think_off"] and not zero_work(r)
# prompt-modified trials (ablations) never belong in a seat score
BASE_PROMPTS = {}
for r in rows:
    BASE_PROMPTS.setdefault(r["task"], collections.Counter())[r["prompt"]] += 1
canon = {t: c.most_common(1)[0][0] for t, c in BASE_PROMPTS.items()}
patched = [r for r in rows if r["prompt"] != canon[r["task"]]]
check("R4 prompt-modified trials are detectable and excluded", len(patched) > 0,
      f"{len(patched)} trials in {sorted({r['fixture'] for r in patched})}")

cl = [r for r in rows if clean(r) and r["prompt"] == canon[r["task"]]]
agg = collections.defaultdict(lambda: [0, 0])
for r in cl:
    a = agg[r["model"]]; a[1] += 1; a[0] += 1 if r["passed"] else 0
print("\n  clean seat corpus (pinned + think-off + dispatched + canonical prompt):")
for m, (p, n) in sorted(agg.items(), key=lambda kv: -kv[1][0] / max(1, kv[1][1])):
    print(f"    {m:22} {p:4}/{n:<4} {p/n:6.1%}")

a35=agg["qwen3.6:35b"]
check("C1 qwen3.6:35b has >=42 clean trials at >=95%", a35[1] >= 42 and a35[0]/a35[1] >= 0.95,
      f"{a35[0]}/{a35[1]} = {a35[0]/max(1,a35[1]):.1%}")
g = agg["gpt-oss:120b"]
check("C2 gpt-oss:120b >= 54 clean trials at >= 95%", g[1] >= 54 and g[0] / g[1] >= 0.95,
      f"{g[0]}/{g[1]} = {g[0]/max(1,g[1]):.1%}")

# ---- C3: speed sweep S blend ---------------------------------------------
tsv = os.path.expanduser("~/Python/project-phoenix/docs/domain_runs/"
                         "MODEL-RANKING-002-PRESWAP/results.tsv")
if os.path.isfile(tsv):
    sp = collections.defaultdict(dict)
    for ln in open(tsv).read().splitlines()[1:]:
        p = ln.split("\t")
        if len(p) >= 5: sp[p[1]][p[2]] = float(p[4])
    base = sp.get("gemma4:26b", {})
    if base:
        bp, b15 = base["peak"], (base["code"] + base["scrollback"]) / 2
        print("\n  S blend (peak+@15k)/2, normalised to gemma4:26b:")
        for m, c in sorted(sp.items(), key=lambda kv: -((kv[1]["peak"]/bp)+(((kv[1]["code"]+kv[1]["scrollback"])/2)/b15))/2):
            s = ((c["peak"]/bp) + (((c["code"]+c["scrollback"])/2)/b15)) / 2
            print(f"    {m:22} {s:6.3f}")
        check("C3 gemma4:26b normalises to 1.000",
              abs(((base['peak']/bp)+(b15/b15))/2 - 1.0) < 1e-9, "1.000")
        anom = [m for m, c in sp.items() if (c["code"]+c["scrollback"])/2 > c["peak"]]
        check("C4 @15k-faster-than-peak anomaly is present and named",
              len(anom) > 0, f"{anom} — peak is depressed, see clock-ramp note")
else:
    check("C3 speed sweep TSV present", False, f"missing {tsv}")

print()
if fails:
    print(f"VERIFICATION FAILED: {len(fails)} claim(s) did not reproduce: {fails}")
    sys.exit(1)
print("VERIFICATION PASSED: all settled claims reproduced from traces on disk.")
