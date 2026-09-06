# The 45 GB convergence is real; the 1.9x throughput gap next to it was not

**Run:** desktop (dual RTX 3090), 2026-09-05. Contract-v1 probe
(`num_predict 128`, `temperature 0` at request level), ollama 0.32.12. Both
45 GB-class models measured **pinned and unpinned in the same session**, all
tags unloaded between loads. Throughput re-measured n=3 interleaved with order
alternated. Layer counts from `journalctl -u ollama`; VRAM from `nvidia-smi`,
net of idle baseline.

**Question:** `VRAM_IS_A_BUDGET_STUB.md` headlines that the 80B and 120B occupy
the same memory (45.75 vs 45.6 GB, 0.3% apart). The 45.75 GB figure existed only
in prose — **no fixture, no recorded `num_ctx`** — while its comparison partner
was pinned at 16384. After `gemma4:26b`'s 262,144 default was found to double its
footprint and split it across both cards, the convergence had to be re-checked:
was it a KV-cache artifact of comparing an unpinned model against a pinned one?

## Result: the convergence survives, and tightens

| config | GPU0 | GPU1 | net resident | layers | decode tok/s |
|---|---:|---:|---:|---|---:|
| qwen3-next unpinned | 22,921 | 23,058 | 45,425 MiB (44.36 GiB) | **49/49** | 54.3 |
| **qwen3-next `ctx16384`** | 22,861 | 23,000 | **45,384 MiB (44.32 GiB)** | **49/49** | **79.1** |
| gpt-oss:120b unpinned | 23,055 | 23,206 | 45,773 MiB (44.70 GiB) | **37/37** | 28.3 |
| **gpt-oss:120b `ctx16384`** | 22,791 | 23,081 | **45,302 MiB (44.24 GiB)** | **37/37** | **34.1** |

**Pinned against pinned, the two are 0.2% apart** — 45,384 vs 45,302 MiB, across
a 37-billion-parameter gap. Tighter than the 0.3% originally claimed, and now
measured under matched configurations. **The stub's headline claim stands.**

Context pinning barely moves these models: 0.1% for the 80B, 1.0% for the 120B.
That is the opposite of `gemma4:26b`, whose 262,144 default **doubled** its
footprint. The difference is proportion — 45 GB of weights swamps a 16K-vs-128K
KV cache, whereas 19 GB of weights does not. **The ctx trap scales with how
small the model is**, which is the reverse of where one would look for it.

All four configurations are **100% GPU-resident** (49/49 and 37/37), pinned or
not, confirming the offload correction on independent evidence.

## But the throughput claim beside it was measuring two different things

The stub's claim 3 — "at identical footprint, throughput differs 1.9x" — paired
**54.3 tok/s from the unpinned 80B** against **28.7 tok/s from the pinned 120B**.
Mismatched configs, in the direction that understates the gap.

Matched, n=3 interleaved, ranges non-overlapping:

| model | decode tok/s (n=3) | range |
|---|---:|---|
| qwen3-next `ctx16384` | **79.1** | 78.7 – 79.4 |
| gpt-oss:120b `ctx16384` | **34.1** | 33.9 – 34.3 |
| | **ratio 2.32x** | |

**2.32x, not 1.9x.** The stub's own gloss — "active-parameter count (3B vs 5.1B)
points the right direction but does not carry the whole ratio" — gets weaker, not
stronger: the active-parameter ratio is 1.7x and the measured gap is now 2.32x.

## An unexplained result worth its own question

**`qwen3-next` gains 46% of decode from context pinning (54.3 -> 79.1) at
essentially unchanged footprint** (0.1%). Nothing moved between cards, no layer
count changed, and residency was already complete. Pinning bought speed without
buying memory, which the residency story does not explain. `gpt-oss:120b` shows
the same effect much weaker (28.3 -> 34.1 across sessions, and see the caveat
below).

This is now the most interesting open question in the stub, and it is not a
footprint question at all.

## Two instrument problems this run exposed

1. **`journalctl --user -u ollama` returns nothing on the desktop.** Ollama runs
   as a **system** service here and a `--user` service on the testbench. The
   measurement script's `--user` query silently produced "n/a" for every layer
   count. The audit instruction written into `BOTTLENECKS.md` yesterday —
   "use `nvidia-smi` plus `journalctl … offloaded N/M layers`" — is
   machine-specific and wrong for the desktop as written. Corrected there.
2. **`gpt-oss:120b` decode drifted 28.7 -> 34.1 tok/s across sessions (19%)**,
   pinned identically both times. Within this run it is stable (33.9–34.3). The
   80B and `gemma4:26b` drift ~1% across sessions. Unexplained; the 2.32x ratio
   uses same-session interleaved values and is not exposed to it, but any
   cross-session comparison of this model is.

## Naming

The base tag is **`qwen3-next:latest`**, not `qwen3-next:80b` as the stub and
`BOTTLENECKS.md` both write it. `ollama show` reports no context length for it at
all, so its default is unknown — the unpinned row above is "whatever ollama
chose", not a known configuration.

## Limits

- Footprint is deterministic and was measured once per configuration; decode is
  n=3 interleaved for the pinned pair only, n=1 for the unpinned rows.
- The 46% pinning gain for the 80B rests on n=1 unpinned against n=3 pinned. It
  is large enough to survive that, but the mechanism is untested.
- Two models. Whether the ~45 GB convergence generalises still needs a third
  model in the class — unchanged from the stub's RQ1.
