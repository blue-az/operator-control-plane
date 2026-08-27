# q36-35b-e9-z13 — 35b is 100% GPU on this host; 26b still wins the battery

**Run:** z13, 2026-08-17T23:31–23:45Z, 60/60 cells, 60/60 traces.
`num_ctx 16384 · temperature 0.8 · think off`. Same-run control:
`gemma4:26b`. **Not UID-verified.** AC plugged in, `balanced` /
`powersave` (could not set `performance` without sudo).

Same blob as desktop: `qwen3.6:35b` `07d35212591f`.

## Result

| Model | Total | csv | booking | consts | anchor | logfmt | place |
|---|---:|---:|---:|---:|---:|---:|---|
| `gemma4:26b` | **24/30** | 0/6 | 6/6 | 6/6 | 6/6 | 6/6 | 100% GPU (14/14) |
| `qwen3.6:35b` | 18/30 | 0/6 | 6/6 | **0/6** | 6/6 | 6/6 | **100% GPU (15/15)** |

26b matched its desktop E9 and z13-l2 score (24/30). Instrument held.
Fisher 18/30 vs 24/30 **p=0.16** — 26b is ahead, n=6 does not separate
them as cleanly as the desktop 14 vs 24 (p=0.015).

35b on z13 vs 35b on desktop (14/30): recovered booking (4→6), anchor
(5→6), logfmt (5→6). Still 0/6 on `constant-and-callers` (stale
`up to 3 times`). csv floor for both (`food=46.44`). Cross-machine
14 vs 18 is p=0.44 — do not call that a host effect.

## Finding — the missed gap is residency, not a seat flip

`ollama ps` on z13: **22 GB, 100% GPU, ctx 16384 and 32768**. Desktop
is the 4% weight lip. Decode (`q36-35b-z13-tps`):

| | z13 | desktop |
|---|---:|---:|
| `qwen3.6:35b` 16k | **59.2** (100% GPU) | 86.4 (4%/96%) |
| `gemma4:26b` 16k | 55.2 (100% GPU) | 128.0 (100% GPU) |

On this laptop 35b is the *faster* Qwen and fully on the iGPU. On the
3090 it is the slower one and spilling. G2 + a desktop-only ranking
hid that inversion.

26b is also 100% GPU here. `Z13_BENCHMARK.md` still lists it at 16%/84%
/ 46.8 t/s (2026-08-13). Serving moved. Quote this pack, not that row.

## Seat

Unchanged on both machines. 26b 24/30 twice. 35b 14/30 desktop, 18/30
z13, 0/6 consts both times. z13 is where you *run* 35b at 100% GPU and
~59 t/s. It is not where 35b becomes the executor.

## Limits

n=6, conservative power profile, not `performance`. A `performance`
re-run may add tok/s; it will not create the 100% GPU result. Not
pooled into E9's seven-model table.
