# gemma4:26b — VRAM envelope on the 3090 (24 / 16 / 12 / 8 / CPU)

**Run:** desktop RTX 3090, 2026-08-17, same meter as `desktop_sweep`
(`eval_count/eval_duration`, think off, temp 0.8, 128 tokens, ctx 16384).
n=3 per envelope (1 cold + 2 warm). **Not a 4070/4060 number.** Layer cap
via `options.num_gpu` (no sudo for `OLLAMA_GPU_OVERHEAD`).

26b wants ~18.5 GiB at 16k when 100% GPU.

| envelope | `num_gpu` | VRAM | place | warm tok/s | vs full |
|---|---:|---:|---|---:|---:|
| full 24GB | default | 18.0 GiB | 100% GPU | **125.6** | 1.00 |
| razor 16.5GB | 30 | 16.4 GiB | 11%/89% | **100.1** | 0.80 |
| **16GB** | 28 | 15.3 GiB | 14%/86% | **71.3** | 0.57 |
| **12GB** | 20 | 11.4 GiB | 39%/61% | **34.4** | 0.27 |
| **8GB** | 12 | 7.3 GiB | 62%/38% | **23.1** | 0.18 |
| CPU only | 0 | 0.4 GiB | 100% CPU | **12.9** | 0.10 |

Variance on the warm pairs is tiny (12.9/12.9, 23.1/23.2, 34.2/34.6).

## Finding — there is a floor, and 8GB is sitting on it

The ~20 tok/s “I am watching this” line is the one this programme already
uses. **8GB (23.1) still clears it. CPU-only (12.9) does not.**

12GB at 34 t/s is still an interactive 26b, at 0.27× the 24GB card. 16GB
at 71 is the respectable row. Below 16GB you are buying a smaller
chassis, not a cheap 26b.

The curve is not linear in CPU %:

| CPU-placed | tok/s | drop vs previous step |
|---:|---:|---|
| 0% | 125.6 | — |
| 11% | 100.1 | −20% |
| 14% | 71.3 | −29% of 100 |
| 39% | 34.4 | −52% of 71 |
| 62% | 23.1 | −33% of 34 |
| 100% | 12.9 | −44% of 23 |

11–14% is the steep bit. That is why 35b’s 4% lip is still a “few tok/s”
hope and a 16GB 26b is already a different machine.

CPU-only 12.9 is the measured floor on this host (desktop CPU + no iGPU
layers). It is not zero. It is below interactive.

## What this is not

Not a 4070/4060/3060 result (those cards are slower per GPU-resident
layer). Not the 35b 4%→0% A/B. Not a MAX 390 number.

## Limits

Layer-count cap, not a hard VRAM fence. A real 12GB/8GB card fills VRAM
then spills; we picked `num_gpu` just under the envelope. n=2 warm, one
prompt. Service left unloaded.
