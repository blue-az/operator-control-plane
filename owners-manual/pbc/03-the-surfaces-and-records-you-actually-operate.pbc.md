---
id: pbc_the_surfaces_and_records_you_actually_operate
title: "The Surfaces and Records You Actually Operate — Behavior Contract Draft"
context: the-surfaces-and-records-you-actually-operate
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# The Surfaces and Records You Actually Operate — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

This chapter gives the owner the map of what is actually operated: a fixed command surface and a durable local ledger. The important part is not the command count, but which records the product creates, what it expects you to inspect, and how briefs, handoffs, sessions, and usage move context between harnesses.

## Actors

```pbc:actors
- id: product_owner
  name: Product owner
  type: human
  description: The person using the manual to understand, evaluate, and decide on the product.
- id: product_user
  name: Product user
  type: human
  description: A person who uses the product or workflow described by the codebase.
- id: product_system
  name: Product system
  type: system
  description: The code-backed system described by this manual.
- id: external_system
  name: External system
  type: external
  description: A dependency, integration, service, or repository boundary referenced by the manual.
```

## Behavior Candidate

```pbc:behavior
id: THE_SURFACES_AND_RECORDS-BHV-001
name: "The Surfaces and Records You Actually Operate"
actor: product_system
description: "This chapter gives the owner the map of what is actually operated: a fixed command surface and a durable local ledger. The important part is not the command count, but which records the product creates, what it expects you to inspect, and how briefs, handoffs, sessions, and usage move context between harnesses."
trust: provisional
```

## Section Responsibilities

```pbc:grounding
status: draft
section_responsibilities:
  - "One-Minute Snapshot"
  - "What You Should Be Able To Explain"
  - "Why the Surfaces Matter"
  - "How the Surface and Ledger Fit Together"
  - "What the Reviewed Evidence Supports"
  - "What Is Strong Here"
  - "Attention Cards"
  - "Owner Decisions"
  - "Evidence Boundary"
```

## Attention Grounding

```pbc:grounding
status: draft
attention:
  - title: "Status-bearing evidence can bypass the verifier gate when no claim is present"
    severity: "critical"
    why_it_matters: "An owner could mistake status for universal verification, but this path is narrower than it looks and can let unsupported trust state into the ledger."
  - title: "Quarantine can overwrite a task that was already terminal"
    severity: "high"
    why_it_matters: "Closeout is not one-way; an owner who treats verified or complete as final may miss a later write that changes the task state again."
  - title: "Usage import is more permissive than exact matching"
    severity: "medium"
    why_it_matters: "A caller who expects a strict one-session, one-row import may end up merging or selecting more than intended."
  - title: "Direct usage intake bypasses the session-import trail"
    severity: "medium"
    why_it_matters: "Accounting can look complete while the provenance path the owner expected is missing, which complicates review and reconciliation."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should task-bound writes keep the implicit current-task fallback, or should the owner require explicit task identifiers on every write?"
    state: "open"
    why_it_matters: "Implicit fallback is convenient, but it ties record creation to repository state in a way that can surprise a user who assumes the target task is always explicit."
  - question: "Should any status-bearing evidence write require a claim, or should bare evidence status writes remain allowed?"
    state: "open"
    why_it_matters: "This is the boundary between a record that merely exists and a record that can advance trust state."
  - question: "Should quarantine be allowed to downgrade a task that is already verified or complete?"
    state: "open"
    why_it_matters: "This determines whether closeout is final or can be revised by a later evidence write."
  - question: "Should imported usage remain permissive and placeholder-hydrating, or should it be narrowed to stricter matching and append-only behavior?"
    state: "open"
    why_it_matters: "This choice affects whether usage records optimize for smooth reconciliation or for tighter provenance and less accidental merging."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b"
  confidence: inferred
  review_status: "reviewed"
  note: "Source snapshot for the generated Owner's Manual."
```
