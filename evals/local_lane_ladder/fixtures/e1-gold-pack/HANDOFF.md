# E1 gold pack handoff

## Created

- `MANIFEST.md`: new L2 model-comparison question, fixed 27-cell matrix,
  deterministic grading rule, machine/ledger boundary, and claim boundary.
- `RUN.md`: import smoke, task-provenance check, L2 lint, safe dry-run, GPU
  residency requirement, trace gate, and deferred desktop command.
- `tasks/alias_add.yaml`, `tasks/config_value_change.yaml`, and
  `tasks/function_add.yaml`: pinned ladder tasks with artifact-based
  postconditions and non-scored three-action trajectory hints.

## Not run

No model cell and no full matrix was run during implementation. In
particular, E0 was not rerun or relabeled, no 216-cell sweep was started, no
32b/dual-GPU row was added, and no Alignerr PDFs were imported. The only
permitted implementation checks are YAML/runner imports, deterministic task
lint/provenance checks, and the runner's no-execution dry-run.

## Blocker and boundaries

The current runner discards captured stdout and stderr and exposes no trace
retention option. Its state records cannot reconstruct model output or tool
activity. D3 and GOLD_STANDARD therefore prohibit a scoreable E1 run until an
approved runner change persists per-cell traces for passes and failures.

Model installation and 100%-GPU residency were not assumed. The desktop
operator must select the exact installed 14b-class Qwen, document any
substitution, and retain `ollama ps` evidence during its cells. All eventual
run and ledger records belong to desktop; Front H forbids treating z13's
separate `.operator/` tree as the same ledger.

The pack is a scaffold, not verified Front E routability evidence.

## Suggested next operator action

Have Grok or Claude supervise a narrowly scoped trace-retention fix or approve
an existing trace-capable runner path. Then perform the single-cell trace
preflight and, only if it passes, run the 27-cell desktop matrix exactly as
bounded in RUN.md. A distinct UID should re-derive the postcondition totals,
trace completeness, model tags, GPU residency, and machine provenance before
any routability claim is verified.
