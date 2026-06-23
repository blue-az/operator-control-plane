---
id: pbc_what_operator_is_for
title: "What operator Is For — Behavior Contract Draft"
context: what-operator-is-for
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# What operator Is For — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

operator is a local command-line control plane with a file-backed ledger under .operator/. Its job is not to be a general project tracker or a hosted control plane; it is to keep multi-agent work legible through a task, claim, evidence, and verification frame. For the owner, the important thing is the boundary: this product is about preserving accountable work records inside a bounded local workflow.

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
id: WHAT_OPERATOR_IS_FOR-BHV-001
name: "What operator Is For"
actor: product_system
description: "operator is a local command-line control plane with a file-backed ledger under .operator/. Its job is not to be a general project tracker or a hosted control plane; it is to keep multi-agent work legible through a task, claim, evidence, and verification frame. For the owner, the important thing is the boundary: this product is about preserving accountable work records inside a bounded local workflow."
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
  - title: "This may be only the local tool, not the whole workflow"
    severity: "critical"
    why_it_matters: "If later evidence shows external companion steps, the manual must keep the boundary explicit instead of implying that operator is the entire operating system for the business."
  - title: "Init does not repair a broken ledger tree"
    severity: "high"
    why_it_matters: "A partial or damaged ledger will not be fixed by rerunning bootstrap, so the owner should treat setup as creation, not repair."
  - title: "Some writes depend on the current task already being set"
    severity: "high"
    why_it_matters: "This is convenient when the workflow is already anchored, but it can surprise an operator who expects every write to stand alone without repository state."
  - title: "A claim is not trusted when it is created"
    severity: "medium"
    why_it_matters: "The owner should not read claim creation as correctness; it is only a tracked assertion that still needs support and verification."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should this manual treat operator as the whole operating environment, or as one local component inside a larger workflow?"
    state: "open"
    why_it_matters: "That choice controls how far the manual is allowed to generalize beyond the repository evidence."
  - question: "Should task-bound writes rely on the current task by default, or should every write require an explicit task selection?"
    state: "open"
    why_it_matters: "The current fallback is useful, but it makes the product depend on existing ledger state."
  - question: "Should bootstrap stay a first-run setup step, or should it also repair an existing .operator/ tree?"
    state: "open"
    why_it_matters: "The answer determines whether a partially initialized ledger is an expected maintenance case or a supported recovery path."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b"
  confidence: inferred
  review_status: "reviewed"
  note: "Source snapshot for the generated Owner's Manual."
```
