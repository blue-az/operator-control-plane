# C1 repair cohort, RTX 3090, 2026-10-01

Mode: benchmark. Authorized by the operator ("please run this") against
`../../COMPARISON_FIELD_PLAN_20261001.md`, priority P1. New packet; not an
append to F0 or to any archived Ollama run.

## What C1 is

The **current seat weights at the controlled profile**, on Ollama. Not the
seats' everyday 32K / q8_0-KV / speculative configuration.

- Same tasks, levels, trial counts, timeout and qualification as F0
  (`standard-l012-20260930-r2`): five tasks x L0/L1/L2 x six trials = 90 cells
  per model; three-cell canary first; loaded decode separate.
- Same sampler as F0: temperature 0.7, top_p 0.8, top_k 20, min_p 0,
  typical_p 1, neutral penalties, seed 1234, 16,384 context, 4,096 output,
  thinking off. Ollama-only fields: num_keep 4, `draft_num_predict 0`
  (speculation off; the seat tags ship 2 and 3).
- Runtime differs from F0 and stays labeled: Ollama 0.32.12 (its bundled
  engine), not the Prism CUDA fork.

## Daemon and identity

Dedicated `ollama serve` started and stopped by `launch-c1-3090.py` via
`testbench:~/c1-study-20261001/serve.sh`: 127.0.0.1:18669, GPU0
(`GPU-22b9dafe-…`) only, NUM_PARALLEL 1, MAX_LOADED_MODELS 1, flash attention
on, **KV cache f16** (F0 parity; the shared seat daemons use q8_0), keep-alive
forever, NOPRUNE. Its model store holds **hardlinks** of the seat blobs (no
copies, no new tags on the shared daemons) plus pinned tags:

| Pinned tag | From seat tag (digest) | Weight blob | Projector |
|---|---|---|---|
| `c1-qwen3.6-35b:latest` `bdb91065…` | `qwen3.6:35b` `096fdbd0…` | `d372de8e…` | `a62390d2…` |
| `c1-gemma4-26b:latest` `fa421b1e…` | `gemma4:26b` `08ae7ec1…` | `dfd98d27…` | `41926ed5…` |

Identity gate: every before/after gate checks version, tag digest, FROM blobs
and every pinned parameter (`preflight_comparison.py`). Blob **bytes** are hashed
at the start and end of each model block (`blobs-start-*`, `blobs-end-*`), not
per cell — Ollama gates do not rehash, unlike F0's per-gate GGUF hash.

Fit check before launch (prompt-free load): Qwen35 21,800 MiB, Gemma26 18,678
MiB attributed on GPU0, `size_vram == size`, all layers offloaded.

## Cache reset (differs mechanically from F0)

Ollama exposes no slot erase. Before each cell and each decode call the model is
unloaded, absence confirmed via `/api/ps`, then reloaded with a prompt-free
`/api/generate` (`done_reason: load`, no tokens). The before-gate follows the
reload. Result: empty KV, warm page-cached weights; reload is outside the task
timer. Recorded in each cell's `cache-reset.json`.

## Loaded decode

Same corpus (sha256 `8eae41b3…`), one discarded warmup + three measured 128-token
calls at temperature 0, raw prompt, num_ctx 16384. Depth by tokenizer (qualified
before launch, 1-token calls): Qwen35 12,811 prompt tokens (same as F0), **Gemma26
14,595** — label it. Ollama has no `ignore_eos`: a call stopping before 128
tokens fails the contract and is recorded as `DECODE_FAILED.json`; the quality
packet still runs. tok/s = eval_count / eval_duration.

## Stop rules

As F0: abort on gate failure, changed frozen inputs, foreign request-log traffic,
replaced logs, unconfirmed cache reset, occupied ports or foreign GPU workload.
An unproven canary blocks that model's full packet. No eviction, no shared-daemon
restart, new output directories only. `STARTED` blocks reuse; `DONE` means both
repair blocks finished. Native Fusion (36 cells/model) is a separate packet.
