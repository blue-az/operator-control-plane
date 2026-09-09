# Dual wins on prefill, not decode - and the mechanism is unknown

**Run:** desktop, 2026-09-08. `hw_standard.py`, Standard A (as-shipped defaults),
loaded regime (~12.8-14.6k prompt tokens), `num_ctx` 16384, n=3. Solo arm on the
`:11435` daemon pinned with `CUDA_VISIBLE_DEVICES=0` **and**
`OLLAMA_LLM_LIBRARY=cuda_v13`, verified by reading `/proc/18731/environ`.

## Result

| model | solo tok/s | dual tok/s | delta | solo prefill | dual prefill | prefill delta | solo VRAM | dual VRAM |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `gemma4:26b` *(control)* | 171.3 | 170.1 | +0.7% | 3.5 s | 3.5 s | none | 19,309 | 19,311 |
| `qwen3.6:35b` | 132.7 | 124.4 | +6.7% | 4.8 s | 3.9 s | **dual -19%** | 22,591 | 23,698 |
| `qwen3.8:27b` | 56.4 | 61.3 | -8.0% | 11.1 s | 11.0 s | none | 18,907 | 20,424 |
| `gemma4:31b` | 33.7 | 33.8 | -0.3% | 14.2 s | 8.5 s | **dual -40%** | 22,081 | 23,719 |

`gemma4:26b` is the control: it is single-card in both arms, so its +0.7% confirms
the two daemons are comparable. `single-vs-split-placement` read +0.1% for the
same control on the empty-KV standard.

## Decode: the null holds under load

Range **-8.0% to +6.7%**, against -4.7% to +9.3% measured empty in
`single-vs-split-placement`. Signs and magnitudes are close, so that finding
transfers to the loaded regime. There is no general dual-card decode advantage
while the model fits one card.

The mechanism is that decode walks layers sequentially. Split across two cards,
one card computes while the other waits, so two cards never contribute bandwidth
simultaneously. What crosses the boundary is the hidden state - about 4 KB per
token for 35b - which is negligible even at x4.

## Prefill: a real dual advantage, and no explanation

Two of four models prefill materially faster on two cards. **The proposed
mechanism was wrong.** The penalty appeared to track headroom (the two models with
under 2.5 GB free paid it, the two with over 5 GB free did not), predicting that
`qwen3.8:27b` would develop the same penalty once its context filled the card.

`ctx-sweep-27b-2026-09-08` falsified that: 27b solo prefill is **0.872 ms/token at
16384, 32768 and 65536**, dead flat while headroom fell from 5,669 to 1,979 MiB.

So the 31b and 35b prefill penalty is an **open finding with no mechanism**. Do
not cite a cause for it. Candidates not yet tested: layer count (61 and 42 against
66 and 31), architecture family, and batch scheduling differences.

## Also here

`gemma4-26b-offload-curve.json` - a forced-offload sweep on `gemma4:26b`
(31 layers), empty-KV regime, n=3: 224.8 tok/s at 31/31 layers, **172.7 at 30/31**.
One layer off the GPU costs 23%. All four points fit one law: 4.45 ms per token
resident, **+1.34 ms per CPU-resident layer**. That per-layer constant does **not**
transfer - see the 27b sweep, where it is ~5.5 ms.
