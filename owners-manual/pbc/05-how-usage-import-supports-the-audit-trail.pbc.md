---
id: pbc_how_usage_import_supports_the_audit_trail
title: "How Usage Import Supports the Audit Trail — Behavior Contract Draft"
context: how-usage-import-supports-the-audit-trail
status: draft
tags:
  - pbc
  - owner-manual
  - generated-projection
---

# How Usage Import Supports the Audit Trail — Behavior Contract Draft

> Draft PBC projection derived from one chapter of the unlocked Owner's Manual.

## Scope

Usage import gives the owner a second line of sight into work: it pulls supported harness activity into the local ledger so you can reconstruct sessions, compare activity or cost patterns, and review provenance. It helps the audit trail, but it does not replace claims, evidence, or verification, and it should stay subordinate when imported activity conflicts with verified ledger records.

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
id: HOW_USAGE_IMPORT_SUPPORT-BHV-001
name: "How Usage Import Supports the Audit Trail"
actor: product_system
description: "Usage import gives the owner a second line of sight into work: it pulls supported harness activity into the local ledger so you can reconstruct sessions, compare activity or cost patterns, and review provenance. It helps the audit trail, but it does not replace claims, evidence, or verification, and it should stay subordinate when imported activity conflicts with verified ledger records."
trust: provisional
```

## Section Responsibilities

```pbc:grounding
status: draft
section_responsibilities:
  - "One-Minute Snapshot"
  - "What You Should Be Able To Explain"
  - "Usage import is audit context, not proof"
  - "Imported activity is matched back to a source session"
  - "What the current behavior actually preserves"
  - "Why this layer is still worth having"
  - "Attention Cards"
  - "Owner Decisions"
  - "Evidence Boundary"
```

## Attention Grounding

```pbc:grounding
status: draft
attention:
  - title: "Imported activity is context, not proof"
    severity: "high"
    why_it_matters: "Owners need a clear trust order. Otherwise a noisy import can look more authoritative than the ledger record that was actually verified."
  - title: "The accounting model is not uniform across harnesses"
    severity: "high"
    why_it_matters: "The owner can misread cost or activity if the chapter collapses distinct metering rules into one number."
  - title: "Missing source logs only warn"
    severity: "high"
    why_it_matters: "The audit trail remains useful, but the owner should not assume fail-closed retention or permanent source-log availability."
```

## Owner Decisions

```pbc:grounding
status: draft
decisions:
  - question: "Should imported usage stay advisory when it conflicts with verified ledger records?"
    state: "open"
    why_it_matters: "This chapter currently treats import as supporting evidence, not the record of truth. Changing that would change how every audit review is read."
  - question: "Should the manual keep separate language for token-metered and activity-only harnesses?"
    state: "open"
    why_it_matters: "A single blended summary would hide the real differences in the imported data."
  - question: "Should a missing source log stay a warning instead of a hard failure?"
    state: "open"
    why_it_matters: "The current behavior preserves best-effort provenance after import, but it does not guarantee permanent source availability."
```

## Provenance

```pbc:provenance
- ref: "blue-az/operator-control-plane:master@c5cd06fca49d13e59ffb989d928d7c8fe923819f"
  confidence: reviewed
  note: "Source snapshot for the generated Owner's Manual."
```
