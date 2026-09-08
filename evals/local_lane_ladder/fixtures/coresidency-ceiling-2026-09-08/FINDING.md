# Two models co-reside on the pair up to ctx 32768 — switching costs 0.6 s instead of 124 s

**Run:** desktop (dual RTX 3090, 49,152 MiB pool), 2026-09-08. `qwen3.8:27b` +
`qwen3.6:35b`, both pinned per context, `temperature 0.8`, loaded sequentially on
the system daemon and left resident (`keep_alive 15m`). Switch cost is a second
request to the first model after the second has loaded.

**Question:** the operator alternates between two models interactively and was
paying a full reload on every switch. Can both stay resident, and to what
context?

## Result

| `num_ctx` | 27b MiB | 35b MiB | total | both resident | switch | 27b decode | 35b decode |
|---:|---:|---:|---:|:---:|---:|---:|---:|
| 16,384 | 20,382 | 23,268 | 43,650 | **yes** | **0.6 s** | 69.9 | 88.2 |
| 24,576 | 21,112 | 22,588 | 43,700 | **yes** | **0.6 s** | 70.8 | 78.9 |
| 32,768 | 22,041 | 21,652 | 43,693 | **yes** | **0.6 s** | 68.9 | 72.9 |
| 49,152 | 25,478 | 1,358 | 26,836 | **no** | 14.0 s | 54.5 | — |

**The ceiling is between 32,768 and 49,152.** At 49,152 the first model claims
25,478 MiB and the second never loads.

Against the operator's unpinned baseline (`num_ctx` 262144, ~39 GB for a single
model), the switch cost is **124 s**. Pinned to 32,768 with both resident it is
**0.6 s — a 200x improvement.**

## Ollama fits to the pool, not to the request

Total resident is **flat at ~43,650 MiB** across 16k, 24k and 32k. Only the split
between the two models moves — 27b climbs 20,382 → 22,041 while 35b falls
23,268 → 21,652. The scheduler is sizing both to the available pool rather than
allocating each independently.

**This behaviour has never been in view before**, because every prior measurement
in this program was single-model. It means `num_ctx` does not mean the same thing
on a shared box as it does alone, and it is why headroom does not shrink as
context grows — the models compress instead.

## What co-residency actually costs

Not memory. **Decode**, and unevenly:

| model | 16k → 32k |
|---|---|
| qwen3.8:27b (dense) | 69.9 → 68.9 — **flat** |
| qwen3.6:35b (MoE) | 88.2 → **72.9** — **−17%** |

The MoE model pays for co-residency; the dense one does not. That is the
**reverse** of the single-card result (`hw-standard-preswap`), where the dense
model collapsed 91% under memory pressure and the MoE degraded gracefully.
Architecture predicts the direction of degradation, but the sign flips with the
kind of pressure — capacity pressure punishes dense, sharing pressure punishes
MoE.

## Operator consequence

| configuration | switch | context each | note |
|---|---:|---:|---|
| **both pinned 32,768** | **0.6 s** | 32k | recommended for alternating work |
| both pinned 16,384 | 0.6 s | 16k | no benefit over 32k |
| one model, ~98,304 | 124 s | ~98k | for deep single-model sessions |
| unpinned (262,144) | 124 s | 82k used | **worst of both** — pays for headroom never reached |

The operator's real sessions run to **82k tokens**, which no co-resident
configuration reaches. **The choice is genuine and hardware-bound:** 32k each
with instant switching, or ~98k on one model with 124 s switches. The current
unpinned default achieves neither.

## Limits

- Decode here uses a trivial prompt, so these are empty-context rates and are
  **not comparable** to `hw-standard-preswap`, which uses a 12,811-token prompt.
  The movement across contexts is the signal; the absolute values are not.
- The ceiling was not bisected between 32,768 and 49,152.
- Two models. A third would change the fit entirely.
- n=1 per configuration. The switch-cost figures (0.6 s vs 14 s) are far apart
  enough that repetition was not required to separate them; the decode figures
  are not.
- `ollama ps` reported 35b at "3%/97% CPU/GPU" in an earlier pass at this pool
  utilisation. That instrument is known-bad here, but it is consistent with
  running at ~90% of the pool.
