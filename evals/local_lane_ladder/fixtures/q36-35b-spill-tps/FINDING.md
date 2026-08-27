# qwen3.6:35b spill tok/s — 4% CPU is not a decode killer

**Run:** desktop, 2026-08-15T05:35:41Z, 18/18 cells, think off, 128-token
`generate`, same meter as `desktop_sweep.py`. Trial 1 cold; warm = trials 2–3.
**Not UID-verified.** **On the desktop speed ranking** as of 2026-08-17
(`DESKTOP_BENCHMARK.md` addendum, `GOLD_STANDARD.md` §3). Not a seat. G2
no longer vetoes this row: a few-percent weight lip is host-conditioned,
not a KV-default confound.

## Warm mean tok/s

| model | ctx | place | mean tok/s |
|---|---:|---|---:|
| `qwen3.6:35b` | 16384 | 4%/96% CPU/GPU | **86.4** |
| `qwen3.6:35b` | 32768 | 4%/96% CPU/GPU | **84.0** |
| `qwen3.6:27b` | 16384 | 100% GPU | 37.8 |
| `qwen3.6:27b` | 32768 | 100% GPU | 37.8 |
| `gemma4:26b` | 16384 | 100% GPU | **128.0** |
| `gemma4:26b` | 32768 | 100% GPU | 127.8 |

35b’s CPU fraction did not grow from 16k to 32k. Doubling the window cost
~3% decode (86.4 → 84.0). 26b and 27b were flat across the same pair.

## What that means

A few-percent spill is **not** a total killer on this meter. Spilling 35b
still decodes **~2.3×** the fully-resident `qwen3.6:27b` and **~2.5×**
the last 31b sweep (34.8). It is **~1.5×** slower than the seat (`26b`
128 tok/s), which stays fully on GPU at both windows.

This is **not** a measurement of “how much the 4% costs 35b.” There is no
100% GPU 35b row on this card, so there is no same-model no-spill
baseline. Dual-3090 (or a slimmer quant) is what produces that delta.
Until then: 35b-with-spill is usable and fast; it is not cleaner than 26b.
It **is** a desktop speed row — second on this machine, behind 26b only.

## Limits

n=2 warm, one prompt, one machine, 320 W. Some 35b cells stopped at
95–98 tokens (`done_reason: stop`); rate is per-token so it still
compares. This pack is the speed ranking source. It is not an Elo /
L0–L2 / seat source — that needs the E9 five-fixture battery with a
same-run 26b control, placement logged, not used as a veto.
