---
id: pbc_retoolable_research_factory
title: "Retoolable Research Factory — Behavior Contract"
context: operator-research-factory
status: draft
tags:
  - pbc
  - operator
  - factory
  - research
  - evidence
  - proposed
updated: 2026-09-12
---

# Retoolable Research Factory — Behavior Contract

> Working draft for two pilot runs: a PPR Data Atlas audit and a local
> inference placement/offload study. This document is not yet an extracted,
> evidence-backed factory contract. Run both pilots under the existing
> control-plane rules first; then revise this draft from what they actually
> required. It does not declare either work item verified.

## Why This Exists

The factory must be useful beyond one benchmark or one model family. Its value
is the repeatable path from an authoritative substrate to an independently
reviewed result. Domain-specific runners and evidence instruments may change;
the authority boundary, artifact lifecycle, and human gates must not.

The initial GPU work has already demonstrated why this matters: a plausible
`31/31 layers` signal did not prove MoE expert residency, and an apparent
per-layer cost risked being generalized across architectures. The factory must
be able to discover and preserve such instrument corrections rather than hide
or average them away.

## Scope

This contract governs:

- defining a bounded work item from a PBC/specification;
- assigning and tracking it through the Operator ledger;
- selecting an authority substrate and domain adapter;
- running isolated, reproducible workers;
- collecting machine-readable evidence and human-readable handoffs;
- comparing independent outputs;
- rerunning disputed evidence;
- passing through a named supervisor reconciliation and a separate human-owner decision before merge, acceptance, or publication.

## Non-Goals

- A universal benchmark score or universal performance law.
- A self-approving autonomous release pipeline.
- Treating model prose, crystals, dashboards, or summaries as verification.
- Replacing domain instruments with one generic metric.
- Automatic deployment, publication, schema changes, or source-data changes.
- Running repeated trials whose task, prompt, model, protocol, or evaluation
  target has not changed.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Owns scope, authority decisions, review, merge, acceptance, and publication.
- id: supervisor
  name: Frontier supervisor
  type: system
  description: Designs briefs, inspects evidence, compares worker outputs, and records reconciliation; does not become substrate authority.
- id: local_worker
  name: Local worker
  type: external
  description: Executes a bounded adapter task in an isolated workspace and returns artifacts plus evidence.
- id: operator_ledger
  name: Operator ledger
  type: system
  description: Source of record for task lifecycle, claims, evidence, handoffs, and review state.
- id: domain_adapter
  name: Domain adapter
  type: system
  description: Supplies substrate, tools, runner, evidence schema, acceptance checks, and stop conditions for one work purpose.
```

## Factory Spine

```pbc:rules
- id: RRF-RUL-001
  name: Specification Precedes Dispatch
  rule: >
    Every factory run begins with a bounded specification naming the objective,
    scope, non-goals, authoritative substrate, allowed tools, deliverables,
    acceptance gates, cost limit, and stop criteria.
  trust: proposed
- id: RRF-RUL-002
  name: Control-Plane Task Is The Work Record
  rule: >
    The specification is instantiated as a control-plane task, recorded through
    the `op` command surface, before execution. The `op` command is a ledger
    interface, not a reviewer or an authority seat. Chat recaps do not
    substitute for the task, and a worker result does not close the task without
    evidence and named review.
  trust: proposed
- id: RRF-RUL-003
  name: Adapter Retools The Factory
  rule: >
    Domain variation is expressed by an adapter. An adapter declares its
    authoritative substrate, deterministic tools, worker brief, artifact
    contract, evidence schema, acceptance checks, and stop conditions. The
    factory spine does not encode those domain facts.
  trust: proposed
- id: RRF-RUL-004
  name: Authority Is Explicit
  rule: >
    Every factual result names its authority source. Substrates and deterministic
    tool outputs outrank HTML, prose, model answers, dashboard renderings, and
    crystals. Unknown, NULL, unsupported, blocked, and invalid states remain
    distinct.
  trust: proposed
- id: RRF-RUL-005
  name: Independence Is Adapter-Specific
  rule: >
    Each adapter declares whether independence requires identical workers,
    repeated controlled measurements, or another design. Audit adapters may
    use identical workers in isolated workspaces; measurement adapters must
    not claim independence merely because two agents share a host. Work is not
    divided merely to create parallel-looking output.
  trust: proposed
- id: RRF-RUL-006
  name: Evidence Is Machine-Readable
  rule: >
    A worker handoff includes sorted evidence rows with source location, status,
    reproduction command or query, expected value, observed value, and action.
    Human-readable narration may accompany it but cannot replace the rows.
  trust: proposed
- id: RRF-RUL-007
  name: Reconciliation Is A Separate Pass
  rule: >
    The supervisor compares worker inventories, observations, classifications,
    diffs, tests, and unresolved questions. One-sided findings are investigated,
    not silently discarded. Disputes are rerun from the frozen substrate.
  trust: proposed
