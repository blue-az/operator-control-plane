# Alignerr-Derived Internal Use-Case Benchmark

Local-only benchmark packet derived from saved Alignerr work artifacts. This is for internal benchmarking only; do not access or depend on any external Alignerr systems.

## Purpose

This benchmark is separate from FastFoodAgent. FastFoodAgent measures local model coding implementation over a frozen Python substrate. This Alignerr-derived benchmark measures the work style that actually appeared in the Alignerr lane:

1. code-transcript preference judgment,
2. document/rule-grounded dispute handling,
3. MuJoCo / robotics verification methodology.

## Source artifacts used locally

- `/home/blueaz/Documents/Career/Applications/Alignerr/ALIGNERR_EVAL_RESULT_2026-04-24.md`
- `/home/blueaz/Documents/Career/Applications/Alignerr/ALIGNERR_EVAL_DECISION_2026-04-24.md`
- `/home/blueaz/Alignerr/Test_Instructions.md`
- `/home/blueaz/Alignerr/batch4_failure_catalog.md`
- `/home/blueaz/Alignerr/mujoco-prep/PREP_BRIEF.md`
- `/home/blueaz/Alignerr/mujoco-prep/GPU_CPU_BENCH_SECTION.md`
- `/home/blueaz/Alignerr/mujoco-prep/INTERVIEW_CRIB.md`
- `/home/blueaz/Alignerr/mujoco_spike/MUJOCO_LESSONS_LEARNED.md`

## Benchmark lanes

| Lane | Actual use case | What to score |
|---|---|---|
| AUB-1 Code Preference | Compare two coding responses/transcripts and justify a preference | Correct winner, semantic risk detection, verification-gap honesty, concise reviewer-quality rationale |
| AUB-2 Dispute Re-Derivation | Evaluate reviewer disputes against literal source rules/evidence | Does not capitulate; decomposes compound disputes; re-derives arithmetic/file-set claims independently |
| AUB-3 MuJoCo Verification | Design/evaluate simulation/RL evidence with measurable claims | Closed-form checks, deterministic reruns, CPU/GPU crossover reasoning, honest scope/caveats |

## Scoring

Each lane is scored on a 0-3 rubric per dimension:

- `0`: wrong or unsupported
- `1`: partly right but misses major evidence/rule issue
- `2`: substantively right with minor omissions
- `3`: correct, evidence-grounded, and clearly communicated

Recommended aggregate: report lane totals separately. Do not collapse into one universal score unless a downstream decision needs a single number.

## Relationship to FastFoodAgent

FastFoodAgent now provides the current local coding model separation: Qwen 3.8 leads hard behavioral accuracy. This benchmark should be used to test a different axis: whether a harness can perform real evaluator/reviewer work under evidence discipline.
