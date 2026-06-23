---
id: pbc_running_a_multi_harness_workflow
title: "Running a Multi-Harness Workflow — Behavior Contract Draft"
context: running-a-multi-harness-workflow
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# Running a Multi-Harness Workflow — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

This chapter is about continuity. The product does not just record isolated tasks; it keeps a local operating rhythm where an operator, an assigned harness, and a review harness move work forward through briefs, handoffs, session closeout, and usage records.

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
id: RUNNING_A_MULTI_HARNESS_-BHV-001
name: "Running a Multi-Harness Workflow"
actor: product_system
description: "This chapter is about continuity. The product does not just record isolated tasks; it keeps a local operating rhythm where an operator, an assigned harness, and a review harness move work forward through briefs, handoffs, session closeout, and usage records."
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
  - title: "A quarantine can still downgrade a finished task"
    severity: "critical"
    why_it_matters: "Closeout is not one-way. If the owner reads terminal status as final, a later quarantine can reverse that conclusion and change what the business thinks is done."
  - title: "Session closeout can diverge from usage cleanup"
    severity: "high"
    why_it_matters: "The task status you see may not match the usage picture unless the owner knows which record was allowed to win. That matters when handoffs are used to judge whether work is still active."
  - title: "Verification is not a blanket rule on every evidence write"
    severity: "high"
    why_it_matters: "If the owner assumes every status change is checked the same way, trust can drift without being noticed. This is an authority boundary, not just a convenience difference."
  - title: "Usage import can match more broadly than an exact session ID"
    severity: "medium"
    why_it_matters: "A rushed import can attach the wrong session or merge into a row that was already open. That affects accountability even when the ledger still looks tidy."
  - title: "The repository may not be the whole operating system"
    severity: "low"
    why_it_matters: "If the owner treats this chapter as the whole truth, they may miss external coordination steps that are outside the bounded evidence and therefore still unverified."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should the generated brief remain the canonical handoff text for the next harness?"
    state: "open"
    why_it_matters: "The brief is the main continuity artifact. If it stops being the source of truth, the next harness can inherit stale context or miss the current next action."
  - question: "Should task-bound writes keep the implicit current-task fallback, or should the manual require explicit task selection in high-risk work?"
    state: "open"
    why_it_matters: "Several write paths depend on the active task when no task is passed. That is fast, but it also makes continuity dependent on repository state."
  - question: "Should session end be allowed to override the fallback assignment when usage closes, or should usage closeout and task status stay strictly coupled?"
    state: "open"
    why_it_matters: "The workflow can separate usage cleanup from task status. If the owner wants a simpler lifecycle, that flexibility may need to be narrowed."
  - question: "Should usage import stay permissive about session matching and placeholder hydration, or should the owner require stricter selection rules?"
    state: "open"
    why_it_matters: "Permissive matching is forgiving, but it also increases the chance of pulling in the wrong session or rewriting an open placeholder unexpectedly."
  - question: "Should the manual keep describing this as a local ledger workflow unless broader system boundaries are confirmed?"
    state: "open"
    why_it_matters: "The evidence does not prove the repository is the entire system. Overstating the boundary would make the owner trust a wider operating model than the evidence supports."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:main@9b9e3e63a7f0f54ccde541c6c10570c8fdbe8f5b"
  confidence: inferred
  review_status: "reviewed"
  note: "Source snapshot for the generated Owner's Manual."
```
