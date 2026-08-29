# gpt-oss:120b — E9 ceiling battery

**Run:** desktop, 2026-08-29, same meter as `e9-pi-rerun` (`num_ctx` 16384,
`temperature` 0.8, `think` off, dispatched via `pi`). 5 fixtures x n=6 = 30
cells, standard `runner.py` path (`ensure_pinned_model`, trace retention on).

**Model:** `gpt-oss:120b` -- 116.8B total params, MoE (128 experts, 4 active,
~3.1% active fraction), GQA 64:8, MXFP4 quant, 67 GB on disk, native context
131072. Loaded split 35%/65% CPU/GPU across both cards (67 GB does not fit
one 24 GB card, so this split is necessary, not the avoidable-split problem
documented elsewhere in this Front for smaller models).

**Why screened first:** `ollama ps` showing 65% CPU placement on a 67 GB
model looked like a strong candidate for a very slow run. An ad-hoc single
trial (no pin, default settings) came back in 59.7s, passed, 1113 tokens --
fast enough to justify the real battery rather than skip it.

## Result: 30/30, clean sweep

| model | E9 pass | decode tok/s (contract-v1 probe) | wall_clock_s (mean) |
|---|---|---:|---:|
| gemma4:26b | 28/30 | 137.3 | 37.1 |
| gemma4:31b | 30/30 | 34.3 | 68.8 |
| qwen3.6:35b | 30/30 | 133.4 | 13.1 |
| qwen3.8:27b | 30/30 | 77.5 | 19.0 |
| **gpt-oss:120b** | **30/30** | **32.7** | **41.4** |

Per-task: 6/6 on all five fixtures (`ambiguous-anchor`, `booking-off-by-one`,
`constant-and-callers`, `csv-summarize-repair`, `strict-log-format`).

## Reading it: efficient, not fast

Decode speed (32.7 tok/s) sits right next to gemma4:31b's (34.3) -- both
near the bottom of the roster, as expected for a 67 GB model with majority
CPU placement even with extreme MoE sparsity keeping it far above what a
dense model that size would manage. But wall-clock (41.4s) beats gemma4:31b's
(68.8s) by a wide margin despite near-identical decode speed. Per-task token
counts confirm why -- tight and low, not just fast:

| task | completion tokens (6 trials) | turns (6 trials) |
|---|---|---|
| csv-summarize-repair | 1173, 1250, 1330, 1048, 1662, 1319 | 5,5,5,5,5,5 |
| strict-log-format | 952, 843, 630, 1022, 910, 792 | 5,5,5,5,5,5 |
| ambiguous-anchor | 640, 750, 845, 1204, 553, 970 | 4,5,4,7,4,8 |
| booking-off-by-one | 381, 515, 550, 620, 410, 411 | 5,5,4,5,5,5 |
| constant-and-callers | 718, 720, 710, 701, 759, 671 | 8,8,8,8,8,8 |

Compare csv-summarize-repair's ~1297-token mean here against qwen3.8:27b's
902 (terse) and gemma4:31b's 3028 (verbose, see the same session's
brevity-ablation finding) -- gpt-oss:120b sits closer to the terse end.
Turn counts are also unusually tight per-task (constant-and-callers is
exactly 8 every single trial) -- much lower variance than gemma4:26b showed
on the same fixtures (5-12 turns). This is the same token-efficiency axis the
brevity-ablation work isolated as separate from raw decode speed, showing up
here as a model's own default behavior rather than something a prompt change
induced.

## What this means for the roster

A 120B-class MoE model, two-thirds CPU-offloaded, clears the identical
ceiling every other model in the current roster clears (28-30/30). This
widens the span of model sizes E9 fails to discriminate at -- not a knock on
gpt-oss:120b, but further evidence the harness itself, not model capability,
is now the binding constraint on this roster. Reinforces the standing
open item: a harder/more discriminating task tier is needed before adding
more models to this exact battery tells us anything new.

## Limits

- Single `num_ctx` pin (16384), well below the model's native 131072 --
  untested whether CPU-offload fraction or throughput changes at longer
  context.
- The pre-battery screening trial used the model's own default settings (no
  pin) for speed; only the 30-cell battery above used the standard pinned
  methodology.
- Single machine, single quant (MXFP4, the only one Ollama distributes for
  this model).
