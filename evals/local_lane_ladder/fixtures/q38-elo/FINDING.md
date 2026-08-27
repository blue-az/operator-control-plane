# q38 Elo placement — three-item E11 scale, plus a failed mid-band fixture

**Computed:** 2026-08-14, grok, from retained e9+e11+q38-ladder traces.
**Not UID-verified.** The original Rasch fitter is not in the repo; this
reconstructs it. Two placements are reported so the reconstruction is
visible rather than hidden.

## Official 3.8 vs 3.6 (vendor card, not this ladder)

Source: [`Qwen/Qwen3.8-27B`](https://huggingface.co/Qwen/Qwen3.8-27B)
model card, text-performance table. 3.6 column is Qwen's same-harness
re-eval, not a copy of the April 3.6 blog.

| Bench | 3.8-27B | 3.6-27B | Δ |
|---|---:|---:|---:|
| GPQA Diamond | 89.2 | 87.8 | +1.4 |
| LiveCodeBench v6 | 90.3 | 83.9 | +6.4 |
| SWE-bench Pro | 61.7 | 53.5 | +8.2 |
| Terminal-Bench 2.1 | 73.0 | 63.4 | +9.6 |

Footnotes on that card: SWE-Pro / DeepSWE / NL2Repo use the Claude Code
harness at temp=1.0, 256K, thinking on; "problematic tasks were
corrected." QwenSWEBench / CoWorkBench / JobBench are in-house.
Terminal-Bench **2.1** 63.4 for 3.6 is not the April blog's Terminal-Bench
**2.0** 59.3.

These numbers are **not** our ladder. Our local run is Q4_K_M, think off,
ctx 16384, opr. Vendor direction (3.8 up on agentic/coding contracts)
matches our `strict-log-format` gain. Vendor does **not** license a seat
change here.

## Placement of `qwen3.8:27b` on the E11 items

Items frozen at the published difficulties (1511 / 1598 / 1994). q38's
pattern is 16/18, 15/18, 3/18.

| Method | q38 Elo | vs 26b/31b (1814) | vs 3.6 (1689) |
|---|---:|---|---|
| 1D MLE on frozen items (Elo-400) | **1814** | tie | above |
| Joint 8-player Rasch, scale locked to 26b−gemma3 spread, mean 1500 | 1714 [1644, 1806] | overlap | separate |

Bootstrap 400 resamples of the joint fit: **P(q38 > 26b) = 0.14**,
**P(q38 > 3.6) = 0.92**. q38 is in the top band, not in 3.6's band, and
is not above the gemma4 pair.

Joint medians (same scale; the 1500-mean now includes an 8th player, so
every rating shifts down ~60 vs the published 7-player table — compare
ranks, not the 1814 number):

| Model | Raw | Joint median | 95% boot |
|---|---:|---:|---|
| `gemma4:26b` | 36/54 | 1754 | [1720, 1802] |
| `gemma4:31b` | 36/54 | 1754 | [1720, 1802] |
| `qwen3.8:27b` | 34/54 | 1718 | [1644, 1806] |
| `qwen3.6:27b` | 28/54 | 1622 | [1564, 1689] |
| `qwen3-vl:30b` | 12/54 | 1438 | [1366, 1497] |
| `qwen3:32b` | 4/54 | 1303 | [1212, 1377] |
| `qwen2.5-coder:14b` | 3/54 | 1269 | [1156, 1353] |
| `gemma3:27b` | 0/54 | 1145 | [1126, 1166] |

The top-three intervals still overlap. The 3.6 interval does not reach
the gemma4 pair. That is the ranking this battery can support.

## `window-stamp` — authored, smoked, retired as saturated

Two independently checkable halves (exclusive / overnight window vs
`HHMM\|name` stamp). Intended ~1800.

Smoke n=2: `gemma4:26b` 2/2, `31b` 2/2, `qwen3.8` 2/2, `qwen3.6` 2/2,
`gemma3:27b` **2/2**, `qwen3-vl` 1/2. `gemma3` is 0/54 on E11 and still
aces this. Same failure class as `booking-off-by-one`. Task file is
marked SATURATED. No eight-model field was run.

The half-split itself worked once: vl t1 failed window (kept the
end-bound) and stamp (kept case) independently. The item is just too
easy. "Rewrite a clear docstring over a wrong body" sits below the
whole field. A real ~1800 item still has to be authored.
