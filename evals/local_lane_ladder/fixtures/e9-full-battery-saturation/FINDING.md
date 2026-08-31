# The entire E9 battery is now saturated for the current roster -- including its own ceiling marker and best discriminator

**Type:** synthesis finding. No new trials were run for this write-up; it
pulls together numbers already collected and committed this session
(`e9-pi-rerun`, `gptoss-120b-e9`, `gemma26-csv-n100-baseline`,
`qwen38-csv-n30-spotcheck`) and cross-references them against the
per-fixture difficulty ratings recorded in each task YAML's header comment
(`operator-control-plane` commit `d9e3bd4`, from the earlier e9+e11 corpus).

**Question:** BOTTLENECKS.md has repeatedly flagged "the ceiling effect...
harder task design remains open" as this program's standing bottleneck,
but always as an assertion, never quantified against the battery's own
original calibration. How saturated is E9, precisely, for the five models
now in the active roster (`gemma4:26b`, `gemma4:31b`, `qwen3.6:35b`,
`qwen3.8:27b`, `gpt-oss:120b`)?

## The numbers

| task | original rating (e9+e11 corpus, n=18/model) | current 5-model roster |
|---|---:|---:|
| booking-off-by-one | SATURATED, 42/42 (~615 Elo) -- already known non-discriminating | 30/30 |
| ambiguous-anchor | **BEST DISCRIMINATOR**, 63/126 (50%, ~1511 Elo) | **30/30** |
| strict-log-format | GOOD, 51/126 (40%, ~1598 Elo) | 29/30 (gemma4:26b 5/6, rest 6/6) |
| constant-and-callers | MILD, 36/42 (86%) | 30/30 |
| csv-summarize-repair | **CEILING MARKER**, 5/126 (4%, ~1994 Elo -- ~180 pts above the strongest model then tested) | gemma4:26b confirmed **75/100** true rate (n=100); all other four models 6/6 (n=6) / **30/30** (qwen3.8:27b, n=30) |

Task files are byte-identical between the original rating and today (checked
via `git diff` across every commit that touched each YAML) -- this is the
same fixture, not a re-authored one, so the comparison is apples-to-apples.

## The headline: it isn't just the ceiling marker

The obvious framing would be "the ceiling marker is stale, replace it." That
undersells it. **`ambiguous-anchor` -- the fixture that historically
discriminated *best*, splitting the field almost exactly in half (50%) --
is now 30/30 (100%) across every model in the current roster.** A task
whose entire value proposition was "genuine capability spread inside the
field's range" now produces zero spread on this roster. `strict-log-format`
(historically 40%) is effectively there too, missing by a single cell.

`csv-summarize-repair`'s recalibration is the most dramatic in absolute
terms -- a task calibrated at ~180 Elo above the strongest model tested
in the e9+e11 corpus, solved only 5 times in 126 attempts by any model
(and only ever by one specific model, `qwen3.6:27b`), is now solved by
**all five current-roster models**, including a confirmed 75% true rate
by the weakest of them at n=100 (not just a lucky n=6 sample -- see
`gemma26-csv-n100-baseline/FINDING.md`) and a confirmed ≥90%-at-95%-
confidence true rate by `qwen3.8:27b` at n=30 (`qwen38-csv-n30-spotcheck/FINDING.md`).

Of the five original E9 fixtures, only `booking-off-by-one` and
`constant-and-callers` were already flagged as non-discriminating before
this session (SATURATED / MILD respectively) -- so this isn't new
information for those two. What's new is that the other three, including
the two rated highest (BEST DISCRIMINATOR and CEILING MARKER), have joined
them. **All five E9 fixtures are now saturated or effectively saturated
for this roster.** The battery, as constituted, has no remaining
discriminating power for the models Erik is actually comparing.

## Interpretation

This is not evidence that E9's fixtures were badly designed -- they did
real work at the time, distinguishing a `gemma3:27b` (0/30 in the original
corpus) from a `gemma4:26b` (18/30). It's evidence that the specific models
now in rotation (`gemma4:26b/31b`, `qwen3.6:35b`, `qwen3.8:27b`,
`gpt-oss:120b`) sit meaningfully above the field E9 was calibrated against
-- a real, measured capability jump, not a harness artifact (the harness
itself was independently hardened this cycle: `pi`-migration, `OPR-RUL-008`
continuation fix, cross-GPU auto-split fix). The E9 numbers reported
throughout this session (28-30/30 for every model) have been read
correctly as "this battery no longer discriminates" every time they came
up; this finding is the first time that reading has been checked against
the battery's own original calibration numbers rather than asserted from
this session's data alone, and it holds up -- more starkly than assumed.

**Consequence:** designing a genuinely harder E9 successor is not a nice-
to-have next step, it is the only way to get comparative signal on this
roster at all. A first candidate stacked-trap fixture
(`ledger-strict-reconciliation`, drafted the same day, screening in
progress) is a direct attempt at this -- see its own FINDING.md once
screened for whether it actually restores discrimination.

## Housekeeping

Each of the five task YAMLs' header comments (measured resolving power,
from `d9e3bd4`) has been left in place as the historical record of what
the e9+e11 corpus showed -- that measurement is still true of that corpus.
A one-line pointer to this file has been added to each header so a future
reader doesn't take the historical rating as current.

## Limits

- This is a synthesis of existing data, not a new controlled run. The
  "current roster" is five specific models; a sixth model could in
  principle still fail one of these fixtures (though nothing in this
  session's evidence suggests that's likely for anything resembling the
  current generation of 26B+ local models).
- `strict-log-format`'s 29/30 (not 30/30) is gemma4:26b's one miss, already
  characterized elsewhere this session as consistent with its own
  documented failure modes, not new information here.
