# gemma4:26b brevity instruction — 2x2 ablation vs qwen3.8:27b control

**Run:** desktop, 2026-08-28/29, `csv-summarize-repair` L2, same meter as
`e9-pi-rerun` (`num_ctx` 16384, `temperature` 0.8, `think` off, dispatched
via `pi`). n=6 per cell. Default-prompt cells are the existing `e9-pi-rerun`
trials (not re-run); only the two `+brevity` cells are new.

**Question:** the wall-clock gap between gemma4:26b (137.3 tok/s decode, but
slow on task completion) and qwen3.8:27b (77.5 tok/s decode, but fast on task
completion) traced to gemma4:26b generating ~5x more tokens per task, not to
raw decode speed. Is that verbosity a fixable default-prompt artifact, or a
structural property of the model that survives explicit steering?

**Brevity addendum** (appended to the standard L2 prompt for the treatment
cells only):

> Be terse. Do not narrate what you are about to do or restate the task back.
> Do not explain your reasoning in prose. Make the edit, run the verification
> command once, and stop as soon as it passes. No summary at the end.

## Result

| cell | completion tokens (mean, range) | turns (mean, range) | wall_clock_s (mean) | passed |
|---|---|---|---:|---|
| gemma4:26b, default | 4730 (2982-7692) | 6.8 (5-12) | 47.7 | 5/6 |
| **gemma4:26b, +brevity** | **2391 (1127-5361)** | **4.3 (4-5)** | **25.5** | **6/6** |
| qwen3.8:27b, default (control) | 902 (716-1473) | 4.3 (4-5) | 24.0 | 6/6 |
| qwen3.8:27b, +brevity (control) | 900 (533-1352) | 4.7 (4-6) | 31.3* | 6/6 |

*one 81.9s outlier trial in this cell; excluding it the mean is 21.2s,
essentially flat against the 24.0s baseline.

## Finding — fixable by asking, not structural

A single added instruction roughly **halved** gemma4:26b's token consumption
(4730 -> 2391, -49%) and cut its mean wall-clock time by **~47%**
(47.7s -> 25.5s), with correctness not worse (5/6 -> 6/6, small-n). The
qwen3.8:27b control barely moved (902 -> 900 tokens), which is the load-bearing
part of this result: it rules out "adding any extra instruction text shrinks
any model's output" as the explanation. The effect is specific to gemma4:26b's
default behavior.

With brevity instructed, gemma4:26b's mean wall-clock (25.5s) lands almost
exactly on qwen3.8:27b's own *default* baseline (24.0s) — the wall-clock gap
between these two models on this task nearly disappears once gemma4:26b is
told what "done" looks like.

## Why n=1 looked ambiguous first

A single pilot run (not part of this n=6 set) measured 9 turns / 3056 tokens
under the brevity prompt — inside gemma4:26b's own *default*-prompt spread
(5-12 turns, 2982-7692 tokens) and therefore uninterpretable on its own. The
default-prompt baseline is noisy enough (2.6x range on tokens, temperature
0.8, non-deterministic) that no single-trial comparison can distinguish a real
effect from ordinary variance — hence the n=6 factorial design.

## What this changes

E9 and Alignerr wall-clock numbers measure **default-prompt** behavior under
one fixed generic coding-agent system prompt, not **achievable-with-minimal-
steering** behavior. For qwen3.8:27b those are close to the same thing; for
gemma4:26b they are not. Any future ranking that treats gemma4:26b's default
verbosity as an inherent capability limit (rather than a steerable default)
should be read with this in mind.

## Limits

- Single task (`csv-summarize-repair`), single brevity wording, one model
  pair. Not yet checked against `strict-log-format` or the other three E9
  fixtures, or against gemma4:31b (the actually-slow-for-architectural-
  reasons model from the same session's dense/full-MHA finding).
- n=6 per cell; the qwen3.8:27b +brevity cell's wall-clock mean is sensitive
  to one 81.9s outlier trial (see above) -- read that cell's wall-clock number
  as noisy, not the token-count number, which is stable.
- Pass-rate changes (5/6 -> 6/6) are consistent with "not worse," not
  evidence of an accuracy improvement; n=6 cannot support that claim.
- No Fisher's-exact or other significance test was run on the pass-rate
  counts; both are near-ceiling (5/6, 6/6) and not distinguishable at this n.

Raw per-trial records: `traces/csv-summarize-repair-brevity__L2__*__t*.json`
(all twelve present). The first attempt at this ablation died mid-way after
six trials, from an unrelated shell-pipe SIGPIPE (piping the run through
`head -20` truncated stdout and killed the process upstream, exit code
misreported as 0 since it reflected `head`'s own status) -- the remaining six
trials were completed in a second, unpiped run. No consolidated JSON was
produced by either run; the traces directory is the complete record.
