# gemma4:26b x csv-summarize-repair — n=100 noise-floor baseline

**Run:** desktop, 2026-08-30, same meter as every other cell this session
(`num_ctx` 16384, `temperature` 0.8, `think` off, dispatched via `pi`,
default prompt, full VRAM). n=100, single task, single model -- a
deliberate departure from this session's usual n=6 to establish a real
noise floor for the single most-contested cell in the whole session.

**Why this cell:** across tonight alone it produced three different-looking
n=6 results that were each treated as informative: the original baseline
(5/6), the brevity-ablation treatment (6/6), and the 12GB-VRAM-cap treatment
(6/6). Two of those were read as "no accuracy cost" / "clean fix." This run
asks: what is the *true* rate this cell converges to, and were those n=6
reads actually distinguishable from chance?

## Result: true pass rate is 75%, not 83-100%

| metric | value |
|---|---|
| pass rate | **75/100 (75.0%)** |
| 95% CI (normal approx.) | **[66.5%, 83.5%]** |
| completion_tokens | mean 5638, median 5497, stdev 1559, range 1502-10039 |
| n_calls (turns) | mean 6.4, median 6.0, range 2-21 |
| wall_clock_s | mean 52.9, median 51.9, range 17.2-98.0 |

All 25 failures decompose into exactly the same two modes seen in every
smaller sample this session -- no new failure mode appeared at 4x the
previous largest n:

| failure mode | count |
|---|---:|
| quoted-CSV-comma parse bug (naive `split(",")`) | 14 |
| scope-creep (created an out-of-scope file) | 11 |

## This changes how tonight's two "positive" findings should be read

Neither the brevity-ablation nor the VRAM-cap-ablation result is wrong, but
both were read with more confidence than the evidence actually supported,
because the *implicit* comparison point (a near-100% baseline) was itself
wrong.

**P(6/6 by chance alone, if the true rate for a condition is 75%) = 17.8%.**
P(>=5/6) = 53.4% -- meaning the *original* n=6 baseline's 5/6 was in fact the
single most probable outcome at this true rate, not an unlucky miss.

This means:
- **`gemma26-brevity-ablation-001`'s pass-rate claim** (5/6 -> 6/6 on this
  exact cell) is **not distinguishable from chance** at n=6 against a 75%
  true baseline. Its real, robust evidence was never the pass rate -- it was
  the continuous token-count reduction (4730 -> 2391 mean, a large effect
  size that n=6 has real power to detect on a continuous measure, unlike a
  binary one). That finding stands. The "no correctness cost" framing should
  be read as "not additionally verified to distinguish from baseline noise,"
  not "proven equal."
- **`gemma26-12gb-cap-e9`'s pass-rate claim** (28/30 -> 30/30 across the
  *full* 5-task battery, of which this task contributed 6/6) has the same
  problem for its `csv-summarize-repair` component specifically. The
  cross-task aggregate (30/30) is somewhat more informative than a single
  task's 6/6 alone, but the same caution applies: a few-cell swing in a
  30-cell battery, on a model with a demonstrated 75% floor on at least one
  of its five tasks, is not strong evidence of an accuracy *improvement*.
  The finding's own Limits section already flagged this ("consistent with
  'no accuracy cost,' not proof of a gain") -- this run confirms that caveat
  was necessary, not just defensive hedging.

**Neither finding is refuted.** Both remain plausible and are not contradicted
by this data. What changes is the confidence level: "no accuracy cost" was
being treated as a settled read where it should have been treated as
"consistent with, but underpowered to confirm."

## What would actually settle it

A matched n=100 (or at least n>=30) of the *treatment* conditions
(brevity-instructed and 12GB-capped) on this exact cell, compared against
this same n=100 baseline via a proper two-proportion test. Not done here --
this run only nails down the baseline side of the comparison.

## Limits

- Single cell (one model, one task, default full-VRAM, default prompt).
  Says nothing about whether other tasks or models have similarly wide gaps
  between their true rate and what an n=6 sample would suggest -- plausible
  given how bimodal-and-stable this cell's own two failure modes are, but
  unverified elsewhere.
- 75% with a [66.5%, 83.5%] CI is itself not a tiny-uncertainty number --
  n=100 narrows things a lot versus n=6, but a wider run (n=300+) would
  still meaningfully tighten this further if the exact rate mattered for a
  future decision.
