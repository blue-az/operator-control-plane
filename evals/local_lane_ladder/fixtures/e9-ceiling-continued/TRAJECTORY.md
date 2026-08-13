# E9 trajectory scoring — the Alignerr trust axis, made operational

Scored retroactively over E9's 210 retained traces. No re-run: the runner has
been capturing structured trajectories since Phase 1, so the data was already on
disk. **The deterministic postcondition remains the sole gate** — nothing here
passes or fails a cell.

## Scores

| Model | Pass | Mean trajectory | Passed w/ clean process | Passed w/ flawed process |
|---|---:|---:|---:|---:|
| `gemma4:26b` | 24/30 | **0.86** | 17 | 7 |
| `gemma4:31b` | 24/30 | 0.82 | 12 | 12 |
| `qwen3.6:27b` | 19/30 | 0.84 | 12 | 7 |
| `qwen3-vl:30b` | 16/30 | 0.83 | 10 | 6 |
| `qwen3:32b` | 13/30 | 0.81 | 4 | 9 |
| `qwen2.5-coder:14b` | 14/30 | 0.72 | 3 | 11 |
| `gemma3:27b` | 12/30 | 0.72 | 6 | 6 |

## The headline is a negative result

**A clean trajectory barely predicts passing:**

- perfect trajectory → **60%** pass (64/107)
- flawed trajectory → **56%** pass (58/103)

Four points, at these sample sizes, is noise. The transferred Alignerr rubric
does **not** predict deterministic success on these fixtures.

That is worth stating plainly rather than dressing up, and it is not a failure of
the transfer — it is what the source rubric says should happen.
`Labeling_Instructions.pdf` §6 names *"Confusing Process with Outcome"* as a
common mistake, and rules that *"process efficiency is a tiebreaker, not the
primary criterion"*, with the three-line summary `Correctness > Efficiency` and
`Final Code > Process`. A process score that predicted outcome would collapse the
two axes the gold standard deliberately keeps apart.

So the trajectory score earns its place as a **tiebreaker and a diagnostic**, not
as a second opinion on correctness. Its use is exactly the `gemma4:26b` vs
`gemma4:31b` case below, where the deterministic result is a dead tie.

## Where it does its work: breaking the 24/30 tie

`gemma4:26b` and `gemma4:31b` are tied on the postcondition, both perfectly
stable. The process column separates them:

| | `gemma4:26b` | `gemma4:31b` |
|---|---:|---:|
| Mean trajectory | **0.86** | 0.82 |
| Passes reached cleanly | **17/24** | 12/24 |
| Passes reached with a flawed process | 7 | **12** |

Half of `gemma4:31b`'s successes came via a blind patch, a skipped source, or a
repeat. It arrives at the right answer by a less reproducible route. Combined
with being 1.5x slower, this strengthens the `gemma4:26b` seat pick — and it is
the one place in 210 cells where a deterministic tie is broken by evidence rather
than by preference.

`qwen2.5-coder:14b` is the inverse: 3 of its 14 passes were clean. It is the
fastest model in the field and the least careful.

## Rule violations across all 210 cells

| Rule | Violations | Alignerr source |
|---|---:|---|
| `no_blind_repeat` | 61 | "explicitly name the rejected candidates" |
| `all_sources_read` | 41 | "the correct answer must require at least two PDFs" |
| `read_before_write` | 39 | "do not use PDF text search as the source of truth" |
| `min_steps` | 19 | "use at least three steps" |
| `single_action_steps` | 13 | "each step describes exactly one action" |

Repetition dominates again, agreeing with the independent failure-mode
classification in `FINDING.md` (32 of 88 failures were loop-guard stops). Two
separate instruments pointing at the same behaviour is the strongest signal in
this pack: **the binding constraint on local agentic work here is not knowledge,
it is failure to advance state.**

`read_before_write` at 39 is the second story — blind patching is common, and it
is the specific behaviour Batch 5's anti-anchoring rule exists to prevent.

## Failure taxonomy

| Class | Count |
|---|---:|
| `MODEL_FAILURE` | 75 |
| `HARNESS_PROTOCOL` | 13 |
| `INFRA` / `TIMEOUT` / `SERVING_INCOMPATIBLE` | 0 |

**Zero infrastructure failures in 210 cells**, so no part of the E9 ranking is
contaminated by the harness being unavailable. The 13 `HARNESS_PROTOCOL` cells
are emissions that never dispatched — still not the model's answer being wrong,
and correctly held apart from `MODEL_FAILURE`.

### A classifier bug worth cataloguing

The first version of this taxonomy reported **19 INFRA failures**. They were all
`ambiguous-anchor` cells, and they were not infrastructure at all: the classifier
matched the substring `"connection"` against the *grader's detail*, and that
detail quotes fixture content — the runbook in that fixture says *"Drain
connections."*

This is the second substring-matching false positive introduced in this session,
after `task_lint`'s ban-list matching `etc` inside `src/fetcher.py`. Both would
have produced confident, wrong findings.

The fix is structural rather than a better pattern: **infrastructure evidence is
read from the harness's own stdout, never from grader text.** A grader's detail
describes the postcondition, and postcondition text quotes fixtures, so it can
never be a safe source of infrastructure signal. Regression test:
`tests/test_trajectory_score.py::test_infra_is_read_from_stdout_not_from_grader_detail`.

Filed here per the Alignerr failure-catalog rule that the catalogue records *the
harness's own* mistakes, not the thing under test.

## Limits

The rubric is a partial transfer. `min_steps` and `single_action_steps` are weak
locally because opr dispatches one tool per call by construction, so they can
only fail in degenerate ways. The genuinely load-bearing rules are
`read_before_write`, `all_sources_read` and `no_blind_repeat`. Rules that cannot
apply to a task score as not-applicable rather than as violations, so a
single-file fixture never penalises a model for the author's choice.
