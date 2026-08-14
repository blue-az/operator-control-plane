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

**Read tok/s, not the CPU/GPU percentage.** z13 is a *unified-memory* machine:
there is one LPDDR5X pool at ~256 GB/s, and the iGPU and CPU cores read the same
memory. So the split `ollama ps` prints is **not** the discrete-GPU story of data
falling off a fast bus onto a slow one — nothing moves to slower memory, because
there is no slower memory. It reports which compute unit executes which layers.

17.5 GiB is therefore a **compute-placement boundary**, not a bandwidth cliff:
past it, layers execute on CPU cores rather than the iGPU. That still costs
throughput, but by a different mechanism and with a much gentler slope than a
PCIe spill on a discrete card. Everything below is stated in tok/s for that
reason; the percentages are context, not the measurement.

## Measured

| Model | Size | **tok/s** | Layer placement | Load |
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
context, not different weights. CPU-placed share fell alongside the throughput rise,
which points at the serving stack (Vulkan/RADV, ollama) rather than at
measurement error.

Consequence: `DEDICATED_VS_UNIFIED_MEMORY.md` and
`GEMMA4-CTX8192-3090-VS-Z13-001` describe a slower machine than the one that
exists today. Their **ratios** (desktop ≈ 4.9x z13 on MoE) are now wrong; the
current gap is roughly 2x.

## Finding 2 — architecture beats size, decisively, on this machine

Same host, similar parameter counts, **6.6x apart**:

| | Params | CPU-placed | tok/s |
|---|---:|---:|---:|
| `gemma4:26b` **MoE** | 25.8B | 16% CPU | **46.8** |
| `gemma4:31b` **dense** | 31B | 31% CPU | **7.1** |

An MoE activates a fraction of its weights per token, so the share of layers
placed on CPU is touched only occasionally. A dense model touches every weight on
every token, so CPU-placed layers are paid on all of them — and dense compute at
256 GB/s is slow even before placement enters into it. The rule for the machine:
**on unified memory, prefer MoE, and treat a large dense model as unusable rather
than slow.**

Note this is a *compute* explanation, not a memory-bandwidth one. On a discrete
card the same table would be read as a spill cliff; here both models are reading
the same pool at the same speed, and the 6.6x gap is architecture plus where the
layers run.

`gemma4:26b` reaches 46.8 tok/s with 16% of its layers on CPU — which on a
discrete card would read as a badly degraded model, and here does not. That gap
between the percentage and the throughput is exactly why tok/s is the metric.
`gemma4:31b` at 7.1 does not come close to the floor.

## Finding 3 — z13 is an interactive machine, not merely a slow one

Four of six models measured clear the conversational floor, two of them by a wide
margin. Notably `gemma4:12b` — which the Rasch fit over the ladder placed at
**1707 Elo, statistically tied with the top of the desktop field** — runs at
25.7 tok/s with every layer on the iGPU.

The practical seat guidance for z13:

| Use | Model | Why |
|---|---|---|
| Interactive / agentic | `gemma4-26b-24k` | 46.8 tok/s, strongest model that stays usable |
| All layers on iGPU | `gpt-oss-16k` (51.5) or `gemma4:12b` (25.7) | no CPU-placed layers; most predictable |
| Throwaway / fast | `granite4` | 88.2 tok/s, but 3.4B scored 8/18 on the floor ladder |
| **Avoid** | `gemma4-31b-24k` | 7.1 tok/s dense; correctness does not pay for 6.6x the wait |

## Finding 4 — KV quantisation moves placement and nothing else (TESTED)

z13 was missing both tunings the desktop has. **Both were enabled and the sweep
re-run identically** (2026-08-13, ollama restarted 18:51):

| | desktop | z13 before | z13 after |
|---|---|---|---|
| `OLLAMA_FLASH_ATTENTION` | `1` | unset | `1` |
| `OLLAMA_KV_CACHE_TYPE` | `q8_0` | unset (fp16) | `q8_0` |

| Model | tok/s before → after | Δ | CPU-placed |
|---|---|---:|---|
| `granite4` | 88.2 → 85.4 | −3.2% | 0 → 0 |
| `gemma4:12b` | 25.7 → 25.7 | 0.0% | 0 → 0 |
| `qwen2.5-14b-24k` | 24.5 → 24.4 | −0.4% | 0 → 0 |
| `gpt-oss-16k` | 51.5 → 51.4 | −0.2% | 0 → 0 |
| `gemma4-26b-24k` | 46.8 → 46.2 | −1.3% | **16 → 13** |
| `gemma4-31b-24k` | 7.1 → 7.2 | +1.4% | **31 → 27** |

**The mechanism executed and bought nothing.** CPU-placed share fell on both
affected models, which proves the KV cache is preallocated at `num_ctx` and that
`q8_0` really halved its footprint — this is not a change that failed to apply.
Throughput still moved by less than the ±3.2% n=1 noise band on every model.

This is the clearest evidence in this document for the framing at the top: **the
placement percentage is not a throughput signal on unified memory.** Improving it
by 3–4 points returned nothing, because there is no bandwidth cliff to climb back
up. On a discrete card the same shift would have shown in tok/s.

**Caveat on scope.** This sweep generates 128 tokens from a short prompt. KV
*allocation* scales with `num_ctx` — hence the placement change — but the
attention *work over* that cache stays trivial at ~150 real tokens, and flash
attention in particular has almost nothing to act on. A long-context workload
(the BT funnel at 22–37k tokens, already on this machine) could differ, and no
pre-tuning long-context baseline exists to compare against.

**Disposition:** left **on**. It costs no measurable throughput here, is lossy in
principle, and matches the desktop configuration. If it is kept permanently the
open question is quality rather than speed — `q8_0` is a lossy cache, and the BT
floor probes are the calibrated instrument on this machine for checking that.

## Limits

n=1 per model, one prompt, one context length; these are throughput figures, not
capability. Load times include cold page-in from disk and vary with
cache state. No fixture pass rates were measured here — whether the ladder's
*rankings* transfer across machines is a separate question, and the deterministic
postconditions should transfer while any timeout-mediated outcome will not
(`MACHINE_PROVENANCE_SPEC.md`). z13's ollama also predates the desktop's tuning,
so machine and configuration are confounded in every cross-machine ratio above.
