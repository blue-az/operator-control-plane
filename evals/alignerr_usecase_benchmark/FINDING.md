# The Alignerr benchmark is saturated, and its scorer measures vocabulary rather than judgment

**Type:** synthesis + methodology finding, 2026-08-31. Covers both runs in
`runs/` (2026-08-25 n=4 models, 2026-08-29 n=2 models), the scorer
(`score_run.py`), and the task specs (`tasks/*.yaml`). No new model trials
were run for this write-up.

**Question:** this packet was being carried as a possible replacement
instrument after the E9 battery saturated (see
`evals/local_lane_ladder/fixtures/e9-full-battery-saturation/FINDING.md`).
Does it discriminate on the current roster?

## It was saturated on the first run

| run | model | total |
|---|---|---:|
| 2026-08-25 | qwen3.6:35b | **20/20** |
| 2026-08-25 | gemma4:26b | 19/20 |
| 2026-08-25 | gemma4:31b | 18/20 |
| 2026-08-25 | qwen3.8:27b | 17/20 |
| 2026-08-29 | gpt-oss:120b | 17/20 |
| 2026-08-29 | qwen3-next:80b | 10/20 -- **invalid, see below** |

Per-lane the bunching is tighter than the totals suggest: AUB-2 scored
6,7,7,7 and AUB-3 scored 7,8,7,8 across the first four models. Six models
spanning 26B to 120B land between 85% and 100% of the scale, with one
invalid row. **This is the same ceiling problem E9 has, and it was present
from the first run rather than developing over time.**

## The one low score is an artifact, not a measurement

`aub3_mujoco_verification__qnext80b.out.md` is **0 bytes**. The model ran
144.7s, exited 0, and emitted nothing; the only stderr is the benign
`Model "qwen3-next:latest" not found for provider "ollama". Using custom
model id.` warning that also appears on the successful rows.

`score_run.py` has no empty-output guard. It regexes an empty string, every
check returns false, and the row scores 0/8 -- which then drags the model's
reported total to 10/20. **A null result and a maximally wrong result are
indistinguishable to this scorer.** This is the same fail-open-on-absence
pattern already recorded across operator/gate/pbc (memory:
`project_stack_silent_gap`), and the same class of error as this cycle's
other two artifact corrections (the OOM-contaminated VRAM sweep, the
cross-GPU CUDA crash scored as 0/12 capability).

## The scorer measures vocabulary, not judgment

`score_run.py`'s docstring is honest -- "intentionally simple and
auditable... a first-pass triage, not an LLM judge." The problem is that
its output is being read as a ranking. What actually earns points:

| check | regex | what it really matches |
|---|---|---|
| `recompute_arithmetic` | `sum` | the bare word "sum" |
| `claim_evidence_workflow` | `evidence` | the bare word "evidence" |
| `literal_rules` | `query` | the bare word "query" |
| `gpu_cpu_crossover` | `3\.0` | any version number or dollar figure |

A response that says "I reviewed the evidence and summed the files"
collects three points without doing anything.

**The cleanest demonstration that it is not measuring judgment:** on AUB-1,
`prefers_a` is the only check that tests whether the model reached the
correct conclusion. `gpt-oss:120b` got it **wrong** (`prefers_a: false`)
and still scored **4/5** -- identical to `qwen3-next`, which got it right.
A model can miss the single thing the task is about and lose nothing
relative to its peers.

**It also rewards exactly what this program already established is noise.**
More output means more regex surface, so verbosity scores higher
mechanically. That is anti-correlated with the brevity-ablation finding
(`fixtures/gemma26-brevity-ablation-001/`), which established that
gemma4:26b's token count is a steerable default rather than a capability
signal.

## The scorer does not implement the rubric it is scoring against

The task specs declare a **0-3 rubric across four named dimensions per
lane** (12 points per lane, 36 total) -- e.g. AUB-1's
`correct_preference`, `semantic_risk_detection`, `verification_gap_honesty`,
`rationale_quality`. `score_run.py` implements none of it: binary keyword
checks totalling 20 points, on dimensions of its own. The README further
instructs "report lane totals separately, do not collapse into one
universal score"; the scorer prints a single collapsed total and sorts
models by it.

So the implemented scorer diverges from the documented design on all three
axes: granularity (binary vs 0-3), dimensions (keyword hits vs named rubric
criteria), and aggregation (one collapsed number vs per-lane).

## Every cell is n=1

Both runs are one trial per model per lane. Under the sample-size policy
codified in `evals/local_lane_ladder/GOLD_STANDARD.md` §2a four days after
the first run, n=1 is "Screen -- never a standalone finding." **No ranking
claim from this corpus is supportable as written, including the 20/20.**

## Interpretation

Two instruments, both saturated -- but they fail differently, and only one
failure is fatal. E9 saturated because the *tasks* became too easy for the
roster. This packet's tasks are not obviously too easy: AUB-2 and AUB-3
pose genuinely hard evaluator work, and they are grounded in real saved
artifacts rather than synthetic fixtures. What is broken here is the
*measurement*, which is a more tractable problem than task design.

The salvageable half is the task set. The replaceable half is the scorer.

## Consequence

Scorer replacement scoped to: a null-guard that reports empty output as
`INVALID` rather than `0`; separation of verdict-correctness (objectively
checkable) from keyword coverage (at best a weak signal, never a ranking);
tightened patterns for the four leaky checks above; per-lane uncollapsed
reporting per the README's own instruction; and honest refusal to score the
rubric's quality dimensions (`rationale_quality`, `scope_honesty`)
deterministically, since keyword presence cannot measure them. Those
dimensions need a human pass or a separately validated judge, and should
read as not-implemented rather than be silently faked.

