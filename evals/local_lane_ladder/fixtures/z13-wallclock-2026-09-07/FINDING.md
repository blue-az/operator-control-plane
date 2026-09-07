# Cross-chip wall clock: the MAX 390 punishes the dense model, and there is no chip factor

**Run:** z13 (Ryzen AI MAX 390), 2026-09-07. Three models × `constant-and-callers`
+ `csv-summarize-repair` × L2 × n=4 (trial 1 cold, 2–4 warm), `e9pin ctx16384
t0.8`, think off, `pi` 0.85.1 — version-matched to the desktop. Compared against
`preswap-wallclock-2026-09-05` on the dual-3090 desktop.

**Purpose:** the published cross-chip ranking normalises every Speed figure
against `gemma4:26b` at 133.0 tok/s — an unpinned two-card-split decode figure —
and decode has since been shown not to predict task time. This is the first
cross-chip data on the corrected axis (measured task wall clock).

**Stated confound:** z13 runs **ollama 0.32.13**, the desktop **0.32.12**. A
0.32.12 → 0.32.15 gap was measured to move wall clock ~25%; a one-patch gap is
unquantified. Downgrading was rejected as a 2.3 GB system change to remove an
unmeasured risk. Treat cross-chip magnitudes as approximate; within-chip
model ordering is unaffected.

## Result

Speed = mean over the two tasks of `t(3090 gemma4:26b) / t(model)`, warm trials.

| # | chip | model | constant | csv | **speed** |
|---:|---|---|---:|---:|---:|
| 1 | RTX 3090 | qwen3.6:35b | 13.0 | 21.2 | **1.662** |
| 2 | RTX 3090 | qwen3.8:27b | 17.9 | 29.7 | **1.193** |
| 3 | RTX 3090 | gemma4:26b | 15.0 | 46.0 | **1.000** |
| 4 | MAX 390 | qwen3.6:35b | 26.1 | 53.0 | **0.721** |
| 5 | MAX 390 | gemma4:26b | 20.6 | 146.6 | **0.521** |
| 6 | MAX 390 | qwen3.8:27b | 57.9 | 60.8 | **0.508** |

## There is no chip multiplier

| model | constant | csv |
|---|---:|---:|
| gemma4:26b | 1.37x | **3.19x** |
| qwen3.8:27b | **3.23x** | 2.05x |
| qwen3.6:35b | 2.01x | 2.50x |

The MAX 390 penalty ranges **1.37x to 3.23x** and **reverses ordering between the
two tasks**: `gemma4:26b` is the least penalised on the short task and the most
penalised on the long one. Any single "the MAX 390 is N× slower" number is wrong.
Budget cross-chip work per task, not per chip — the same conclusion
`testbench-2080-e9-batch1` reached for the 2080.

## The dense model is disproportionately punished

Decode tok/s on the MAX 390, same probe:

| model | arch | decode |
|---|---|---:|
| qwen3.6:35b | MoE | **54.5** |
| gemma4:26b | MoE | **53.7** |
| qwen3.8:27b | **dense** | **22.4** |

**The two MoE models decode ~2.4x faster than the dense one on this chip.** On
the 3090 the dense model is competitive (and wins on task time against 26b). This
is the third instance of the same pattern: the RTX 2080 gave `qwen3.8:27b` 16/66
layers against `gemma4:26b`'s 31/31 (8.2x), and the MAX 390 shows 2.4x.
**Memory-constrained machines punish dense models disproportionately**; the
effect scales with how constrained the machine is.

### Note on the seat — scope clarified by the operator 2026-09-07

The seat is `qwen3.8:27b` (operator decision, 2026-09-06, dense preferred).

On this chip it is the **slowest of the three on the short task** — 57.9 s
against `gemma4:26b`'s 20.6 s. **That is not an objection to the choice.** Per
the operator, **the seat is selected on desktop evidence and then used as the
cross-chip normalisation baseline.** It is a reference point, not a per-machine
deployment recommendation, so a model may hold the seat while being a poor pick
on a chip it is not selected for.

What the data above *does* say is narrower and still worth acting on: **do not
read seat rank as a deployment recommendation for the MAX 390.** On that chip the
two MoE models are roughly 2.4x faster at decode than the dense seat model.

## Quality

n=8 per model on two tasks — **not a seat score** and not comparable to the /54
scale. `qwen3.8:27b` 8/8, `qwen3.6:35b` 8/8, `gemma4:26b` **6/8** (both failures
on `csv-summarize-repair`, matching its 3/4 on the desktop). z13 still has **zero
clean-config trials on the three seat fixtures**, so it cannot be admitted to the
quality axis yet.

## Limits

- n=3 warm per cell, two tasks. Screen tier.
- ollama version differs by one patch (above).
- `gemma4:26b` emits 6,106 output tokens on csv here against 7,004 on the
  desktop — verbosity is a model property and travels across chips.
- The MAX 390 has no L0/L1 data and no seat-fixture data in clean config.

---

## SUPERSEDED 2026-09-07 — timings here include ledger overhead

Every wall-clock figure in this finding was measured with the runner's ledger
path enabled, which put ~+4.5 s/trial of `operator` CLI bookkeeping inside
`wall_clock_s` (fixed in `runner.py` the same day). **Use
`z13-wallclock-noledger-2026-09-07` instead.**

The correction is not a uniform shift. `qwen3.8:27b` moves 57.9 → **35.3 s** on
the short task and 60.8 → **96.8 s** on the long one — opposite directions,
because run-to-run variance is larger than the ledger effect.

**The claim this finding drew from those numbers does not survive.** It argued
the dense model is disproportionately punished on this chip, citing 57.9 s
against `gemma4:26b`'s 20.6 s. Clean, that gap is 35.3 vs 26.3, and on the long
task 27b *beats* 26b. The dense penalty is real in **decode** (22.4 vs 53–54
tok/s) but does not carry into task time, because token economy compensates.

What stands: there is no single chip factor (1.95x–3.40x, reversing between
tasks), and the seat-scope note.
