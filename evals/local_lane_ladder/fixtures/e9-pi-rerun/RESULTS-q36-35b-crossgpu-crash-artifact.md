# Local Lane Ladder — Results

Generated from 102 trial records.
Producer machine(s): desktop.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| gemma4:26b | — | — | 28/30 | 137.3 | 37.1 |
| gemma4:31b | — | — | 30/30 | 34.3 | 68.8 |
| qwen3.6:35b | — | — | 0/12 | 132.9 | 103.4 |
| qwen3.8:27b | — | — | 30/30 | 77.5 | 19.0 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### ambiguous-anchor

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 6/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | 0/6 |
| qwen3.8:27b | — | — | 6/6 |

### booking-off-by-one

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 6/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | 0/6 |
| qwen3.8:27b | — | — | 6/6 |

### constant-and-callers

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 6/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | — |
| qwen3.8:27b | — | — | 6/6 |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 5/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | — |
| qwen3.8:27b | — | — | 6/6 |

### strict-log-format

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 5/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | — |
| qwen3.8:27b | — | — | 6/6 |
