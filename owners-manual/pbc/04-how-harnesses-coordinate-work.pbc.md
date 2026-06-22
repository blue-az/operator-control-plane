---
id: pbc_how_harnesses_coordinate_work
title: "How Harnesses Coordinate Work — Behavior Contract Draft"
context: how-harnesses-coordinate-work
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# How Harnesses Coordinate Work — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

This chapter shows how the Operator Control Plane coordinates external harnesses through the local ledger and the CLI nouns your product already uses. It does not own the harness machines; it records the work, the handoff, the brief, the session, and the review step so an operator can keep supervision intact.

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
id: HOW_HARNESSES_COORDINATE-BHV-001
name: "How Harnesses Coordinate Work"
actor: product_system
description: "This chapter shows how the Operator Control Plane coordinates external harnesses through the local ledger and the CLI nouns your product already uses. It does not own the harness machines; it records the work, the handoff, the brief, the session, and the review step so an operator can keep supervision intact."
trust: provisional
```

## Section Responsibilities

```pbc:grounding
status: draft
section_responsibilities:
  - "One-Minute Snapshot"
  - "What You Should Be Able To Explain"
  - "The Coordination Model"
  - "What the Workflow Actually Does"
  - "What the Evidence Confirms"
  - "What Is Solid Here"
  - "Attention Cards"
  - "Owner Decisions"
  - "Evidence Boundary"
```

## Attention Grounding

```pbc:grounding
status: draft
attention:
  - title: "Do not turn coordination into runtime ownership"
    severity: "critical"
    why_it_matters: "If the manual blurs this boundary, the reader will assume the product controls infrastructure that it does not actually own."
  - title: "Do not blur the builder/reviewer split"
    severity: "high"
    why_it_matters: "If that separation softens, the handoff instructions stop matching the real operating model."
  - title: "Do not describe session close as automatic reassignment"
    severity: "high"
    why_it_matters: "A simplified description would mislead operators about when a task actually returns to assigned."
  - title: "Harness metadata is secondary to the ledger record"
    severity: "medium"
    why_it_matters: "This chapter should stay focused on supervision, not drift into harness-administration detail."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should the manual keep the assigned harness and review harness as a hard distinction?"
    state: "open"
    why_it_matters: "That choice determines whether the chapter reads as supervised multi-harness work or as a generic collaboration flow."
  - question: "Should coordination be framed as controlled recordkeeping rather than orchestration?"
    state: "open"
    why_it_matters: "This is the main boundary that keeps the chapter honest about what the product does and does not own."
  - question: "Should session close be documented as a conditional return to assigned?"
    state: "open"
    why_it_matters: "The operator needs the exact fallback rule to avoid assuming a task is reassigned earlier than it really is."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:master@c5cd06fca49d13e59ffb989d928d7c8fe923819f"
  confidence: reviewed
  note: "Source snapshot for the generated Owner's Manual."
```
