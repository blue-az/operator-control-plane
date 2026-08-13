# E6 finding — thinking is pure tax here, and it drove most of E4's latency spread

**Run:** desktop, 2026-08-13, rev pending, 144/144 cells (72 on + 72 off),
144/144 traces, zero CPU spill, n=6.
**Not UID-verified. No claim registered.**

Thinking mode was the only variable. Everything else identical to `e4-sampled`:
`num_ctx 16384`, `temperature 0.8`, uniform strict-JSON system prompt.

## Result

| Model | think | Pass | Flips | ctok | median | think chars |
|---|---|---:|---:|---:|---:|---:|
| `gemma4:26b` | on | 18/18 | 0 | 353 | 6.8s | 879 |
| `gemma4:26b` | **off** | 18/18 | 0 | **66** | **3.4s** | 0 |
| `gemma4:31b` | on | 18/18 | 0 | 347 | 16.1s | 871 |
| `gemma4:31b` | **off** | 18/18 | 0 | **62** | **4.2s** | 0 |
| `qwen3.6:27b` | on | 18/18 | 0 | 1983 | 37.5s | 7062 |
| `qwen3.6:27b` | **off** | 18/18 | 0 | **61** | **4.0s** | 0 |
| `qwen3:32b` | on | 18/18 | 0 | 1082 | 28.7s | 4438 |
| `qwen3:32b` | **off** | 18/18 | 0 | **55** | **3.5s** | 0 |

Quality is **identical** in every case — 18/18, zero flips, both modes. The cost
difference is not:

| Model | token saving | wall saving |
|---|---:|---:|
| `qwen3.6:27b` | **32.5x** | 9.4x |
| `qwen3:32b` | **19.7x** | 8.2x |
| `gemma4:31b` | 5.6x | 3.8x |
| `gemma4:26b` | 5.3x | 2.0x |

## This overturns E4's practical reading

`e4-sampled` reported a **19x median latency spread** across seven models and
concluded that large models buy latency without accuracy. That conclusion was
substantially an artifact of an uncontrolled variable: those runs had thinking at
each model's default, which is **on** for every thinking-capable model.

With thinking off, the spread among these four collapses to roughly **1.2x**:

```
gemma4:26b 3.4s · qwen3:32b 3.5s · qwen3.6:27b 4.0s · gemma4:31b 4.2s
```

For scale, the two models that were fastest in E4 — `qwen2.5-coder:14b` (2.5s)
and `gemma3:27b` (3.4s) — turn out to have **no thinking mode at all** and so
were never paying the tax. Their apparent speed advantage was largely the
absence of a cost the others were silently carrying.

**`qwen3.6:27b` is the clearest reversal.** E4 measured it at 37.5s median with a
154s worst cell and it read as the most expensive seat in the set. At `think=off`
it is 4.0s and 61 completion tokens — competitive with everything else and 18/18.

## The limit of this result, stated plainly

These fixtures are **saturated** (`e4-sampled`: 62 of 63). Every model passes
whether it reasons or not, so this A/B **cannot detect a quality benefit from
thinking** — there is no headroom in which one could appear. What it establishes
is narrower than it looks:

> On tasks these models already solve, reasoning is pure cost.

It does **not** establish that thinking is useless generally. `LocalClaw`'s
39-row battery (`~/Python/Evaluation/LocalClaw/evals/2026-08-local-model-eval`)
found `gemma4:31b` genuinely **load-bearing** on thinking — 100% with, 97%
without — on a harder 14-task battery. That is entirely consistent with 18/18 in
both modes here; their tasks had headroom and these do not. Any archetype
classification requires a discriminating battery, which `e5-floor` showed this
set is not at these model sizes.

The `flips` metric is likewise uninformative here for the same reason: zero
everywhere, because nothing failed. It needs a battery with failures to measure
stability.

## Two model-configuration facts worth carrying

- **`qwen3-vl:30b` ignores `think=false`.** Asked to suppress reasoning it
  emitted 2,373 characters of it and *more* completion tokens than with thinking
  on (578 vs 271). Excluded from this A/B: an "off" row that is not off measures
  nothing. Independently mirrors LocalClaw's obedience audit, which found gpt-oss
  leaking on 40% (20b) and 27% (120b) of suppressed rows — a different family,
  same defect class.
- **`gemma3:27b` and `qwen2.5-coder:14b` have no thinking mode** — the API errors
  on `think=true`. They cannot be tuned this way and never needed to be.

## Practical

**Set `--think off` for local-lane plan-shaped work.** It costs nothing measurable
in quality on this workload class and returns 5x–32x in tokens and 2x–9x in wall
clock. Revisit per model if a harder fixture ever shows thinking earning its cost
— for `gemma4:31b` there is outside evidence that it does.

Prior packs (`e1` through `e5`) all ran with thinking at model defaults and are
therefore not comparable to any `--think off` run. This is a fifth uncontrolled
variable found and closed, after tool-call extraction, the name-gated system
prompt, context, and sampling.
