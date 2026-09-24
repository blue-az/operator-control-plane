---
id: pbc_op_life_boat
title: "/op:life-boat — Doom Loop Escape Behavior Contract"
context: pi-operator-extension
status: draft
tags:
  - pbc
  - operator
  - pi
  - extension
  - doom-loop
  - proposed
updated: 2026-09-23
---

# /op:life-boat — Doom Loop Escape Behavior Contract

> Draft PBC for a Pi extension command the operator runs when they suspect the agent
> is in a doom loop: cycling through 5+ variations of the same fixes because earlier
> failed attempts have fallen out of its working context.
>
> The command packages an escape pattern Erik has used by hand since early 2026:
>
> 1. Tell the agent you suspect a doom loop.
> 2. Have it summarize every attempt in context and commit that record outside the session.
> 3. Spin up a fresh supervisor to review the committed record.
> 4. The supervisor directs the original agent to the next attempt.
> 5. Repeat as needed.
>
> **Nothing here is implemented.** All new behavior is fenced `pbc:proposed-*`. This
> charter inherits every rule of `appendix-pi-operator-extension.pbc.md`. Where they
> conflict, that charter wins.

## Purpose

Break a doom loop by moving the memory of what failed out of the looping context, into
a record that a fresh reviewer and every later agent can read. Rejected attempts should
stay rejected. The operator should not have to remember them.

## Scope

- One slash command, `/op:life-boat`, in the project-local Pi extension.
- Composition of existing moves: `/op:crystal`, `/op:crystal-attach`, the
  `targets.json` registry, the harness adapter, and `/op:handoff`.
- One new artifact shape: the attempt log, carried inside a crystal.
- One new adapter role for a read-only supervisor, if the existing reviewer path cannot
  be reused (see Open Risks).

## Non-Goals

- **Automatic loop detection.** The tell is the operator's déjà vu. The model may
  *suggest* a life-boat, but it never launches one.
- **Verification.** Supervisor output is direction, not a verdict. It is never
  evidence that the problem is fixed.
- **Rewriting or reverting the operator's code.** No `git reset`, `stash`, `checkout`,
  or commit of work-in-progress source happens inside this command.
- **A second ledger.** Life-boat state lives in crystals and existing ledger records
  only (POE-RUL-101).
- **Replacing `/op:supervisor-review`.** That reviews one finished claim. A life-boat
  reviews an unfinished, stuck line of work. They stay separate commands.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Suspects the loop, launches the life-boat, reviews the attempt log, and decides whether to accept the supervisor's direction.
- id: looping_agent
  name: Looping agent
  type: system
  description: The Pi agent that has been cycling. Holds the attempt history in its context, which is the only place most of it exists when the life-boat starts.
- id: fresh_supervisor
  name: Fresh supervisor
  type: system
  description: A new session from a registered target. Reads only the committed record and the repo. Never inherits the looping context.
- id: operator_cli
  name: Operator CLI
  type: system
  description: ./operator. Records the crystal attachment and handoff. Source of truth.
- id: agent_crystallize
  name: agent-crystallize
  type: external
  description: Writes the crystal that carries the attempt log.
```

## Proposed Rules

```pbc:proposed-rules
- id: LB-RUL-001
  name: Human Launches, Model May Only Suggest
  rule: >
    /op:life-boat is a slash command (POE-RUL-103). No structured tool launches it.
    The Pi agent may tell the operator that it is proposing something that resembles
    an earlier attempt, and suggest a life-boat. The decision stays with the operator.
  trust: proposed
- id: LB-RUL-002
  name: Stop Before Summarizing
  rule: >
    On launch, the looping agent stops editing. No further code changes happen until
    the life-boat closes or the operator cancels it. A loop that keeps running while
    it is being summarized produces a stale log.
  trust: proposed
- id: LB-RUL-003
  name: The Attempt Log Is The Core Artifact
  rule: >
    The looping agent writes one entry per distinct attempt: what it tried, what
    changed, what happened, and why it was abandoned. Variations of the same idea are
    grouped under one attempt with the variations listed. It also states the current
    working hypothesis and anything it believes is still untested.
  trust: proposed