## Addendum 2026-09-01 — scorer replaced, both runs rescored

`score_run.py` was rewritten to report four classes that are never summed:
`STATUS` (OK / MALFORMED / **INVALID**), `VERDICT` (objectively correct
conclusion), `COVERAGE` (weak presence signal), and `MANUAL` (rubric
dimensions emitted unscored). Checks moved into the task YAMLs, so the
scorer is generic; matching is anchored to the output section a check
belongs to, so a keyword in a preamble earns nothing. The old 0-3 `rubric:`
blocks were replaced with what is actually checkable.

**The rescore's finding: coverage saturates, verdict discriminates.** Once
false negatives were removed, coverage is near-uniform (4/4, 6/6, 4/5 almost
everywhere) and carries essentially no signal. Every remaining distinction
sits in `VERDICT`:

| run | model | lane | verdict | coverage | failed check |
|---|---|---|---:|---:|---|
| 08-25 | qwen3.8:27b | AUB-2 | **0/1** | 6/6 | `dispute_is_claim_not_verdict` |
| 08-29 | qwen3-next:80b | AUB-2 | **0/1** | 6/6 | `dispute_is_claim_not_verdict` |
| 08-29 | gpt-oss:120b | AUB-1 | **0/1** | 4/4 | `correct_preference` |
| 08-25 | gemma4:26b | AUB-3 | 1/2 | 4/5 | `gpu_cpu_crossover_direction` |
| 08-29 | gpt-oss:120b | AUB-3 | 1/2 | 4/5 | `gpu_cpu_crossover_direction` |

Three models scored **full coverage while failing the single check their lane
exists to test**. `qwen3.8:27b` and `qwen3-next:80b` named every correct
consideration about handling reviewer disputes and still treated the dispute
as a verdict. `gpt-oss:120b` discussed every relevant risk on AUB-1 and picked
the wrong response. Under the old scorer `qwen3.8:27b` took 6/7 on AUB-2 and
`gpt-oss:120b` took 4/5 on AUB-1 — identical to models that got them right.

So the original 17-20/20 was not a capability ranking. It was a **coverage
ranking**, on an axis that is saturated and therefore uninformative, while
the axis that discriminates was averaged into invisibility.

Other corrections:
- `qwen3-next:80b` AUB-3 is now `INVALID` (0-byte output), not 0/8. Its
  reported 10/20 was never a measurement.
- `gemma4:26b` AUB-2 is `MALFORMED` — it genuinely omitted `PROCEDURE`, a
  real output-contract violation the old scorer had no concept of.

**Retraction, same day:** an earlier version of this addendum reported
`gemma4:31b` scoring AUB-3 `2/2` verdict against `1/5` coverage, and drew
from it a claim that verdict and coverage *anti-correlate*. That 1/5 was a
scorer artifact (over-narrow section anchoring, below). Its real coverage is
4/5. **The anti-correlation claim is withdrawn** — the evidence supports the
weaker and different claim above: coverage is saturated, not inverted.

### Five artifacts in the replacement scorer, all found before trusting output

Every one produced confident, plausible, false numbers:

1. **Header regex required a trailing colon.** `**MEASURED_CLAIMS**` parsed as
   absent, zeroing every check in a 4,672-char correctly-sectioned answer.
2. **Name normalisation mismatch.** The splitter accepted `CORE RULE` and
   stored it under that key; the lookup asked for `CORE_RULE`. The split found
   a section the lookup could not see.
3. **Over-narrow section anchoring.** AUB-3 physics checks were anchored to
   `RERUNNABLE_GATES`/`PHYSICS_API_RULES`. `gemma4:31b` stated each claim once
   under `MEASURED_CLAIMS` and scored 0; `qwen3.6:35b` scored 4/5 by repeating
   itself across two sections. **The scorer was rewarding duplication and
   penalising concision — a verbosity bias, the exact defect it was written to
   remove.**
4. **Typographic punctuation.** `gpt-oss:120b` writes `closed‑form` with U+2011
   NON-BREAKING HYPHEN. Patterns using ASCII `-` matched nothing; it scored 0/5
   on content it plainly discussed.
5. **`verification_gap` patterns too literal.** Matched **zero of six** models
   whose `VERIFICATION_GAPS` sections read "No test harness run", "Absence of
   any CI/lint", "Neither response validates".

**All five failed in the same direction: false negatives.** That is not
coincidence. Tight patterns fail closed, so an unvalidated keyword scorer
systematically *under*-reports, and it penalises hardest the models whose
prose style diverges most from whatever the pattern author imagined. A
keyword scorer's errors are not randomly distributed noise that averages out
across models — they are a systematic bias correlated with writing style.

None were visible in the summary tables. All were found by checking each of
the 18 cells against its raw output.

**Still true:** the benchmark remains saturated on verdict (most models get
most verdicts right), every cell is n=1, and no ranking claim is supportable.
The scorer is now honest about what it measures; it does not make the task
set discriminate.

## Limits

- This finding rates the instrument, not the models. Nothing here says the
  six models are equally capable at evaluator work -- it says this packet
  cannot currently tell, which is a different claim.
- The 2026-08-29 run was left uncommitted and unreported for two days
  before this pass; the `run_benchmark.py` change adding `gpt-oss:120b` and
  `qwen3-next` is committed alongside this finding.
