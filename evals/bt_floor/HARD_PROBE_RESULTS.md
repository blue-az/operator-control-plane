# Hard probes — first field result

**Measured:** 2026-08-14, `current` funnel (40,510 tokens), `num_ctx 49152`,
`temperature 0.8`, `think off`, n=5 per cell with `seed=rep`.
**Not UID-verified. No claim registered.**

Raw: `handoffs/bt_hard_20260814_130202.json` (n=5) and
`bt_hard_20260814_121228.json` (the n=1 pass).

## Result

| Model | h1 hyperlambda | h2 crystal status | h3 cross-machine | total | flips |
|---|---|---|---|---:|---:|
| `gemma4:26b` | 5/5 | **5/5** | 5/5 | **15/15** | 0 |
| `gemma4:12b` | 5/5 | 3/5 | 5/5 | 13/15 | 1 |
| `gemma4:31b` | 5/5 | 1/5 | 5/5 | 11/15 | 1 |
| `qwen3.6:27b` | 5/5 | 1/5 | 5/5 | 11/15 | 1 |
| `granite4` (3.4B) | 0/5 | 2/5 | 0/5 | 2/15 | 1 |

## Finding 1 — h1 and h3 are floor instruments, h2 is the ceiling instrument

h1 and h3 are 5/5 for every model from 12B up and 0/5 for granite4. They
discriminate hard *downward* and not at all above 12B, which is the same
saturation that made p1..p5 useless for ranking strong seats. Cross-document
assembly alone did not produce ceiling resolution.

h2 is the only probe with a spread: 5/5, 3/5, 1/5, 1/5, 2/5.

What separates it is not that it needs more documents — h3 needs three across
two repos and still saturates. It is that h2 asks **two independent questions**
and a model can answer one while inverting the other. Trust rule *and*
implementation status. Every model finds the trust rule. Only `gemma4:26b`
reliably also reports that the mechanism does not exist yet.

**Design rule this yields:** a discriminating probe needs two independently
checkable halves, not more sources.

## Finding 2 — the failure mode is reading a plan as a status

Every h2 failure is the same half of the question, and the corpus makes the
error easy: `CRYSTAL_LEDGER_INTEROP_SPEC.md` is written as a phased build plan
(§188, "Phase 1 (smallest reviewable unit)"), while the fact that none of it
exists lives 80 lines away in `operator-control-plane/AGENTS.md:90` — "nothing
in that doc is implemented yet."

Confabulating models convert the plan into a status:

- `qwen3.6:27b` — "Phases 1–3 ... were **implemented on 2026-07-18**." An
  invented date for work that does not exist.
- `granite4` — quotes T2 verbatim and correctly, then "**Phase 1** ... is fully
  implemented and verified by tests", then concludes the mechanism "has not been
  defined or implemented." Self-contradictory inside one answer.
- `gemma4:31b` — milder and more consistent (4/5): answers the trust half
  thoroughly, never addresses existence, and describes `crystal-attach` /
  `crystal-import` as existing commands "designed to exclude" the capability.
  rep2: "no mechanism in the current **implementation**" — the unbuilt spec
  treated as shipped behaviour.

This generalises past the probe. BOTTLENECKS.md and the specs are largely
planned work, so a model that reports plans as shipped is actively dangerous
for BN/operator triage, independently of how well it retrieves.

## Finding 3 — the gemma4 tie breaks, narrowly

E11 (n=18, 378 cells) left `gemma4:26b` and `gemma4:31b` tied at 1814 Elo,
P=0.49. On h2 they separate 5/5 vs 1/5, Fisher exact two-tailed **p=0.048**.

Read this narrowly:

- 5/5 vs 1/5 is the *minimum* configuration reaching p<0.05 at n=5. One flipped
  cell erases it.
- Nine pairwise tests were computed. Under Bonferroni (α=0.0056) this does not
  survive. The 26b-vs-31b comparison was the pre-specified question this probe
  was built to answer, so it stands as a single planned test; every other pair
  in the matrix is exploratory and none reach significance.
- It is one probe on one axis — document comprehension, not the agentic ladder.

The defensible statement: **on cross-document assembly requiring plan-vs-status
discrimination, `gemma4:26b` beats `gemma4:31b`.** Combined with 26b already
being 1.4x faster and perfectly stable, nothing here argues for 31b as the seat.

`gemma4:12b` at 3/5 is not separable from either (p=0.44 vs 26b, p=0.52 vs 31b).
Its 13/15 total on a 12B model remains the standing surprise from the z13 work.

## Finding 4 — `gemma4:26b` is the only zero-flip model

15/15 with no cell changing verdict across five samples at temperature 0.8.
Every other model including granite4 flipped exactly one probe. Stability was
uninformative on the saturated batteries; here it separates.

## Grading caveat — this instrument was wrong before it was right

The n=1 pass misgraded 4 of 15 cells, all false negatives from paraphrase
("does not exist" vs "does not execute"; "does not exist" vs "does not exist
*yet*"). The contradiction check added to catch confabulation produced its own
false positive on a known-correct answer, matching "is implemented" inside
"nothing in it is implemented yet".

All fixes were applied to the grader and re-scored from retained outputs; no
model was re-run to produce this table. That is the whole reason outputs are
retained verbatim.

Keyword grading of free prose leaks in both directions and every table above
should be read as provisional on the accept lists. The citation check is the
sounder axis and it only covers fabricated *paths* — `granite4`'s invented
"Claude Code agent produces the dashboard" (h1) and `qwen3.6`'s invented
implementation date are both prose, and neither is caught structurally.

## Limits

n=5, one machine, one funnel epoch, one prompt per probe. Five models; the
wider E11 field (`qwen3-vl:30b`, `qwen3:32b`, `gemma3:27b`, `qwen2.5-coder:14b`)
has not been run here. Results are not comparable to p1..p5, which ran on
different epochs at temperature 0. `capped` cannot host these probes at all —
it truncates BOTTLENECKS.md above both h1's and h3's sources.