- id: LB-RUL-004
  name: The Operator Reviews The Log Before It Is Committed
  rule: >
    The attempt log opens in an editor for the operator before anything is written,
    the same way /op:crystal reviews session notes. A looping agent's summary of its
    own loop is the least trustworthy summary available. It may drop attempts or
    describe them as closer to working than they were.
  trust: proposed
- id: LB-RUL-005
  name: Commit The Record, Not The Code
  rule: >
    The reviewed log is written as a crystal via /op:crystal, including a "Rejected
    Attempts" section, and attached to the active task via /op:crystal-attach on
    confirmation. The crystal records git HEAD and a diff stat of the working tree so
    the reviewer knows the state it describes. The operator's source changes are not
    committed, stashed, or reverted.
  trust: proposed
- id: LB-RUL-006
  name: The Supervisor Is Fresh
  rule: >
    The supervisor runs in a new session from a target registered in targets.json. It
    is never the looping session, and it receives no transcript from it. Its inputs
    are the committed crystal, the task, and read access to the repo. The same
    model or vendor is allowed. Freshness is the requirement, not a different vendor.
  trust: proposed
- id: LB-RUL-007
  name: The Supervisor Directs, It Does Not Implement
  rule: >
    The supervisor is read-only. It returns a diagnosis, the single next attempt it
    recommends, and a do-not-retry list naming which logged attempts are ruled out and
    why. It does not edit files, add claims, attach evidence, or set status.
  trust: proposed
- id: LB-RUL-008
  name: Rejected Attempts Carry Forward
  rule: >
    The do-not-retry list goes to the implementer with the direction. If the
    implementer later proposes something the list names, it must say so and state
    what is different this time. Proposing a rejected attempt again without citing it
    is the loop resuming.
  trust: proposed
- id: LB-RUL-009
  name: The Operator Chooses Who Implements Next
  rule: >
    Default is the original agent with the direction and do-not-retry list appended,
    because it holds working knowledge of the code. The operator may choose a fresh
    implementer through /op:delegate instead. Neither choice is automatic.
  trust: proposed
- id: LB-RUL-010
  name: Two Life-Boats On One Task Escalate To The Operator
  rule: >
    A second life-boat on the same task within one session does not send a third
    supervisor automatically. It shows the operator both crystals and both directions
    side by side. Repeated life-boats on one problem are themselves a loop.
  trust: proposed
- id: LB-RUL-011
  name: Closeout Is A Handoff
  rule: >
    When the operator ends the life-boat, it closes with /op:handoff naming the
    crystal, the direction taken, and who implements next. Cancelling part way still
    leaves the crystal if one was written.
  trust: proposed
