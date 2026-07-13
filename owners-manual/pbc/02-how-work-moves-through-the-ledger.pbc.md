---
id: pbc_how_work_moves_through_the_ledger
title: "How Work Moves Through the Ledger — Behavior Contract Draft"
context: how-work-moves-through-the-ledger
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# How Work Moves Through the Ledger — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

The product matters to the owner because it turns work into a governed record instead of a pile of loosely related notes. A task becomes a claim when an assigned harness says what it did, evidence supports that claim, and verification is the separate trust step that decides whether the claim should be treated as trusted.

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
id: HOW_WORK_MOVES_THROUGH_T-BHV-001
name: "How Work Moves Through the Ledger"
actor: product_system
description: "The product matters to the owner because it turns work into a governed record instead of a pile of loosely related notes. A task becomes a claim when an assigned harness says what it did, evidence supports that claim, and verification is the separate trust step that decides whether the claim should be treated as trusted."
trust: provisional
```

## Section Responsibilities

```pbc:grounding
status: draft
section_responsibilities:
  - "One-Minute Snapshot"
  - "What You Should Be Able To Explain"
  - "Mental Model"
  - "How It Works"
  - "Verified Facts"
  - "Strengths"
  - "Attention Cards"
  - "Owner Decisions"
  - "Evidence Boundary"
```

## Attention Grounding

```pbc:grounding
status: draft
attention:
  - title: "Claim status checks are not blanket checks"
    severity: "critical"
    why_it_matters: "If the owner assumes every status write is equally protected, they can overestimate how much the ledger is actually enforcing."
  - title: "A late quarantine can overwrite terminal task state"
    severity: "high"
    why_it_matters: "Closeout is not one-way here. A later quarantine can downgrade a task the owner thought was already finished."
  - title: "Usage import can match more than one shape of source"
    severity: "medium"
    why_it_matters: "Accounting can merge into an existing record instead of creating a fresh one, so a casual import assumption can hide a rewrite."
  - title: "Bootstrap is not a repair path"
    severity: "medium"
    why_it_matters: "A broken local setup may look initialized enough to proceed while still missing parts the workflow depends on."
  - title: "Direct usage intake bypasses session provenance"
    severity: "medium"
    why_it_matters: "The owner should treat direct usage intake as a first-class accounting write, not as imported history with the same provenance shape."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should the manual treat claim-backed evidence status as the only trusted status path?"
    state: "resolved"
    why_it_matters: "Resolved: every status-bearing evidence write requires a claim, and only enforced verification by a distinct registered verifier UID is trusted; other usable verification is advisory."
  - question: "Should a late quarantine be allowed to override a task that already looks complete or verified?"
    state: "open"
    why_it_matters: "This is a closeout policy decision. It controls whether terminal task state is reversible when a later evidence update arrives."
  - question: "Should usage import stay permissive and able to hydrate an open placeholder?"
    state: "open"
    why_it_matters: "This determines whether usage accounting is an append-oriented history or a merge-oriented correction path."
  - question: "Should direct usage intake remain separate from session import provenance?"
    state: "open"
    why_it_matters: "This decides whether manual usage is a distinct accounting path or just another view of imported session history."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b"
  confidence: inferred
  review_status: "reviewed"
  note: "Source snapshot for the generated Owner's Manual."
```
