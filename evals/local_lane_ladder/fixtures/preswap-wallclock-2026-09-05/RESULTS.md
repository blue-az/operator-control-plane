# Local Lane Ladder — Results

Generated from 48 trial records.
Producer machine(s): desktop.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| gemma4:26b | — | — | 7/8 | 230.5 | 32.2 |
| gemma4:31b | — | — | 8/8 | 36.4 | 102.6 |
| gpt-oss:120b | — | — | 8/8 | 34.0 | 80.5 |
| qwen3-next:latest | — | — | 6/8 | 78.9 | 188.9 |
| qwen3.6:35b | — | — | 8/8 | 131.3 | 20.9 |
| qwen3.8:27b | — | — | 8/8 | 74.7 | 28.4 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### constant-and-callers

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 4/4 |
| gemma4:31b | — | — | 4/4 |
| gpt-oss:120b | — | — | 4/4 |
| qwen3-next:latest | — | — | 4/4 |
| qwen3.6:35b | — | — | 4/4 |
| qwen3.8:27b | — | — | 4/4 |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 3/4 |
| gemma4:31b | — | — | 4/4 |
| gpt-oss:120b | — | — | 4/4 |
| qwen3-next:latest | — | — | 2/4 |
| qwen3.6:35b | — | — | 4/4 |
| qwen3.8:27b | — | — | 4/4 |
