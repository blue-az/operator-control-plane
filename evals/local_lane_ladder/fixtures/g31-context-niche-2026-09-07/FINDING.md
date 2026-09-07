# gemma4:31b has no context niche — qwen3.8:27b reaches further in less memory

**Run:** desktop (dual RTX 3090), 2026-09-07. Derived Modelfiles pinning
`num_ctx` only; load forced with a 4-token generate; VRAM from `nvidia-smi` net
of a verified-idle baseline; residency confirmed via `ollama ps` PROCESSOR.

**Question:** `gemma4:31b` is the one roster model believed to have a capability
on the dual-card desktop it does not have on a single card — long context. The
operator's open question was what to do with that. If the niche is real it is an
argument for the pair beyond the 45 GB-class models.

## Result: the niche is not real. 27b covers it better at every size.

| model | `num_ctx` | resident | cards | fits one 24,576 MiB card? |
|---|---:|---:|---:|---|
| qwen3.8:27b | 16,384 | **18,908** | 1 | yes — **5,668 MiB spare** |
| gemma4:31b | 16,384 | 22,076 | 1 | yes — 2,500 MiB spare |
| qwen3.8:27b | 65,536 | **24,794** | 2 | no, by 218 MiB |
| gemma4:31b | 65,536 | 28,298 | 2 | no |

`qwen3.8:27b` has **2.3x the single-card context headroom** (5,668 vs 2,500 MiB),
so it reaches a longer context before the second card is needed at all. At 64k
both require the pair, and 27b does it in **3,504 MiB less**.

There is no context regime in which 31b is the better choice and none in which
it is the only choice.

## And it loses on every other axis

Same machine, same controls (`preswap-wallclock-noledger-2026-09-07`,
clean L2 seat corpus):

| | qwen3.8:27b | gemma4:31b |
|---|---:|---:|
| wall clock, short task | **18.1 s** | 36.4 s |
| wall clock, long task | **32.4 s** | 128.4 s |
| output tokens (csv) | **1,362** | 5,063 |
| L2 clean | **63/63 · 100%** | 28/33 · 85% |
| Eff. (corrected) | **1.08** | 0.67 |

**Consequence: `gemma4:31b` has no role the roster does not already fill.** The
"fat context on dual" argument was the last one for it and it does not hold.

## Unresolved boundary

`qwen3.8:27b` at `num_ctx` 131,072 **failed to load entirely** — 522 MiB
resident, no model in `ollama ps`. Either OOM at 128k against a 48 GB pool or a
different failure; not chased. That boundary is where the interesting question
now sits: **what is the longest context the pair can actually serve, and with
which model.** 31b is not the candidate.

## Method note — three failed attempts before this one

The first two probe loops sampled `nvidia-smi` before eviction had completed, so
a previous model's memory was still counted in the "idle" baseline. That produced
impossible readings — `num_ctx` 65,536 appearing to use *less* memory than
32,768, and two configurations reporting 0 MiB. Fixed by polling `ollama ps`
until empty **and** total VRAM below 1,500 MiB before taking the baseline, and by
asserting the generate returned `"done":true` before recording a row.

Fourth measurement error of this session from recording a number without first
checking the thing had actually happened. The same shape as `journalctl --user`
returning nothing, the layer regex matching a vision projector, and the ledger
timing window.

## Limits

- Footprint is deterministic; measured once per configuration.
- Single-card figures for 16,384 come from `single-vs-split-placement` (a real
  one-GPU daemon); the 65,536 rows are dual-card totals, so "fits one card" there
  is inference from the total, not a direct single-card measurement.
- Only two context sizes. The exact size at which each model needs the second
  card was not bisected.
