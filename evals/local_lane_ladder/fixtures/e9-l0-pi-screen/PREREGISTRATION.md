# Pre-registration — L0 screen under `pi`

> ## AMENDMENT 2026-09-02 — protocol changed after 4 cells, for feasibility
>
> **The 120-cell screen below was stopped after 4 cells and replaced with a
> focused probe.** Recording this as an amendment rather than editing the
> plan, because silently re-scoping a pre-registration defeats its purpose.
>
> **Reason (feasibility, not result-chasing):** mean cell time was **599s**
> against an estimated ~60s. 3 of the first 4 cells hit the 600s timeout.
> Projected runtime **20 hours**, a 10x overshoot, and most cells would have
> produced timeouts rather than pass/fail measurements.
>
> **What the 4 cells showed** (gemma4:26b x ambiguous-anchor, all failed):
> 6, 56, 72 and 57 tool calls against **6-10 at L1** — a tenfold explosion —
> using only `bash` and `read`. **It never called an edit tool.** L0 does not
> produce wrong answers here; it produces unbounded exploration that never
> commits to an action. That is an exploration-budget floor, mechanically
> distinct from the capability floor `q38-shape` implied.
>
> **Replacement probe:** the other three models on `ambiguous-anchor` at L0,
> n=3 each (9 cells, ~1.5h). It answers the single question the full screen
> was funding: **is the explosion universal, or gemma4:26b-specific?** If
> gemma4:31b and gpt-oss:120b complete L0 where gemma4:26b cannot, that is a
> harder discriminator than the 53%-vs-100% already confirmed at L1.
>
> **What this amendment costs:** the confirmation rule below (2 extreme + 3
> random at n=30) is void — there is no 20-cell screen to select from. No
> n=30 confirmation is claimed for L0. Anything from the probe is **n=3,
> Screen tier**, targeting only, and cannot support a rate. The random-arm
> protection against selection bias is therefore *not* in force for L0; any
> follow-up must re-establish it.
>
> The original plan is preserved below unchanged.

**Written and committed BEFORE any results existed.** Check the commit
timestamp against `run.log`'s first PASS/FAIL line. The point of writing it
first is that the confirmation rule cannot then be chosen to suit whatever
the screen happens to show.

## Why this exists

`e9-l1-pi-screen` screened 20 cells, sent the two most extreme to n=30, and
one regressed from 2/6 to 27/30. That regression was **unfalsifiable**: only
the tails were re-run, so there was no way to tell selection artifact from
real effect. Fixing that requires committing to the confirmation set in
advance. See `GOLD_STANDARD.md` §2a, "Selection bias in screen-then-confirm".

## The question

Does E9 discriminate at **L0** under `pi`? L0 has never been run on this
harness. The only evidence that it is a floor is `q38-shape` (opr-era, n=6,
both models under 12%) — and that pack was retired on 2026-09-02 when its
central claim failed to replicate under `pi`. So "L0 is a floor" is an
untested claim of exactly the kind that has already dissolved once.

## Run

4 models x 5 tasks x n=6 = 120 cells, L0, `num_ctx` 16384, `temperature`
0.8, `think` off. `qwen3.6:35b` excluded (cross-GPU CUDA crash on the shared
daemon; needs the isolated single-GPU daemon).

## Confirmation rule — fixed in advance

After the screen, run **n=30 on five cells**:

1. **The 2 most extreme cells** (lowest pass rate; ties broken by lowest
   trial index). These are the winner's-curse candidates.
2. **3 cells chosen at random** from the remaining 18, drawn with
   `python3 -c "import random; random.seed(20260902); ..."` — seed fixed
   here so the draw is reproducible and cannot be re-rolled.

**Why the random three:** they make regression *measurable*. If the extremes
regress and the random cells do not, that is selection. If both regress,
something is wrong with the screen conditions themselves. If neither
regresses, the screen was sound. Without the random arm, none of those
three can be distinguished — which is precisely what went wrong yesterday.

## Interpretation, also fixed in advance

- **L0 discriminates broadly** (spread across several tasks, surviving
  confirmation) → L0 is the working rung; this is the instrument.
- **L0 is a floor** (most cells at or near 0/6) → the ladder is fully
  characterized: L0 floor / L1 one confirmed cell / L2 ceiling. Harder task
  design becomes the only remaining path, and `ledger-strict-reconciliation`
  is the existing candidate.
- **L0 looks like L1** (one or two discriminating cells) → the rung matters
  less than the task; `csv-summarize-repair` is the discriminator and the
  others are saturated at every level.

## Binding constraints

- No pass-rate from the n=6 screen is reportable (§2a). Screen numbers are
  **targeting only** and must not be quoted as rates in any write-up.
- A cell with 0 tool calls or 0 completion tokens is **INVALID**, not a
  score of 0. Check `trajectory.no_dispatch` and `completion_tokens` before
  scoring any zero. gemma4:26b has a documented intermittent no-dispatch
  stall (2/30 at L1, 2/6 in `ledger-strict-screen`).
- Any `qwen3.6:35b` number remains out of scope until the isolated daemon
  run happens.
