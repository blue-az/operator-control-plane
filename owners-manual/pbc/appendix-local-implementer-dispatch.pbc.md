---
id: pbc_local_implementer_dispatch
title: "Local Implementer Dispatch — Behavior Contract"
context: local-lane-dispatch
status: draft
tags:
  - pbc
  - operator
  - opencode
  - local-lane
  - proposed
updated: 2026-08-23
---

# Local Implementer Dispatch — Behavior Contract

> PBC for sending a local-model seat at a ledger task without a human
> copy-pasting supervisor recaps. **Nothing in the Proposed sections is
> implemented.** Fenced as `pbc:proposed-*`. Ledger task: `proposal-lifecycle`.
>
> **Carrier: OpenCode, not opr.** `opencode run` already completes multi-step
> local jobs (gemma4:26b, 3-file edit plus verification, 2026-08-13, recorded
> on the opencode harness yaml). `opr` still exits after one state-changing
> tool (OPR-RUL-008). Building a continuation loop to make opr an implementer
> seat is the wrong investment for this problem.
>
> This contract does **not** add a progress or work-tracker record type.
> Progress is a claim or a handoff. Completion remains claim → evidence →
> verification.

## Why This Exists

On 2026-08-22 a Gemma 4 31B implementer was driven by pasted chat recaps
instead of the ledger. The recaps claimed a completed harness-R3 grid and
then froze Paper 1.45. The files did not match. Operator only saw assignment
versus closeout because nothing was written to claims or evidence.

Three product facts produced that failure:

1. `gemma4_local` is a ledger harness id, not a CLI (`README.md`).
2. `opr` cannot finish a multi-step slice in one dispatch (OPR-RUL-008).
   OpenCode already can (`opencode run`, session export).
3. A chat recap is narration. The ledger does not ingest it.

## Scope

How a local implementer is dispatched at an existing task via OpenCode, how
the seat (model) is distinguished from the harness label, and what counts as
a result.

## Non-Goals

- A new `progress` or `proposal` record type.
- Making `opr` the implementer runner. opr stays the bounded governed REPL.
  OPR continuation (010–018) is a separate product question, not a gate on
  this contract.
- Automatic routing of arbitrary work to local models.
- Changing verification UID isolation.
- Freezing Paper 1.45 from this contract.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Rules on proposed behavior, starts the OpenCode run, and verifies.
- id: grok_supervisor
  name: grok
  type: system
  description: Review harness. Writes handoffs and rulings; does not implement the grid.
- id: opencode_harness
  name: opencode
  type: external
  description: Provider-agnostic coding harness. Headless opencode run is the implementer dispatch. opencode export produces JSON evidence.
- id: gemma4_local
  name: gemma4_local
  type: system
  description: Ledger label only. Not a process. The seat is the OpenCode-configured model (e.g. gemma4:31b).
```

## Rules — as verified today

```pbc:rules
- id: LID-RUL-001
  name: Harness Id Is Not A Runner
  rule: >
    gemma4_local is a registry label (command: null). The runner that already
    completes multi-step local work is opencode. opr is not that runner.
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
    .operator/harnesses/gemma4_local.yaml lists model gemma4:26b.
    Task local-model-task-fit-r3 names the seat gemma4:31b. The yaml default
    is a fallback, not authority. OpenCode's configured model is the seat.
  trust: verified
- id: LID-RUL-004
  name: OpenCode Already Completes Multi-Step Local Jobs
  rule: >
    The opencode harness yaml records gemma4:26b completing a 3-file edit plus
    verification via opencode run (2026-08-13). audio_ports.py was written by
    qwen3.8:27b via opencode. That is existing behavior, not a proposal.
  trust: verified
```

## Proposed Rules

```pbc:proposed-rules
- id: LID-RUL-101
  name: Brief Is The Dispatch
  rule: >
    The implementer is started with opencode run, given the exported builder
    brief for the task (operator export-brief --for opencode --task <id>),
    not a pasted supervisor recap.
  trust: proposed
- id: LID-RUL-102
  name: Harness Id Is Not The Model
  rule: >
    Assign opencode as the implementer harness. The seat is the OpenCode
    model string (e.g. gemma4:31b). gemma4_local may remain a provenance
    label for the model family; it is not the runner.
  trust: proposed
- id: LID-RUL-103
  name: Slice Progress Is A Claim Plus Evidence
  rule: >
    After each measurement slice the implementer claim-add's and
    evidence-attach's the outcome JSON, and may attach opencode export
    output. Chat recap is not an acceptable substitute.
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
name: Dispatch Local Implementer From Brief Via OpenCode
actor: opencode_harness
description: Run opencode run against the exported builder brief for an assigned task, using the configured local model as the seat.
trust: proposed
```

```pbc:proposed-outcomes
- opencode run consumes .operator/briefs/<task>.opencode.export.md (or stdin of that brief).
- The seat is the OpenCode-configured model (gemma4:31b for local-model-task-fit-r3).
- Outcome JSON and optional opencode export JSON are attached as evidence on the same task.
- Paper 1.45 lifecycle is unchanged by the implementer.
- opr is not invoked for this dispatch.
```

## Open Questions For The Operator

1. Reassign `local-model-task-fit-r3` from `gemma4_local` to `opencode` now, or keep gemma4_local as a label and treat opencode as the runner only in this PBC?
2. `review_harness` is write-once (MSC-RUL-004). If the implementer harness changes, a new task may be required.

## Proof Boundary

Shows: opr is the wrong implementer carrier; OpenCode already runs multi-step local jobs; five proposed rules keep Operator as a trust ledger.

Does not show: an Operator wrapper around `opencode run`; that Gemma 4 31B will claim-add without a supervisor prompt; or that harness-R3 cells have been run.
