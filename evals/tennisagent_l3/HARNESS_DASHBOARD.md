# Harness evidence dashboard

> Operational dashboard: separates what the harness demonstrated from what the
> model demonstrated. No card is a capability claim unless all four gates pass.

## Gate board

| Surface | Protocol | Fixture state | Grading | Synthesis | Status |
|---|---|---|---|---|---|
| Local native Fusion L3 | pass | pass | reconciled | pass | **reference** |
| Local native Fusion L3.1 | pass | partial | pass | pass | **preliminary** |
| Haiku staged L2-equivalent | pass | pass | pass | pass | **6/6 staged baseline** |
| Luna staged L2-equivalent | pass | pass | corrected | pass | **6/6 staged baseline** |
| Haiku staged L3.1 canary | pass | partial | preliminary | pass | **canary** |
| Luna staged L3.1 canary | pass | partial | preliminary | partial | **quarantined** |
| Direct frontier JSON loop | fail/variable | n/a | n/a | variable | **quarantined** |

## Established harness lessons

- A text CLI is not automatically a custom tool executor.
- Large raw tool payloads distort synthesis; compact evidence is required.
- Planner → deterministic executor → compact evidence → synthesis is the
  reliable staged shape so far.
- Semantic negative states must not be rejected for wording differences.
- A fixture must prove that its claimed contradiction or ambiguity exists.
- Turn limits must not be confused with reasoning failures.

## Promotion rule

A result moves from **observation** to **reference** only when protocol,
fixture-state, grading, and synthesis gates are independently verified. Failed,
missing, unsupported, contaminated, and adapter-invalid states remain visible.

## Evidence index

- `evidence-0037` — Haiku staged 6/6 baseline
- `evidence-0039` — Luna staged 6/6 baseline
- `evidence-0040` — frontier staged L3.1 canary
- `evidence-0041` — Luna fixture-state repair
- `evidence-0042` — consolidated harness lessons
