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
**on unified memory, prefer MoE, and treat a large dense model as unusable for
INTERACTIVE work rather than merely slow.**

That qualifier is load-bearing and was missing until 2026-08-15. The ~20 tok/s
floor is a *perceived* lower limit for a human watching output arrive, taken from
informal `opr` bench sessions -- it is a human-attention threshold, not a
technical gate. Delegated and batch work has no such floor: a model at 5-9 tok/s
finishing an offloaded task in the background is doing its job. The router policy
already encodes exactly this split (`local_ok + conversational` requires clearing
the floor; `local_ok + delegated` accepts any local model), so "unusable" without
"for interactive" contradicts the policy this repo already runs.

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
| **Not interactive** | `gemma4-31b-24k` | 7.1 tok/s dense — below the ~20 t/s perceived floor. Still valid for delegated/offloaded work, where no floor applies |

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


---

## Addendum 2026-08-15 — qwen3.6/3.8 on z13, and the power-state confound

**Every figure above was measured on an unrecorded power state.** That omission
nearly cost a whole run: a sweep taken on battery in `power-saver` measured
`gemma4-26b-24k` at **13.7 tok/s** against the 46.2 recorded here — 3.4x low,
and entirely plausible-looking. It was caught only because the sweep included
`gemma4-26b-24k` as an **anchor** against a known value. Without that anchor the
qwen numbers would have been published as clean measurements.

**Always anchor a re-run on a model with a recorded value, and always record
power state.** On a laptop a benchmark without its power state is not a
measurement.

### Power state costs 3.8x

| | AC + `performance` | battery + `power-saver` |
|---|---:|---:|
| `gemma4-26b-24k` | **51.6** | 13.7 |

The AC figure also exceeds this document's own 46.2 by 12%, consistent with
`performance` versus whatever profile produced the original — which is exactly
the ambiguity the missing power-state note creates.

### Measured (AC, `performance` governor, `num_ctx` as marked)

| Model | z13 | desktop | desktop / z13 |
|---|---:|---:|---:|
| `gemma4-26b-24k` (MoE, 16384) | 51.6 | 133.0 | 2.58x |
| `qwen3.6:27b` (dense, 16384) | 12.0 | 37.8 | 3.15x |
| `qwen3.6:27b` (dense, 8192) | 13.0 | — | — |
| `qwen3.8:27b` (dense, 4096) | 15.5 | — | — |
| `qwen3.8:27b` (dense, 8192) | **16.3** | 43.7 | — |
| `qwen3.8:27b` (dense, 12288) | OOM | — | — |
| `qwen3.8:27b` (dense, 16384) | OOM | 43.7 | — |

### Finding A — `qwen3.8:27b` fits z13 up to 8192 context, not beyond

**Read the context column before quoting this.** "Does not fit z13" is wrong
without it — the model runs fine in normal use, where ollama's default context
is far below the 16384 this battery pins. Measured boundary, AC/`performance`:

| `num_ctx` | result |
|---:|---|
| 4096 | **15.5 tok/s** (this is what normal interactive use loads) |
| 8192 | **16.3 tok/s** |
| 12288 | OOM |
| 16384 | OOM |

The limit bites at the ladder's pinned 16384, not at everyday context lengths.
Anyone running this model interactively on z13 will never see it.

```
llama-server startup failed after projector CPU offload retry:
llama-server reported out-of-memory during startup:
radv/amdgpu: Not enough memory for command submission.
```

It carries a CLIP vision projector (~460M params) on top of 17 GB of weights;
with a 16384 KV cache that exceeds the 17.5 GiB GPU-addressable pool. ollama
attempts a projector CPU offload and still fails.

The 16384 failure reproduced four times across battery and AC, and 12288 fails
too, so the ceiling sits between 8192 and 12288. One 16384 run did succeed six
minutes after a reboot and never again, which fits a Vulkan contiguous
allocation failing as memory fragments — so 16384 is not merely tight, it is
unreliable even when it occasionally succeeds.

**Two symmetric errors to avoid, both made during this run:** treating "it ran
once at 16384" as "it fits", and treating "it OOMs at 16384" as "it does not fit
z13". The first overstates capacity, the second understates it, and the fix for
both is to state the context.

### Finding B — 3.8 is faster than 3.6 here too, at matched context

At `num_ctx 8192`, AC: **16.3 vs 13.0 tok/s, +25%**. Desktop measured +15.6% at
16384. The direction is consistent across both machines.

Neither clears the ~20 tok/s interactive floor on z13. Per the corrected framing
above, that rules them out for **interactive** use and not for delegated work,
which has no floor.

### Finding C — the dense penalty is not a single number

A prediction made before this run put `qwen3.6` at ~7.9 tok/s by applying
`gemma4:31b`'s 4.8x dense penalty. Measured: **12.0**, a 3.15x penalty. The
prediction was 34% low.

`gemma4:31b`'s 4.8x is not "the dense penalty" — it is that model, which also
carries the field's largest CPU-placed share (27%). `qwen3.6` sits at 9%/91%.
So the useful bands on this machine are roughly:

| | penalty vs desktop |
|---|---|
| MoE | ~2.6x |
| dense, lightly CPU-placed | ~3.2x |
| dense, heavily CPU-placed | ~4.8x |

Extrapolating one model's ratio to another architecture is how the 7.9 estimate
went wrong.


### Addendum B — `gemma4:26b` characterised on z13, and the tag split resolved

The seat model was previously measured on z13 only through the `gemma4-26b-24k`
tag, n=1. Repeated on the standard tag, AC / `performance` / `num_ctx 16384`,
cold load each:

| run | tok/s |
|---|---:|
| 1 | 51.1 |
| 2 | 51.3 |
| 3 | 51.5 |
| **mean** | **51.3** (sd **0.20**) |
| `gemma4-26b-24k`, same conditions | 51.6 |

**sd 0.20 — 0.4% variation.** This is now the best-characterised number on
either machine, and it confirms the two tags are the same model: 51.3 vs 51.6
is inside the noise.

Desktop / z13 = 133.0 / 51.3 = **2.59x**, against a 350 W card run at a 320 W
cap. Placement is a stable 12%/88% CPU/GPU across all three runs.

**The tag split is resolved.** z13 carried `gemma4-26b-24k:latest` where desktop
carried `gemma4:26b`, so the shared opencode model list showed both names and
half the list was dead on whichever machine you were using. They were never
different models — identical blob `sha256-7121486771cb..`, identical ollama id
`5571076f3d70`, identical `temperature 1`. The sole difference was a baked
`PARAMETER num_ctx 24576`.

`ollama pull gemma4:26b` on z13 completed in under a second by reusing the
existing blob, and the duplicate entry was removed from
`~/.config/opencode/opencode.jsonc` (not dotfiles-tracked; backup in
`handoffs/`). Set `num_ctx` per request rather than relying on a baked tag.

Two z13-only tags remain unmatched — `gemma4-31b-24k` and `qwen2.5-14b-24k` —
because no standard-tag equivalent is installed on z13. `gemma4:31b` is not
worth unifying: it is no longer a seat and runs at 7.2 tok/s here.
