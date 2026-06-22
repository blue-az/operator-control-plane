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

This chapter explains the part of the product that turns supervised work into a record. A task is the unit of work, a claim is the asserted outcome, evidence is the proof attached to that claim, a handoff keeps the next step visible, and a session marks when work is active and when it closes. Read the ledger as a linked trail of records, not as one simple status field.

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
description: "This chapter explains the part of the product that turns supervised work into a record. A task is the unit of work, a claim is the asserted outcome, evidence is the proof attached to that claim, a handoff keeps the next step visible, and a session marks when work is active and when it closes. Read the ledger as a linked trail of records, not as one simple status field."
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
  - title: "Do not treat one status as the whole story"
    severity: "high"
    why_it_matters: "If the owner reads only the end state, disputes can hide the record chain that shows what actually happened."
  - title: "Session closure only returns to assigned under narrow conditions"
    severity: "high"
    why_it_matters: "The owner could think work is ready for reassignment while the ledger still treats it as active."
  - title: "Current-task fallback is command-specific"
    severity: "medium"
    why_it_matters: "If the manual overgeneralizes this rule, operators will expect the same fallback or the same validation everywhere."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should this chapter keep the product framed as a local ledger rather than a hosted workflow system?"
    state: "open"
    why_it_matters: "That framing sets the owner's expectation for where records live and how much of the workflow is meant to be local and inspectable."
  - question: "Should the manual say session closure falls back to assigned only when the task is still running and no open sessions remain?"
    state: "open"
    why_it_matters: "This is the point where a quick reading can produce the wrong operational conclusion about whether the work is actually finished."
  - question: "Should the manual list which commands use the current-task fallback and which commands check harness state?"
    state: "open"
    why_it_matters: "This affects how much the owner can trust omitted task context and missing harness files."
  - question: "Should this chapter keep evidence capture separate from later verification?"
    state: "open"
    why_it_matters: "The workflow is easier to understand when proof material is attached first and trust is judged in the later chapter."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:master@c5cd06fca49d13e59ffb989d928d7c8fe923819f"
  confidence: reviewed
  note: "Source snapshot for the generated Owner's Manual."
```
