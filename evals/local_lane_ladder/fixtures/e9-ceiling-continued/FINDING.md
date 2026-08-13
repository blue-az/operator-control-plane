# E9 finding — the ceiling battery works, and it ranks the seats

**Run:** desktop, 2026-08-13, rev `422e8ee`, 210/210 cells, 210/210 traces, zero
CPU spill, n=6, `num_ctx 16384 · temperature 0.8 · think off`, uniform system
prompt, R6 scope enforced on every fixture.
**Not UID-verified. No claim registered.**

Corrects `e8-ceiling`, where `OPR-RUL-008` capped every cell at one state change.

## Result — a ranking, finally

| Model | Total | csv | booking | consts | anchor | logfmt | median |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma4:31b` | **24/30** | 0/6 | 6/6 | 6/6 | 6/6 | 6/6 | 16.1s |
| `gemma4:26b` | **24/30** | 0/6 | 6/6 | 6/6 | 6/6 | 6/6 | **10.4s** |
| `qwen3.6:27b` | 19/30 | **3/6** | 6/6 | 1/6 | 6/6 | 3/6 | 12.3s |
| `qwen3-vl:30b` | 16/30 | 0/6 | 6/6 | 6/6 | 3/6 | 1/6 | 91.9s |
| `qwen2.5-coder:14b` | 14/30 | 0/6 | 6/6 | 5/6 | 2/6 | 1/6 | 7.0s |
| `qwen3:32b` | 13/30 | 0/6 | 6/6 | 6/6 | 0/6 | 1/6 | 11.4s |
| `gemma3:27b` | 12/30 | 0/6 | 6/6 | 6/6 | 0/6 | 0/6 | 16.4s |

**122/210**, spanning 12/30 to 24/30 — a factor of two between best and worst.
After 495 cells across seven prior packs that produced almost nothing but
ceilings, this instrument resolves.

## The continuation fix, and the control that validates it

| Fixture | E8 (capped) | E9 (continuation) |
|---|---:|---:|
| `constant-and-callers` | 0/42 | **36/42** |
| `booking-off-by-one` | 22/42 | **42/42** |
| `strict-log-format` | 11/42 | 18/42 |
| `csv-summarize-repair` | 0/42 | 3/42 |
| **`ambiguous-anchor`** (control) | **22/42** | **23/42** |

`ambiguous-anchor` is single-edit and declares no continuation budget, so it
should not have moved. It went 22 → 23, inside noise. That is the result that
makes the rest of the table trustworthy: after six harness confounds in this
programme, a column that *should* stay still and does is worth more than another
column that moves.

`constant-and-callers` 0 → 36 confirms the E8 diagnosis outright. The
multi-file/cross-file domain was never a capability finding; it was a harness cap.

## Fixture quality, measured

| Fixture | Rate | Verdict |
|---|---:|---|
| `csv-summarize-repair` | 3/42 | **Brackets the top.** Only `qwen3.6:27b` passes any. Near-floor rather than discriminating — keep as a ceiling marker, do not read as a ranking. |
| `ambiguous-anchor` | 23/42 | **Best discriminator**, closest to 50%. Failures are genuine: models patch all three sections instead of the one under the named heading. |
| `strict-log-format` | 18/42 | **Good discriminator.** The trap is the output contract, not the logic. |
| `constant-and-callers` | 36/42 | Mild discrimination; separates `qwen3.6:27b` (1/6) from the field. |
| `booking-off-by-one` | 42/42 | **Now saturated — retire or harden.** Its entire E8 spread was the harness cap, not capability. |

That last row is worth stating plainly: `booking-off-by-one` looked like the
sharpest discriminator in E8 and is worth nothing. Every model solves it once the
harness lets them finish.

## Failure modes, classified mechanically

88 failures, from the trajectory parse rather than by reading traces:

| Mode | Count |
|---|---:|
| loop-guard repeat (re-issued an identical call) | 32 |
| edited, result wrong | 22 |
| tool errored — bad path or anchor | 21 |
| never dispatched | 13 |

Only 22 of 88 are "the model did the work and got it wrong." The largest single
mode is still **repetition** — a model that reads a file and then reads it again
instead of advancing. That is a behavioural failure rather than a knowledge one,
and it is the dominant obstacle to local agentic work on this evidence.

## Scope: zero violations in 210 cells

R6 was enforced on every fixture and **not one model wrote outside its declared
file set**. Worth recording as a negative result: the contract rule that went
ungraded for the whole programme turns out not to be where these models fail.
Enforcement stays on — it is cheap, and its value is precisely that a violation
would now be visible.

## Stability

Flips are finally informative, because failures exist:

| Model | Score | Unstable fixtures |
|---|---:|---:|
| `gemma4:26b` | 24/30 | **0/5** |
| `gemma4:31b` | 24/30 | **0/5** |
| `gemma3:27b` | 12/30 | 0/5 |
| `qwen3:32b` | 13/30 | 1/5 |
| `qwen3-vl:30b` | 16/30 | 2/5 |
| `qwen2.5-coder:14b` | 14/30 | 3/5 |
| `qwen3.6:27b` | 19/30 | 3/5 |

Both `gemma4` models are perfectly deterministic across six reps on all five
fixtures — every cell is 0/6 or 6/6. `qwen3.6:27b` buys its third place with
instability: 3 of 5 fixtures are coin-flips. This reproduces LocalClaw's
"reliably imperfect, precisely gateable" distinction, on different fixtures.

## Practical

**`gemma4:26b` is the local executor seat.** It ties `gemma4:31b` at 24/30, is
perfectly stable, and is **1.5x faster** (10.4s vs 16.1s median). Nothing in 210
cells justifies the larger model on this workload.

`qwen3.6:27b` is the only model that solved any `csv-summarize-repair` cell, so
it is worth keeping for genuinely messy repair work despite ranking third — but
its instability means gate it, do not trust a single run.

`qwen3-vl:30b` remains accurate-but-unsteerable: 91.9s median, ~9x the seat pick,
because it ignores `--think off` (see `e7`).

## Limits

n=6 on one machine, one prompt shape (L2), five fixtures, one quantisation.
`booking-off-by-one` is now dead weight. `csv-summarize-repair` is near-floor and
should not be read as ranking anything. Seeds are not honoured by this Ollama
build, so these are six independent draws rather than a reproducible set. Not
comparable to `e1`–`e8`: different continuation regime, and `e1`–`e6` also ran at
model-default thinking.
