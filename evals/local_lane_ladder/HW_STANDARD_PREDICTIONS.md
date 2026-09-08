# Pre-swap predictions — registered 2026-09-08, before measurement

Run with `hw_standard.py`. **These are written down first on purpose.** A
prediction confirmed after seeing the data is not a test, and this program has
already retracted seven measurements that were recorded without a prior
expectation to check them against.

## Machine state at registration

| GPU | board | PCI | link | note |
|---|---|---|---|---|
| 0 | **EVGA** RTX 3090 | 01:00.0 | **x16** (CPU lanes) | |
| 1 | **ZOTAC** RTX 3090 | 03:00.0 | **x4** (chipset) | moves to the other machine |

Desktop: i9-9900KF, 31 GB, ollama 0.32.12, driver 580.178.04.
Post-swap intent: one card per machine, Zotac consistently in slot 1.

## Predictions

Each is falsifiable and names what would disprove it.

### P1 — `qwen3.8:27b` at ctx 262144 does NOT fit one card
Needs ~29 GB (measured dual: 18,692 + 20,176 MiB) against a 24,576 MiB card.
**Predict:** partial CPU offload, layer count below 66/66, decode well under
30 tok/s.
**Falsified if:** it reports 66/66 and holds >50 tok/s.
**Confidence: medium.** This is arithmetic, not measurement — no model has ever
been measured on a single *discrete* 24 GB card at fat context. The only spill
record in the program is `gemma4:31b` on the **z13**, an APU with unified memory,
taken with `ollama ps`, the instrument this program has since discredited.

### P2 — `qwen3.8:27b` at ctx 16384 fits one card at full speed
Measured solo on GPU0 (2026-09-06): 18,908 MiB, 75.3 tok/s.
**Predict:** reproduces within 10%, 66/66 layers, one card.
**Falsified if:** it splits, spills, or lands below 68 tok/s.
**Confidence: high** — this is a re-measurement, not an extrapolation.

### P3 — `qwen3.6:35b` at ctx 16384 is marginal on one card
Measured 24,628 MiB at ctx 16384 against a 24,576 MiB card — over by 52 MiB.
**Predict:** it does *not* fit; either splits on the dual host or spills solo.
**Falsified if:** it fits one card cleanly.
**Confidence: medium.** The measurement was taken without a temperature pin;
the pinned variant read 23,682 MiB, which *would* fit. The two disagree across
the card boundary, which is exactly why this needs the standard.

### P4 — the Zotac's x4 link costs load time, not inference
Layer-split decode is already known not to be PCIe-bound (79.1 and 34.1 tok/s
measured across the x4). Single-card inference never crosses PCIe at all.
**Predict:** moving the Zotac from x4 to a primary x16 slot improves **load
time** materially and changes decode by <5%.
**Falsified if:** decode moves >5%, or load time does not improve.
**Confidence: medium-high** on decode, **low** on the load-time magnitude —
load time has never been compared across link widths here.

### P5 — dual vs solo is a wash for a model that fits one card
Measured for `gemma4:26b`: 226.6 dual vs 226.8 solo, +0.1%.
**Predict:** holds for `qwen3.8:27b` at ctx 16384, within ±5%.
**Falsified if:** either direction exceeds 5%.
**Confidence: high** — replicating a measured result on a second model.

## How to run

Pause any interactive session first; the standard fails closed if it cannot
reach a clean idle GPU state, rather than silently measuring a contended card.

```bash
# second daemon pinned to GPU0 (needs sudo; shares the system model store)
sudo -u ollama env CUDA_VISIBLE_DEVICES=0 OLLAMA_LLM_LIBRARY=cuda_v13 \
     OLLAMA_HOST=127.0.0.1:11435 ollama serve
# OLLAMA_LLM_LIBRARY is required: CUDA_VISIBLE_DEVICES does not hide the card
# from Vulkan, so without it the "solo" daemon can still reach both GPUs.

python3 hw_standard.py \
  --models qwen3.8:27b qwen3.6:35b \
  --ctx 16384 65536 262144 \
  --solo-host 127.0.0.1:11435 \
  --out fixtures/hw-standard-preswap/desktop.json
```

Re-run the identical command on each machine after the swap. Differences are
attributable only if the protocol block in the output matches.
