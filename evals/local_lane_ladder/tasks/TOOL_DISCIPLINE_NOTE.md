# Salvage note — what came out of FLAPPY-ONESHOT-001, and what did not

**Source:** `flappy-oneshot-benchmark` task, `project-phoenix/docs/domain_runs/FLAPPY-ONESHOT-001/`.
Two packs (one-shot Flappy Bird codegen; GSM8K maths), six models, single-trial.

## Not incorporated, and why

| pack | blocker |
|---|---|
| Flappy one-shot | n=1; "Renders" column is a screenshot judgment, not deterministic grading; BN-contaminated by the pack's own admission |
| NLP extraction | ceiling effect — every model 6/6, no discriminative power |
| GSM8K as scored | 10 of 1319 items, n=1, and **it did not measure arithmetic** (below) |

## The GSM8K score was measuring something else

Reported: gemma4:26b 10/10, gemma4:31b 10/10, qwen3.6:35b 10/10,
qwen38-mtp-2 8/10, qwen38-mtp-8 7/10, qwen3.8:27b 7/10.

Failure modes, from the pack's own table: mtp-8's three losses were **all
tool-call attempts** under a plain-text protocol; 27b-stock's three likewise;
mtp-2 lost one to a tool-call attempt and one to a genuine wrong answer.

Strip the tool-call violations and every model is 9–10/10 on the maths — the
same ceiling the NLP task hit. **The apparent discrimination was tool discipline,
not reasoning.**

## What that is worth keeping

Tool-call behaviour discriminated across *both* packs, in opposite directions:

- Qwen 27B configs **dispatched tools when forbidden** (GSM8K)
- `qwen3.6:35b` **could not dispatch one when required** (flappy 0/2 — drifted
  from JSON tool-call format into XML-style mid-generation)
- `gemma4:26b` **emitted code-fenced text instead of calling `write_file`** (flappy)

The ladder already exercises tools as a *means* (every L2 trace carries
read_file/write_file) but never scores tool behaviour as the thing under test.
`tasks/tool_forbidden.yaml` does, deterministically: correct answer in text
(`output_contains`) AND nothing on disk touched (`files_unchanged`, `allowed: []`).

Item is GSM8K test #2, canonical, chosen because it is trivially in-head — the
refusal is the measurement, not the sum.

## Second salvage — a discriminating NLP task

The extraction probe ceilinged because every field was a literal lookup from four
unambiguous sentences. `tasks/extraction_faithful.yaml` rebuilds it with the three
things the original lacked:

- **absent fields** — `funding_source` and `co_author_count` are never stated and
  must come back `null`; inventing them is the classic extraction-faithfulness failure
- **distractors** — an announcement date (Sept 3) beside the discovery date (June 14),
  and a vehicle rating (4,000 m) beside the observed depth (2,300 m)
- **a derived field** — `expedition_end_date` is not in the passage; it is six weeks
  after the discovery date (2025-07-26)

Validated offline against grading.py before any GPU time: the gold answer passes all
8 checks; an answer that takes both distractors and invents both nulls is caught by 5.

This exists to test a specific outside claim ("for my nlp stuff, Qwen is king") that
the original task could not evaluate in either direction, because everything scored 6/6.

## Still open

- No `tool-required` counterpart yet (the 35b/26b failure direction). Would need
  a fixture whose answer is only knowable by reading a file.
- Not yet run. Author it into a pack with n>=6 and a same-run control, per
  `new_model_gate.sh` and the GOLD_STANDARD read order.
- Whether tool discipline correlates with the existing L2 field is unmeasured.
