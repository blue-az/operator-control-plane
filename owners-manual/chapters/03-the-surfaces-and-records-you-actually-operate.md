## The Surfaces and Records You Actually Operate

_This chapter gives the owner the map of what is actually operated: a fixed command surface and a durable local ledger. The important part is not the command count, but which records the product creates, what it expects you to inspect, and how briefs, handoffs, sessions, and usage move context between harnesses._

### One-Minute Snapshot

This chapter gives the owner the map of what is actually operated: a fixed command surface and a durable local ledger. The important part is not the command count, but which records the product creates, what it expects you to inspect, and how briefs, handoffs, sessions, and usage move context between harnesses. Because no live runtime ledger snapshot is mounted here, this chapter stays at the documented category level instead of pretending to show observed live state.

### What You Should Be Able To Explain

- Recognize that operator is a fixed CLI surface, not a loose script.
- See the local ledger as the durable record surface that matters for inspection and backup.
- Understand how briefs and handoffs move context between an assigned harness and a review harness.
- Know the main record families: tasks, claims, evidence, verification, sessions, usage, briefs, and handoffs.
- Notice where this chapter relies on documented behavior rather than a live runtime snapshot.

### Why the Surfaces Matter

If you do not know which surfaces are real, you cannot tell what to inspect, what to back up, or what to review after something drifts. Here the product is not a single opaque script; it is a fixed CLI family plus a durable local ledger. That ledger is where the product remembers tasks, claims, evidence, verification, sessions, usage, briefs, and handoffs. The evidence for this chapter is bounded, and there is no live runtime ledger snapshot mounted here, so the safe reading is the documented surface, not an imagined live state.

> **Figure:** The owner should treat the CLI as a fixed front door and the ledger as the durable record surface; first-run setup lays the scaffold once, but the real operating records live in the ledger.

```mermaid
flowchart LR
  C[Closed command surface]
  I[First-run setup]
  L[Durable local ledger]
  R[Records to inspect and back up]
  C -->|writes into| L
  I -->|creates the ledger scaffold once| L
  L -->|holds| R
```

The diagram shows a fixed command surface feeding a durable local ledger. First-run setup creates the ledger scaffold once. The ledger holds the records the owner inspects and backs up.

### How the Surface and Ledger Fit Together

The command surface is a family of named entry points, and several write paths follow the current task automatically when the caller does not supply one. That makes the local ledger behave like a governed workspace, not a free-form note pad. First-run bootstrap creates the standard local ledger structure; it does not repair an already-partial tree. Briefs and handoffs are the native document flow between an assigned harness and a review harness, and the generated brief is meant to carry forward the latest handoff, the current state, and the next action. Usage has a separate path: some usage comes from imported session records, and some comes from direct usage intake. The direct path is a first-class ledger write, not a hidden side channel.

> **Figure:** Context moves through recorded briefs, handoffs, and session transitions, while usage follows a separate intake path instead of being reconstructed from memory.

```mermaid
sequenceDiagram
  participant A as Assigned harness
  participant L as Local ledger
  participant R as Review harness
  participant U as Usage intake
  A->>L: Add handoff details
  L->>L: Build the brief with the latest handoff
  L->>R: Pass the brief to the next harness
  A->>L: Start the session
  L->>L: Mark the task running and open usage
  L->>U: Record usage through its own intake path
```

An assigned harness writes handoff details into the local ledger, the ledger builds the brief and passes it to the review harness, and the session marks the task running while opening usage. Usage is recorded through its own intake path.

### What the Reviewed Evidence Supports

A task is the parent record; a claim is a tracked assertion attached to that task; a fresh claim starts unverified, with no verifier and no evidence links. Evidence can be attached to a claim, but verification is not the same thing as simply adding a record. The record families around the core lifecycle are distinct enough to matter: sessions frame activity, usage records account for it, and briefs and handoffs carry context forward. The command surface and the README use the same lifecycle vocabulary, which reduces the chance that the manual invents terms the product itself does not use.

> **Figure:** The claim-based verifier gate is narrower than a blanket evidence rule, so a status write without a claim can still change the task path without passing the same check.

```mermaid
flowchart TD
  subgraph Protected path
    C[Claim-backed evidence]
    G[Verifier gate]
    T[Task record]
    C -->|status with a claim| G
    G -->|approved write| T
  end
  B[Bare status evidence write]
  B -->|skips that gate| T
```

Claim-backed evidence goes through the verifier gate before it changes the task record. A bare status evidence write goes straight to the task record without that same gate, so verification is not universal across every evidence write.

### What Is Strong Here

The strongest part of this product is the clarity of its surface. The ledger is local and durable, so inspection, backup, and review can happen on the same machine that created the records. Bootstrap is predictable. The command surface is fixed rather than discovered at runtime. The brief and handoff flow gives the next harness something structured instead of forcing it to reconstruct context from memory. Executor stamping on operational writes gives the operator a provenance trail for most ongoing record changes.

> **Figure:** Imported usage is built for reconciliation and can fill an open placeholder instead of creating a fresh row, while direct intake writes straight to the ledger and keeps provenance simpler but less source-linked.

```mermaid
flowchart LR
  subgraph Imported path
    M[Source session details]
    I[Imported usage]
    H[Open placeholder]
    M -->|matches against| I -->|may hydrate| H
  end
  subgraph Direct path
    D[Direct usage intake]
    R[Usage ledger row]
    D -->|appends directly| R
  end
  H -->|becomes the stored row| R
```

