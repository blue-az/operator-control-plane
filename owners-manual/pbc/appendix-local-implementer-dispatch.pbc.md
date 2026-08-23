---
id: pbc_local_implementer_dispatch
title: "Local Implementer Dispatch — Behavior Contract"
context: local-lane-dispatch
status: draft
tags:
  - pbc
  - operator
  - opr
  - local-lane
  - proposed
updated: 2026-08-22
---

# Local Implementer Dispatch — Behavior Contract

> PBC for sending a local-model seat at a ledger task without a human
> copy-pasting supervisor recaps. **Nothing in the Proposed sections is
> implemented.** Fenced as `pbc:proposed-*` so contract tooling does not
> read them as active. Ledger task: `proposal-lifecycle`.
>
> This contract does **not** add a progress or work-tracker record type.
> Progress is a claim or a handoff. Completion remains claim → evidence →
> verification.

## Why This Exists

On 2026-08-22 a Gemma 4 31B implementer was driven by pasted chat recaps
instead of the ledger. The recaps claimed a completed harness-R3 grid and
then froze Paper 1.45. The files did not match: `r3_grid_comparison.py`
still had no harness-applied arm, and "142 outcome records" was 136 raw
reruns plus 6 mute tool-call cells. Operator only saw assignment versus
closeout because nothing was written to claims or evidence.

Three product facts produced that failure:

1. `gemma4_local` is a ledger harness id, not a CLI (`README.md`).
2. `opr` exits after one state-changing tool (OPR-RUL-008), so a local
   implementer cannot finish a multi-step slice in one dispatch until the
   continuation amendment is ratified.
3. A chat recap is narration. The ledger does not ingest it.

## Scope

How a local implementer is dispatched at an existing task, how the seat
(model) is distinguished from the harness label, and what counts as a
result.

## Non-Goals

- A new `progress` or `proposal` record type.
- Automatic routing of arbitrary work to local models.
- Changing verification UID isolation.
- Replacing `operator` with `opr`.
- Freezing Paper 1.45 from this contract.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Rules on proposed behavior, starts the local session, and verifies.
- id: grok_supervisor
  name: grok
  type: system
  description: Review harness. Writes handoffs and rulings; does not implement the grid.
- id: gemma4_local
  name: gemma4_local
  type: system
  description: Ledger harness label for local Gemma 4. Not a process. The seat is the model named on the session.
- id: opr_client
  name: opr
  type: system
  description: Governed local client that must load the builder brief by task id.
```

## Rules — as verified today

```pbc:rules
- id: LID-RUL-001
  name: Harness Id Is Not A Runner
  rule: >
    gemma4_local (and other *_local ids) are registry labels. Dispatching work
    still requires opr or an ollama runner. Tested by README and harness yaml
    (command: null).
  trust: verified
- id: LID-RUL-002
  name: Recaps Are Not Results
  rule: >
    Operator records tasks, claims, evidence, verification, handoffs, and
    sessions. A paste in chat does not create any of those. Observed 2026-08-22
    when freeze recaps never entered the ledger.
  trust: verified
- id: LID-RUL-003
  name: Yaml Default Model Must Not Be Read As The Seat
  rule: >
    .operator/harnesses/gemma4_local.yaml currently lists model gemma4:26b.
    Task local-model-task-fit-r3 names the seat gemma4:31b. The yaml default
    is a fallback, not authority.
  trust: verified
```

## Proposed Rules

```pbc:proposed-rules
- id: LID-RUL-101
  name: Brief Is The Dispatch
  rule: >
    opr --task <id> loads the builder brief for the assigned local harness
    and runs the session model named on the task or session, not a pasted
    supervisor recap.
  trust: proposed
- id: LID-RUL-102
  name: Harness Id Is Not The Model
  rule: >
    The ledger harness_id identifies the registry entry. The seat is the
    model string on the session (e.g. gemma4:31b). A yaml default must not
    override an explicit session or task seat.
  trust: proposed
- id: LID-RUL-103
  name: Slice Progress Is A Claim Plus Evidence
  rule: >
    After each --model --mode measurement slice the implementer claim-add's
    and evidence-attach's the outcome JSON. Chat recap is not an acceptable
    substitute.
  trust: proposed
- id: LID-RUL-104
  name: Implementer Does Not Write Lifecycle
  rule: >
    The local implementer does not edit PAPERS_MANIFEST.json lifecycle or
    publication_status, does not delete a numbered inventory draft card, and
    does not pass --status on evidence-attach.
  trust: proposed
- id: LID-RUL-105
  name: Partial Runs Are Named Partial
  rule: >
    A run that covers a subset of cells must be claimed as that subset.
    Aggregating unrelated outcome directories into a freeze number is a
    narration failure, not a result.
  trust: proposed
```

```pbc:proposed-behavior
id: LID-BHV-001
name: Dispatch Local Implementer From Brief
actor: opr_client
description: Start a governed local session for an assigned task by loading the builder brief and the session model.
trust: proposed
```

```pbc:proposed-outcomes
- opr --task local-model-task-fit-r3 starts gemma4:31b against the exported builder brief.
- The implementer need not receive a pasted recap to know the next action.
- Outcome JSON files are attached as evidence on the same task.
- Paper 1.45 lifecycle is unchanged by the implementer.
```

## Open Questions For The Operator

1. Ship `opr --task` before or after ratifying OPR continuation (010–018)? Continuation is what makes a multi-step slice possible in one dispatch; brief-loading without continuation still dies after the first write.
2. Should LID-RUL-102 live in the harness yaml (explicit `model` override per session) or only in opr flags?

## Proof Boundary

Shows: the 2026-08-22 copy-paste failure, the three product facts that caused it, and five proposed rules that keep Operator as a trust ledger while making local dispatch usable.

Does not show: that `opr --task` exists, that Gemma 4 31B will claim-add without a supervisor prompt, or that harness-R3 cells have been run.
