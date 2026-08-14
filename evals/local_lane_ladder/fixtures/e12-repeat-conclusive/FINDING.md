# E12 finding — mechanism proven, outcome still not; and my design diluted it

**Run:** desktop, 2026-08-13, rev `1d1d30d`, 432 cells (216/arm), 9 cell classes
× n=24 × 2 arms, arms interleaved per class.
`num_ctx 16384 · temperature 0.8 · think off`. **Not UID-verified. No claim.**

Built to settle what `e10` left open: E10 measured +11.1 pts on engaged cells at
**p=0.32**, roughly 4x underpowered. E12 targets only the classes where the repeat
path engages, at n=24, powered for a ~14-pt effect.

## Pre-specified result: not significant

| Class | stop | feedback | Δ |
|---|---:|---:|---:|
| `booking-off-by-one` × `qwen2.5-coder:14b` | 21/24 | 24/24 | +12.5 |
| `booking-off-by-one` × `qwen3.6:27b` | 24/24 | 24/24 | +0.0 |
| `booking-off-by-one` × `qwen3:32b` | 24/24 | 24/24 | +0.0 |
| `constant-and-callers` × `gemma3:27b` | 24/24 | 24/24 | +0.0 |
| **`constant-and-callers` × `qwen3.6:27b`** | **13/24** | **23/24** | **+41.7** |
| `csv-summarize-repair` × `gemma4:26b` | 0/24 | 2/24 | +8.3 |
| `csv-summarize-repair` × `gemma4:31b` | 0/24 | 0/24 | +0.0 |
| `csv-summarize-repair` × `qwen2.5-coder:14b` | 0/24 | 0/24 | +0.0 |
| `strict-log-format` × `gemma4:31b` | 24/24 | 24/24 | +0.0 |
| **aggregate** | **130/216** | **145/216** | **+6.9** |

**Fisher exact p = 0.1613.** The properly powered test did not reach significance.

## Why: I selected the wrong classes

**Seven of nine classes were pinned at ceiling or floor in *both* arms** — five at
24/24, two at 0/24. They cannot express an outcome difference regardless of what
the intervention does, and they contributed **144 cells per arm of pure
dilution**.

The selection criterion was "the repeat path engaged here in E10". That is not
the same as "this class can show an outcome difference". A class can hit the
repeat guard on every trial and still finish 24/24 because the model recovers
anyway, or 0/24 because it cannot solve the task even unstuck. **Engagement is a
property of the process; headroom is a property of the outcome.** A future test
must select on both.

This is the second design error on the same question: `e10` was underpowered,
`e12` was diluted. The question is not hard to answer — it has been hard to
*ask*.

## Restricted to the three classes with headroom

| | cells/arm | rate | |
|---|---:|---:|---|
| stop | 72 | 34/72 (47.2%) | |
| feedback | 72 | 49/72 (68.1%) | **+20.8 pts** |

**Fisher exact p = 0.0179.**

**Treat this as hypothesis-generating, not confirmatory.** The subset was chosen
*after* seeing the data. The criterion is principled and derivable from the stop
arm alone, but post-hoc subsetting is exactly the procedure that manufactures
false positives, and it would be dishonest to present p=0.018 as the finding when
the pre-specified analysis returned p=0.16.

## Mechanism: overwhelming, and not in doubt

| | repeat-stops | fed back | state-changing calls |
|---|---:|---:|---:|
| stop | **169/216** | 0 | 347 |
| feedback | **51/216** | 190 | **501** |

Repeat-stops fell **69%**; state-changing tool calls rose **44%**. Feedback fired
190 times and 51 cells still ended in a stop — those exhausted the 3-round budget,
so roughly **three-quarters of repeats are recoverable and one quarter are
genuinely stuck**. That split did not exist as a measurable quantity before.

## Verdict

**Keep `stop` as the default.** Two properly-run experiments have failed to show
an outcome benefit at the pre-specified level, and a default change needs better
than that.

**The mechanism claim is settled and worth acting on separately:** the guard
*is* cutting models off mid-task, at scale, and `--on-repeat feedback` recovers
most of those runs. Whether recovery converts to passing depends on whether the
model could have solved the task at all — which is precisely what the ceiling and
floor classes above demonstrate.

**A third attempt should select classes on mid-range baseline** (say 25–75% in
the stop arm), not on repeat engagement. On this evidence roughly one class in
three qualifies, so it needs a wider survey first to find enough of them.
