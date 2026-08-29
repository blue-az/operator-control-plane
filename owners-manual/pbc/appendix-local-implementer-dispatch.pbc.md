---
id: pbc_local_implementer_dispatch
title: "Local Implementer Dispatch — Behavior Contract"
context: local-lane-dispatch
status: draft
tags:
  - pbc
  - operator
  - opencode
  - pi
  - local-lane
  - proposed
updated: 2026-08-28
---

# Local Implementer Dispatch — Behavior Contract

> PBC for sending a local-model seat at a ledger task without a human
> copy-pasting supervisor recaps. Ledger task: `proposal-lifecycle`.
> LID-RUL-101–105 ratified 2026-08-23 (`trust: provisional`, claim-0077).
> LID-BHV-001 and its outcomes remain proposed; brief dispatch is not
> implemented. No opr continuation.
>
> **Carrier superseded 2026-08-28: `pi`, not OpenCode.** The rules below were
> ratified 2026-08-23 against an OpenCode carrier and are retained verbatim as
> the record of that ratification — `trust: verified` entries (LID-RUL-001–004)
> are *observations of runs that actually happened on OpenCode*, and rewriting
> them would falsify evidence. Read every "opencode run" in the ratified rules
> as naming the carrier of record at that date. The live carrier is now `pi`
> (migrated `ed22df8`, 2026-08-27), which drives any model it is pointed at,
> Claude only in extra-usage mode. OpenCode is deprecated as the carrier but not
> disallowed and may earn a seat back. Whether pi can drive grok or gemini-agy
> is untested; neither is in use. **LID-RUL-101–105 and LID-BHV-001 need
> re-ratification against pi before they bind.**
>
> **Carrier: not opr.** `opr` exits after one state-changing tool
> (OPR-RUL-008); it now exits 2 with a deprecation notice. Building a
> continuation loop to make opr an implementer seat is the wrong investment.
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

How an implementer is dispatched at an existing task via the carrier of record,
how the seat (model) is distinguished from the harness label, and what counts as
a result. Ratified below against OpenCode; the live carrier is `pi`.

## Non-Goals

- A new `progress` or `proposal` record type.
- Making `opr` the implementer runner. `opr` is deprecated; `pi` is the
  carrier (OpenCode was, through 2026-08-27). OPR continuation (010–018) is
  rejected, not deferred.
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
  description: Provider-agnostic coding harness. Carrier of record for the 2026-08-23 ratification; headless opencode run was the implementer dispatch. Deprecated as carrier 2026-08-28, not disallowed.
- id: pi_harness
  name: pi
  type: external
  description: Live implementer carrier as of 2026-08-27 (ed22df8). Drives any model it is pointed at, Claude only in extra-usage mode. Dispatch rules not yet re-ratified against it.
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
- id: LID-RUL-101
  name: Brief Is The Dispatch
  rule: >
    The implementer is started with opencode run, given the exported builder
    brief for the task (operator export-brief --for opencode --task <id>),
    not a pasted supervisor recap.
  trust: provisional
- id: LID-RUL-102
  name: Harness Id Is Not The Model
  rule: >
    Assign opencode as the implementer harness. The seat is the OpenCode
    model string (e.g. gemma4:31b). gemma4_local may remain a provenance
    label for the model family; it is not the runner.
  trust: provisional
- id: LID-RUL-103
  name: Slice Progress Is A Claim Plus Evidence
  rule: >
    After each measurement slice the implementer claim-add's and
    evidence-attach's the outcome JSON, and may attach opencode export
    output. Chat recap is not an acceptable substitute.
  trust: provisional
- id: LID-RUL-104
  name: Implementer Does Not Write Lifecycle
  rule: >
    The local implementer does not edit PAPERS_MANIFEST.json lifecycle or
    publication_status, does not delete a numbered inventory draft card, and
    does not pass --status on evidence-attach.
  trust: provisional
- id: LID-RUL-105
  name: Partial Runs Are Named Partial
  rule: >
    A run that covers a subset of cells must be claimed as that subset.
    Aggregating unrelated outcome directories into a freeze number is a
    narration failure, not a result.
  trust: provisional
```

## Proposed behavior (not yet implemented)

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

Shows: opr is the wrong implementer carrier; OpenCode already runs multi-step local jobs; five provisional rules keep Operator as a trust ledger.

Does not show: an Operator wrapper around the carrier; that Gemma 4 31B will claim-add without a supervisor prompt; that harness-R3 cells have been run; or that any rule here holds under the `pi` carrier — LID-RUL-101–105 were ratified against OpenCode and are unverified against pi.
