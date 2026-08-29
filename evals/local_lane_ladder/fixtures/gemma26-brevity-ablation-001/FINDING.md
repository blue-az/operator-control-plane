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

## Generalization check (2026-08-29)

Two follow-on questions from the Limits section above, both run n=6/cell,
same meter, same brevity wording.

**Does it hold on a more-verbose task?** `strict-log-format` is gemma4:26b's
worst fixture (8065 mean tokens default, up to 13823) -- a bigger baseline
verbosity than `csv-summarize-repair`'s 4730.

| cell | tokens (mean, range) | wall_clock_s (mean) | passed |
|---|---|---:|---|
| gemma4:26b, default | 8065 (5593-13823) | 76.9 | 5/6 |
| **gemma4:26b, +brevity** | **2241 (264-4962)** | **29.8** | 5/6 |
| qwen3.8:27b, default (control) | 793 (672-894) | 23.4 | 6/6 |
| qwen3.8:27b, +brevity (control) | 728 (437-1183) | 23.0 | 6/6 |

**-72% tokens, -61% wall-clock**, pass rate unchanged (5/6 both conditions).
Control moved -8%, within the same noise band as before. Effect is larger
here than on `csv-summarize-repair`, not smaller -- it scales with how
verbose the model's default behavior already is on a given task, which is
what "fixable default, not a floor" predicts.

**Does gemma4:31b have the same fixable component?** `31b`'s slowness was
attributed to its dense/full-MHA architecture (see the same session's decode-
speed finding), but its baseline tokens on `csv-summarize-repair` (3028 mean)
are also elevated versus qwen3.8:27b's ~900 -- a smaller gap than gemma4:26b's
but real. Control is the existing qwen3.8:27b +brevity cell on this same task
(900 tokens, above) -- not re-run.

| cell | tokens (mean, range) | wall_clock_s (mean) | passed |
|---|---|---:|---|
| gemma4:31b, default | 3028 (1770-4192) | 114.2 | 6/6 |
| **gemma4:31b, +brevity** | **1347 (753-3713)** | **57.9** | 6/6 |

**-55% tokens, -49% wall-clock**, perfect pass rate both conditions (one
1002->3713-token outlier trial pulls the +brevity mean up; the other five
land 753-1002). So gemma4:31b's real-world slowness is not purely
architectural -- it has its own smaller verbosity tax, independent of and
stacking on top of the decode-speed disadvantage. Fixing this does not touch
the architecture problem (still no GQA, still no MTP head available for this
model), but it is a real, free, separate win on top of it.

**Conclusion: the effect generalizes across both task and model.** It is not
an artifact of one prompt or one model's quirks.

## Limits

- Two tasks, two models beyond the original pair checked (not the other
  three E9 fixtures, not qwen3.6:35b).
- n=6 per cell throughout; several cells have one outlier trial pulling the
  mean (noted per-cell above) -- read means alongside the printed range, not
  in isolation.
- Pass-rate changes are consistent with "not worse," not evidence of an
  accuracy improvement; n=6 cannot support that stronger claim at any cell.
- No Fisher's-exact or other significance test was run on any pass-rate
  comparison; all cells are near-ceiling and not distinguishable at this n.

Raw per-trial records: `traces/csv-summarize-repair-brevity__L2__*__t*.json`
(all twelve present). The first attempt at this ablation died mid-way after
six trials, from an unrelated shell-pipe SIGPIPE (piping the run through
`head -20` truncated stdout and killed the process upstream, exit code
misreported as 0 since it reflected `head`'s own status) -- the remaining six
trials were completed in a second, unpiped run. No consolidated JSON was
produced by either run; the traces directory is the complete record.
