# Runbook: one model per card, and why the split is not a misconfiguration

**Status:** operational runbook. Footprint figures are a mix of measured and
extrapolated — each is labelled. The procedure in §5 has **not** been executed
on this host yet.

## 1. The failure this fixes

Asking session A for status, then session B, when the two sessions use
*different* models on the shared `:11434` daemon. Neither request is lost; the
second one waits for the first to finish generating, then waits again for a full
model evict-and-reload.

Measured cost of that reload, from `fixtures/coresidency-ceiling-2026-09-08`:

| `num_ctx` | 27b MiB | 35b MiB | total | both resident | switch |
|---:|---:|---:|---:|:---:|---:|
| 16,384 | 20,382 | 23,268 | 43,650 | yes | **0.6 s** |
| 32,768 | 22,041 | 21,652 | 43,693 | yes | **0.6 s** |
| 49,152 | 25,478 | 1,358 | — | no | 14 s |
| unpinned (262144) | ~39 GB | — | — | **no** | **124 s** |

Unpinned, one model claims ~39 GB of the 49 GB pair, so the second can never be
resident and every alternation pays the full reload.

**Compounding factor — host RAM, not VRAM.** This host has 31.3 GiB of system
memory. Ollama disables mmap when `model_size + headroom` (20.2 + 7.5 =
27.7 GiB) exceeds available (~23.4 GiB), so each 35b load reads the full
20.2 GiB into anonymous RAM rather than demand-paging from page cache.
Observed: **54 such loads in six hours**, with 3 GiB driven into swap. Model
switching is therefore expensive on both sides of the PCIe bus.

## 2. Telling the two regimes apart

This is not visible in the tmux status bar. That bar shows
`3090: <util>% <temp>° <watts>W` — utilization, temperature, power, **no VRAM** —
and both regimes light up both cards, so they look identical there. Two
side-by-side session screenshots differ only in the model name in each pane's
bottom-right corner.

Use memory over time instead:

- **Split** (one model across both cards): `mem_used` **flat and high on both
  cards**, utilization alternating 0↔100% as decode walks layers sequentially.
- **Switching** (two models trading places): `mem_used` **steps** — one card
  drains toward zero and refills, with a long gap while it reloads.

Captured split, 2026-09-09 12:37:43–12:38:12, one model resident:

```
12:37:43  gpu0 19082 MiB   0%   |  gpu1 20719 MiB  100%
12:37:45  gpu0 19082 MiB 100%   |  gpu1 20719 MiB   22%
12:37:51  gpu0 19082 MiB 100%   |  gpu1 20719 MiB    0%
12:37:54  gpu0 19082 MiB   0%   |  gpu1 20719 MiB  100%
```

Memory constant to the megabyte; utilization ping-ponging.

Captured switch, same session, 2026-09-09 12:38–12:41 — the user asked one
session for status, then the other, with different models:

```
12:38:32  gpu0 19086 MiB  |  gpu1 20725 MiB   resident=qwen3.8:27b
12:41:06  gpu0   383 MiB  |  gpu1   595 MiB   resident=none          <- fully evicted
12:41:09  gpu0 11306 MiB  |  gpu1 10625 MiB   resident=none          <- refilling
```

Both cards drain to the bare desktop baseline (383 / 595 MiB) before the second
model begins loading. Nothing is shared, nothing is retained; the first model is
discarded in full. That drain-and-refill step is the signature, and it is
unmistakable against the flat-memory split above. Elapsed from request to a
usable second model was over four minutes in this instance, against the 124 s
figure in §1 — the difference is that the first session's generation must finish
before the eviction can even start.

The GPU dashboard
reports `Mem:` per card and its recorder already has a `mem_used_mib` column —
but **Recording defaults to OFF**, and the only capture on disk is 20 rows
covering 9 seconds. Turn recording on before reproducing this.

## 3. The constraint that forces the split

pi is configured for a 128k context window; observed session inputs were 53,935
and 94,228 tokens. `qwen3.8:27b` at `num_ctx` 131072 needs **28,644 MiB**, which
does not fit one 24,576 MiB card.

**So the split is not a misconfiguration — it is required by the context window
in use.** Isolation to one card per model is only reachable by lowering context.
That trade is the whole decision.

## 4. Single-card footprints

`qwen3.8:27b` — all measured (`fixtures/ctx-sweep-27b-2026-09-08`, solo arm):

| ctx | VRAM | note |
|---:|---:|---|
| 16,384 | 18,907 | |
| 32,768 | 20,027 | |
| 65,536 | 22,237 | decode still flat at 56.4 tok/s |
| 131,072 | 22,823 | **decode 11.2 tok/s** — 5× loss, cause unverified |

`qwen3.6:35b` — 22,591 measured at 16,384 (`fixtures/singlecard-rank-2026-09-08`);
the rest **extrapolated** from its own KV logs, which scale at 352 MiB per 16K
(hybrid: only 11 of 42 layers are cached, plus ~188 MiB fixed recurrent):

