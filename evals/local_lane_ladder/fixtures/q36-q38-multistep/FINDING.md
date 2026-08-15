# 3.6 vs 3.8 on a multi-step fixture — null, on a fixture with headroom

**Measured:** 2026-08-15, `constant-and-callers`, L2, n=18 per model,
`num_ctx 16384`, `temperature 0.8`, `think off`, `state_changes: 5`. 36 cells.
**Not UID-verified. No claim registered.**

## The question

Qwen reports large **long-horizon agentic** gains for 3.6 → 3.8: DeepSWE 1.1
13.3 → 42.2, Terminal-Bench 2.1 63.4 → 73.0, OSWorld-Verified 63.9 → 84.3.
Every fixture run so far resolves in 3–4 tool calls, which is the wrong regime
to see that. `constant-and-callers` requires 5 state changes across three files
that must end consistent, with the stale value surviving nowhere.

Ruled out first: the ollama `qwen35` parse bug fires on **0.12%** of requests
(10 / 8,122 since 2026-08-01; 2 / 153 during the contract run). Too rare to
explain a null result, so it is not the reason.

## Result

| Model | Pass |
|---|---:|
| `qwen3.8:27b` | 13/18 (72.2%) |
| `qwen3.6:27b` | 12/18 (66.7%) |

**p=1.000.** Zero timeouts, zero failed tool calls from either model.

This is the strongest null of the set, because **this fixture has headroom**.
The others were saturated (100% / 88.9%) or floored (16.7%), where no difference
could show even if one existed. At 67–72% both models sit in the discriminating
middle, and there is still nothing to see.

## The replication record

Two findings reached significance across this work. **Both died on retest.**

| finding | original | retest |
|---|---|---|
| contract fidelity | `strict-log-format` **p=0.0005** | `strict-table-render` p=0.104, *direction reversed* |
| `run_command` usage | `strict-table-render` **p=0.0455** | `constant-and-callers` p=0.733 |

The `run_command` result was that 3.6 never verified — 0/18. On this fixture it
verified in **10/18** cells. It was a fixture property, not a model property.

## Head-to-head totals

| pack | 3.8 | 3.6 |
|---|---|---|
| ladder, 3 fixtures | 34/54 | 28/54 |
| `strict-table-render` | 14/18 | 18/18 |
| `constant-and-callers` | 13/18 | 12/18 |
| comprehension probes | 15/15 | 15/15 |
| **total** | **76/105** | **73/105** |

**p=0.761.**

## Tool census (this fixture)

| | patch_file | read_file | run_command | grep_search | failed |
|---|---:|---:|---:|---:|---:|
| `qwen3.6` | 45 | 13 | 10 | 0 | **0** |
| `qwen3.8` | 45 | **2** | 12 | 1 | **0** |

Identical patch volume and median call count (4). `qwen3.8` reads far less — 2
`read_file` calls across 18 cells against 3.6's 13 — and it costs nothing here.
Small numbers, recorded rather than claimed.

## What this does and does not say

It does **not** say Qwen's benchmarks are wrong. DeepSWE and Terminal-Bench are
long-horizon, multi-turn, and far harder than a five-edit fixture; nothing here
reaches that regime.

It says that **on bounded local agentic work, across 210 head-to-head cells,
these two revisions are not distinguishable** — and that the instrument used
here resolves roughly 14 of 54 cells while the gaps in question are 0–2 cells
wide. Closing that by trials alone needs ~2,600 cells per model.

The honest conclusion is about the measurement, not the models.
