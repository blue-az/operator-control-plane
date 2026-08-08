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
- id: OPR-RUL-008
  name: State-Changing Tools Terminate The Agent Loop
  rule: A successful write_file, patch_file, or run_command ends the agent loop immediately and returns to the caller; only read-only tools accumulate context and continue to the next turn. The loop is additionally bounded at 10 turns.
  trust: trusted
- id: OPR-RUL-009
  name: Identical Tool Calls Are Not Re-Executed
  rule: A tool call whose full JSON fingerprint has already been handled in this loop must halt the loop rather than execute again.
  trust: trusted
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

```pbc:behavior
id: OPR-BHV-004
name: Terminate On State Change
actor: opr_client
description: End the agent loop and return control after the first successful state-changing tool call.
trust: trusted
```

```pbc:outcomes
- A successful run_command returns "[Tool completed: run_command]" and the loop exits.
- The model is not re-prompted, so a task requiring N sequential shell commands completes at most its first.
- This bounds unsupervised chaining of state-changing actions to exactly one per dispatch.
- Multi-step CLI tasks are therefore out of scope for a single opr dispatch by construction, independent of model capability.
```

## Proposed Amendment: Supervised Continuation Loop

> **NOT IMPLEMENTED.** The blocks below are deliberately fenced as
> `pbc:proposed-*` rather than `pbc:rules` / `pbc:behavior` so contract
> tooling does not read them as active behavior. Promote them to the live
> blocks only when the implementation lands and is verified. See
> `docs/OPR_CONTINUATION_LOOP_SPEC.md`.

Motivation: OPR-RUL-008 was written to bound unsupervised chaining of
destructive actions, which is a sound safety property. Its side effect is
that no multi-step CLI task can ever complete in one dispatch. Observed
2026-08-07: a three-step git task (`add` / `commit` / verify) completed only
step 1, and this was initially and wrongly attributed to model truncation.
The amendment must preserve the safety property while removing the
structural ceiling.

```pbc:proposed-rules
- id: OPR-RUL-010
  name: Continuation Requires Per-Call Consent
  rule: Continuing after a state-changing tool must not weaken the existing per-call confirmation gate; every subsequent state-changing call requires its own confirmation.
  trust: proposed
- id: OPR-RUL-011
  name: Continuation Is Bounded
  rule: A dispatch must declare a maximum number of state-changing calls; exceeding it halts the loop and returns partial-completion status rather than continuing.
  trust: proposed
- id: OPR-RUL-012
  name: Completion Is Explicit
  rule: The loop must terminate on an explicit model-emitted completion signal or on the step budget, never on the mere success of a state-changing call.
  trust: proposed
  note: >
    Measurement 2026-08-07 (gemma4:26b, n=5, three-step git task) found the commit landed and the
    tree was clean in 5/5 trials while task_complete was emitted in only 1/5. Treating an absent
    signal as failure therefore produces false negatives at a 4-in-5 rate. Amend before
    implementation hardens: the signal should be a hint, and authority for "done" should move to a
    caller-supplied success predicate per OPR-RUL-018.
- id: OPR-RUL-018
  name: Completion Is Verified By Predicate, Not Self-Report
  rule: Where the caller supplies a success predicate, that predicate is authoritative for completion status; a model-emitted task_complete is advisory only and must never override a failing predicate.
  trust: proposed
- id: OPR-RUL-013
  name: Partial Completion Is Reported, Not Masked
  rule: A dispatch that ends without a completion signal must return a distinguishable partial status naming which steps ran, so callers can detect supervisor substitution rather than reading it as success.
  trust: proposed
- id: OPR-RUL-014
  name: Confirmation Waiver Is Per-Invocation
  rule: The confirmation waiver (--dangerous) must be settable only as a command-line flag for a single run; it must be rejected if present in a config file, so it cannot be left enabled and forgotten.
  trust: proposed
- id: OPR-RUL-015
  name: Waiving Review Does Not Waive Bounding
  rule: The confirmation waiver must not widen the workspace boundary (OPR-RUL-003) or lift the state-change budget (OPR-RUL-011); it removes the prompt only.
  trust: proposed
- id: OPR-RUL-016
  name: Confirmation Mode Is Recorded And Taints Provenance
  rule: Every governed session must record confirmation_mode as interactive, allowlist, or bypassed; evidence attached from a bypassed session must surface that mode at verification time so unreviewed output cannot be laundered into the claims ledger as reviewed work.
  trust: proposed
- id: OPR-RUL-017
  name: Waiver Discloses Its Blast Radius
  rule: On invocation the waiver must report the executing identity and whether the operator-builder deny-read set (SSH keys, ledgers, sensor data) currently holds, so the difference between waiving review under UID isolation and waiving it as the full user is visible at point of use.
  trust: proposed
```

```pbc:proposed-behavior
id: OPR-BHV-005
name: Supervised Multi-Step Continuation
actor: opr_client
description: After a state-changing tool succeeds, feed its output back as context and re-prompt for the next step until an explicit completion signal or the step budget is reached.
trust: proposed
```

```pbc:proposed-outcomes
- Tool output from a state-changing call is appended to accumulated context rather than returned.
- Each subsequent state-changing call re-enters the existing confirmation gate.
- The loop halts on an explicit completion signal, the state-change budget, the existing 10-turn cap, or a failed call.
- The return value distinguishes completed / partial / halted-on-budget / failed.
- Opt-in: the current terminate-on-state-change behavior remains the default until this is verified.
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
- ref: "opr:828-884"
  confidence: verified
  review_status: "active"
  note: "run_agent_loop. Source of OPR-RUL-008 (terminal_tools at line 831, early return at 874), OPR-RUL-009 (seen_tool_calls fingerprint halt), and the 10-turn cap at line 828."
```

## Open Risks

- Tool audit logs may need promotion from sidecar JSONL into first-class operator records.
- Frontier CLI usage and cost import are provider-specific and should not be over-claimed before
  transcript/status parsing is implemented.
- **OPR-RUL-008 is a capability ceiling that reads as a model defect.** Because the loop exits on the
  first successful `run_command`, a multi-step CLI dispatch returns after step 1 with a success-shaped
  message (`[Tool completed: run_command]`). On 2026-08-07 this was misdiagnosed as the local model
  truncating. Any evaluation of local-model agentic capability run through `opr` before the continuation
  amendment lands is measuring the harness, not the model, and should be re-run before it is cited.
- No metric currently distinguishes "task completed" from "harness returned after step 1." Until
  OPR-RUL-013 exists, supervisor substitution is invisible in the ledger.
