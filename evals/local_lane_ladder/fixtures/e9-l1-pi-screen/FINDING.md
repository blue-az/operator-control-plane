# L1 still discriminates under `pi` — and `q38-shape` retires as an opr-era artifact

**Run:** desktop, 2026-09-02. 4 models x 5 E9 tasks x n=6 = 120 cells, all
at **L1**, `num_ctx` 16384, `temperature` 0.8, `think` off, dispatched via
`pi`. `qwen3.6:35b` excluded (cross-GPU CUDA crash on the shared daemon —
see HANDOFF.md). Screen tier per `GOLD_STANDARD.md` §2a.

**Question:** the 2026-08-31 saturation finding was L2-only. Did the
`opr` → `pi` harness upgrade — which moved gemma4:26b at L2 from 18/30 to
28/30 and flattened the whole roster — also lift L1 into saturation?

## Headline: no. L1 still separates the roster.

| model | L1 | fails | of which no-dispatch stalls |
|---|---:|---:|---:|
| gemma4:31b | **30/30** | 0 | 0 |
| gpt-oss:120b | **30/30** | 0 | 0 |
| qwen3.8:27b | 26/30 | 4 | 0 |
| gemma4:26b | 24/30 | 6 | **2** |

The battery is not exhausted. It was being run at the wrong rung.

## The signal is concentrated in two cells, and they are different models

| task | gemma4:26b | gemma4:31b | gpt-oss:120b | qwen3.8:27b |
|---|---:|---:|---:|---:|
| ambiguous-anchor | 6/6 | 6/6 | 6/6 | 6/6 |
| booking-off-by-one | 6/6 | 6/6 | 6/6 | 6/6 |
| strict-log-format | 5/6 | 6/6 | 6/6 | 6/6 |
| **constant-and-callers** | 5/6 | 6/6 | 6/6 | **2/6** |
| **csv-summarize-repair** | **2/6** | 6/6 | 6/6 | 6/6 |

Three of five tasks are saturated at L1 too. All discrimination lives in
two cells — and crucially, **different models fail different tasks**. That
is capability structure, not one weak model dragging a total. A composite
score would have averaged both into invisibility, which is what L2 did.

**`qwen3.8:27b` on `constant-and-callers` is a clean capability miss.** All
four failures are identical: `no stale value in code: pattern not found:
'up to 5 times'`, at 6-10 tool calls, 576-1361 tokens, zero timeouts. It
consistently updates the constant and misses one caller — precisely what the
task exists to test.

**`gemma4:26b` on `csv-summarize-repair` is mixed**, and must not be read as
four wrong answers: one scope-creep file creation (its documented mode from
`gemma26-csv-n100-baseline`), one wrong output, and **two no-dispatch
stalls**.

## The stall is now a characterized, model-specific failure mode

In both stalled trials gemma4:26b produced a correct plan in its thinking
block, emitted prose announcing the tool call — *"I will start by listing
the files in the repository"* — and the turn ended with `no_dispatch: True`
at 139 and 239 tokens. No tool was ever called.

- **2 of 30 cells for gemma4:26b. 0 of 90 for the other three models.**
- Same 2-in-6 rate observed independently in `ledger-strict-screen`, where
  it diagnosed all four stacked traps correctly and then never edited.
- Intermittent, not systematic: the same model dispatched normally in its
  other trials on this exact task (4, 6, 10 and 12 calls).

**This is a distinct failure class from a wrong answer and RESULTS.md
currently conflates them.** The runner already records `no_dispatch`; it
simply is not surfaced. Whether "narrated the action instead of taking it"
should score as a task failure is a genuine question — failing to act is
failing — but it is not evidence about reasoning quality, and pooling the
two makes gemma4:26b look worse at the task than it is.

## `q38-shape` retires

Its central claim was that `qwen3.8:27b` needs plan-shaped input, resting on
L1 = 7/18 against gemma4:26b's 14/18 (Fisher p = 0.0409).

| | opr-era L1 (`q38-shape`) | pi-era L1 (this run) |
|---|---:|---:|
| gemma4:26b | 14/18 = **78%** | 24/30 = **80%** |
| qwen3.8:27b | 7/18 = **39%** | 26/30 = **87%** |

