# E2 finding — qwen3-vl:30b as a local coding seat (superseded as a comparison)

**Run:** desktop, 2026-08-12, rev `5be7db5`, 18/18 cells, 18/18 traces, both
models 100% GPU at 32768 ctx. **Not UID-verified. No claim registered.**

First post-fix pack (balanced-scan extractor). Ran before the remaining two
harness confounds were found, so it is **superseded as a comparison** by
`e4-sampled/`. Retained for the vision-language result, which still stands.

| Model | L2 pass | median | max |
|---|---:|---:|---:|
| `qwen3-vl:30b` | **9/9** | 56.4s | 78.5s |
| `gemma4:26b` | 8/9 | 6.3s | 20.2s |

## What stands

`qwen3-vl:30b` is a **vision-language** model, and these fixtures are text-only,
so only its text and tool-calling path was exercised. On that path it works: 9/9
with a tool dispatched in every cell and no emission failures.

It fits comfortably — 20 GB at 100% GPU with 32768 context — and its raw decode
is the fastest measured on this host at **138.7 tok/s**. But per-task latency is
poor: 56.4s median against `gemma4:26b`'s 6.3s. Fast decode did not translate
into fast completion, which the traces attribute to reasoning tokens. Viable for
delegated work, poor for interactive.

## Why it is superseded

Two confounds were still live when this ran, both found afterwards:

1. The strict-JSON system prompt was gated on `"26b" in model`, so `gemma4:26b`
   received an instruction `qwen3-vl:30b` did not.
2. No sampling or context control — each model used its own Modelfile defaults.

The single `gemma4:26b` failure here was a loop-guard repeat, which
`e3-controlled` later showed is strongly temperature-dependent.

Cite `e4-sampled/` for cross-model comparison. This pack is the record of the
VLM result and of the first run under the fixed extractor.
