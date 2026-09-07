# Pre-swap baseline — and four of six models split across cards that did not need to

**Run:** desktop, 2026-09-05, immediately before both RTX 3090s move to the
testbench. Six roster models, all pinned `num_ctx` 16384 / `temperature` 0.8,
contract-v1 probe, **n=3 round-robin with model order reversed each rep**, all
tags unloaded between every measurement. Machine state recorded in
`baseline.json`.

**Purpose:** `HARDWARE_TRANSFER.md` establishes that wall-clock, tok/s and
residency figures do not survive a hardware change. This is the reference
snapshot so post-swap differences are attributable to the move rather than to
drift or configuration mismatch — the failure mode that produced three wrong
published figures earlier the same day.

## Baseline

Environment: MSI MPG Z390 GAMING PLUS, i9-9900KF, 31 GB RAM, driver 580.178.04,
ollama 0.32.12, **GPU links x16 / x4**.

| model | tok/s (n=3) | range | VRAM (MiB) | cards | layers |
|---|---:|---|---:|---:|---|
| gemma4:26b | **226.3** | 225.4–226.7 | 19,301 | **1** | 31/31 |
| gemma4:31b | 37.7 | 36.7–38.2 | 23,451 | 2 | 61/61 |
| qwen3.8:27b | 78.1 | 76.8–79.5 | 20,364 | 2 | 66/66 |
| qwen3.6:35b | 130.0 | 128.0–131.8 | 23,682 | 2 | 42/42 |
| qwen3-next:latest | 78.5 | 77.7–79.0 | 45,378 | 2 | 49/49 |
| gpt-oss:120b | 33.8 | 32.8–34.5 | 45,226 | 2 | 37/37 |

**All six are 100% GPU-resident.** Ranges are tight — the widest is ±1.7%.

## The finding: models that fit on one card are being spread across two

Only `gemma4:26b` is single-card. The three mid-size models are **split despite
fitting comfortably in one 24,576 MiB card**:

| model | total VRAM | headroom on one card | placement |
|---|---:|---:|---|
| qwen3.8:27b | 20,364 MiB | **4,212 MiB spare** | split 10,286 / 10,116 |
| gemma4:31b | 23,451 MiB | 1,125 MiB spare | split 12,248 / 11,399 |
| qwen3.6:35b | 23,682 MiB | 894 MiB spare | split 12,666 / 11,016 |

`qwen3.8:27b` has over 4 GB of headroom and is still spread across both cards.

This matters because **splitting a model that fits cost `gemma4:26b` 35% of its
decode** (`fixtures/gemma4-26b-ctx-default-split/`). If the same penalty applies
here, the mid-band numbers in this baseline — and everywhere else in the program
— are depressed by a placement decision nobody chose.

**It is untested.** Forcing single-GPU placement requires restarting the ollama
daemon under `CUDA_VISIBLE_DEVICES=0`; ollama runs as a **system** service on
this host, so it needs root and was not attempted. This is the highest-value
open experiment and it should run **before** the cards move, because after the
swap the same test on a 4c/4t i3 confounds placement with CPU.

### It also corrects the stub

`VRAM_IS_A_BUDGET_STUB.md` records `qwen3.8:27b` as "**~18 GB, 1 card**". Measured
here it is **20,364 MiB across 2 cards**. Both halves were wrong, and the "1 card"
appears to have been assumed rather than read.

## An instrument bug in this run's own capture

The layer-count regex took the **last** `offloaded N/M layers` line in the
window. `gemma4:26b` ships a vision projector, which logs its own `5/5` after the
LLM's `31/31`, so the model was recorded as `5/5`. Corrected in `baseline.json`
with a note; no other model has an mmproj, so nothing else is affected.

Fifth instrument problem in a week, and the same shape as the others: **wrong
answer, no error.**

## How to use this after the swap

Re-run the identical script on the bench with both 3090s installed. Compare
per-model tok/s and placement. Attribute differences only after confirming the
pinned tags and `num_ctx` match — `baseline.json` records the full environment
for exactly that check.

Expect placement itself to change: the bench has the same board but 15 GB of
system RAM until the 32 GB moves with the cards, and ollama's split decision
takes host memory into account.

## Limits

- Decode only. No wall-clock or task-completion figures; for those the
  comparable reference is `fixtures/roster-walltime-2026-09-05/`.
- n=3 per model, single session, no thermal soak. Ranges are tight but a
  sustained load could diverge.
- The split-vs-single penalty is **assumed** from `gemma4:26b`, not measured for
  these three models.
