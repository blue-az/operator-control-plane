# z13 benchmark — unified-memory laptop as a local-model host

**Measured:** 2026-08-13, `ctx 16384`, `temperature 0.8`, 128-token generations,
each model loaded cold and unloaded after. Decode rate excludes load time.
**Not UID-verified. No claim registered.**

Run while the desktop was busy with E11, on a different machine, so neither
interfered with the other.

## The machine

| | |
|---|---|
| APU | AMD Ryzen AI MAX 390 (Strix Halo), Radeon 8050S, 24 threads |
| Memory | 27 GB unified |
| **GPU-addressable** | **17.5 GiB** = 4.0 GiB VRAM carve-out + 13.5 GiB GTT |
| Backend | Vulkan (RADV GFX1151) — not ROCm |

**17.5 GiB is the number that governs everything here.** It is not the 27 GB on
the box and not the 4 GiB the carve-out advertises: the driver reaches the rest
through GTT. Models whose weights plus KV cache stay under it run fully resident;
17 GB and 19 GB models do not.

## Measured

| Model | Size | tok/s | Residency | Load |
|---|---:|---:|---|---:|
| `granite4` | 2.1 GB | **88.2** | 100% GPU | 2s |
| `gpt-oss-16k` | 13 GB | **51.5** | 100% GPU | 12s |
| `gemma4-26b-24k` (MoE) | 17 GB | **46.8** | 16%/84% CPU/GPU | 20s |
| `gemma4:12b` | 7.6 GB | 25.7 | 100% GPU | 6s |
| `qwen2.5-14b-24k` | 9.0 GB | 24.5 | 100% GPU | 11s |
| `gemma4-31b-24k` (dense) | 19 GB | **7.1** | 31%/69% CPU/GPU | 22s |

## Finding 1 — the numbers on record for z13 are stale by up to 2.5x

| Model | Recorded (2026-07) | Now | Change |
|---|---:|---:|---|
| `gemma4:26b` | 18.8 tok/s, 38% CPU | **46.8**, 16% CPU | **2.5x** |
| `gemma4:31b` | 4.86 tok/s, 45% CPU | **7.1**, 31% CPU | 1.5x |

Verified like-for-like before believing it: `gemma4-26b-24k` on z13 and
`gemma4:26b` on desktop report the same architecture, the same 25.8B parameters
and the same Q4_K_M quantisation — the `-24k` suffix is a Modelfile with a baked
context, not different weights. Spill percentages improved alongside throughput,
which points at the serving stack (Vulkan/RADV, ollama) rather than at
measurement error.

Consequence: `DEDICATED_VS_UNIFIED_MEMORY.md` and
`GEMMA4-CTX8192-3090-VS-Z13-001` describe a slower machine than the one that
exists today. Their **ratios** (desktop ≈ 4.9x z13 on MoE) are now wrong; the
current gap is roughly 2x.

## Finding 2 — architecture beats size, decisively, on this machine

Same host, similar parameter counts, **6.6x apart**:

| | Params | Spill | tok/s |
|---|---:|---:|---:|
| `gemma4:26b` **MoE** | 25.8B | 16% CPU | **46.8** |
| `gemma4:31b` **dense** | 31B | 31% CPU | **7.1** |

An MoE model activates a fraction of its weights per token, so spilling part of
it to system memory costs proportionally little. A dense model touches every
weight every token, so the spilled fraction is paid on every single one. This is
the single most useful rule for the machine: **on unified memory, prefer MoE, and
treat a dense model that does not fit as unusable rather than slow.**

`gemma4:26b` at 46.8 tok/s clears the ~20 tok/s conversational floor **while
spilling**. `gemma4:31b` at 7.1 does not come close.

## Finding 3 — z13 is an interactive machine, not merely a slow one

Four of six models measured clear the conversational floor, two of them by a wide
margin. Notably `gemma4:12b` — which the Rasch fit over the ladder placed at
**1707 Elo, statistically tied with the top of the desktop field** — runs at
25.7 tok/s fully resident on a laptop.

The practical seat guidance for z13:

| Use | Model | Why |
|---|---|---|
| Interactive / agentic | `gemma4-26b-24k` | 46.8 tok/s, strongest model that stays usable |
| Fully-resident, no spill | `gpt-oss-16k` (51.5) or `gemma4:12b` (25.7) | predictable, no CPU fallback |
| Throwaway / fast | `granite4` | 88.2 tok/s, but 3.4B scored 8/18 on the floor ladder |
| **Avoid** | `gemma4-31b-24k` | 7.1 tok/s dense; correctness does not pay for 6.6x the wait |

## Finding 4 — an unclaimed config gap

z13 is missing both tunings the desktop has:

| | desktop | z13 |
|---|---|---|
| `OLLAMA_FLASH_ATTENTION` | `1` | unset |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | unset (fp16) |

On a machine whose binding constraint is a 17.5 GiB ceiling, an fp16 KV cache is
twice the footprint it needs to be — and footprint is exactly what pushes the
17 GB and 19 GB models over. Enabling `q8_0` plausibly moves `gemma4-26b-24k`
from 16% spill toward fully resident.

**Not changed.** It is a systemd service edit on the operator's laptop, and the
right form is a measured before/after rather than a silent flip. The experiment
is cheap: set both, restart ollama, re-run this same sweep, compare.

## Limits

n=1 per model, one prompt, one context length; these are throughput and residency
figures, not capability. Load times include cold page-in from disk and vary with
cache state. No fixture pass rates were measured here — whether the ladder's
*rankings* transfer across machines is a separate question, and the deterministic
postconditions should transfer while any timeout-mediated outcome will not
(`MACHINE_PROVENANCE_SPEC.md`). z13's ollama also predates the desktop's tuning,
so machine and configuration are confounded in every cross-machine ratio above.
