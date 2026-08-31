# qwen3.8:27b x csv-summarize-repair — n=30 spot-check (does the n=100 surprise generalize?)

**Run:** desktop, 2026-08-30, same meter and same exact task as
`gemma26-csv-n100-baseline` (`num_ctx` 16384, `temperature` 0.8, `think`
off, dispatched via `pi`, default prompt, full VRAM). n=30 -- "Reportable"
tier per `GOLD_STANDARD.md` #2a, not the full n=100 rate-estimate tier, but
enough to detect a meaningfully-below-100% true rate if one exists.

**Question:** the night before, `gemma26-csv-n100-baseline` found gemma4:26b's
true pass rate on this exact task is only 75% (95% CI [66.5%, 83.5%]), despite
looking clean (5/6, 6/6, 6/6) across three separate n=6 samples. qwen3.8:27b
went 30/30 clean across the *entire* E9 battery (all 5 tasks) when it was
originally run. Does that clean number also hide a lower true rate, the way
gemma4:26b's did -- or is qwen3.8:27b genuinely more reliable on this task?

## Result: clean at n=30, genuinely different from gemma4:26b

| model | task | true rate finding |
|---|---|---|
| gemma4:26b | csv-summarize-repair (n=100) | **75%** [66.5%, 83.5%] |
| **qwen3.8:27b** | csv-summarize-repair (n=30) | **30/30** -- true rate >= ~90% at ~95% confidence (rule-of-three bound for a zero-failure sample) |

| metric | value |
|---|---|
| completion_tokens | mean 1403, median 1106, stdev 1074, range 646-6493 |
| n_calls (turns) | mean 4.7, range 4-8 |
| wall_clock_s | mean 28.7, range 16.9-105.3 |

Zero failures in 30 independent draws. The rule-of-three bound (1 - 3/n for
a 0-failure binomial sample) puts the true rate at or above ~90% with ~95%
confidence -- meaningfully higher than gemma4:26b's 75% point estimate, and
the two intervals do not overlap in the region that matters ([90%, 100%]
for qwen3.8:27b vs [66.5%, 83.5%] for gemma4:26b).

**This does not fully replicate to n=100 rigor** -- a true rate of, say, 88%
would still be consistent with 30/30 by chance (`0.88^30 ~= 2.2%`, rare but
not impossible), so this is not as airtight as the gemma4:26b comparison.
But it is strong enough evidence to answer the actual question: the n=100
surprise does **not** trivially generalize to every model. qwen3.8:27b's
clean E9 number on this task looks like a real reflection of high
reliability, not an artifact of small-n luck the way gemma4:26b's was.

## One qualifier: real per-trial variance exists, just not correctness variance

Token counts ranged from 646 to 6493 (one clear outlier against a median of
1106) -- qwen3.8:27b is not perfectly uniform in *how* it solves the task
from run to run, only in *whether* it solves it correctly. This matters:
the reliability finding here is specific to correctness, not to a claim
that this model behaves identically every time.

## Interpretation

`csv-summarize-repair`'s known trap (naive `line.split(',')` on a quoted,
comma-containing amount) is a genuine capability discriminator between
these two models on this exact task -- gemma4:26b misses it roughly 1 in 4
times, qwen3.8:27b appears to miss it rarely if at all. This is a real,
model-specific correctness difference the original E9 battery's n=6 could
not have resolved for either model, and it took deliberately raising n on
both sides of the comparison to see it clearly.

**Practical consequence for the sample-size policy (`GOLD_STANDARD.md` #2a):**
"was this model's clean E9 number a fluke" is not a question with the same
answer for every model. A model this reliable does not need n=100 to trust
its pass rate; a model with gemma4:26b's specific bimodal-failure profile
does. The policy's guidance to reserve n=100 for "the most-contested,
most-cited cell" rather than applying it blanket is validated here -- this
n=30 spot-check was the right-sized tool for this specific question.

## Limits

- Single task, single model comparison point. Does not establish whether
  qwen3.8:27b holds up this well on its *other* four E9 tasks, or whether
  other models in the roster (qwen3.6:35b, gpt-oss:120b, qwen3-next) have
  their own hidden gemma4:26b-style gaps on tasks they've only been run at
  n=6.
- n=30, not n=100 -- the confidence bound here (>=~90%) is real but looser
  than gemma4:26b's tightly-bracketed 75% [66.5%,83.5%]. A true rate in the
  low-to-mid 90s cannot be fully ruled out as "actually lower than it looks"
  with this sample alone.
