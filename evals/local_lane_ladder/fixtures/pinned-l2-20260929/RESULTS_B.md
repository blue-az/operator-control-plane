# Local Lane Ladder — Results

Generated from 30 trial records.
Producer machine(s): desktop.

> **1 of 30 cells are unproven** (dispatch, placement). An unproven cell is evidence about the harness, not about the model: it is not a failure and is not poolable as a result. Triage the instrument before reading the spread below.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| pinB-qwen3-next-thinking:latest | — | — | 29/30 (1 unproven, 29/30 attempted) | 69.7 | 139.2 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### ambiguous-anchor

| Model | L0 | L1 | L2 |
|---|---|---|---|
| pinB-qwen3-next-thinking:latest | — | — | 6/6 |

### booking-off-by-one

| Model | L0 | L1 | L2 |
|---|---|---|---|
| pinB-qwen3-next-thinking:latest | — | — | 6/6 |

### constant-and-callers

| Model | L0 | L1 | L2 |
|---|---|---|---|
| pinB-qwen3-next-thinking:latest | — | — | 5/6 (1 unproven, 5/6 attempted) |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| pinB-qwen3-next-thinking:latest | — | — | 6/6 |

### strict-log-format

| Model | L0 | L1 | L2 |
|---|---|---|---|
| pinB-qwen3-next-thinking:latest | — | — | 6/6 |
