# The simulated 8 GB envelope predicted a real 8 GB card to within 7%

**Run:** testbench (System 2), 2026-09-05. `gemma4:26b` on a real **RTX 2080,
8 GB**, contract-v1 probe (`num_predict 128`, `temperature 0`, two calls, run 2
is the warm figure per the contract).

**Question:** `gemma26-8gb-cap-e9` measured gemma4:26b at a *simulated* 8 GB
envelope — a 24 GB RTX 3090 with `num_gpu=12` — and reported **23.5 tok/s**.
Does that ablation method predict what a genuine 8 GB card does?

## Result: yes, and closer than it had any right to be

| | decode tok/s |
|---|---:|
| **Predicted** — 3090 capped to 8 GB (`num_gpu=12`), CUDA | **23.5** |
| **Measured** — real RTX 2080, 8 GB, Vulkan | **21.97** |
| delta | **−6.5%** |

Cold run: 11.88 tok/s (48.4 s wall, prefill 14.5 tok/s). Warm run 2: **21.97
tok/s**, 7.3 s wall, prefill 177.7 tok/s. Residency: **7,608 MiB of 8,192 MiB on
the GPU**, the rest mmap'd into page cache (13 GB in `buff/cache` on a 15 GB
box).

**gemma4:26b runs on 8 GB.** That was the prediction and it holds.

## Why the closeness is surprising, and why that is the interesting part

Four things differ between the prediction and the measurement, and every one of
them should have moved the number:

| | desktop (predicted) | bench (measured) |
|---|---|---|
| backend | **CUDA** | **Vulkan** — driver 535 is below ollama's 550 requirement, so it fell back |
| GPU | 3090, Ampere, 936 GB/s | **2080, Turing, 448 GB/s** |
| CPU running offloaded layers | i9-9900KF, 8C/16T | **i3-9100F, 4C/4T** |
| system RAM | 31 GB | **15 GB** |

A different compute backend, half the memory bandwidth, half the CPU, half the
RAM — and the result lands within 6.5%.

**The most likely reading: at a severe VRAM cap, decode rate is dominated by the
memory-bandwidth cost of streaming CPU-resident weights, and everything else is
second-order.** That is exactly the mechanism the MoE constraint findings
proposed, and it is the first time this program has predicted a number on
different hardware and been right.

## This is the counter-example the widening stub asked for

`EVERY_WIDENING_SHRANK_THE_CLAIM_STUB.md` lists as required evidence:

> **A case where widening did *not* shrink a claim**, to establish that the
> program is capable of producing one. Its absence so far is suggestive but also
> consistent with never having tested a true effect.

**This is that case.** Widening from a simulated envelope to real hardware — a
harder test than any of the five instances in that stub — left the claim
standing. The 8 GB VRAM-cap result was not an artifact of the cap mechanism.

It nudged 6.5% lower, which is directionally consistent with the stub's thesis
but well inside what a single warm probe across four confounds can resolve. The
claim survived; it did not collapse.

## Caveats, and one that favours the bench

- **n=1 warm probe.** Screen tier for pass/fail purposes. Decode tok/s is a
  continuous measure and has real power at low n where pass/fail does not
  (`GOLD_STANDARD.md` §2a), but this is one number, not a distribution.
- **Context length differs and it favours the bench.** The desktop's cap runs
  pinned `num_ctx 16384`; the bench ran ollama's vram-based default of
  **`-c 4096`**, reserving far less KV cache and leaving more of 8 GB for
  weights. A matched-context run would likely be slower than 21.97.
- **MTP speculative decoding is active** on the bench
  (`--spec-type draft-mtp --spec-draft-n-max 3`). Whether the desktop's capped
  runs had it enabled is unverified; same ollama version (0.32.12, deliberately
  matched) makes it likely but it is not confirmed.
- **Vulkan, not CUDA.** Not a like-for-like backend, and this number should not
  be quoted as a CUDA figure.

## Next

A driver upgrade to 550+ on the bench would allow a CUDA run and remove the
largest confound. Debian 12 ships only 535 with no backports configured, so that
needs bookworm-backports. **If CUDA lands materially faster than 21.97, the
match here was partly luck** — Vulkan happening to cost about what the weaker
hardware saved. Worth knowing which.

A matched-context run (`num_ctx 16384`) would remove the one confound that
currently favours the bench.

## Provenance

- Prediction: `../gemma26-8gb-cap-e9/FINDING.md` (23.5 tok/s, `num_gpu=12`).
- Envelope calibration: `../gemma4-26b-16gb-cap/FINDING.md`.
- Probe: contract-v1 prompt at
  `project-phoenix/docs/domain_runs/GEMMA4-CTX8192-3090-VS-Z13-001/prompt.txt`,
  the same file `runner.py`'s `measure_tok_s` uses, so this figure is directly
  comparable to existing Front I throughput data.
- Bench: `~/.dotfiles/machines/testbench/` — Debian 12, kernel 6.1.0-52,
  ollama 0.32.12 user-local, version-matched to the desktop.
