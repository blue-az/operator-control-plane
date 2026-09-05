# `num_gpu` capping does not simulate a smaller card — it caps layers, which is a different constraint

**Run:** testbench (System 2), 2026-09-05. `gemma4:26b` on a real **RTX 2080,
8 GB**, contract-v1 probe (`num_predict 128`, `temperature 0`), ollama 0.32.12
deliberately version-matched to the desktop.

> ## ⚠️ SUPERSEDES an earlier version of this file
>
> An earlier revision reported the real 8 GB card at **21.97 tok/s** against a
> predicted 23.5 — "within 7%" — and cited it as the counter-example
> `EVERY_WIDENING_SHRANK_THE_CLAIM_STUB.md` was asking for. **That was wrong.**
> The 21.97 figure was measured on **Vulkan**, because the bench's driver (535)
> was below ollama's 550 requirement for CUDA and silently fell back. The match
> was a coincidence: Vulkan's penalty happened to drag the real card down to
> meet a prediction that was itself too low.
>
> With CUDA working, the real card does **31.0 tok/s**. The prediction was off
> by **+32%**, and the counter-example is withdrawn.

## Result

| condition | decode tok/s |
|---|---:|
| **Predicted** — 3090 at `num_gpu=12`, "8 GB envelope" | **23.5** |
| Measured — real 2080, **Vulkan** (driver too old for CUDA) | 21.97 |
| **Measured — real 2080, CUDA, `num_ctx` 4096** | **31.10** |
| **Measured — real 2080, CUDA, `num_ctx` 16384** (matched to desktop) | **31.02** |

Context length was tested and is **not** the explanation — 31.10 at 4k versus
31.02 at 16k. Warm run 3 in both cases; cold runs were 8.9 and 26.8.

## The mechanism: layers are not bytes, and for MoE they are wildly not bytes

`gemma4:26b` is **30 blocks, 128 experts, 8 active per token**, 18 GB on disk.

| | layers on GPU | VRAM used |
|---|---|---|
| Real RTX 2080 (8 GB) | **31/31** — every block plus the output layer | 7.4 GB |
| Desktop `num_gpu=12` ("8 GB envelope") | **12 of 30** | — |

**The real 8 GB card fits the entire model's layer stack in 7.4 GB.** It can,
because for an MoE model the per-layer non-expert weights are small — the 128
experts dominate the 18 GB and stream from system RAM regardless of what the GPU
holds. The simulation, meanwhile, forced two-fifths of the layers off the GPU.

So `num_gpu=12` was **far more constrained than a real 8 GB card**, and the
resulting 23.5 tok/s was not an 8 GB measurement. It was a 12-layer measurement.

## What this invalidates

**The "envelope" framing of the VRAM-cap findings is wrong**, and those files say
"8GB envelope" and "12GB envelope" throughout:

- `gemma26-8gb-cap-e9` (`num_gpu=12`)
- `gemma26-12gb-cap-e9` (`num_gpu=20`)
- `gemma4-26b-16gb-cap` — the calibration those two rest on

Their **accuracy** conclusions are untouched: pass rates genuinely did not move
under layer-count constraint (30/30 and 29/30). But they did not measure what a
smaller card does, and the tok/s figures should not be read as predictions for
real hardware of that VRAM.

**And it may reach further than the framing.** The dense-vs-MoE constraint
asymmetry — MoE absorbing severe caps while `gemma4:31b` stalled — was measured
with the same instrument. For a **dense** model, layer count and memory footprint
are close to proportional, so `num_gpu` does approximate a VRAM cut. For an
**MoE** model it does not, because experts stream from RAM either way. Some of
"MoE tolerates constraint better" may simply be that the cap constrains MoE
models less, in a way the mechanism made invisible. **Not established here** —
but the 2×2 that killed the architecture claim, and this, are pointing at the
same instrument.

## Consequence for the widening stub

`EVERY_WIDENING_SHRANK_THE_CLAIM_STUB.md` still has **no counter-example.** This
looked like one for about an hour, and removing a confound turned it into
instance six:

| axis widened | before | after |
|---|---|---|
| simulated envelope → real hardware | "8 GB gives 23.5 tok/s" | real 8 GB gives **31.0**, and the ablation was measuring layer count |

Six widenings, six shrinks or breaks. The stub's requirement — "a case where
widening did *not* shrink a claim" — remains unmet, and its thesis is stronger
than when it was written.

## Caveats

- n=1 warm probe per condition, three runs each, warm figure taken per the
  contract. Continuous metric, so more power at low n than pass/fail, but not a
  distribution.
- Driver versions differ: bench 610.57.04, desktop 580.178.04. The intended pin
  to 580.178.04-1 did not take during a messy install and the newest branch went
  on instead. Both are far above ollama's 550 CUDA threshold, so this does not
  explain a 32% gap, but it is not a matched comparison either.
- Hardware still differs by design: Turing 448 GB/s vs Ampere 936 GB/s, i3-9100F
  4C/4T vs i9-9900KF 8C/16T, 15 GB vs 31 GB RAM. The real card wins by 32%
  *despite* all of these being worse, which is how much the layer cap was
  costing.
- MTP speculative decoding is active on the bench
  (`--spec-type draft-mtp`, draft model 5/5 layers on GPU). Desktop status
  unverified. Same ollama version makes it likely, not certain.

## What would settle the remaining question

Run the desktop's 3090 at a `num_gpu` chosen so that **VRAM used matches 7.4 GB**
rather than at a guessed layer count — then the two are comparable and the
"envelope" language can be either repaired or retired. That is a single probe
and it decides whether the cap findings need rewriting or only relabelling.

## Provenance

- Superseded prediction: `../gemma26-8gb-cap-e9/FINDING.md`.
- Calibration those rest on: `../gemma4-26b-16gb-cap/FINDING.md`.
- Probe: contract-v1 prompt,
  `project-phoenix/docs/domain_runs/GEMMA4-CTX8192-3090-VS-Z13-001/prompt.txt`.
- Bench: `~/.dotfiles/machines/testbench/`. Debian 12, kernel 6.1.0-52, driver
  610.57.04 from NVIDIA's debian12 repo, ollama 0.32.12 user-local.
