# Local Lane Ladder — Results

Generated from 9 trial records.
Producer machine(s): desktop.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| gemma4:31b | 1/3 | — | — | 36.8 | 449.6 |
| gpt-oss:120b | 0/3 | — | — | 30.9 | 90.0 |
| qwen3.8:27b | 1/3 | — | — | 81.7 | 26.7 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### ambiguous-anchor

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:31b | 1/3 | — | — |
| gpt-oss:120b | 0/3 | — | — |
| qwen3.8:27b | 1/3 | — | — |
