# gemma4:26b's default 256K context splits it across both cards and costs 35% of decode

**Run:** desktop (dual RTX 3090), 2026-09-05. Contract-v1 probe
(`num_predict 128`, `temperature 0` set at request level), ollama 0.32.12.
n=6 per configuration, **interleaved A/B/A/B with order alternated per rep** and
both tags unloaded before every measurement, so session drift and load-order
effects cancel.

**Question:** `gemma4:26b` measured 133.3 tok/s in the morning re-baseline and
214.1 tok/s in the afternoon roster run, same machine, same day. Which is real?

## Result: both are real; they are different configurations. The pinned one is correct.

| configuration | decode tok/s (n=6) | range | VRAM | cards |
|---|---:|---|---|---|
| `gemma4:26b` (base tag) | **139.9** | 135.8 – 142.3 | 18,010 + 21,325 MiB = **39.3 GB** | **both** |
| `gemma4-26b-e9pin-ctx16384-t0p8` | **214.4** | 213.2 – 215.4 | 19,676 MiB | **one** (GPU1 idle at 479 MiB) |

**Ranges do not overlap.** Twelve measurements, tight distributions, 1.53x apart.
This is not noise and it is not drift.

## Mechanism: the default context is 262,144 tokens

```
$ ollama show gemma4:26b
    architecture        gemma4
    parameters          25.2B
    context length      262144
```

Unpinned, ollama sizes the KV cache for **256K context**. That takes the model
from 19.7 GB to **39.3 GB — it no longer fits one 24 GB card, so it splits.**
Pinning `num_ctx` to 16384 shrinks the cache, the model fits GPU0 alone, and
GPU1 sits idle at baseline.

**Cross-GPU split costs 35% of decode throughput** for a model that did not need
to be split. Decode is sequential across layers, so spanning two cards adds
interconnect latency per token and buys nothing — there is no parallelism to
gain when each layer waits on the one before it.

## This inverts the second-card story for models that already fit

The dual-card case has two distinct halves and they point opposite ways:

- **A model that cannot fit one card** (`gpt-oss:120b`, `qwen3-next:80b`, both
  45.6 GB): the second card is what makes it resident at all. Categorical gain.
- **A model that can fit one card but is allowed to spill** (`gemma4:26b` at
  default context): the second card makes it **35% slower** than pinning it to
  one.

So "more VRAM is free" is wrong in the second case. Unpinned defaults will
silently consume the second card and pay for the privilege. **Pin `num_ctx` to
what the workload needs.**

## Correction issued

The 133.3 tok/s figure for `gemma4:26b` in `VRAM_IS_A_BUDGET_STUB.md` was
measured on the base tag and is a **two-card split-model number**, while the
same table's footprint entry for that row reads "19.2 GB, 1 card" — a
single-card figure. The row pairs a single-card footprint with a two-card
throughput. Corrected to 214.4 tok/s single-card.

The afternoon roster run (`fixtures/roster-walltime-2026-09-05`) used pinned tags
throughout, so **its decode column and its token-economy conclusion are
unaffected** — the 2.9x decode gap it reports between `gemma4:26b` and
`qwen3.8:27b` was already measured on correctly-pinned models.

## Limits

- One model. The other roster members have default context lengths that were not
  checked; any of them may have the same trap. `gemma4:31b` is the obvious next
  candidate — a prior finding already notes it needs `num_ctx` 8192 for full GPU
  residency, which is likely the same mechanism.
- The 35% figure is for this model on this card pair at this context size. It is
  the cost of splitting *this* model, not a general cross-GPU constant.
- Only decode was measured. Prompt processing may split differently, and a very
  long prompt is exactly the case where 256K context would be needed.

---

## Addendum 2026-09-05 — the 214.4 figure was thermally depressed; the correct value is ~226

Re-measured twice since, same tag, same machine: **226.3** (n=3,
`preswap-baseline-2026-09-05`) and **226.0** (n=6, min 224.4 max 229.0). Both
agree. The **214.4** reported above (213.2–215.4, n=6) is ~5% low.

**Cause: the interleaving partner.** This finding's A/B design alternated the
pinned tag against the **base tag, which loads 39.3 GB across both cards** — a
much heavier thermal and power load than the 19.3 GB single-card pinned arm. GPU
telemetry over a clean 6-rep run shows temperature climbing 46 °C → 61 °C with
throughput falling 229.0 → 224.8 in step, so the pinned arm was being measured
against a progressively hotter card than it would see alone.

**Interleaving cancels time-ordered drift, not load-asymmetric drift.** When the
two arms of an A/B impose materially different power draw, alternating them does
not remove the bias — it *couples* each arm's measurement to the other's thermal
footprint. Every A/B in this program with asymmetric arms is exposed to this,
including the `num_gpu` cap ablations.

**What this does and does not change:**

- **The finding stands.** 139.9 vs 214.4 is a 1.53x gap; a ~5% thermal effect
  cannot produce it, and the residency evidence (39.3 GB across two cards vs
  19.7 GB on one) is independent of throughput entirely.
- **The absolute number was wrong.** Anywhere `gemma4:26b` single-card decode is
  quoted, it is **~226 tok/s**, not 214.4.
- **Noise floor established: 2.0% within a session** for this model, and ~5%
  across sessions with differing thermal history. Post-swap differences below
  ~5% are not attributable to hardware.
