# Evals — benchmark suite index

Seven distinct local-model benchmark suites exist across this repo. They were built
at different times for different questions and don't share fixtures, task formats,
or scoring — this file exists so that isn't only discoverable by reading each one's
own README separately. If you're about to build an eighth, check here first for
whether one of these already covers the question.

| Suite | Location | Measures | Status |
|---|---|---|---|
| **local_lane_ladder** | `evals/local_lane_ladder/` | Task-shape complexity (L0/L1/L2: goal-shaped → file-named → plan-shaped) vs. local-model success. The foundational suite — everything else post-dates it. | Active. Governs Front E (routability). `GOLD_STANDARD.md` is canonical; e0–e12 pack series, current ranking is the E9 ceiling battery. |
| **FastFoodAgent** | `fastfoodagent/` (top-level, not under `evals/`) | Local model coding implementation over a frozen MenuStat Python substrate. The reference/baseline the two below define themselves against. | See `docs/FASTFOOD_CROSSED_SEAT_STUDY_PLAN.md` — note its 2026-08-23 banner: the harness-hierarchy framing in that doc is obsolete, only §§1–2 (adapter, `operator study-*`, MenuStat freeze) still stand. |
| **alignerr_usecase_benchmark** | `evals/alignerr_usecase_benchmark/` | The *work style* from Erik's Alignerr lane specifically — code-transcript preference judgment, document/rule-grounded dispute handling, MuJoCo/robotics verification methodology. Derived from real saved Alignerr artifacts, local-only; explicitly not a dependency on any external Alignerr system. | Has runs on disk (`runs/`, `score_run.py`). |
| **ppr_agent_benchmark** | `evals/ppr_agent_benchmark/` | Real-world data/product comprehension over the actual `ppr-agent` CRM Product Performance Registry extract — product-boundary preservation, deterministic query/gate reasoning, resisting chatbot/clinical-tool framing drift. | Has runs on disk. Precedent set 2026-08-25: a timestamped run dir was committed then reverted same-day as side-effect-prone (`a90626d`) — `evals/ppr_agent_benchmark/runs/` is gitignored as of 2026-08-27; don't re-litigate that call without new reasoning. |
| **bt_floor** | `evals/bt_floor/` | How small a model can recover the Bulkhead Tau boundary map from a cold read of 5 repo documents. Tracks input-corpus drift explicitly as a first-class variable (22.7k tokens in the `july` epoch → 37k in `current`, +63%) — results across epochs are declared non-comparable, same discipline as harness-revision tracking elsewhere. | `HARD_PROBE_RESULTS.md` on disk. Record which epoch a run used. |
| **comfyui_symbolic_benchmark** | `evals/comfyui_symbolic_benchmark/` | Image-generation symbolic-constraint compliance — a fixed prompt (an editorial cartoon requiring several meaning-carrying constraints, e.g. relative size/pose, to land simultaneously) for Paper 1.19, "The Capability Ceiling." | Has runs on disk (`score_sheet.csv`). |
| **stella_vs_pi_smoke** | `evals/stella_vs_pi_smoke/` | Third-party coding-agent comparison (not a local-model suite): Stella vs. pi on Terminal-Bench 2.1, same model (GLM-5.2) via OpenRouter. | **One real 5-of-89-task smoke run, evidence-backed, deliberately never published** — see that suite's own README for why. Do not cite the result as a benchmark claim without a full 89-task re-run. |

## On "the Stella benchmark work"

Two separate things both answer to that description, and it's worth keeping them apart:

1. **Stella's own upstream `bench/`** (`~/Python/Evaluation/stella/bench/`, part of the
   read-only clone reviewed in `~/Python/Evaluation/eval-notes/stella.CLAUDE.md`) — a
   SWE-bench runner, a Terminal-Bench 2.1 protocol, a Harbor adapter, `trace_triage`,
   `wirelog`. This is upstream's own tooling and evidence, including a real
   preregistered Stella-vs-Claude-Code result already on disk at
   `bench/evidence/tb21-hh10-20260731/` (Stella 58/89 = 65.2%, Claude Code 44/89 =
   49.4%, verified legitimate). **Nothing here was run by us** — it's what the repo
   ships, read but not executed.
2. **`stella_vs_pi_smoke`** (this repo, above) — the one place real execution
   happened: Harbor was actually installed, pi's native Harbor adapter was actually
   run against 5 of Stella's own published tasks. This is the "we matched stella
   against pi" work.

## Conventions across all suites

Each suite that predates `LOCAL_INFERENCE_BENCH_HARNESS.md` (2026-08-19, governs
`project-phoenix/docs/domain_runs/*` hardware/throughput work) has its **own**
protocol — none of these seven use that contract, because none of them measure raw
decode throughput. Don't cite a number from one suite as if it were comparable to
another's, or to a `docs/domain_runs/` figure, without checking whether the
protocols line up.
