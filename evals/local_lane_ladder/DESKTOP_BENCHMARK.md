# Desktop benchmark — single RTX 3090, the last clean baseline

**Measured:** 2026-08-14, `ctx 16384`, `temperature 0.8`, 128-token generations,
each model loaded cold and unloaded after. Decode rate is
`eval_count / eval_duration` — it excludes load time and prompt eval.
**Not UID-verified. No claim registered.**

Method deliberately mirrors `Z13_BENCHMARK.md` so the two machines compare
like-for-like. Raw: `handoffs/desktop_sweep_20260814_144605.json`.
Script: `desktop_sweep.py`.

> **This is the single-3090 baseline and it expires.** A second RTX 3090 is
> installed but not powered — the cord was wrong; replacement due 2026-08-18.
> Every figure below is historical from the day it comes up. Re-run
> `desktop_sweep.py` after the upgrade and diff, rather than assuming a number
> labelled "desktop" still describes the same machine.

## The machine

| | |
|---|---|
| GPU | 1× NVIDIA RTX 3090, 24 GB, 320 W power limit |
| Second card | installed, **unpowered** (wrong cord; replacement due 2026-08-18) |
| KV cache | `q8_0`, flash attention on |

## Measured

| Model | **tok/s** | Load | Placement |
|---|---:|---:|---|
| `granite4` (3.4B) | **197.9** | 2.9s | 100% GPU |
| `qwen3-vl:30b` | **177.2** | 12.7s | 100% GPU |
| `gemma4:26b` (MoE) | **133.0** | 11.9s | 100% GPU |
| `gemma4:12b` | 75.2 | 7.2s | 100% GPU |
| `qwen2.5-coder:14b` | 72.9 | 6.5s | 100% GPU |
| `qwen3.8:27b` | 43.7 | 11.8s | 100% GPU |
| `gemma3:27b` | 39.9 | 17.6s | 100% GPU |
| `qwen3.6:27b` | 37.8 | 11.0s | 100% GPU |
| `qwen3:32b` | 35.1 | 11.5s | 100% GPU |
| `gemma4:31b` (dense) | 34.8 | 22.7s | 100% GPU |

**Every model ran fully on GPU.** That independently confirms the residency
check in `HARDWARE_TRANSFER.md`: nothing in the ladder field was spilling while
it was scored, so the rankings measure capability rather than VRAM pressure.

## Finding 1 — speed and correctness are close to uncorrelated

The two fastest models on this machine are the two *worst* on the ladder:

| Model | tok/s | ladder (n=18) |
|---|---:|---:|
| `granite4` | 197.9 | 8/18 floor; 3/15 on probes |
| `qwen3-vl:30b` | 177.2 | 12/54 |
| `gemma4:26b` | 133.0 | **36/54** |
| `gemma4:31b` | 34.8 | 36/54 |

`qwen3-vl:30b` generates 5× faster than `gemma4:31b` and solves a third as much.
Throughput tables cannot be read as capability tables, in either direction.

## Finding 2 — the seat pick is far wider than the ladder implied

`gemma4:26b` and `gemma4:31b` are tied on correctness (36/54 each, P=0.49 in
E11). On this machine `gemma4:26b` is **3.8× faster** — 133.0 vs 34.8 tok/s —
and loads in half the time.

The earlier estimate of "1.4× faster" understated it substantially; that figure
came from wall-clock on ladder cells, which is dominated by prompt eval and tool
turnaround rather than decode. On decode rate specifically the gap is 3.8×.

Two models with statistically indistinguishable correctness, one of them nearly
four times faster. Nothing in this table argues for `gemma4:31b`.

## Finding 3 — `qwen3.8:27b` is faster than `qwen3.6:27b` as well as more compliant

43.7 vs 37.8 tok/s, **+15.6%**, same architecture and quantisation. Combined with
the `strict-log-format` contract gain (16.7% → 83.3%, p=0.0005), the point
release is better on both axes measured so far. It remains unrankable against
`gemma4:26b` on correctness — and is 3× slower on this machine.

## Finding 4 — the z13 penalty is architecture-dependent

Against `Z13_BENCHMARK.md`'s post-KV-tune figures:

| Model | desktop | z13 | desktop / z13 |
|---|---:|---:|---:|
| `granite4` | 197.9 | 85.4 | 2.3× |
| `gemma4:26b` (MoE) | 133.0 | 46.2 | 2.9× |
| `gemma4:12b` | 75.2 | 25.7 | 2.9× |
| `gemma4:31b` (dense) | 34.8 | 7.2 | **4.8×** |

The general penalty for moving to the z13 is ~2.3–2.9×. For the large dense
model it is 4.8× — the outlier, and consistent with the compute-placement story
in `Z13_BENCHMARK.md`, where `gemma4:31b` is the model with the largest CPU-placed
share (27%) and pays it on every token.

This also settles a stale note: `Z13_BENCHMARK.md` estimated the current gap at
"roughly 2×" after finding the old 4.9× ratio outdated. Measured like-for-like,
**both were right about different things** — MoE is ~2.9×, dense is still ~4.8×.
The single-ratio framing was the error.

## Limits

n=1 per model, one prompt, one context length, one generation length. These are
throughput figures and say nothing about correctness. Load times include cold
page-in and vary with page cache state. Generation lengths vary (87–128 tokens)
because some models stopped early on `done_reason: stop`; the rate is unaffected,
being per-token. Single 3090 at 320 W — a different power limit changes these.
