# ledger-strict-reconciliation screening: real variance, but not the kind expected

**Run:** desktop, 2026-08-30/31, `ledger-strict-reconciliation` (drafted
same day as a candidate E9 successor -- see
`fixtures/e9-full-battery-saturation/FINDING.md`). Initial n=1 screen
across the 5-model current roster, followed by a targeted n=5 recheck on
the one ambiguous result.

**Question:** does this stacked-trap fixture (RFC4180 escaped-quote
parsing, multi-currency symbols, round-half-up rounding, footer-row-skip)
actually restore discrimination where the entire original E9 battery has
now saturated?

## Screen 1 (n=1 each): 3 clean, 1 invalidated, 1 ambiguous

| model | result | note |
|---|---|---|
| gemma4:31b | PASS (129.0s) | |
| qwen3.8:27b | PASS (37.2s) | |
| gpt-oss:120b | PASS (186.9s) | |
| gemma4:26b | FAIL (69.3s) | ambiguous -- see below |
| qwen3.6:35b | FAIL (130.1s) | **invalid, not a capability result** |

**qwen3.6:35b's failure is a reproduction of the known cross-GPU
auto-split CUDA crash** (`CUDA error: an illegal memory access was
encountered`, `Xid 31` class), root-caused 2026-08-28 (BOTTLENECKS.md Front
I) and previously fixed only by running this specific model against an
isolated single-GPU Ollama daemon (`CUDA_VISIBLE_DEVICES=0`,
`GGML_VK_VISIBLE_DEVICES=`). This screen ran against the standard shared
daemon, not that isolated one, so the crash recurred exactly as expected --
0 tool calls, 0 tokens, three auto-retries, all identical CUDA errors. This
is not new information and does not belong in this fixture's rating.
**qwen3.6:35b needs a proper re-screen against the isolated daemon before
it counts here** -- not done in this pass; flagged as a follow-up.

## gemma4:26b's failures: every one is a stall, not a wrong answer

The n=1 screen's failure showed something unusual on inspection: 3 tool
calls total (`ls -R`, read `src/ledger.py`, read `tests/check_ledger.py`),
6464 output tokens entirely inside a `thinking` block that correctly
identified all four traps and ended mid-plan ("...use `edit` to replace the
function body.") -- then the turn ended. No edit was ever attempted. This
is not a wrong fix; it is no fix at all, arrived at only after fully
correct diagnosis.

A targeted n=5 recheck (same task, same settings) reproduced this exact
pattern once more (trial 1 of 5: identical 3-call, no-edit, stall) and
passed cleanly on the other four (trials 2-5, 48.0-116.2s). **Combined
across both runs: 4/6 (67%) pass, 2/6 (33%) fail, and both failures are the
identical stall -- zero wrong-fix failures.** Every trial that got past the
reading phase and attempted an edit (4/4) got the fix completely right on
the first attempt, including all four stacked traps at once.

This is a genuinely different failure mode from anything in
gemma4:26b's characterized profile on the simpler `csv-summarize-repair`
task -- the n=100 baseline there decomposed 100% of failures into two known
modes (quoted-CSV parse bugs, scope-creep file creation), zero stalls.
Stacking four traps into one task instead of two appears to push
gemma4:26b into a longer up-front reasoning pass that, roughly a third of
the time, consumes the entire turn before any tool call is emitted --
this looks like the same category of harness-adjacent budget/continuation
issue this session's `OPR-RUL-008` fix and `gemma31-vramcap-e9`'s
near-total-stall finding both describe, not a reasoning-quality limit.

## Interpretation

**This fixture does produce real variance on the current roster -- but not
for the reason it was designed to test.** The goal was harder *logic* to
separate accuracy; what showed up instead is a harder *task* surfacing a
turn-completion/stall risk that the simpler, saturated E9 tasks never
triggered for this model. That is still useful information (a stacked-trap
task is more likely to expose this class of failure than a single-trap
one), but it means this fixture is not yet a clean successor to
`csv-summarize-repair` as a ceiling marker -- it needs either a
continuation/budget fix analogous to `state_changes` (untested: declaring
`state_changes: 2` was not tried this pass) or a larger n to establish
whether 33% is a stable stall rate or noise, before being trusted as a
discriminator.

Three of five current-roster models (`gemma4:31b`, `qwen3.8:27b`,
`gpt-oss:120b`) are clean at n=1 each -- too small a sample to claim they
won't also show gemma4:26b-style stalls or other failures at higher n; the
`csv-summarize-repair` retirement finding is the standing reminder that a
clean n=1-6 sample can hide real structure.

## Next steps (not done this pass)

- Re-screen `qwen3.6:35b` against the isolated single-GPU daemon.
- Run `gemma4:31b`, `qwen3.8:27b`, `gpt-oss:120b` to at least n=6 each to
  check the clean n=1 holds.
- Try `state_changes: 2` on this task to see if it eliminates gemma4:26b's
  stall, which would confirm the harness-budget explanation over a
  genuine capability read.

## Limits

- Total valid data so far: 6 gemma4:26b trials, 1 trial each for the other
  three passing models. Nowhere near enough to rate this fixture's
  difficulty the way the d9e3bd4 annotations rate the original five.
- The "stall" diagnosis (thinking-budget/continuation, not reasoning
  quality) is inferred from trace inspection (correct diagnosis in the
  thinking block, followed by an unexplained stop), not confirmed against
  `pi`'s internals or Ollama's own turn-handling. Worth a direct look if
  this becomes a recurring pattern on future harder fixtures.