gemma4:26b is unchanged. `qwen3.8:27b` more than doubled. **The
plan-shaped-input finding does not replicate and was substantially a harness
artifact** — `opr` was suppressing that model specifically, by roughly the
margin that produced the significant p-value. The two harnesses' L1 numbers
are not comparable and `q38-shape` should not be cited as live evidence.

This is the fifth instrument artifact identified in this program in a week,
and the second where a *significant* result dissolved under a better
instrument.

## Consequences

1. **`e9-full-battery-saturation/FINDING.md` is overstated.** Its claim is
   L2-specific. The battery discriminates at L1 on this roster. Amend it.
2. **L1 becomes the working rung** for roster comparison, not L2.
3. **`q38-shape/FINDING.md`** needs an opr-era retirement notice.
4. **Surface `no_dispatch` in RESULTS.md** so stalls are visible rather than
   silently pooled into wrong answers.

## Amendment 2026-09-02 — half of this finding was the winner's curse

Both spread cells were confirmed at n=30. **One survived, one evaporated.**

| cell | screen | n=30 | 95% CI | P(screen \| n=30 rate) |
|---|---:|---:|---|---:|
| qwen3.8:27b x constant-and-callers | 2/6 | **27/30 = 90%** | [79%, 100%] | **0.001** |
| gemma4:26b x csv-summarize-repair | 2/6 | **16/30 = 53%** | [35%, 71%] | 0.284 |

**`qwen3.8:27b`'s deficit was not real.** Its true rate on
`constant-and-callers` is ~90%, statistically indistinguishable from
gemma4:26b's 5/6 on the same task. The screen's 2/6 had a 0.1% chance of
occurring at that rate. Mechanical causes were checked and ruled out: all
six screen trials ran consecutively on a warm model (one switch before the
block, no per-trial churn), failures were not clustered at the start
(F,F,P,F,F,P), decode speed was identical (80.1 vs 81.8 tok/s), and the
failure mode was the same in both runs.

**`gemma4:26b`'s deficit is real.** 53% [35%, 71%] against the other three
models at 6/6 — a CI nowhere near 100%. Failure modes are its documented
ones: 11 wrong outputs, 3 out-of-scope file creations. It is also
consistently worse at L1 (53%) than at L2 (75% at n=100), which is the
coherent direction for reduced scaffolding.

### The methodological error was mine, and it is general

**These two cells were selected for confirmation precisely because they were
the most extreme of twenty.** Extremity partly reflects noise, so
re-measuring only the extremes guarantees regression toward the mean. Across
20 cells, one deviating this far is ~2.5% likely — unlikely, not remarkable.

That makes this finding's original framing wrong. "Different models fail
different tasks — capability structure, not one weak model" was built on two
cells, one of which was noise. **The corrected picture is one model failing
one task**, which is exactly the "one weak model" reading that framing
rejected.

Corrected roster estimate, substituting confirmed rates into the screen:

| model | screen | corrected |
|---|---:|---:|
| gemma4:31b | 30/30 | 30/30 |
| gpt-oss:120b | 30/30 | 30/30 |
| qwen3.8:27b | 26/30 | **~29/30** |
| gemma4:26b | 24/30 | **~25/30** |

Flatter than reported. L1 is closer to saturated than this finding claimed —
it retains exactly one discriminating cell on this roster.

**Standing consequence for the program:** a screen tells you where to look,
but the cells it flags are biased high in extremity by construction.
Confirming only the extremes will show regression every time and cannot
distinguish a real effect from selection. Confirm a random subset alongside
the extremes, or treat screen numbers strictly as targeting rather than as
effect estimates. This is a second, distinct sample-size trap from the one
`GOLD_STANDARD.md` §2a already covers: §2a says a clean n=6 can hide a low
true rate; this says an *extreme* n=6, chosen because it was extreme, will
regress regardless of whether anything is there.

## Limits

- **n=6. Screen tier. No pass rate here is reportable.** A 2/6 is consistent
  with a true rate anywhere from roughly 5% to 65%. The two spread cells are
  queued at n=30, which is where any real claim has to come from.
- Four models, not five. `qwen3.6:35b` is untested at L1 and needs the
  isolated single-GPU daemon before any number from it counts.
- L0 remains untested under `pi`. It was a floor under `opr` (both models
  under 12%), but that measurement carries the same harness caveat this
  finding just established — it may not be a floor here either.
