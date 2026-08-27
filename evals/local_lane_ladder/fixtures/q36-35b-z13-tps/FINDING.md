# q36-35b z13 tok/s — 35b is 100% GPU here, and slightly faster than 26b

**Run:** z13, 2026-08-17, same blob as desktop (`07d35212591f`, Q4_K_M, 23 GB).
Same meter as `desktop_sweep.py` / `q36-35b-spill-tps`. AC plugged in,
`powerprofilesctl=balanced`, CPU governor `powersave` (could not switch to
`performance` without sudo). **Not UID-verified.**

## Warm mean

| model | ctx | place | z13 tok/s | desktop tok/s | desktop place |
|---|---:|---|---:|---:|---|
| **`qwen3.6:35b`** | 16384 | **100% GPU** | **59.2** | 86.4 | 4%/96% |
| `qwen3.6:35b` | 32768 | **100% GPU** | 58.6 | 84.0 | 4%/96% |
| `gemma4:26b` | 16384 | **100% GPU** | 55.2 | 128.0 | 100% GPU |
| `gemma4:26b` | 32768 | **100% GPU** | 55.3 | 127.8 | 100% GPU |

Cold loads ~8s. Zero errors. 32k did not change placement or drop decode.

## Finding — the 3090 lip inverts on UMA

On the 3090, 35b is a 23 GB file on a 24 GB card: 4% CPU, 86 t/s, *slower*
than 26b (128). On z13 the same file is **22 GB / 100% GPU / 32k** on 27 GB
unified memory. 35b is then *faster* than 26b (59 vs 55).

That is the hole. G2 treated 35b as a spilling desktop special case and
never put it on `Z13_BENCHMARK.md`. z13 is the machine where 35b's size
stops being a tax.

`Z13_BENCHMARK.md` still has 26b at 16%/84% and 46.8 t/s (2026-08-13).
This run has 26b at **100% GPU / 55 t/s** on the same host, AC, conservative
governor. Serving stack moved. Do not quote the old 16% row as current.

Power state is **not** `performance`. 08-15 addendum: battery/`power-saver`
read 3.4× low. This run is AC + balanced. 26b at 55 is *above* the 46.8
and the 51.6 AC/`performance` anchors, so this is not a power-saver
collapse. A `performance` re-run may still add a few tok/s; it will not
create the 100% GPU result (already here).

## Limits

n=2 warm, one prompt, one machine. Not an Elo row. E9 battery is
`q36-35b-e9-z13`.
