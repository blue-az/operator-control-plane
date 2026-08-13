# E10 finding — the repeat-guard, and the first measured noise floor

**Run:** desktop, 2026-08-13, rev `e1bdeb0`. Feedback arm **210/210 cells**;
stop arm deliberately **not run** — see below. **Not UID-verified. No claim.**

## Design change, mid-run

Planned as 420 cells, both arms fresh, to avoid comparing across invocations.
The second arm was cut at the arm boundary once it became clear it would consume
a whole cheap-power window to answer a question `e9-ceiling-continued` already
answers: E9 *is* a stop arm at identical settings (`ctx 16384`,
`temperature 0.8`, `think off`, `--on-repeat` default).

The substitution is **validated rather than assumed**, using a probe the design
makes available: `--on-repeat` can only change a cell where a repeat actually
fires, so cells where none fired are a clean drift measurement.

## The noise floor — the most reusable number here

**142 flag-inert cells** (no repeat in either run):

| | passed |
|---|---|
| E9 | 89/142 (62.7%) |
| E10 feedback | 83/142 (58.5%) |

Aggregate drift **4.2 points** — small enough that the substitution holds. But
**16 of 142 cells (11.3%) disagree individually.**

That is the first quantification of cross-invocation variance in this programme,
and it explains a great deal retroactively: the 200–400 point Elo CIs, the
`3/3 → 3/8 → 8/8 → 6/6` swings on one cell class, and how a confounded A/B
produced a false regression claim earlier the same day.

**It also gives `MSC-RUL-107` a number.** Roughly one cell in nine flips on its
own, so a single-trial correction carries less evidence than a coin flip.

## The repeat-guard result

| Cell group | E9 (stop) | E10 (feedback) | Δ |
|---|---:|---:|---:|
| repeat path **engaged** (≥3/6 trials) | 31/54 (57.4%) | 37/54 (68.5%) | **+11.1** |
| repeat **never fired** (control) | 82/132 (62.1%) | 78/132 (59.1%) | −3.0 |

Difference-in-differences **+14.1 points**, and the control moving the opposite
way argues against a general uplift.

**It is not significant.** Fisher exact on the engaged group: **p = 0.32**.
Against an 11.3% noise floor, 54 cells is roughly **4x underpowered** — detecting
a 14-point effect at 80% power needs ~200 cells per arm.

## Mechanism, by contrast, is unambiguous

| | E9 | E10 feedback |
|---|---:|---:|
| repeat-stops | **61**/210 | **10**/210 |
| feedback fired | — | 50/210 |

The intervention does exactly what it claims. Whether that converts to passing
is unproven, and this run cannot prove it.

## Verdict

Unchanged from the pilot, now with numbers: **keep `stop` as the default; use
`feedback` as a diagnostic.** It answers "stuck, or just lost the context?" in
one A/B, which was previously unanswerable.

A conclusive outcome test needs ~200 engaged cells per arm. That is a deliberate
spend against a specific question, not a side effect of another sweep — and it
should target the cell classes where the repeat path actually engages (9 of 35
classes here), not the full matrix.
