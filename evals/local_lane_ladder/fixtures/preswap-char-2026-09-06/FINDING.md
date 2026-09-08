# Pre-swap characterization: 2080, 3090×1, 3090×2, and an Agy stick

**Run:** 2026-09-06, immediately before the 3090s move to the testbench.
Local pin is the runner e9pin path (`num_ctx` 16384, `temperature` 0.8 baked;
contract-v1 probe is `num_predict` 128 / `temperature` 0). n=3 **warm**
(one discarded generate). `think` off. Agy is `gemini-3.7-flash-low`
`--effort low` (the machine's Agy default), not luna.

**Do not mix these with** unpinned 256K numbers (133), the 2026-09-05 e9pin
214 cluster, or `baseline.json` base-tag+options (226). Today's e9pin 26b
decode is **225**, same cluster as 226.

## 26b — the only model on every local host

| host | decode tok/s n=3 | wall clock L2 n=3 warm | placement |
|---|---|---|---|
| **2080 + i3** | **29.1** (27.2–30.4) | *(not re-run; 2026-09-05 batch1 mean 141 s, n=3, mixed cold)* | MoE 100% GPU historically; this run's `nvidia-smi` was accidentally the **desktop** |
| **3090×1 + i9** | **210.9** (210.0–211.7) | constant **6.0 / 7.5 / 10.9 s** all pass; csv 41.9 fail, 37.3 / 43.7 pass | 19,372 MiB GPU0, GPU1 idle 462. **Docker ollama 0.32.15** on `:11435` |
| **3090×2 + i9** | **225.0** (224.4–225.3) | constant **11.1 / 11.8 / 12.2 s** all pass; csv **27.8 / 41.7 / 45.8 s** all pass | 19,676 MiB GPU0, GPU1 idle 454. Host ollama **0.32.12**. 26b does **not** use the second card |
| **Agy** Flash Low | not ollama-decode: **5.9 / 7.0 / 9.8 s** wall for ~2.6–2.9k chars of LRU code | constant-and-callers **31.1 fail / 35.7 pass / 21.5 fail** | cloud |

26b on dual is a single-card model. Dual vs solo decode 225 vs 211 is **not a
dual tax** — the solo daemon is a different ollama (0.32.15 in docker vs
0.32.12 on the host). Wall clock on the short task is if anything **faster**
on solo (6–11 s vs 11–12 s).

2080 is **~7.7× slower** than 3090×2 on the same e9pin 26b decode (29 vs 225).
The 3.8× wall-clock ratio from batch1 is a different pin/cold mix; do not
naively scale 11 s × 3.8.

## Dual tax, where it can exist (35b, splits)

| | decode | csv-summarize-repair wall n=3 |
|---|---|---|
| 3090×2 (split 22,976 + 20,156 MiB) | **131.2** (130.0–132.1) | **13.0 / 22.5 / 31.2 s** all pass |
| 3090×1 (docker) | **137.2** (134.9–140.2) | **17.4 / 12.4 / 13.0 s** all pass |

Direction matches `single-vs-split-placement`: solo decode **+5%** here vs
+9.3% there. Wall clock means 22 s dual vs 14 s solo, but dual's range is
13–31 — the 13 s dual rep overlaps solo completely. **n=3 cannot claim a
wall-clock tax.** Decode still says splitting this model is slightly worse
than pinning it, not 35%.

26b never paid a dual tax today. GPU1 was idle.

## Agy stick

Pinned to the user's Agy default, not a thinking-high Pro.

- **Decode stick is not contract-v1 tok/s.** Agy has no `num_predict`. It
  emitted a full LRU module (~2.6–2.9k chars) in 6–10 s. 26b's probe is
  capped at 128 tokens and finishes in ~0.6 s of eval. You cannot say
  “frontier is slower than 26b decode” from these two clocks. Rough char/s
  still has 26b ahead (~900 vs ~400) but that is not the published column.
- **Operator stick:** 1/3 pass on constant-and-callers L2. Failures left
  `MAX_RETRIES=3`. Pass took **36 s**; 26b dual does the same task in
  **11–12 s** at 3/3. Local 26b is the faster *and* more reliable implementer
  on this fixture, Screen-tier n=3.

## Why numbers kept moving

1. **Pin path:** unpinned 256K split (133) vs e9pin (214 yesterday, **225
   today**) vs base+options (226). Today's e9pin landed on 225.
2. **PCIe link training on this board is not stable.** GPU0 was gen1×16 this
   morning and **gen3×16** during this run; GPU1 stays ×4 and flips gen1/gen3.
   Record the link next to every decode row after the swap.
3. Solo numbers are docker 0.32.15 because this user cannot `sudo -u ollama`
   a second host daemon. Treat 211 vs 225 as **confounded**.
4. The 2080 decode `smi` in this fixture is the desktop's `nvidia-smi`. tok/s
   still came from `testbench.local:11434`.

## What to re-run on the bench after the cards move

Same script, e9pin, n=3 warm:

- 26b decode + two-task wall (this is the bridge row)
- 35b decode + csv wall (capacity / split row)
- Do not compare to 133, 214, or GOLD_STANDARD 133.0
- Compare to **225 / 11–12 s** (26b) and **131 / csv 13–31 s** (35b dual) above

Agy can be re-measured anytime; it does not live on the cards.

## Limits

- n=3 warm, two tasks, one board. Continuous metrics only.
- Solo ×1 is a different ollama binary than dual.
- Agy 2/3 fail; wall clock on fails is still wait time, not a successful job.
- No 2080 wall-clock re-run today (quota/time); decode only.
- 320 W caps still on. 1000 W PSU was not used to uncap for this snapshot.
