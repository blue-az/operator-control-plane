# Confound Pilot — Findings

Commissioned in handoff-0004 on task `opr-continuation-loop-audit`, as a cheaper
alternative to rerunning all 88 historical ladder negatives.

**Question.** The 216-trial ladder in `RESULTS.md` produced 88 failing trials, all under
a harness with two defaults later found defective: `run_command` was a terminal tool
that ended the agent loop on its first successful state-changing command (fixed in
890d595), and the Ollama read timeout was hardcoded to 120s (fixed in d5eea34). How many
of those negatives were the harness rather than the model?

**Machine.** All runs on `z13`. Results are decode-rate dependent and do not transfer to
other hosts — gemma4:31b is 21GB and runs ~28% on CPU here.

## Design

Sampled 17 of the 27 *reachable* unique failing `(task, level, model)` cells — 63%
coverage. (36 unique failing cells exist; 9 are `qwen2.5-coder:32b`, which is no longer
installed.) Each cell was replayed against fresh fixtures and graded by the ladder's own
unmodified postconditions.

Three arms, run as two passes:

| Arm | continuation | read timeout | meaning |
|---|---|---|---|
| A1 | steps 0 | 120s | faithful pre-890d595/pre-d5eea34 harness |
| A2 | steps 0 | 600s | timeout fix only |
| B  | steps 4 | 600s | both fixes |

Pass 1 (`pilot_confound.py`) ran A2 and B. It was framed as reproducing old behavior,
but both of its arms inherited the *current* 600s default, so neither reproduced the
harness that produced the historical negatives. Pass 2 (`pilot_pass2_oldharness.py`)
added A1 and merged.

Attribution per cell, earliest fix that rescues it owning the outcome:

- `A1 pass` → **did not reproduce** (historical record unreliable for this cell)
- `A1 fail, A2 pass` → **timeout**
- `A2 fail, B pass` → **truncation**
- `A1 fail, B fail` → **survives both**

## Results (n=17)

| Attribution | n |
|---|---|
| survives both fixes | 9 |
| truncation | 4 |
| did not reproduce | 4 |
| timeout | 0 |

**Among the 13 cells that reproduce: 4 (31%) are harness artifacts, 9 (69%) survive both
fixes.**

By model:

| Model | n | truncation | survives both | did not reproduce |
|---|---|---|---|---|
| gemma4:26b | 5 | 2 | 1 | 2 |
| gemma4:31b | 3 | 0 | 1 | 2 |
| llama3.1:8b | 9 | 2 | 7 | 0 |

## The timeout confound does not apply to this dataset

Zero cells were timeout-attributable, and **no read timeout fired at all** under the
120s config. This is structural, not luck: `runner.py` invokes `opr` with no
`--continue-steps`, so the historical ladder was **single-dispatch**. The 120s ceiling
was a real defect, but it bit on the *final turn of multi-step* runs — which is the
configuration the earlier audit measured it in (`--continue-steps 4`). One dispatch
rarely reaches 120s of generation.

Consequence: d5eea34 does not retroactively rescue any ladder negative, and pass 1's
single `pass->pass` cell was never timeout-driven.

## Variance is the limiting factor

**4 of 17 cells did not reproduce** their historical failure under faithful replay. Two
of those were counted as truncation wins in pass 1. Three pass1↔pass2 label
disagreements, all consistent with run-to-run noise:

```
gemma4:26b  multi-file-rename-reference L0   pass1=fail->pass  pass2=did_not_reproduce
gemma4:26b  config-value-change         L0   pass1=fail->pass  pass2=did_not_reproduce
gemma4:31b  function-add                L2   pass1=fail->fail  pass2=did_not_reproduce
```

Each arm is **n=1**. A single flip cannot be distinguished from variance, and cells
demonstrably flip. Pass 2 also compares a fresh A1 against A2/B recorded ~16 hours
earlier, inheriting variance from both passes.

**Neither 41% (pass 1) nor 31% (pass 2) should be reported as a point estimate.** The
defensible statement is directional: a minority of the historical negatives are harness
artifacts, most survive both fixes, and the sample cannot bound the fraction tightly.

## What this revises

70491e7 flagged all 88 failing trials as confounded and left the 128 passing trials
valid. That was correct on the evidence then available and remains directionally right,
but "confounded" is now quantified at roughly a third of reproducing cells rather than
implied wholesale. The ladder's negative findings are **more** defensible than the
commit suggested, not less.

The "degrees of freedom, not knowledge" hypothesis remains open. This pilot does not
support it and does not refute it; it only removes the harness as the dominant
explanation for most negatives.

## Known limitations

1. n=1 per arm. No confidence interval is computable. Repeating each arm ~5× is the
   single highest-value follow-up.
2. 63% coverage of reachable cells; 9 `qwen2.5-coder:32b` cells unreachable without a
   ~20GB pull.
3. Cross-pass comparison (fresh A1 vs. 16h-old A2/B) rather than a single simultaneous
   three-arm run.
4. Pass 1 and pass 2 used `--dangerous`, not the `--eval-auto-confirm` the original
   sweep used. The flags differ in confirmation handling only, but this was asserted
   rather than tested.
5. All results from one machine, and the measured quantity is hardware-dependent.

## Artifacts

- `pilot_confound.py`, `pilot_pass2_oldharness.py` — runners
- `/home/blueaz/Documents/local/routing/pilot_confound/` — pass 1 results + every raw trace
- `/home/blueaz/Documents/local/routing/pilot_confound_pass2/` — pass 2 results + traces
  and the generated `old_harness_timeout.yaml`
