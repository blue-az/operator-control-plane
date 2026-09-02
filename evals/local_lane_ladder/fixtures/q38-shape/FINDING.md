# q38-shape — L0/L1 distinguishes qwen3.8:27b from the seat

> **RETIRED 2026-09-02 — opr-era artifact. Do not cite.** This pack's
> central claim (qwen3.8:27b needs plan-shaped input, L1 7/18 vs gemma4:26b
> 14/18, Fisher p=0.0409) **does not replicate under `pi`**. Re-run at L1
> on the current harness: gemma4:26b 80% (essentially unchanged from 78%
> here), **qwen3.8:27b 87%, up from 39%**. `opr` was suppressing that model
> specifically, by roughly the margin that produced the significant result.
> The two harnesses' numbers are not comparable. Retained as the record of
> what was measured, not as evidence about model capability. See
> `../e9-l1-pi-screen/FINDING.md`.

**Measured:** 2026-08-14, desktop, `num_ctx 16384`, `temperature 0.8`,
`think off`, n=6, 72/72 cells, 72/72 traces. Same-run control: `gemma4:26b`.
**Not UID-verified. No claim verified.**

L2 pass/fail and mean trajectory could not separate these two
(`q38-ladder` 34/54 vs E11 `gemma4:26b` 36/54 pooled, p=0.84; mean traj
0.909 vs 0.903). This pack asks the remaining seat-relevant question:
does `qwen3.8:27b` need plan-shaped input?

## Result

| | L0 | L1 |
|---|---:|---:|
| `qwen3.8:27b` | 1/18 | **7/18** |
| `gemma4:26b` | 2/18 | **14/18** |
| Fisher two-sided | p=1.000 | **p=0.0409** |

| Fixture | q38 L0 | 26b L0 | q38 L1 | 26b L1 |
|---|---:|---:|---:|---:|
| `ambiguous-anchor` | 0/6 | 0/6 | 4/6 | 6/6 |
| `csv-summarize-repair` | 0/6 | 0/6 | 0/6 | 2/6 |
| `strict-log-format` | 1/6 | 2/6 | 3/6 | 6/6 |

No per-fixture L1 contrast is individually significant (all p≥0.18). The
aggregate L1 gap is the same direction on every fixture.

## Finding 1 — L0 is a floor for both

1/18 vs 2/18. Neither model works from a goal-only prompt on this battery.
`qwen3.8` at L0 on `ambiguous-anchor` typically never finds `runbook.md`
(grep of `.` or a wander into `config/settings.ini`, then the repeat-guard
stops it). `gemma4:26b` at L0 either patches the wrong file or patches all
three `--force` occurrences. Different failure modes, same score.

## Finding 2 — L1 is the first measurement that separates them

7/18 vs 14/18, p=0.0409. The 39-point gap is well above the 11.3% per-cell
noise floor from e10. Combined L0+L1 is 8/36 vs 16/36, p=0.079.

This is an instruction-shape result, not a new reasoning result. At L2
(plan-shaped, numbered steps, named paths) they were tied. At L1
(file-named / partial structure — the prompt a human actually types)
`gemma4:26b` is reliable and `qwen3.8:27b` is not.

`qwen3.8:27b` therefore **needs plan-shaped input** to sit in the top band.
That is the seat-relevant distinction L2 pass/fail could not make.

n=6, one run, one machine. MSC-RUL-107: this does **not** revise the
`gemma4:26b` seat. It is the first instrument that can tell the two apart.

## Finding 3 — L2 reference, not pooled

Do not pool this pack with `q38-ladder` or E11. Those are L2-only and a
different sampling structure. For orientation only:

| | q38 L2 (prior) | 26b L2 (E11) |
|---|---:|---:|
| `ambiguous-anchor` | 16/18 | 12/12 |
| `csv-summarize-repair` | 3/18 | 0/12 |
| `strict-log-format` | 15/18 | 12/12 |

The L2 ceiling-marker fixture stays a ceiling at L1 for q38 (0/6) and
almost one for 26b (2/6). 26b's two L1 `csv` passes are the first time
this model has solved that fixture in any pack on disk; treat as n=6
instability until replicated. They do not license a "26b is better at
messy repair" claim.

## Serving / harness notes

- 1 genuine Ollama 500 (`strict-log-format` L0 q38 t6). Exclude from any
  model-capability reading of that one cell. Does not move L0 (1/17 vs 2/18
  is still p=1).
- `no_dispatch` / `HARNESS_PROTOCOL`: 1 q38 cell, 4 26b cells. 26b's three
  L1 `csv` `no_dispatch` fails mean the L1 14/18 is if anything conservative
  for the seat, not inflated.
- Think leak: 0/72.
- Timeouts: 0/72.
- `ollama ps`: 0 CPU placements, 30 samples at `100% GPU`.
- Repeat-stops: q38 17/18 at L0, 11/18 at L1; 26b 8/18 and 2/18. The L0
  floor for q38 is mostly "never advances state."

## Limits

- n=6 is the spec minimum. The L1 aggregate is significant at α=0.05 and
  would not survive a Bonferroni across the two levels (α=0.025). Report
  the p-value; do not dress it as a ranking.
- Single invocation, single 3090 at 320 W, second card still unpowered.
- No L0/L1 for `qwen3.6:27b` in this pack — predecessor comparison is L2
  only (`q38-ladder`).
