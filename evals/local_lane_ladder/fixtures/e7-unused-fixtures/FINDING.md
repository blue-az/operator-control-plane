# E7 finding — the ladder is exhausted at the top; and qwen3-vl:30b disobeys --think off

**Run:** desktop, 2026-08-13, rev `118fdca`, 126/126 cells, 126/126 traces, zero
CPU spill, n=6, `num_ctx 16384 · temperature 0.8 · think off`.
**Not UID-verified. No claim registered.**

Phase 0 of the ceiling-battery plan: run the three fixtures that were written but
never executed in any pack, before building anything new.

## Result — a perfect sweep

| Model | Total | doc-fix | grep-and-report | multi-file-rename | median |
|---|---:|---:|---:|---:|---:|
| `qwen2.5-coder:14b` | 18/18 | 6/6 | 6/6 | 6/6 | 3.0s |
| `gemma4:26b` | 18/18 | 6/6 | 6/6 | 6/6 | 3.0s |
| `qwen3:32b` | 18/18 | 6/6 | 6/6 | 6/6 | 3.7s |
| `qwen3.6:27b` | 18/18 | 6/6 | 6/6 | 6/6 | 3.8s |
| `gemma4:31b` | 18/18 | 6/6 | 6/6 | 6/6 | 4.1s |
| `gemma3:27b` | 18/18 | 6/6 | 6/6 | 6/6 | 4.7s |
| `qwen3-vl:30b` | 18/18 | 6/6 | 6/6 | 6/6 | **16.1s** |

**126 of 126.** Zero discrimination. These three fixtures add nothing above 14B.

## All six ladder fixtures are now confirmed saturated

Combined with `e4-sampled` (62/63 on the original three), every fixture in
`tasks/` is now known to be cleared by every model from 14B to 32B. The
instrument is comprehensively exhausted at the top — this is not "we happened to
pick the three easy ones."

**The most important correction is to `multi-file-rename-reference`.** It was
recorded as the only fixture ever producing per-model *shape* differences
(`gemma4:31b` 3/3 at every level; `qwen2.5-coder:32b` needed L1; `gemma4:26b`
needed full L2; `llama3.1:8b` 0/9). It scores 6/6 for everyone here.

That historical spread was measured on the original 216-cell grid, which ran under
the **confounded harness** — greedy brace-span tool extraction, the system prompt
gated on `"26b" in model`, and no sampling, context or thinking control. Every one
of those defects has since been found and fixed. The apparent capability ladder
was substantially harness artifact. This is the fourth time in this programme a
"model difference" has dissolved under a fixed harness, and it is exactly the
pattern the Alignerr failure catalog exists to record: *the harness's own mistakes,
not the thing under test.*

Consequence for the plan: **Phase 2 has no overlap to avoid.** No capability the
new hard fixtures target is already covered, so all four domains proceed as
designed.

## qwen3-vl:30b ignores `--think off` — confirmed in a graded run

Every cell of this run passed `--think off`. Mean per-cell token accounting:

| Model | mean ctok | mean think_chars |
|---|---:|---:|
| `gemma4:26b` | 51 | 0 |
| `qwen3:32b` | 46 | 0 |
| `qwen3.6:27b` | 51 | 0 |
| **`qwen3-vl:30b`** | **2,648** | **11,407** |

Six of seven models obey. `qwen3-vl:30b` emits **11,407 characters of reasoning
while being told not to**, at **52x** the completion tokens of its peers, which
fully accounts for its 16.1s median against their 3.0–4.7s.

This was first seen as a probe before `e6-think-ab` and the model was excluded
from that A/B on those grounds. It now reproduces in a full graded run, so it is a
property of the model and not of the probe. It independently mirrors LocalClaw's
obedience audit, which found both gpt-oss sizes leaking on 40% and 27% of
suppressed rows — a different family, the same defect class.

**Practical:** `qwen3-vl:30b` cannot be cost-controlled through the `think`
parameter on this stack. Any budget or latency assumption that relies on
suppression is void for this model. It remains accurate (18/18 here, 9/9 in
`e2-postfix-vl`) — it is simply not steerable.

## Limits

Saturation means these numbers rank nothing. The only differentiating signal in
this pack is latency, and the only notable latency result is a disobedience
finding rather than a capability one. `flips` is zero everywhere for the usual
reason: nothing failed.
