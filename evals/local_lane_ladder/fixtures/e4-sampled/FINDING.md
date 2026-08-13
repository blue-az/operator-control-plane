# E4 finding — the L2 fixtures are saturated

**Run:** desktop, 2026-08-13, rev `8f6ccca`, 63/63 cells, 63/63 traces, zero
CPU-spill samples, all seven models 100% GPU at `num_ctx 16384`.
**UID-verified 2026-08-13** by uid 971 (`operator-builder`) on the z13 ledger (`uid_isolated`, enforced). Claims: `claim-0018` (six-pack integrity), `claim-0015` (62/63 totals). Re-derive artifacts: `REDERIVE.md` / `.operator/evidence/front-e1-gold-pack/rederive/e4-sampled.json`.

First epoch with every known variable controlled: uniform context, uniform
system prompt, realistic sampling, fixed extractor.

## Result

| Model | L2 pass | median | mean | max |
|---|---:|---:|---:|---:|
| `qwen2.5-coder:14b` | 9/9 | **2.2s** | 4.5s | 9.9s |
| `gemma3:27b` | 9/9 | 3.4s | 8.0s | 17.8s |
| `gemma4:26b` | 8/9 | 9.1s | 9.6s | 21.9s |
| `gemma4:31b` | 9/9 | 20.3s | 19.4s | 36.6s |
| `qwen3:32b` | 9/9 | 27.3s | 33.9s | 100.5s |
| `qwen3-vl:30b` | 9/9 | 37.1s | 40.2s | 70.1s |
| `qwen3.6:27b` | 9/9 | 41.4s | 49.6s | 154.2s |

**62 of 63 cells passed.** Six of seven models are perfect.

## The headline is that this benchmark is finished

These three fixtures **no longer discriminate between local models**. Every
model in the set, from a 14B to a 32B, clears them. That is the same condition
the router corpus reached (`gemma4:26b` scoring 16/16 on every axis), and it
means the same thing: the instrument has no resolving power left, so it cannot
rank seats and must not be cited as if it can.

The single failure is genuine and worth keeping as a specimen.
`gemma4:26b` on `alias-add` read `bash/.bash_aliases` correctly, then issued
`patch_file` against `.bash_aliases` — dropping the directory prefix. The tool
ran and returned `File not found`, so it failed loudly rather than silently.
That is a real path-tracking error, correctly graded, and it is the *only*
model-attributable failure in 63 cells.

## What the numbers actually decide

Correctness is a tie, so the seat decision is a **latency** decision:

- `qwen2.5-coder:14b` (2.2s) and `gemma3:27b` (3.4s) are an order of magnitude
  faster than the large models and just as correct **on tasks this size**.
- `qwen3.6:27b` (41.4s median, 154.2s worst) and `qwen3-vl:30b` (37.1s) pay a
  large latency premium for accuracy they do not demonstrably have here.
- `qwen3:32b` is usable fully GPU-resident at `num_ctx` ≤ 24576, but only
  reaches parity, not advantage.

Any claim that a bigger model is *better* for local-lane work needs a fixture
these models can actually fail. This set is not it.

## Three harness defects had to be fixed to reach this table

Every one of them silently biased earlier results:

1. **Greedy brace-span extraction** (`5be7db5`). A `re.search(r"\{.*\}", DOTALL)`
   spanned two objects at once and failed to parse, so a correct tool call was
   returned as prose and nothing dispatched. Confounded 5 of 45 cells across two
   model families.
2. **System prompt gated on the model name** (`8f6ccca`). `"26b" in model` gave
   `gemma4:26b` a strict-JSON instruction none of its comparators received —
   speaking directly to the emission behaviour being graded.
3. **No sampling or context control at all** (`017d672`). Context came from each
   model's Modelfile, so it differed per model *and* pushed `qwen3:32b` into CPU
   spill at its 32768 default.

## Temperature 0 is not a neutral control (see e3-controlled)

The preceding epoch pinned `temperature 0` for reproducibility and produced
`gemma4:26b` 6/9, with all three failures being the repeat-guard. Direct test:

| Setting | `gemma4:26b` × `alias-add` |
|---|---|
| temperature 0 | **1/6** |
| temperature 0.8 | **6/6** |

Greedy decoding locks an agentic loop into re-issuing an identical call, which
the repeat-guard then stops. Temperature 0 buys reproducibility by introducing a
failure mode that does not occur in real use. `e3-controlled` is retained as the
record of that artifact, **not** as a model comparison.

## Reproducibility is not currently achievable

`seed` is **not reliably honoured** by this Ollama build — the same seed on a
high-entropy prompt produced different outputs on consecutive calls. The
apparent determinism inside a cell comes from the fixtures being low-entropy
(the model is confident about `patch_file` regardless of sampling), not from
seeding working.

Consequence: **n=3 carries less information than it appears to.** Real variance
shows up *across* invocations — `gemma4:26b` on `alias-add` measured 3/3, 3/8,
8/8, 8/8, 6/6 across separate windows today — which points at something varying
at the server or model-load level that none of these controls reach. Closing
that would need many repetitions spread over time, and it is the honest limit of
what three fixtures can support.

## Status of earlier packs

| Pack | Status |
|---|---|
| `e1-gold-pack` | Superseded as a comparison. Valid as the harness-defect record. |
| `e1x-27b` | Superseded as a comparison. Valid as the two-family confound record. |
| `e2-postfix-vl` | Superseded as a comparison. |
| `e3-controlled` | Record of the temperature-0 greedy artifact. Not a comparison. |
| `e4-sampled` | Current. Saturated — read it as "no model fails these", not as a ranking. |

## Next

The useful next step is **not** another model. It is a fixture these models can
fail: multi-file edits, an edit whose anchor appears more than once, a task
requiring state across four or more dependent steps, or a repair loop after a
failing test. Until such a fixture exists, adding models to this matrix produces
more 9/9 rows and no information.