One path imports usage from source session details, where it can fill an open placeholder and rewrite that row in place. The other path adds usage directly to the ledger as a first-class write. The owner gets smoother reconciliation on the import path and a cleaner source trail on the direct path.

### Attention Cards

Some of the most important risks are not about whether records exist, but about when the product will accept them as trustworthy. A status-bearing evidence attach only enforces the verifier gate when a claim is present, so a status write without a claim can bypass the trust check the owner may assume is universal. A late quarantine can also overwrite a task that was already terminal, so closeout is not one-way. Usage import is permissive enough to widen beyond a strict exact match, and it can rewrite an open placeholder instead of always appending a fresh row. Direct usage intake bypasses the session-import trail, which means accounting can be correct while still being disconnected from the provenance path the owner might expect.

#### ⚠ Status-bearing evidence can bypass the verifier gate when no claim is present  _(attention · critical)_

**What happens:** A status write on evidence does not automatically go through the claim-based verifier check; that trust rule only applies when a claim is supplied.

**Why it matters:** An owner could mistake status for universal verification, but this path is narrower than it looks and can let unsupported trust state into the ledger.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When surfaces and records behavior or related owner decisions change.

#### ⚠ Quarantine can overwrite a task that was already terminal  _(attention · high)_

**What happens:** A quarantine write is not blocked by prior terminal state the way verified promotion is, so late quarantine can downgrade a task.

**Why it matters:** Closeout is not one-way; an owner who treats verified or complete as final may miss a later write that changes the task state again.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When surfaces and records behavior or related owner decisions change.

#### ⚠ Usage import is more permissive than exact matching  _(attention · medium)_

**What happens:** Usage import can match by more than exact session ID and can hydrate an existing open placeholder instead of always creating a fresh row.

**Why it matters:** A caller who expects a strict one-session, one-row import may end up merging or selecting more than intended.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When surfaces and records behavior or related owner decisions change.

#### ⚠ Direct usage intake bypasses the session-import trail  _(attention · medium)_

**What happens:** Usage added directly is a first-class ledger write, but it does not carry the same source-session provenance as imported usage.

**Why it matters:** Accounting can look complete while the provenance path the owner expected is missing, which complicates review and reconciliation.

**What to do:** Review this boundary and decide whether the current behavior is intentional.

**Revisit when:** When surfaces and records behavior or related owner decisions change.

### Owner Decisions

Before relying on this chapter operationally, the owner should decide how strict the local workflow needs to be. If current-task fallback is convenient, task-bound writes can stay implicit; if not, the workflow should require explicit task identifiers. If the product must never accept a status-bearing evidence attach without a claim, that behavior needs to be treated as a boundary, not a convenience. If a verified or complete task must not move back to quarantined, then quarantine needs stricter handling. If imported usage should remain merge-friendly and permissive, the current import behavior may be acceptable; if not, it should be narrowed to more exact matches and clearer provenance rules.

#### ⚖ Should task-bound writes keep the implicit current-task fallback, or should the owner require explicit task identifiers on every write?  _(owner decision · open)_

**Why it matters:** Implicit fallback is convenient, but it ties record creation to repository state in a way that can surprise a user who assumes the target task is always explicit.

**Revisit when:** Before changing the related surfaces and records behavior.

#### ⚖ Should any status-bearing evidence write require a claim, or should bare evidence status writes remain allowed?  _(owner decision · open)_

**Why it matters:** This is the boundary between a record that merely exists and a record that can advance trust state.

**Revisit when:** Before changing the related surfaces and records behavior.

#### ⚖ Should quarantine be allowed to downgrade a task that is already verified or complete?  _(owner decision · open)_

**Why it matters:** This determines whether closeout is final or can be revised by a later evidence write.

**Revisit when:** Before changing the related surfaces and records behavior.

#### ⚖ Should imported usage remain permissive and placeholder-hydrating, or should it be narrowed to stricter matching and append-only behavior?  _(owner decision · open)_

**Why it matters:** This choice affects whether usage records optimize for smooth reconciliation or for tighter provenance and less accidental merging.

**Revisit when:** Before changing the related surfaces and records behavior.

### Evidence Boundary

> **Evidence boundary** — Reviewed:
- The reviewed evidence covers a fixed command family, a local durable ledger, and the native record categories that the owner is expected to inspect.
- It also covers first-run bootstrap, task-bound writes, claim creation, evidence and verification behavior, briefs and handoffs, usage intake and import, and the diagnostic checks that surface drift.
- The reviewed material is enough to describe the documented operating surfaces, but not enough to pretend there is a live runtime example in this chapter.

Not reviewed:
- No live local ledger snapshot was mounted for this stage.
- No runtime session log corpus from the host environment was mounted for this stage.
- Owner interview answers and product-intent framing were not supplied for this run.

Compare the current executable and documentation with a live local ledger snapshot and a real session log from the same environment. Then confirm that the command surface, bootstrap behavior, task binding, brief and handoff flow, usage intake, and diagnostic checks still match the record categories described here.

> Reviewed: blue-az/operator-control-plane repository snapshot, Founder/owner context

> Not reviewed: External runtime and integrations, Unreviewed runtime and owner context