```

## Proposed Behaviors

```pbc:proposed-behavior
id: LB-BHV-001
name: Launch And Freeze
actor: operator_user
description: Operator runs /op:life-boat. The extension confirms the active task, tells the looping agent to stop editing, and asks it for the attempt log.
trust: proposed
```

```pbc:proposed-outcomes
- Launch requires an active task selected with /op:use. No task means no life-boat.
- The looping agent makes no file edits between launch and closeout or cancel.
- The launch is visible in the session, and the operator can cancel at any step.
```

```pbc:proposed-behavior
id: LB-BHV-002
name: Capture And Review The Attempt Log
actor: looping_agent
description: The looping agent drafts the attempt log per LB-RUL-003. It opens in an editor for the operator to correct, add missing attempts, or reject.
trust: proposed
```

```pbc:proposed-outcomes
- Each attempt has: what was tried, what changed, the result, why it was abandoned.
- The operator's edits are what gets committed, not the agent's first draft.
- An empty or single-attempt log shows a warning. It may not be a loop.
```

```pbc:proposed-behavior
id: LB-BHV-003
name: Commit The Record
actor: agent_crystallize
description: The reviewed log is written as a crystal with a Rejected Attempts section, git HEAD and a working-tree diff stat, then attached to the task on confirmation.
trust: proposed
```

```pbc:proposed-outcomes
- Crystal is written through the existing /op:crystal path.
- Attachment goes through /op:crystal-attach with its usual confirmation and provenance checks.
- git status shows no change to tracked source files caused by the life-boat.
```

```pbc:proposed-behavior
id: LB-BHV-004
name: Fresh Supervisor Review
actor: fresh_supervisor
description: The operator picks a registered target. A new read-only session gets the crystal, the task, and repo access, and returns diagnosis, one next attempt, and a do-not-retry list.
trust: proposed
```

```pbc:proposed-outcomes
- Target chooser excludes the looping session. Unknown targets fail closed (POE-RUL-108).
- The supervisor session has no write access to the working tree or the ledger.
- Output is shown to the operator as direction, labeled as not evidence.
```

```pbc:proposed-behavior
id: LB-BHV-005
name: Direct The Implementer
actor: operator_user
description: The operator accepts, edits, or rejects the direction, then chooses the original agent or a fresh implementer via /op:delegate. The direction and do-not-retry list are handed over.
trust: proposed
```

```pbc:proposed-outcomes
- The original agent resumes with the direction and do-not-retry list in its context.
- A fresh implementer receives the same two items in its brief.
- The life-boat closes with /op:handoff per LB-RUL-011.
```

## Grounding

```pbc:grounding
status: draft
reuses:
  - /op:use: active task required at launch
  - /op:crystal: crystal capture with editor review, agent-crystallize (extension pins 0.1.16)
  - /op:crystal-attach: ledger attachment with confirmation and provenance check
  - targets.json: registered supervisor targets, shared with /op:delegate
  - /op:delegate: optional fresh implementer
  - /op:handoff: closeout record
new:
  - /op:life-boat: slash command, human-launched only
  - attempt log shape: carried in a crystal "Rejected Attempts" section
  - read-only supervisor role: adapter support to confirm (see Open Risks)
origin:
  - "LinkedIn comment, 2026-02-28: doom loop escape pattern, five steps"
  - "LinkedIn comment, 2026-05-31: after try 3, log attempts and spin up a supervisor"
related:
  - "stewie-sh/pbc-spec#12: proposed `rejected` trust level, the same idea for rules"
```

## Provenance

```pbc:provenance
- ref: "owners-manual/pbc/appendix-pi-operator-extension.pbc.md"
  confidence: verified
  review_status: "active"
  note: "Parent charter. POE-RUL-101 (no second ledger), -102 (never reuse the current agent as reviewer), -103 (slash commands are human ergonomics), -108 (registered targets, fail closed)."
- ref: ".pi/extensions/operator/README.md"
  confidence: verified
  review_status: "active"
  note: "Shipped command inventory: /op:crystal, /op:crystal-attach, /op:delegate, /op:handoff, /op:targets exist. No /op:life-boat."
- ref: "LinkedIn comments 2026-02-28 and 2026-05-31 (data export)"
  confidence: verified
  review_status: "active"
  note: "The manual escape pattern this command packages."
```

## Open Risks

- **The looping agent writes its own log.** LB-RUL-004 puts the operator in front of
  it, but operators skim when tired, and a loop usually means tired. A cheap check: the
  supervisor may flag attempts that the diff or file history shows but the log leaves out.
- **Read-only supervisor may need a new adapter role.** The adapter has an IMPLEMENTER
  role today. `/op:supervisor-review` is claim-scoped and needs a verify command, so it
  does not fit an unfinished line of work. Whether to extend the review bundle or add a
  SUPERVISOR role is undecided.
- **"Stop editing" is an instruction, not an enforcement.** Pi may have no way to block
  the agent's tools while the life-boat is open. If it can't, LB-RUL-002 is advisory
  and should say so.
- **The do-not-retry list can go stale.** An attempt that failed for an environmental
  reason may be right later. LB-RUL-008 allows a retry with a stated difference rather
  than banning it.
- **Crystal format has no Rejected Attempts section.** agent-crystallize's default
  template does not include one, so the section is freehand until the format adopts one.
  It's the same gap as pbc-spec#12.
