---
id: pbc_opr_governed_llm_client
title: "opr Governed LLM Client — Behavior Contract"
context: opr-generalization
status: active
tags:
  - pbc
  - owner-manual
  - opr
  - governed-client
---

# opr Governed LLM Client — Behavior Contract

> PBC for `opr` client integration inside `operator-control-plane`.

## Scope

`opr` is the interactive and one-shot LLM client surface governed by the operator ledger. It brokers
local model execution, optional frontier CLI pass-through, bounded workspace read tools, and session
usage records. This contract describes the verified open-source behavior implemented in this repository.

## Non-Goals

- Direct API-first billing integrations
- Unbounded filesystem access
- Automatic frontier escalation without explicit user opt-in
- Replacing the core `operator` ledger commands

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Starts runs, approves sensitive context sharing, and chooses models.
- id: opr_client
  name: opr client
  type: system
  description: CLI/REPL surface that dispatches model work and records governed sessions.
- id: operator_ledger
  name: Operator ledger
  type: system
  description: File-backed record of tasks, sessions, usage, handoffs, claims, and evidence.
- id: model_harness
  name: Model harness
  type: external
  description: Local Ollama/Camelid endpoint or frontier CLI subprocess such as Claude, Codex, or Agy.
```

## Rules

```pbc:rules
- id: OPR-RUL-001
  name: Local By Default
  rule: opr must route to local model execution unless the user explicitly enables frontier pass-through.
  trust: trusted
- id: OPR-RUL-002
  name: Frontier Is Explicit
  rule: Any frontier CLI dispatch must require --allow-frontier or an equivalent reviewed configuration setting.
  trust: trusted
- id: OPR-RUL-003
  name: Workspace Is Bounded
  rule: File read tools must resolve paths under the configured workspace root and reject traversal or symlink escapes.
  trust: trusted
- id: OPR-RUL-004
  name: Sensitive Context Requires Consent
  rule: Accumulated local tool output must not be sent to a frontier harness without an explicit confirmation prompt.
  trust: trusted
- id: OPR-RUL-005
  name: Subprocess Dispatch Avoids Shell Expansion
  rule: Frontier harness commands must run via argv subprocess execution, not shell=True.
  trust: trusted
- id: OPR-RUL-006
  name: Session Transitions Are Transactional
  rule: A model switch must not close the current governed session until the target model or harness has been validated.
  trust: provisional
- id: OPR-RUL-007
  name: Tool Calls Are Audited
  rule: Allowed and denied local tool invocations must be recorded with session id, tool name, argument, outcome, and byte count.
  trust: provisional
```

## Behaviors

```pbc:behavior
id: OPR-BHV-001
name: Start Governed Local Session
actor: opr_client
description: Start a local model one-shot run or REPL and create an operator session tagged as local/bounded.
trust: trusted
```

```pbc:outcomes
- The run uses the configured default local model unless overridden.
- The operator ledger records harness id, model, lane, task class, start time, and closeout.
- If the local model is unavailable, the failed run does not masquerade as a successful model switch.
```

```pbc:behavior
id: OPR-BHV-002
name: Execute Bounded Read Tool
actor: opr_client
description: Execute a read-only workspace tool and append its output to accumulated context for the next prompt.
trust: trusted
```

```pbc:outcomes
- /pwd, /ls, /cat, /rg, and /tree operate inside the workspace root.
- Missing paths return clear errors.
- Path escapes are denied and audited.
```

```pbc:behavior
id: OPR-BHV-003
name: Dispatch Frontier CLI
actor: opr_client
description: Run an explicitly enabled frontier provider through a local CLI subprocess.
trust: provisional
```

```pbc:outcomes
- Claude, Codex, and Agy/Gemini map to configured command templates.
- Prompts are passed through stdin or explicit {prompt}/{task} argv placeholders.
- The ledger records frontier_author or frontier_driver with task_class hard.
- Cost remains 0.0 unless imported or annotated from harness-native usage data.
```

## Provenance

```pbc:provenance
- ref: "opr"
  confidence: verified
  review_status: "active"
  note: "Fully generalized client script implemented in the root of the repository."
- ref: "tests/test_opr.py"
  confidence: verified
  review_status: "active"
  note: "Unit and integration tests verifying configurations, safe path boundary checks, and routing."
- ref: "OPR_GENERALIZATION_SPEC.md"
  confidence: verified
  review_status: "active"
  note: "Completed generalization spec requirements."
```

## Open Risks

- Tool audit logs may need promotion from sidecar JSONL into first-class operator records.
- Frontier CLI usage and cost import are provider-specific and should not be over-claimed before
  transcript/status parsing is implemented.
