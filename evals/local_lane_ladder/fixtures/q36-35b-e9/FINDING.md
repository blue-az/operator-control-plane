# q36-35b-e9 — 35b is on the E9 battery, and it does not take the seat

**Run:** desktop, 2026-08-17T23:10:32Z–23:19:47Z, rev `3e49564`, 60/60 cells,
60/60 traces. `num_ctx 16384 · temperature 0.8 · think off`. Same-run
control: `gemma4:26b`. Placement sampled every 30s. **Not UID-verified.**
G2 was not a veto.

Question: where does `qwen3.6:35b` sit on the E9 ceiling battery.

## Result

| Model | Total | csv | booking | consts | anchor | logfmt | median |
|---|---:|---:|---:|---:|---:|---:|---:|
| `gemma4:26b` | **24/30** | 0/6 | 6/6 | 6/6 | 6/6 | 6/6 | 8.3s |
| `qwen3.6:35b` | 14/30 | 0/6 | 4/6 | **0/6** | 5/6 | 5/6 | 7.3s |

Fisher two-sided **p=0.015** (14/30 vs 24/30). The same-run 26b row is
identical to E9 (24/30, 0/6 csv, 6/6 on the rest). The instrument held.

## Finding 1 — 86 t/s does not buy the ceiling

35b is second on this desk for decode and last of the two on this battery.
The hole was not “35b would have won if we had ranked it.” The hole was
refusing to measure. Measured: it is a fast Qwen that fails
`constant-and-callers` outright (0/6, stale `up to 3 times`) and drops
two booking cells E9 had as saturated (42/42).

`strict-log-format` 5/6 matches the earlier 3-fixture look (6/6 there).
`csv-summarize-repair` is floor for both (0/12), same `food=46.44`
miss. Do not read csv as a ranking.

Do not pool this 14/30 with E9’s seven-model table as if 35b had been
in that invocation. Compare 26b to 26b (held) and treat 35b as a new
row against that control.

## Finding 2 — placement stayed a lip, not a confound

`ollama ps` during the pack: 35b `100% GPU` (22 GB) and `4%/96%` (23 GB);
26b `100% GPU` every sample. Same host row as `q36-35b-spill-tps`. Cells
completed in 2.5–29s against a 600s limit. Nothing was timeout-mediated.
The 4% did not produce the 0/6 on consts — those fails are a stale
literal, not a spill cliff.

## Seat

Unchanged. `gemma4:26b` remains the seat. 35b is a desktop **speed** row
(86.4 t/s) and an E9 **correctness** row (14/30). Those are now both on
the table. Neither moves 26b.

## Limits

n=6, two models, one machine, 9 minutes wall. Not UID-verified. Not
pooled into E9/E11 aggregates. Cross-invocation 27b 19/30 (E9) is
orientation only — 35b was not faster *and* not better than that
predecessor on this battery.
