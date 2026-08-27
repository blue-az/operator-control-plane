# nemotron-3-nano decode — 7% spill, not 31b-slow

**Run:** desktop, 2026-08-15T06:24:10Z, 9/9 cells, think off, 128-token
`generate`, `num_ctx 16384`. Trial 1 cold; warm = 2–3. **Not UID-verified.**
Not L2. Not Elo.

## Warm mean tok/s

| model | place | mean tok/s |
|---|---|---:|
| `gemma4:26b` | 100% GPU | **127.4** |
| `nemotron-3-nano:latest` | **7%/93% CPU/GPU** | **121.2** |
| `gemma4:31b` | 100% GPU | 34.4 |

Nano is ~26b, not ~31b. The 7% spill costs a few tok/s against a fully
resident 26b, not a 3× cliff. Architecture (hybrid Mamba + ~3.5B active)
shows up; the CPU slice does not make it dense-slow.

Load is heavier (22.9s vs 26b 16.9s). That is the 24 GB blob, not decode.

No L2 pack from this. Say go if you want the same 54-cell host row as 35b.
