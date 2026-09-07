# Local Lane Ladder — Results

Generated from 54 trial records.
Producer machine(s): z13.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| gemma4:26b | — | — | 16/18 | 52.2 | 124.4 |
| qwen3.6:35b | — | — | 18/18 | 54.5 | 27.5 |
| qwen3.8:27b | — | — | 18/18 | 22.2 | 65.2 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### ambiguous-anchor

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 5/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 5/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |

### strict-log-format

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 6/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |
