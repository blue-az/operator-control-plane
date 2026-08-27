# q38-ladder trajectory — scored 2026-08-14 by grok

Scored retroactively over the 54 retained `qwen3.8:27b` traces, compared
with E11's `gemma4:26b` / `gemma4:31b` / `qwen3.6:27b` on the same three
fixtures and settings. No re-run. The postcondition remains the sole gate.

**Not UID-verified.**

## Serving flake (do not fold into the model score)

5 of 54 cells ended in `Ollama API Error: 500` on `/api/generate`
(`ambiguous-anchor` t3, `csv-summarize-repair` t12/t17/t18,
`strict-log-format` t13). `classify_failure` marks them `INFRA`.
They are not model failures. The published 34/54 treats them as fails.

Adjusted: **34 pass / 5 infra / 15 model-fail = 34/49** (69.4%).
Still indistinguishable from `gemma4:26b` 24/36 on E11 (66.7%) and the
pooled 36/54 (66.7%). This does not move the ranking.

Two further zero-call cells (`csv-summarize-repair` t9,
`strict-log-format` t12) are not infra: the model emitted a one-sentence
intent ("Let me start by reading…") and stopped. Those stay `MODEL_FAILURE`.

## Scores (E11 models are n=12/fixture; q38 is n=18)

| Model | Pass (raw) | Mean traj | Passed clean | Passed flawed | Repeat-stops |
|---|---:|---:|---:|---:|---:|
| `qwen3.8:27b` | 34/54 (34/49 ex-infra) | **0.909** | 27 | 7 | 9 |
| `gemma4:26b` | 24/36 | 0.903 | 22 | 2 | 14 |
| `gemma4:31b` | 24/36 | 0.822 | 12 | 12 | 23 |
| `qwen3.6:27b` | 16/36 | 0.968 | 16 | 0 | 2 |

Mean trajectory does **not** break the q38 vs 26b tie (0.909 vs 0.903).
Among successes, 26b is cleaner (22/24 = 92% vs 27/34 = 79%). q38 repeats
less often than either gemma4 (9/54 vs 14/36 and 23/36). Think leak is
zero on all 54 q38 cells. `no_dispatch` is zero.

## Per fixture

| Fixture | q38 pass | q38 traj | 26b pass | 26b traj |
|---|---:|---:|---:|---:|
| `ambiguous-anchor` | 16/18 | 0.97 | 12/12 | 1.00 |
| `strict-log-format` | 15/18 | 0.87 | 12/12 | 0.96 |
| `csv-summarize-repair` | 3/18 | 0.89 | 0/12 | 0.75 |

## What this does and does not settle

The E9-style tiebreaker (mean trajectory) that separated `gemma4:26b` from
`gemma4:31b` does **not** separate `qwen3.8:27b` from `gemma4:26b` on this
battery. L2 pass/fail cannot either. The remaining untested seat-relevant
axis is L0/L1 shape dependence — q38 has never been run off plan-shaped
input, and neither gemma4 has on these three fixtures.

Ladder wall-clock (q38 9.3s mean vs 26b 12.1s) is not a decode-rate claim.
Decode is already measured separately (43.7 vs 133 tok/s). Do not promote
the wall-clock ratio.
