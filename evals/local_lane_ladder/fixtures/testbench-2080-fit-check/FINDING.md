# The bench is an MoE-only host: dense models get 24% of their layers on an 8 GB card

**Run:** testbench, 2026-09-05. Contract-v1 probe (`num_predict 128`,
`temperature 0`, `num_ctx 16384`) on a real RTX 2080, 8 GB. ollama 0.32.12.

**Question:** the campaign plan moves most functional benchmarking to the
headless bench. `gemma4:26b` works there. Which other roster models can follow?

## Result: only MoE models are viable

| model | class | layers on GPU | VRAM used | decode tok/s |
|---|---|---:|---:|---:|
| gemma4:26b | **MoE** (30 blocks, 128 experts, 8 active) | **31/31** — 100% | 7,416 MiB | **31.02** |
| qwen3.8:27b | **dense** (66 blocks) | **16/66** — 24% | 6,438 MiB | **3.80** |

**8.2x slower on the same card**, from a model that is *smaller* on disk (17 GB
vs 18 GB). Rates were stable — 3.68 / 3.77 / 3.79 / 3.80 across four runs.

For reference, `qwen3.8:27b` does **74-77 tok/s** on the desktop's 3090. The
2080 gives it about **5% of that**.

## The mechanism is arithmetic, not inference

A **dense** layer carries its full weight matrix, so layer count and memory
footprint scale together — 8 GB buys 16 of 66 layers, and the other 50 stream
from system RAM every token.

An **MoE** layer does not. `gemma4:26b`'s 18 GB is dominated by 128 experts, of
which 8 are active per token and all of which stream from RAM regardless of what
the GPU holds. The per-layer non-expert weights are small enough that **all 30
blocks plus the output layer fit in 7.4 GB.**

Same card, same VRAM budget, opposite outcomes — because "how many layers fit"
means something completely different for the two architectures.

This is the dense-vs-MoE constraint story in the form that survives. An earlier
attempt at it (`ARCHITECTURE_PREDICTS_THE_WALL_NOT_THE_CEILING_STUB.md`, retired)
died because `num_gpu` capping constrains dense and MoE models differently and
the asymmetry was an instrument artifact. **Here the constraint is a physical
card and the measurement is a layer count read from the daemon**, not a
simulated envelope.

## Consequence: dense models cannot complete E9 on this bench at all

Not "slowly" — **at all**, within the harness's own timeout.

Projecting from `gemma4:26b`'s measured bench wall-clock at the 8.2x decode
ratio:

| | gemma4:26b (measured) | qwen3.8:27b (projected) |
|---|---:|---:|
| mean per trial | 141 s | **~1,150 s** |
| worst task (`csv-summarize-repair`) | 331 s | **~2,700 s** |
| harness timeout | 600 s | 600 s |

The mean alone is nearly double the timeout; the worst task is **4.5x** over it.
A dense-model E9 run here would produce a wall of timeouts that look like
capability failures and are not — the same conflation already flagged for
`no_dispatch` stalls and for the `gemma4:31b` VRAM stall.

**So the bench hosts MoE models only.** For the campaign split that means the
functional lanes can move for `gemma4:26b` and, pending their own fit checks,
`qwen3.6:35b` (`qwen35moe`, 22 GB) — while every dense model stays on the
desktop.

## Limits

- **Two models, one of each class.** The mechanism is arithmetic and the layer
  counts were read directly, but the 2x2 lesson applies: do not assume every MoE
  fits or every dense model fails until each is checked. `qwen3.6:35b` at 22 GB
  is the next candidate and is untested here.
- `gpt-oss:120b` is out regardless — 45.6 GB resident against 8 GB of VRAM and
  15 GB of RAM.
- `gemma4:31b` (dense, 19 GB, 60 blocks) is expected to behave like
  `qwen3.8:27b` or worse. Untested.
- n=1 configuration per model; decode is a continuous metric measured across
  four runs with a stable plateau.

## Provenance

- Bench: `~/.dotfiles/machines/testbench/`, Debian 12, RTX 2080 8 GB,
  i3-9100F, 15 GB RAM, driver 610.57.04, ollama 0.32.12.
- Layer counts from `journalctl --user -u ollama` (`offloaded N/M layers`);
  VRAM from `nvidia-smi`. **Not** from `/api/ps`, which misreports.
- gemma4:26b reference figures: `../rtx2080-8gb-real/FINDING.md`.
- Bench wall-clock reference: `../testbench-2080-e9-batch1/FINDING.md`.
