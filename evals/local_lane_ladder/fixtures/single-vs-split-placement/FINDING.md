# There is no general dual-card decode penalty — the 35% was the KV cache, not the split

**Run:** desktop, 2026-09-05. Two ollama daemons sharing one model store: the
system daemon on **:11434** (both cards) and a second daemon started as the
`ollama` user with `CUDA_VISIBLE_DEVICES=0` on **:11435** (GPU0 only). Four
models, pinned `num_ctx` 16384, contract-v1 probe, **n=3 interleaved with port
order reversed each rep**, all models unloaded from *both* daemons before every
measurement.

**Hypothesis under test:** the pre-swap baseline found three models split across
both cards despite fitting on one. Since splitting cost `gemma4:26b` **35%** of
its decode, the mid-band was suspected of paying the same unnecessary tax.

## Result: the hypothesis is wrong

| model | split (:11434) | single GPU (:11435) | delta | placement |
|---|---:|---:|---:|---|
| gemma4:26b *(control)* | 226.6 | 226.8 | **+0.1%** | 1 card → 1 card |
| gemma4:31b | 38.0 | 37.4 | **−1.6%** | 2 → 1 |
| qwen3.8:27b | 79.0 | 75.3 | **−4.7%** | 2 → 1 |
| qwen3.6:35b | 129.8 | 141.9 | **+9.3%** | 2 → 1 |

**Two of the three got *slower* on a single card.** There is no general penalty
to recover. The effect is model-dependent and small, spanning −4.7% to +9.3%.

The control validates the rig: `gemma4:26b` was already single-card on the dual
daemon and reads **+0.1%** across daemons, so the second daemon contributes no
measurable overhead of its own.

## Why the extrapolation failed

`gemma4:26b`'s 35% loss was never a *splitting* cost. Its base tag defaults to
**262,144 context**, which inflated the KV cache until the model no longer fit
one card. The split was a *symptom* of an oversized configuration, and the 35%
was the cost of that configuration — not of spanning two cards.

Here every model is pinned at `ctx16384` and split by ollama's ordinary
scheduler, with no cache inflation. Splitting under those conditions is roughly
free. **Same observable — "model spans two cards" — two unrelated causes.**

This is the same error shape as `ARCHITECTURE_PREDICTS_THE_WALL` and the
`num_gpu` envelope artifact: a mechanism inferred from one model's behaviour,
generalised, and falsified by a 2x2. Fourth instance in the program.

## What splitting does cost: about 1.4 GB of VRAM

| model | split total | single-GPU | overhead |
|---|---:|---:|---:|
| gemma4:31b | 23,451 MiB | 22,076 MiB | **1,375 MiB** |
| qwen3.8:27b | 20,402 MiB | 18,908 MiB | **1,494 MiB** |
| qwen3.6:35b | 23,682 MiB | 22,594 MiB | **1,088 MiB** |

Per-device buffers are duplicated, so a split model carries **1.1–1.5 GB** more
than the same model on one card. That is the real cost of spreading, and it is
memory rather than throughput — which matters for what else can be resident, not
for how fast anything runs.

## Operator consequence

**Do not build per-model host routing to avoid splitting.** The gain does not
exist for two of three models and is negative for `qwen3.8:27b`.

The one case that earns it is **`qwen3.6:35b` at +9.3%**, which is real and
reproducible (141.4–142.5 across three reps against 129.2–130.9 split). If a
second daemon is kept for any reason, that model is the one to route to it.

**The pre-swap baseline stands as measured.** Its numbers were taken under
ollama's default placement, which is within ~5% of optimal for every model
tested, so no part of it needs re-deriving.

## Limits

- Decode only, `num_predict` 128. A long-generation or long-prompt workload
  moves more activation traffic across the PCIe link and could differ — note
  this board runs card 2 at **x4**.
- Four models, one context size, one machine.
- Load time was not measured and is where the x4 link should hurt most.
- `+9.3%` for `qwen3.6:35b` is unexplained. It has the fewest layers of the
  three (42), so per-layer boundary crossings may matter, but that is a guess.

---

## Caveat added 2026-09-08 — the solo daemon was not *enforcing* single-card

This finding compared the system daemon against a second daemon started with
`CUDA_VISIBLE_DEVICES=0`. That hides the card from **CUDA but not from Vulkan**.
Re-examined 2026-09-08, such a daemon enumerates both:

```
library=Vulkan  name=Vulkan0  pci_id=0000:03:00.0    <- the other card
library=CUDA    name=CUDA0    pci_id=0000:01:00.0
```

**The results here are almost certainly still valid**: every solo row recorded a
`2 → 1` placement transition with the second card at ~0 MiB, so the models did
land on one GPU. But that was ollama *preferring* CUDA, not the rig *enforcing*
one card — and the preference is not reliable. On 2026-09-08 a configuration
under the same setup failed with `ggml_gallocr_reserve_n_impl: failed to
allocate Vulkan0 buffer`, i.e. it tried to use the card that was supposed to be
hidden.

**Any future single-card work must add `OLLAMA_LLM_LIBRARY=cuda_v13`** to bypass
backend autodetection. The control in this finding (`gemma4:26b` at +0.1% across
daemons) is unaffected either way, since that model was single-card on both.
