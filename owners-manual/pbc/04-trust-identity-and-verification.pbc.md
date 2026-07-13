---
id: pbc_trust_identity_and_verification
title: "Trust, Identity, and Verification — Behavior Contract Draft"
context: trust-identity-and-verification
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# Trust, Identity, and Verification — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

Trust in this product is not a feeling; it is the result of separated roles, evidence-backed claims, and identity checks. A task becomes dependable only when the assigned harness has produced a claim, the evidence is attached, a separate verifier has confirmed it under the right identity rules, and doctor no longer sees integrity drift.

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
id: TRUST_IDENTITY_AND_VERIF-BHV-001
name: "Trust, Identity, and Verification"
actor: product_system
description: "Trust in this product is not a feeling; it is the result of separated roles, evidence-backed claims, and identity checks. A task becomes dependable only when the assigned harness has produced a claim, the evidence is attached, a separate verifier has confirmed it under the right identity rules, and doctor no longer sees integrity drift."
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
  - title: "Trusted verification requires distinct OS UIDs"
    severity: "high"
    why_it_matters: "Roles organize permissions, but only an enforced verifier UID distinct from the claim author creates UID-isolated authority."
  - title: "Quarantine can downgrade a finished task"
    severity: "high"
    why_it_matters: "Closeout is not one-way, so a late integrity finding can reopen a supposedly settled task."
  - title: "Bootstrap is not self-healing"
    severity: "medium"
    why_it_matters: "A broken initial setup can persist unnoticed, and trust audits should not assume bootstrap records prove provenance."
  - title: "Usage import can merge instead of append"
    severity: "medium"
    why_it_matters: "If the owner expects a strict append-only accounting trail, the import path does not behave that way."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should quarantine be allowed to overwrite verified or complete task status?"
    state: "open"
    why_it_matters: "This decides whether terminal status is final or whether a late integrity finding can still downgrade the task."
  - question: "Should usage import stay permissive on matching and placeholder hydration, or should it require an exact match and append-only writes?"
    state: "open"
    why_it_matters: "This sets whether usage import is a flexible reconciliation path or a stricter provenance trail."
```

## Resolved Boundaries

- Status-bearing evidence requires a claim.
- Local evidence copy or fingerprint failure aborts before trust records are written.
- `single_user` status writes remain usable and are explicitly advisory.
- `uid_isolated` requires enforced mode and a registered verifier OS UID distinct from the author.

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b"
  confidence: inferred
  review_status: "reviewed"
  note: "Source snapshot for the generated Owner's Manual."
```