| ctx | VRAM | basis |
|---:|---:|---|
| 16,384 | 22,591 | measured |
| 32,768 | ~22,943 | extrapolated |
| 65,536 | ~23,647 | extrapolated, does not fit with display overhead |

Compute buffers also grow with capacity and are **not** in these totals.

## 5. Procedure

Card identity — `CUDA_DEVICE_ORDER` is unset on this host, so `CUDA_VISIBLE_DEVICES=0`
is **not** guaranteed to be `nvidia-smi` index 0. Pin by UUID:

| Card | PCI | UUID | Display | Usable |
|---|---|---|---|---:|
| 0 | 01:00.0 | `GPU-22b9dafe-e97d-dbb2-50ba-2f1f1dea61f9` | disabled (~400 MiB sway) | ~24,176 |
| 1 | 03:00.0 | `GPU-102e9c9e-f883-58fa-6119-8c72f81fd88e` | **active** (Xwayland + Chrome, variable) | ~23,776 |

Assignment: `qwen3.8:27b` is dense and its footprint grows with context, so it
takes the clean card where there is room to grow. `qwen3.6:35b` is MoE and its
footprint is nearly flat across context, so it tolerates the display card —
though see §7.

```bash
sudo systemctl stop ollama          # stop the shared :11434 daemon first

# card 0 — qwen3.8:27b @ 65,536
sudo -u ollama env \
  CUDA_VISIBLE_DEVICES=GPU-22b9dafe-e97d-dbb2-50ba-2f1f1dea61f9 \
  OLLAMA_LLM_LIBRARY=cuda_v13 OLLAMA_HOST=127.0.0.1:11435 \
  OLLAMA_CONTEXT_LENGTH=65536 OLLAMA_KEEP_ALIVE=-1 OLLAMA_MAX_LOADED_MODELS=1 \
  ollama serve

# card 1 — qwen3.6:35b @ 32,768
sudo -u ollama env \
  CUDA_VISIBLE_DEVICES=GPU-102e9c9e-f883-58fa-6119-8c72f81fd88e \
  OLLAMA_LLM_LIBRARY=cuda_v13 OLLAMA_HOST=127.0.0.1:11436 \
  OLLAMA_CONTEXT_LENGTH=32768 OLLAMA_KEEP_ALIVE=-1 OLLAMA_MAX_LOADED_MODELS=1 \
  ollama serve
```

`OLLAMA_LLM_LIBRARY=cuda_v13` is required, not optional (`hw_standard.py:26`) —
without it the daemon also enumerates Vulkan. `KEEP_ALIVE=-1` keeps the model
resident permanently; `MAX_LOADED_MODELS=1` stops a second model landing on the
card.

Point each session at its own daemon — pi honors `OLLAMA_HOST`:

```bash
OLLAMA_HOST=127.0.0.1:11435 pi     # sessions that use 27b
OLLAMA_HOST=127.0.0.1:11436 pi     # sessions that use 35b
```

Verify: each card should show one model resident, `mem_used` flat, and
`offloaded N/N layers` in that daemon's own log with N equal to the model's full
layer count (66 for 27b, 42 for 35b). Any `N/M` with N<M means it spilled and
the context pin is too high for that card.

## 6. What this buys

- **Switch cost goes to zero.** Both models are permanently resident on separate
  cards; neither ever evicts the other. This is better than the 0.6 s
  co-residency option in §1, which still shares both cards.
- **No mmap thrash.** Each model loads once, so the 54-loads-in-six-hours
  pattern and the swap pressure both stop.
- **Likely resolves the `qwen3.6:35b` CUDA crash.** Every reproduction of
  `ggml-cuda.cu:106 illegal memory access` was on a two-card split; the
  single-GPU arm in `fixtures/e9-pi-rerun` scored 30/30 with the same pinned
  tag. Unconfirmed, but this configuration is the one that has never crashed.

## 7. What it costs, and what is unverified

- **27b drops from 128k to 65,536.** Sessions above ~62k tokens will compact
  more often. One observed session was at 94,228 tokens and would be affected.
- **35b drops to ~32,768.**
- **Card 1 headroom is thin** — roughly 800 MiB with the 35b at 32,768, against a
  browser whose VRAM use varies. A spike could push it to spill. If that proves
  fragile, move the 35b to card 0 and cap the 27b at 32,768 instead.
- 35b footprints above 16,384 are **extrapolated**, not measured.
- The cost of a spilled layer on a **dense** model has never been measured here.
  The only offload curve on disk is `gemma4:26b`, which is **MoE**, and that
  constant does not transfer. See
  `REVIEW_CALL_dense-offload-curve_2026-09-09.md`.
- `OLLAMA_CONTEXT_LENGTH` as the pinning mechanism has not been tested on this
  host; the established method elsewhere is a per-context derived tag
  (`hw_standard.py:163`). Confirm the daemon log shows the intended `-c` value
  before trusting it.
