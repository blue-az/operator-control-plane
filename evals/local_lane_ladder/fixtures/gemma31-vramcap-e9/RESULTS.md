# Local Lane Ladder — Results

Generated from 6 trial records.
Producer machine(s): desktop.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| gemma4:31b | — | — | 3/6 | 5.0 | 375.7 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under.

## Per-task breakdown

### constant-and-callers

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:31b | — | — | 3/3 |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:31b | — | — | 0/3 |
