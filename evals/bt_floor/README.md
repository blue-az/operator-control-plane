# BT floor — funnel epochs

The BT local-LLM floor benchmark asks how small a model can recover the Bulkhead
Tau boundary map from a cold read of five repo documents. Its input was never
pinned, and the corpus moved underneath it:

| Epoch | Tokens | Note |
|---|---:|---|
| `july` | 22,689 | pinned to phoenix `c25e8c3d` / operator `79fd91b` — the 2026-07-18 run |
| `current` | 37,002 | today's HEAD; **+63% since July** |
| `capped` | **12,921** | today's HEAD with `BOTTLENECKS.md` truncated at `## Self-Blocked` |

`./build_funnel.sh <epoch>` emits the funnel on stdout. **Record which epoch a run
used.** Results from different epochs are not comparable, exactly as results from
different harness revisions are not.

## Why this exists

The 2026-08-13 rerun found the benchmark had outgrown its own window. The original
run used a 24,576-token context with ~800 tokens spare; the corpus is now 37,002.
Two consequences were measured:

- `granite4` (3.4B) dropped **4/5 → 3/5** with the model, probes and settings
  unchanged. Only the corpus grew. That is the cost of an unpinned input.
- `qwen2.5-14b-24k` — the model that *established* the July floor — silently clamps
  to 16,386 tokens and now sees 44% of the corpus, so it can no longer run the
  benchmark at all.

`BOTTLENECKS.md` is 68% of the funnel and grows monotonically by design. It is the
whole mechanism.

## What `capped` cuts, and the caveat

Everything from `## Self-Blocked` onward — the open-work entries. The probes ask
about boundaries and vocabulary, which live in the header and glossary above that
line. All five answers were verified present after the cut.

**But `capped` is a third condition, not a cheaper `current`.** Two answers survive
with only a single mention each (`Product Behavior Contract`, `Hyperlambda`), where
the fuller funnels repeat them. Cutting redundancy can make a probe *harder* even
when the answer is technically present, so a lower score on `capped` does not by
itself mean a weaker model. Establish a baseline on it before comparing anything to
it.

Its virtue is that it is **bounded**: it does not grow as the open-work board does,
and at 12,921 tokens it fits inside every model tested — including the one that
clamps at 16,386.

## Reference results (2026-08-13, z13, `think=false`)

| Funnel | Model | Params | Score |
|---|---|---:|---:|
| july | `qwen2.5-14b-24k` | 14.8B | 5/5 |
| july | `gemma4:12b` | 11.9B | 5/5 |
| july | `granite4` | 3.4B | 4/5 |
| current | `qwen2.5-14b-24k` | 14.8B | *invalid — saw 44%* |
| current | `gemma4:12b` | 11.9B | 5/5 |
| current | `granite4` | 3.4B | 3/5 |

Full writeup and all 30 verbatim answers: `~/handoffs/BT_FLOOR_ANSWER_2026-08-13.md`
and `bt_floor_2026-08-13_raw.json`.

## Two harness rules this benchmark taught

1. **Set `think=false` explicitly.** With reasoning unset, `gemma4:12b` returned
   zero characters and `done_reason=length` on every probe — scored 0/5, when it
   actually scores 5/5.
2. **Detect truncation by comparing across models, not within one.** A per-model
   calibration pass cannot catch a model that clamps, because its calibration
   clamps too and the self-comparison always passes. Compare each model's token
   count for a funnel against a reference model's count for the same funnel.
