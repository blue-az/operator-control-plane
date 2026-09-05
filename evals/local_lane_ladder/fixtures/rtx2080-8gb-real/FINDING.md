# The VRAM-cap ablation predicts a real card to within 1.7% — and a stale baseline nearly buried that

**Run:** 2026-09-05. `gemma4:26b`, contract-v1 probe (`num_predict 128`,
`temperature 0`, `num_ctx 16384`), ollama 0.32.12 on both machines,
**both sides re-measured on the same day.**

> **Third revision of this file.** Two earlier versions were wrong in opposite
> directions. The revision history is kept below because it is the most useful
> part.

## Result: the simulation is accurate

| condition | VRAM | decode tok/s |
|---|---:|---:|
| **Desktop 3090, `num_gpu=12`** — the simulated envelope | 8,099 MiB | **31.55** |
| **Bench RTX 2080, real 8 GB card** | 7,416 MiB | **31.02** |
| | | **1.7% apart** |

Run 2 figures agree as closely: 30.41 vs 30.30. Context matched at 16384 on
both; the bench also gave 31.10 at 4096, so context is not a factor.

**`num_gpu` capping does simulate a smaller card, and does it well.** An 8 GB
envelope produced by layer capping on a 24 GB card predicts a genuine 8 GB card
to within measurement noise — despite Turing vs Ampere, 448 vs 936 GB/s, an
i3-9100F vs an i9-9900KF, and 15 vs 31 GB of system RAM.

## What actually went wrong: the baseline had expired

`gemma26-8gb-cap-e9` records **23.5 tok/s** at this exact setting, measured
**2026-08-30**. Re-running that identical configuration today gives **31.55**.
Same machine, same `num_gpu`, same model tag, same ollama version.

The difference is **MTP speculative decoding**. The desktop's llama-server now
runs `--spec-type draft-mtp --spec-draft-n-max 3` with a 5-layer draft model;
it did not on 30 August. That is a **+34%** decode improvement, and it arrived
on its own — a model or runtime update between the two dates.

**So the number in a committed finding stopped being reproducible six days after
it was written, on the machine that produced it, with nothing changed by hand.**

## The revision history, because it is the finding

| version | claimed | why it was wrong |
|---|---|---|
| v1 | Real card = 21.97, prediction held "within 7%" | 21.97 was **Vulkan** — the bench's driver 535 was below ollama's 550 CUDA threshold and silently fell back. Two errors cancelled: Vulkan's penalty dragged the real card down onto a stale prediction. |
| v2 | Real card = 31.0, prediction wrong by 32%, `num_gpu` "caps layers not bytes" | The mechanism was invented to explain a gap that was really baseline drift. Measured directly, `num_gpu=12` uses **8,099 MiB** — an 8 GB envelope, exactly as labelled. |
| **v3 (this)** | Simulation and real card agree to 1.7% when both are measured the same day | — |

Each version was internally coherent and each had a plausible mechanism. What
separated them was measuring instead of reasoning.

## Two instrument failures worth carrying forward

**1. Silent backend fallback.** Ollama logged `NVIDIA driver too old ...
required_driver="550 or newer"` at INFO level and continued on Vulkan. Nothing
in the benchmark output indicated a different compute backend. **Always confirm
`library=CUDA` in the daemon log before trusting a throughput number** — the
figure is otherwise not comparable to anything.

**2. `/api/ps` misreports VRAM.** It returned 0.8–1.2 GB for an 18 GB model on
both machines. Every VRAM figure here comes from `nvidia-smi`, which was the
only instrument that tracked reality. Do not use `size_vram` from `/api/ps`.

## Correction: only the CAPPED baseline drifted, not all of them

The first version of this section claimed throughput baselines expire generally.
**That was too broad.** A full-roster re-measurement on 2026-09-05, same day,
same prompt, against the committed figures:

| model | committed | 2026-09-05 | delta | MTP active now |
|---|---:|---:|---:|---|
| gemma4:26b | 137.3 | 133.33 | **-3%** | yes |
| gemma4:31b | 34.3 | 36.12 | **+5%** | no |
| qwen3.8:27b | 77.5 | 74.16 | **-4%** | yes |
| qwen3.6:35b | 133.4 | 120.71 | **-10%** | yes |

**Full-VRAM decode rates reproduce within +/-10%, three of four within +/-5%.**
The committed figures are sound. What did not reproduce is the *capped*
measurement: gemma4:26b at `num_gpu=12` went 23.5 -> 31.55, **+34%**, while the
same model at full VRAM moved -3%.

**So the drift is specific to the offloaded configuration, and the cause is not
established.** MTP speculative decoding is active now and is a plausible
candidate — its benefit should scale with forward-pass cost, which is high when
layers are CPU-resident and low when they are not, which would fit the pattern
exactly. **But this was never verified against the 30 August runtime.** Asserting
MTP as the cause was an assumption presented as a finding, and it is withdrawn
as such. What is established is *what* moved, not *why*.

**Practical rule, narrowed:** full-VRAM throughput figures in this repo can be
cited. **Any tok/s measured under a `num_gpu` cap or with CPU offload should be
re-measured before use** — that is the regime that moved, and it is also the
regime most of the constraint findings live in.

Two side observations from the same run:

- **`gemma4:31b` has no MTP at all.** Speculative decoding here is model-specific,
  not a runtime-wide change.
- **`qwen3.6:35b` completed without the cross-GPU CUDA fault**, because a vLLM
  process occupying GPU0 forced ollama onto a single card. That confirms the
  single-GPU workaround functions in the ordinary daemon, not only in an
  isolated one.

## Consequence for the widening stub

`EVERY_WIDENING_SHRANK_THE_CLAIM_STUB.md` requires, before promotion:

> **A case where widening did *not* shrink a claim**, to establish that the
> program is capable of producing one.

**This is that case, measured properly.** Widening from a simulated envelope to
real hardware — the hardest widening attempted — left the claim standing at
1.7%. The stub's thesis needs amending: widenings do not *always* shrink claims.
What they reliably expose is *stale or confounded* claims.

That is a more defensible thesis than the original and it survives this
instance, where the absolute version does not.

## Caveats

- Warm figures from 3 runs per condition, n=1 configuration. Continuous metric.
- Driver versions differ (bench 610.57.04, desktop 580.178.04) — the intended
  pin to 580 did not take during install. Both are above the CUDA threshold.
- MTP is active on both sides now, which is what makes the comparison valid.
  Any future comparison must confirm this again rather than assume it.

## Provenance

- Superseded baseline: `../gemma26-8gb-cap-e9/FINDING.md` (23.5 tok/s,
  2026-08-30, not reproducible 2026-09-05).
- Probe: contract-v1 prompt,
  `project-phoenix/docs/domain_runs/GEMMA4-CTX8192-3090-VS-Z13-001/prompt.txt`.
- Bench: `~/.dotfiles/machines/testbench/`, Debian 12, kernel 6.1.0-52,
  driver 610.57.04, ollama 0.32.12 user-local.
