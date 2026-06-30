# Appendix: opr Governed LLM Client

This appendix describes the open-source governed model client `opr` implemented in this repository.

## One-Minute Snapshot

`opr` is the governed LLM client that sits next to the `operator` ledger. `operator`
records tasks, claims, evidence, sessions, and usage; `opr` runs local models, bounded workspace
tools, and explicitly enabled frontier CLI harnesses while writing those runs back to the ledger.

The client is fully generalized to load its configuration from `~/.config/operator/opr.yaml`.

## What You Should Be Able To Explain

- `opr` is a model client surface; `operator` is the ledger and governance substrate.
- Local Ollama/Camelid execution stays the default.
- Frontier harnesses are opt-in CLI subprocess adapters, not automatic escalation.
- Workspace tools expose local context through bounded, audited reads.
- The generalized client should be configured through `~/.config/operator/opr.yaml`.

## Mental Model

Think of `opr` as the cockpit and `operator` as the logbook. The user talks to `opr`; `opr` decides
which harness to invoke, brokers local context, asks before sending sensitive context to frontier
tools, and records the session through `operator`.

The important boundary is authority. The model does not receive raw filesystem access. `opr` owns the
workspace root, path resolution, shell/write flags, and confirmation prompts. The model only sees
tool output that `opr` allowed and collected.

## Target Behavior

`opr` without arguments opens a REPL. `opr "prompt"` performs a one-shot run. Both paths should open
and close governed sessions unless `--no-govern` is passed.

Local model switching must be transactional. If `/model gemma4:31b` names a model Ollama cannot
serve, the current session and prompt label must remain unchanged.

Read tools should include `/pwd`, `/ls`, `/cat`, `/rg`, and `/tree`. Each resolves paths under the
workspace root and appends successful output to accumulated context for the next prompt.

Frontier execution should require `--allow-frontier` or an accepted config setting. Claude, Codex,
and Agy/Gemini should run through configured subprocess command templates. Before accumulated local
context is sent to a frontier harness, `opr` should ask for confirmation.

## Configuration

The target config file is `~/.config/operator/opr.yaml`. It should hold the ledger root, default
workspace, default local model, Ollama endpoint, frontier command templates, and tool permissions.

See [OPR_GENERALIZATION_SPEC.md](../../OPR_GENERALIZATION_SPEC.md) for the proposed schema and
migration plan.

## Attention Cards

- **high: Frontier pass-through is an authority boundary** — local context must not be sent to
  Claude, Codex, or Agy/Gemini without explicit opt-in and confirmation.
- **medium: Tool audit records may need promotion** — sidecar JSONL audit logs are useful, but a
  first-class operator record type may be cleaner for open-source users.

## Owner Decisions

- Should `opr` own routing policy, or should callers pass explicit model and lane decisions?
- Should frontier CLI transcript capture create evidence records automatically?
- Should shell/write tools be included in the first open-source release or left as local-only
  advanced features?

## Evidence Boundary

Reviewed:

- Implementation of `opr` CLI client in the root of the repository.
- Unit and integration tests in `tests/test_opr.py` confirming configuration loading, safe path resolution, routing, and gating behavior.
- Configuration schemas loading from `~/.config/operator/opr.yaml`.
- Existing operator owner-manual and PBC structure.
