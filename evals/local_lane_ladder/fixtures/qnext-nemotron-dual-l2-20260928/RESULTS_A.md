# Local Lane Ladder — Results

Generated from 90 trial records.
Producer machine(s): desktop.

> **4 of 90 cells are unproven** (placement). An unproven cell is evidence about the harness, not about the model: it is not a failure and is not poolable as a result. Triage the instrument before reading the spread below.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| nemotron-lightning-e9pin-ctx16384-t0p8:latest | — | — | 30/30 (24/30 attempted) | 109.4 | 41.7 |
| qwen3-next-instruct-e9pin-ctx16384-t0p8:latest | — | — | 26/30 (4 unproven, 22/30 attempted) | 67.5 | 46.2 |
| qwen3.6-35b-e9pin-ctx16384-t0p8:latest | — | — | 30/30 (24/30 attempted) | 120.0 | 15.1 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### ambiguous-anchor

| Model | L0 | L1 | L2 |
|---|---|---|---|
| nemotron-lightning-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |
| qwen3-next-instruct-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |
| qwen3.6-35b-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |

### booking-off-by-one

| Model | L0 | L1 | L2 |
|---|---|---|---|
| nemotron-lightning-e9pin-ctx16384-t0p8:latest | — | — | 6/6 (0/6 attempted) |
| qwen3-next-instruct-e9pin-ctx16384-t0p8:latest | — | — | 6/6 (0/6 attempted) |
| qwen3.6-35b-e9pin-ctx16384-t0p8:latest | — | — | 6/6 (0/6 attempted) |

### constant-and-callers

| Model | L0 | L1 | L2 |
|---|---|---|---|
| nemotron-lightning-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |
| qwen3-next-instruct-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |
| qwen3.6-35b-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| nemotron-lightning-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |
| qwen3-next-instruct-e9pin-ctx16384-t0p8:latest | — | — | 5/6 (1 unproven, 5/6 attempted) |
| qwen3.6-35b-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |

### strict-log-format

| Model | L0 | L1 | L2 |
|---|---|---|---|
| nemotron-lightning-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |
| qwen3-next-instruct-e9pin-ctx16384-t0p8:latest | — | — | 3/6 (3 unproven, 5/6 attempted) |
| qwen3.6-35b-e9pin-ctx16384-t0p8:latest | — | — | 6/6 |
