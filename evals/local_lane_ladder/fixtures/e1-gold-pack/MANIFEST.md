# E1 gold pack — L2 local-executor comparison

**Status:** scaffolded; scoreable matrix blocked on trace retention (2026-08-11).

## Question

On the desktop single-RTX-3090 host, for three plan-shaped (L2) local-lane
fixtures, how do deterministic postcondition pass rates compare across
`gemma4:26b`, `gemma4:31b`, and a 100%-GPU-resident
`qwen2.5-coder:14b` (or the installed 14b-class Qwen substitute), with three
trials per cell?

This is a model comparison on L2 task execution under the post-`890d595`
harness. It is **not** the question “Did harness fixes change July L2?” E0
already answered that harness-regression question and is not Front E
routability evidence. Reusing task definitions does not turn E1 into an E0
replay because the comparison matrix and floor-model question are new.

The binding methodology is [GOLD_STANDARD.md](../../GOLD_STANDARD.md). The
complexity subset is L2 / plan-shaped under
[LOCAL_LANE_CONTRACT.md](../../../../LOCAL_LANE_CONTRACT.md); this pack does
not re-derive L0→L2 monotonicity.

## Matrix and target

| Dimension | Fixed value |
|---|---|
| Machine | `desktop`, single RTX 3090 |
| Level | L2 only |
| Tasks | `alias-add`, `config-value-change`, `function-add` |
| Models | `gemma4:26b`, `gemma4:31b`, 100%-GPU 14b-class Qwen |
| Trials | n=3 per task/model cell |
| Planned cells | 27 |
| Grading | deterministic postconditions only |

The preferred floor tag is `qwen2.5-coder:14b`. If that exact tag is absent,
the operator must record the substituted installed 14b-class Qwen tag here
before execution. A substitution is eligible only when `ollama ps` reports
100% GPU residency during its cell. Do not add a spilling 32b model or require
a dual-3090 setup. Record `ollama list`, `ollama ps`, machine identity, and the
exact git revision with the run artifacts; no capacity claim follows without
the residency evidence.

## Tasks and gold answers

The three YAML files in `tasks/` are pinned pack copies of compatible main
ladder definitions, with non-scored `trajectory_hint` lists added. Their L2
prompts name exact paths and anchors, split actions into single-tool steps,
state machine-checkable success conditions, use closed imperative language,
and bound touched files (R1–R6).

Only the `postcondition` object is scored:

| Task | Deterministic check |
|---|---|
| `alias-add` | exact line is present in `bash/.bash_aliases` |
| `config-value-change` | new value is present and stale value absent |
| `function-add` | importing and calling `square(4)` returns 16 |

The shared grader is [grading.py](../../grading.py). It reads fixture
artifacts or executes the declared local assertion; model narration and
self-reported success are not gold.

## Trace-retention blocker — RESOLVED 2026-08-12

**Was:** [runner.py](../../runner.py) invoked `opr` with captured stdout and
stderr but discarded both after grading. `state.json` retained only summary
fields such as pass/fail, detail, return code, and wall-clock time, with no
trace-output flag. That reproduced the raw-output gap identified in the E0
consultant review and failed GOLD_STANDARD rule 4.

**Now:** `runner.py` takes `--trace-dir DIR` and persists one JSON per cell —
raw opr stdout/stderr (which carry the tool-call log), exact argv and prompt,
git rev, machine, and grade outcome — for passes, graded fails, and timeouts
alike. Default behaviour without the flag is unchanged, and the runner warns to
stderr that such a run is not scoreable. Trace writes fail closed.

Resolved on desktop at rev `77a31e2` under Claude supervision; the single-cell
preflight and the failure/timeout retention tests are recorded in
[RUN.md](RUN.md) §3. Any scoreable E1 cell must be produced by a command that
includes `--trace-dir`.

Still required before the matrix counts as evidence: operator authorisation of
the phase, `ollama ps` 100%-GPU residency captured during each model's cells,
27 retained traces, and a distinct-UID re-derive.

## Ledger and claim boundary

Execute and record the eventual matrix on the `desktop` ledger only. Do not
merge or backfill the z13 `.operator/` tree and do not assume it contains the
desktop eval history (Front H). Use a pack-specific state/results/trace area
so E1 records do not silently reuse historical cells.

This scaffold is not verified routability evidence. Register claims only
after the full desktop matrix is run, its traces and residency artifacts are
retained, and a distinct UID independently verifies the measured result.

## Non-goals

- Relabeling E0 or historical confounded failures as routability evidence.
- Re-running the 216-cell ladder or implementing a router.
- Importing Alignerr invoice PDFs or other binary corpora.
- Merging desktop and z13 ledgers.
- Making dual-GPU or spilling-32b capacity claims.