- id: RRF-RUL-008
  name: Human Gate Owns Consequence
  rule: >
    Human review is mandatory before merging changes, changing public claims,
    modifying data/schema/charter/tool contracts, declaring acceptance, or
    publishing/deploying. The supervisor may recommend ready for human-owner
    decision only.
  trust: proposed
- id: RRF-RUL-009
  name: Invalid Runs Are Preserved And Excluded
  rule: >
    Placement failure, missing telemetry, substrate drift, blocked access,
    harness failure, and unsupported inference are recorded with structured
    causes. Invalid runs remain available for diagnosis but cannot contribute
    to accepted scores or claims.
  trust: proposed
- id: RRF-RUL-010
  name: Retoolability Is A Pilot Question
  rule: >
    The two pilot runs are evidence about which conventions transfer and which
    belong only to an adapter. Do not declare the spine retoolable, or freeze
    this draft as a contract, until both pilots have completed and their
    actual requirements have been compared.
  trust: proposed
- id: RRF-RUL-011
  name: Longitudinal Data Requires Provenance
  rule: >
    Repeated research measurements retain raw telemetry, model or artifact
    digests, host identity, runtime/configuration, prompt or input identity,
    timing/count data, failures, placement evidence, and host memory state
    including free RAM, cache pressure, major faults, and I/O where relevant.
    Rounded summaries do not replace raw records.
  trust: proposed
- id: RRF-RUL-013
  name: Instrument Faults Become Checks
  rule: >
    Each adapter maintains a known-instrument-fault list. A discovered fault
    becomes a deterministic check or an explicit invalidation rule before the
    affected measurement is reused. Intent to discover faults is not evidence
    that the instrument detected them.
  trust: proposed
- id: RRF-RUL-012
  name: Generalize Process, Not Findings
  rule: >
    A result is scoped to the measured substrate, artifact, protocol, and
    environment. Cross-model, cross-architecture, cross-host, or universal
    claims require their own evidence and review.
  trust: proposed
```

## Adapter Contract

Each adapter must provide:

```text
adapter_id
objective and bounded scope
authoritative substrate and digest method
deterministic tools and invocation contract
worker brief and isolated-workspace rule
machine-readable evidence schema
artifact and handoff paths
acceptance checks and negative/unknown cases
cost and runtime limit
stop conditions
reconciliation fields
```

Initial adapters:

- `local-inference-placement`: Ollama, model metadata, daemon load logs,
  per-device GPU/RAM/I/O telemetry, and timing probes.
- `ppr-data-atlas`: SQLite, deterministic 15-tool registry, local JSON/HTML,
  public-page/link inspection, and stale/unsupported-claim ledger.

## Lifecycle Gates

```pbc:gates
- id: RRF-GATE-A
  name: Baseline frozen
  check: >
    Task, adapter, source/artifact digest, host/runtime identity, and access
    status are recorded before worker execution.
- id: RRF-GATE-B
  name: Instrument admissible
  check: >
    Required telemetry and deterministic checks are available; missing or
    misleading signals cause an explicit invalid result.
- id: RRF-GATE-C
  name: Independent outputs
  check: >
    Required workers started from the same baseline and returned evidence or a
    structured failure.
- id: RRF-GATE-D
  name: Reconciled
  check: >
    Agreements, one-sided findings, conflicts, supervisor reruns, decisions,
    and human owners are recorded.
- id: RRF-GATE-E
  name: Human-owner decision
  check: >
    The human owner reviews scope, authority, provenance, non-goals, and
    consequence before merge, acceptance, publication, or deployment.
```

## Deferred Product Question

A longitudinal measurement dataset may eventually be valuable, but that is
outside this working contract. It must not determine what gets measured or
weaken the evidence gates.

## Pilot Execution Tiers

The adapter chooses the least ceremonial tier that preserves provenance:

- **Probe:** one bounded measurement, explicit host/config snapshot, and
  structured pass/invalid result.
- **Study:** repeated controlled measurements, raw telemetry, and an adapter
  review; use when variance or host state is part of the question.
- **Change:** worker implementation, evidence handoff, reconciliation, and
  human-owner decision; use for code or public-surface changes.

A tier may escalate when a fault, conflict, or consequence requires it. The
control plane records the chosen tier and reason.

## Current Work Items

- `ppr-data-atlas-v1`: first retooling proof using SQLite and public HTML.
- `offload-curve-moe-residency`: determine whether the observed MoE offload
  curve is expert/page-cache behavior rather than a transferable dense-layer
  constant.

Both remain subject to control-plane recording and explicit evidence capture.
The Data Atlas pilot is a Change-tier candidate with supervisor reconciliation
and human-owner decision. The offload pilot is a Study-tier candidate; a
second worker is not required unless its adapter specification says so.
