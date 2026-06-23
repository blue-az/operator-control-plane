---
id: pbc_sessions_usage_and_accountability
title: "Sessions, Usage, and Accountability — Behavior Contract Draft"
context: sessions-usage-and-accountability
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# Sessions, Usage, and Accountability — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

Sessions are the accountability wrapper around governed work. For the operator, usage is a way to explain what happened and when, not the product's center. A session opens usage, writes the brief that hands the task to the next harness, and closes usage when the work stops. Imported usage can pull external session history into the ledger; direct usage entries remain a separate write path.

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
id: SESSIONS_USAGE_AND_ACCOU-BHV-001
name: "Sessions, Usage, and Accountability"
actor: product_system
description: "Sessions are the accountability wrapper around governed work. For the operator, usage is a way to explain what happened and when, not the product's center. A session opens usage, writes the brief that hands the task to the next harness, and closes usage when the work stops. Imported usage can pull external session history into the ledger; direct usage entries remain a separate write path."
trust: provisional
```

## Section Responsibilities

```pbc:grounding
status: draft
section_responsibilities:
  - "One-Minute Snapshot"
  - "What You Should Be Able To Explain"
  - "The role sessions play"
  - "How sessions and usage move together"
  - "What is actually recorded"
  - "What this layer does well"
  - "Attention Cards"
  - "Owner Decisions"
  - "Evidence Boundary"
```

## Attention Grounding

```pbc:grounding
status: draft
attention:
  - title: "Import matching can pull in more than one source"
    severity: "medium"
    why_it_matters: "If the operator assumes one exact session is being imported, the ledger can pick a different record and make the usage trail look cleaner or messier than reality."
  - title: "Manual usage entries do not carry the same source trail"
    severity: "high"
    why_it_matters: "A later review can mistake a direct entry for imported accounting unless the owner keeps the two habits distinct."
  - title: "Session closeout can change the final task state"
    severity: "high"
    why_it_matters: "If closeout conventions are loose, the final state in the ledger may reflect the last closeout action rather than the full work history."
  - title: "Import fidelity depends on external session logs"
    severity: "medium"
    why_it_matters: "When the source data is missing or inconsistent, the ledger can only account for what it can see, not the full runtime history."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should manual usage entries stay as a separate direct-write path, or should every usage row be normalized around imported session records?"
    state: "open"
    why_it_matters: "The choice sets whether usage is a flexible accounting input or a more uniform audit trail. Mixing both habits without a rule makes later review harder."
  - question: "Should session import keep its permissive matching and fallback behavior, or should it require one exact source session?"
    state: "open"
    why_it_matters: "This choice decides whether the owner favors operational tolerance or import precision. A permissive selector reduces friction, but it also raises the chance of pulling the wrong session into the ledger."
  - question: "Should closeout keep the automatic fallback to assigned when usage ends, or should every closeout require an explicit final state?"
    state: "open"
    why_it_matters: "This choice determines how much final-state ambiguity the owner is willing to tolerate at the end of a session. Automatic fallback is easier to run; explicit final states are easier to audit."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b"
  confidence: inferred
  review_status: "reviewed"
  note: "Source snapshot for the generated Owner's Manual."
```
