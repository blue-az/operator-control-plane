# Local Lane Ladder — Results

Generated from 120 trial records.
Producer machine(s): desktop.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| gemma4:26b | — | 24/30 | — | 137.9 | 36.0 |
| gemma4:31b | — | 30/30 | — | 34.8 | 133.9 |
| gpt-oss:120b | — | 30/30 | — | 32.9 | 69.5 |
| qwen3.8:27b | — | 26/30 | — | 80.1 | 24.0 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### ambiguous-anchor

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | 6/6 | — |
| gemma4:31b | — | 6/6 | — |
| gpt-oss:120b | — | 6/6 | — |
| qwen3.8:27b | — | 6/6 | — |

### booking-off-by-one

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | 6/6 | — |
| gemma4:31b | — | 6/6 | — |
| gpt-oss:120b | — | 6/6 | — |
| qwen3.8:27b | — | 6/6 | — |

### constant-and-callers

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | 5/6 | — |
| gemma4:31b | — | 6/6 | — |
| gpt-oss:120b | — | 6/6 | — |
| qwen3.8:27b | — | 2/6 | — |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | 2/6 | — |
| gemma4:31b | — | 6/6 | — |
| gpt-oss:120b | — | 6/6 | — |
| qwen3.8:27b | — | 6/6 | — |

### strict-log-format

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | 5/6 | — |
| gemma4:31b | — | 6/6 | — |
| gpt-oss:120b | — | 6/6 | — |
| qwen3.8:27b | — | 6/6 | — |
