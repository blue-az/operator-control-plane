# Quality rank transfers across chips; speed rank does not

**Run:** z13 (Ryzen AI MAX 390), 2026-09-07. Three models × the three seat
fixtures × L2 × n=6 = 54 cells. `e9pin ctx16384 t0.8`, think off, `--no-ledger`,
`pi` 0.85.1 version-matched to the desktop. **The first clean-config data this
machine has** — before this run z13 had 96 trials and *zero* that qualified for
the quality axis.

## Result

| model | ambiguous-anchor | csv-summarize-repair | strict-log-format | total | rate |
|---|---|---|---|---|---:|
| qwen3.8:27b | 6/6 | 6/6 | 6/6 | **18/18** | **100%** |
| qwen3.6:35b | 6/6 | 6/6 | 6/6 | **18/18** | **100%** |
| gemma4:26b | 5/6 | 5/6 | 6/6 | 16/18 | 88.9% |

Against the desktop's clean L2 corpus:

| model | z13 | desktop | agrees? |
|---|---:|---:|---|
| qwen3.8:27b | 100% (n=18) | 100% (n=63) | yes |
| qwen3.6:35b | 100% (n=18) | 100% (n=51) | yes |
| gemma4:26b | 88.9% (n=18) | 83.7% (n=178) | yes |

**Both machines produce the same ordering and the same shape** — two models at
ceiling, `gemma4:26b` trailing by a similar margin. On a very different
accelerator (iGPU vs discrete, ~2.4x slower on MoE and ~3.5x on dense).

## The asymmetry that matters

**Quality rank is a model property here. Speed rank is not.**

The companion wall-clock run (`z13-wallclock-2026-09-07`) shows the MAX 390
*reorders* the speed axis: `qwen3.8:27b` is second-fastest of the three on the
desktop and the **slowest** on this chip (57.9 s vs `gemma4:26b`'s 20.6 s on the
short task), because dense models are punished disproportionately on constrained
memory. The chip penalty also has no single factor — it ranges 1.37x to 3.23x
and reverses between tasks.

**Operator consequence: measure quality once per model, speed once per machine.**
Re-running the seat battery on every new host costs hours and reproduces the
answer already in hand. Re-running wall clock is mandatory, because it does not
transfer.

## Scale — do not pool this with the desktop

This is n=6 per fixture: an **`/18` floor-battery score**, not the `/54` seat
score. `LOCAL_LANE_POWER_RANKING_PROTOCOL.md` states the scales are not
interchangeable. Expressed as rates above so the two are comparable without
implying a shared denominator.

## Limits

- n=6 per fixture. Adequate to confirm the ordering transfers, not to separate
  the two models at 100% — the same saturation the desktop battery has.
- **z13 runs ollama 0.32.13, the desktop 0.32.12.** A stated confound. Pass/fail
  on deterministic postconditions is far less exposed to it than timing is, but
  it is not zero.
- Three models. The roster's other three do not run here or were not tested.
- L2 only. z13 still has no clean L0/L1 data, and L0 is known broken as authored
  (`l0-tiebreak-2026-09-06`).
