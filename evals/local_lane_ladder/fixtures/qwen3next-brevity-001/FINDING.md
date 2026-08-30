# qwen3-next brevity ablation — negative result

**Run:** desktop, 2026-08-29, `strict-log-format` L2, same meter as
`gemma26-brevity-ablation-001` (`num_ctx` 16384, `temperature` 0.8, `think`
off, dispatched via `pi`, same brevity addendum text). n=6. Baseline is the
existing `qwenflash-e9` default-prompt data (not re-run).

**Question:** the same session's `gemma26-brevity-ablation-001` found that a
one-sentence brevity/stop-condition instruction roughly halved gemma4:26b's
tokens and wall-clock with no correctness cost, on both a task-generalization
check and a model-generalization check (gemma4:31b). qwen3-next was flagged
as a candidate for the same fix -- its wall-clock (146.6s mean, `qwenflash-e9`)
is far worse than its raw decode speed (70.0 tok/s, 2x gpt-oss:120b's rate)
would predict, driven by extreme per-message verbosity (7-13x gpt-oss:120b's
token counts on matched tasks) rather than excess turns. Does the same
brevity instruction fix it the way it fixed gemma4:26b?

**Brevity addendum** (identical text to `gemma26-brevity-ablation-001`):

> Be terse. Do not narrate what you are about to do or restate the task back.
> Do not explain your reasoning in prose. Make the edit, run the verification
> command once, and stop as soon as it passes. No summary at the end.

## Result: no. It made things worse on every axis.

| cell | completion tokens (mean, range) | wall_clock_s (mean) | passed |
|---|---|---:|---|
| default (`qwenflash-e9`) | 11608 (9914-12997) | 209.4 | 6/6 |
| **+brevity** | **13394 (8740-19613)** | **230.9** | **3/6** |

+15% tokens, +10% wall-clock, and pass rate collapsed from perfect to half.
This is not noise-floor territory -- it is a clear, consistent regression
across the sample.

## Why: the instruction appears to push under-verification, not less talk

The three failures are not the same failure mode, but share a pattern of
incompleteness rather than incorrect-but-complete reasoning:

- **t3**: function returns `[]` -- the core logic never actually ran/matched.
- **t4**: `IndentationError` -- the code does not even parse. A genuine
  syntax slip, not a design mistake.
- **t6**: `raise NotImplementedError` left in the body -- the model appears
  to have stopped before finishing the implementation.

"Make the edit, run the verification command once, and stop as soon as it
passes" was written to stop a model from over-exploring after success (which
is what it did for gemma4:26b). For qwen3-next it instead appears to read as
pressure to rush to a first attempt and declare done, skipping the
verification step's actual diagnostic value -- producing stub, broken, or
unverified code rather than a leaner correct one.

## Why this differs from the gemma4:26b result

`gemma26-brevity-ablation-001` isolated gemma4:26b's problem as **more turns
and more tokens** (6.8 mean turns, wide token range from repeated
exploration). qwen3-next's problem, per this session's own token/turn
breakdown, is **long individual messages at a low turn count** (2.7-4.5 mean
turns on this same task family, but 7-13x gpt-oss:120b's tokens per message).
These are different failure shapes, and a stop-condition instruction tuned
for "stop over-exploring" does not obviously transfer to "stop writing such
long messages" -- if anything, telling a model mid-long-message to hurry up
and finish looks like it produces exactly the rushed, unverified output seen
here.

## Conclusion

The brevity fix from `gemma26-brevity-ablation-001` does not generalize
model-to-model as a blanket "make local models faster" instruction. It fixed
a specific failure shape (over-exploration/restatement) in a specific model
and made a different failure shape (under-verification) worse in a different
model. Any future application of this instruction to a new model should be
screened the same way both of these were -- via a real ablation, not assumed
from precedent.

## Limits

- Single task, single model, n=6 -- a screening-scale negative result, not a
  fully powered one.
- No second brevity wording was tried; a differently-worded instruction
  (e.g., one that doesn't explicitly say "stop as soon as it passes") might
  behave differently. Not tested here.
- Ran with a video playing fullscreen on the same machine/GPU throughout
  (accepted risk, no crash occurred) -- does not affect the correctness of
  the pass/fail or token-count results, which come from the model's own
  output, but is noted for completeness.
