# OPR Generalization Spec

## Purpose

`opr` is currently implemented inside `project-phoenix` as a governed LLM client for local
Ollama/Camelid models plus optional frontier CLI pass-through. The open-source path is to move it
into `operator-control-plane` as a configurable client surface backed by the existing operator
ledger.

The generalized `opr` should preserve the current safety model while removing Project
Phoenix-specific paths, routing policy, and command assumptions.

## Target Shape

- Package `opr` as an installable command from this repository.
- Store user configuration in `~/.config/operator/opr.yaml`.
- Use a central governed ledger by default, configurable as `ledger_root`.
- Keep local models as the default execution mode.
- Require explicit opt-in for frontier subprocess harnesses.
- Keep workspace file access bounded by a configured or current working directory root.

## Configuration

Example:

```yaml
ledger_root: ~/.operator-usage
workspace_root: .
default_model: gemma4:26b
local:
  ollama_url: http://localhost:11434
frontier:
  enabled: false
  commands:
    claude: claude
    codex: codex
    agy: antigravity
tools:
  read: true
  shell: false
  write: false
```

Environment overrides such as `OPR_CLAUDE_CMD`, `OPR_CODEX_CMD`, and `OPR_AGY_CMD` may remain, but
the config file should be the canonical durable interface.

## Required Behaviors

- `opr` without arguments opens a REPL with governed session start/end.
- `opr "prompt"` performs one governed run.
- `/model <name>` switches sessions transactionally; missing local models must not alter state.
- `/pwd`, `/ls`, `/cat`, `/rg`, and `/tree` read only within the workspace root.
- `!command` and write tools require explicit flags and confirmation.
- Frontier providers are CLI subprocess adapters, not API-first integrations.
- Frontier dispatch is blocked unless `--allow-frontier` or config enables it.
- Accumulated local context requires confirmation before sending to a frontier subprocess.
- Tool calls and denied access attempts append audit JSONL records to the operator ledger.

## Ledger Mapping

Local model runs should log:

- `harness_id`: local model family, for example `gemma4_local`
- `lane`: `local`
- `task_class`: `bounded` unless overridden

Frontier CLI runs should log:

- `harness_id`: `claude`, `codex`, or `gemini-agy`
- `lane`: `frontier_author` or `frontier_driver`
- `task_class`: `hard`
- `cost_estimate_usd`: `0.0` unless imported from harness-native usage data later

## Migration Plan

1. Copy the Project Phoenix `scripts/opr` behavior into an `operator-control-plane` module.
2. Replace hardcoded paths with config loading and CLI flags.
3. Replace Project Phoenix router imports with a local minimal routing layer or explicit model
   selection.
4. Add tests for safe path resolution, REPL model switching, frontier gating, subprocess dispatch,
   and ledger writes.
5. Add installation docs and update the owner manual once behavior is implemented in this repo.

## Open Questions

- Should `opr` own routing policy, or should routing stay outside and pass explicit model/lane values?
- Should tool audit logs become first-class operator records instead of a sidecar JSONL file?
- Should frontier CLI transcript capture be stored as evidence records?
- Should config support named profiles such as `local-only`, `review`, and `frontier-enabled`?
