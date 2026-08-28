# Local Lane Ladder — Results

Generated from 102 trial records (gemma4:26b, gemma4:31b, qwen3.8:27b) + 30 trial
records (qwen3.6:35b, re-run separately -- see note below).
Producer machine(s): desktop.

**Note on qwen3.6:35b:** the first attempt at this cell (120-cell run, same batch
as the other three models) produced 0/12 -- not a capability failure, but a
CUDA illegal-memory-access crash caused by Ollama auto-splitting the model
across both GPUs on this rig's asymmetric-slot dual-3090 (one x16, one x4
riser), a regression introduced by the matched-pair GPU upgrade. Root cause
confirmed by a controlled single-GPU daemon test (`CUDA_VISIBLE_DEVICES=0`,
`GGML_VK_VISIBLE_DEVICES=` to also block Vulkan's independent GPU discovery --
see Front I finding for the full diagnosis). qwen3.6:35b was then re-run in
isolation against that single-GPU daemon; those are the real capability numbers
below. The original 0/12 crash artifacts are preserved at
`RESULTS-q36-35b-crossgpu-crash-artifact.md` for the record.

## Pass rate per model x level (all tasks combined)

| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | wall_clock_s (mean, per trial) |
|---|---|---|---|---|---|
| gemma4:26b | — | — | 28/30 | 137.3 | 37.1 |
| gemma4:31b | — | — | 30/30 | 34.3 | 68.8 |
| qwen3.6:35b | — | — | **30/30** | 133.4 | 13.1 |
| qwen3.8:27b | — | — | 30/30 | 77.5 | 19.0 |

> decode tok/s is a supplementary direct-Ollama probe (`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, `temperature 0`, run against the same pinned model config as the trial), not derived from the implementer's own turn timing -- see runner.py's `measure_tok_s` docstring for why. wall_clock_s is task-completion time (includes tool-execution, not decode-only) and is what the capability pass/fail cells above were actually measured under. qwen3.6:35b's wall_clock_s (13.1) is not directly comparable to the other three -- it was measured single-GPU (no cross-GPU split overhead, no contention from co-scheduled models) rather than against the shared systemd daemon the other three ran under.

## Per-task breakdown

### ambiguous-anchor

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 6/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |

### booking-off-by-one

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 6/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |

### constant-and-callers

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 6/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |

### csv-summarize-repair

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 5/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |

### strict-log-format

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | — | — | 5/6 |
| gemma4:31b | — | — | 6/6 |
| qwen3.6:35b | — | — | 6/6 |
| qwen3.8:27b | — | — | 6/6 |

## Headline

All four current-roster models hit the E9 ceiling under `pi` (28-30/30), with
gemma4:26b the sole outlier (misses on csv-summarize-repair and
strict-log-format). This roster no longer discriminates at L2 -- the ceiling
effect flagged earlier in this session (opr-era harness quality was the real
bottleneck, not model capability) still holds now that the harness itself is
solid. Harder/more discriminating task design remains the open next step.
