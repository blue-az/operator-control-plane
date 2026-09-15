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
updated: 2026-09-14
---

# Retoolable Research Factory — Behavior Contract

> Working draft for two pilot runs: a PPR Data Atlas audit and a local
> inference placement/offload study. This document is not yet an extracted,
> evidence-backed factory contract. Run both pilots under the existing
> control-plane rules first; then revise this draft from what they actually
> required. It does not declare either work item verified.
>
> Ledger task: `retoolable-research-factory-pbc`. **Nothing here is implemented.**
> Every rule and behavior is fenced `pbc:proposed-*`. Phases, exit criteria, and
> the deviation logs this draft is revised from: `docs/RETOOLABLE_FACTORY_ROADMAP.md`.

## Why This Exists

The factory must be useful beyond one benchmark or one model family. Its value
is the repeatable path from an authoritative substrate to an independently
reviewed result. Domain-specific runners and evidence instruments may change;
the authority boundary, artifact lifecycle, and human gates must not.

The initial GPU work has already demonstrated why this matters, twice:

- On the RTX 2080 desktop, `gemma4:26b` logged `offloaded 31/31 layers to GPU`
  while every MoE expert tensor sat in system RAM. The layer counter did not
  prove expert residency.
- On the RTX 3090s behind the i9 desktop, a ~1.34 ms per CPU-resident layer cost
  measured on `gemma4:26b` (MoE) risked being generalized to dense models. It
  was withdrawn as a transferable constant.

The factory must be able to discover and preserve such instrument corrections
rather than hide or average them away.

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
- Re-running an unchanged task, prompt, model, protocol, and evaluation target
  in order to obtain a different verdict. Planned repeated trials (n>1),
  dispute reruns from a frozen substrate, and versioned longitudinal
  collection are in scope.

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

## Proposed Factory Spine

```pbc:proposed-rules
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
    the `./operator` CLI (`task-create`, `claim-add`, `evidence-attach`), before
    execution. The CLI is a ledger interface, not a reviewer or an authority
    seat. Chat recaps do not substitute for the task, and a worker result does
    not close the task without attached evidence and verification by a distinct
    identity under the ledger's existing verification rules.
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
    Missing, unlogged, or misreported placement evidence, missing telemetry,
    substrate drift, blocked access, harness failure, an unmet host-state
    precondition, and unsupported inference are recorded with structured
    causes. Invalid runs remain available for diagnosis but cannot contribute
    to accepted scores or claims. Mixed or partial placement that is logged is
    not invalid: it is a condition attached to the row, and its cost is already
    in the measured outcome.
  trust: proposed
- id: RRF-RUL-010
  name: Retoolability Is A Pilot Question
  rule: >
    The two pilot runs are evidence about which conventions transfer and which
    belong only to an adapter. Do not declare the spine retoolable, or ratify
    this draft as a contract, until both pilots have completed and their
    actual requirements have been compared. Registering this draft as a
    proposal claim (PROPOSAL_LIFECYCLE.md FROZEN state) is not ratification.
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
- id: RRF-RUL-012
  name: Generalize Process, Not Findings
  rule: >
    A result is scoped to the measured substrate, artifact, protocol, and
    environment. Cross-model, cross-architecture, cross-host, or universal
    claims require their own evidence and review.
  trust: proposed
- id: RRF-RUL-013
  name: Instrument Faults Become Checks
  rule: >
    Each adapter maintains a known-instrument-fault list. A discovered fault
    becomes a deterministic check or an explicit invalidation rule before the
    affected measurement is reused. Intent to discover faults is not evidence
    that the instrument detected them.
  trust: proposed
```

## Pilot Evidence (2026-09-14)

The first PPR Data Atlas pilot exercised the draft spine without deploying:

- one control-plane task (`ppr-data-atlas-v1`);
- two workers from the same frozen baseline;
- read-only substrate checks and independent handoffs;
- supervisor deterministic reruns and reconciliation;
- a human-owner decision on public tool-scope wording;
- a bounded source change committed locally but not published.

The GPU pilot exercised a different shape: controlled repeated measurements on
one host, with no second worker required. It exposed two instrument faults that
became checks: auxiliary `5/5` placement lines must not mask the main model,
and MoE layer counts do not prove expert residency. Host memory and page-cache
state are measurement variables, not optional commentary.

These observations are evidence for revising this draft, not ratification of
all proposed rules. In particular, the adapter—not the spine—chooses worker
independence, telemetry, and execution tier.

## Adapter Contract

Each adapter must provide:

```text
adapter_id
objective and bounded scope
authoritative substrate and digest method
deterministic tools and invocation contract
worker brief and isolated-workspace rule
independence design (RRF-RUL-005)
machine-readable evidence schema and status vocabulary
known instrument faults (RRF-RUL-013)
execution tier and escalation reason
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

## Proposed Lifecycle Gates

```pbc:proposed-behavior
id: RRF-BHV-001
name: Advance A Work Item Through Lifecycle Gates
actor: supervisor
description: Move a factory work item from specification to human-owner decision, recording each gate in the ledger. Gates A-E are checked in order; a failed gate stops the item with a structured cause.
trust: proposed
```

```pbc:proposed-outcomes
- Gate A, baseline frozen: task, adapter, execution tier, source/artifact
  digest, host/runtime identity, cost limit, stop criteria, and access status
  are recorded before worker execution.
- Gate B, instrument admissible: required telemetry, host-state preconditions,
  and known-fault checks are available; missing or misleading signals cause an
  explicit invalid result.
- Gate C, independent outputs: the independence design the adapter declares
  (RRF-RUL-005) is satisfied from the same baseline, and every run returned
  evidence or a structured failure.
- Gate D, reconciled: agreements, one-sided findings, conflicts, supervisor
  reruns, decisions, and human owners are recorded.
- Gate E, human-owner decision: the operator reviews scope, authority,
  provenance, non-goals, and consequence before merge, acceptance, publication,
  or deployment (RRF-RUL-008), recorded with `operator decide`.
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
  constant. The original curve was measured with the RTX 3090s behind the i9
  desktop; the cards have since moved to the i3-9100F testbench, so any rerun
  is a new protocol version on a new host, not a continuation.

Both remain subject to control-plane recording and explicit evidence capture.
The Data Atlas pilot is a Change-tier candidate with supervisor reconciliation
and human-owner decision. The offload pilot is a Study-tier candidate; a
second worker is not required unless its adapter specification says so.

## Provenance

```pbc:provenance
- ref: "evals/local_lane_ladder/fixtures/moe-expert-residency-2026-09-12/FINDING.md"
  confidence: measured
  review_status: "unverified"
  note: "RTX 2080 desktop, ollama 0.32.12. gemma4:26b logs 31/31 layers on GPU while all MoE experts are in system RAM, on every load. Decode 32-34 tok/s cached vs 4.0-4.5 tok/s on page-cache eviction at identical placement. Source for the first Why This Exists example and for host memory state in RRF-RUL-011."
- ref: "evals/local_lane_ladder/fixtures/singlecard-rank-2026-09-08/FINDING.md"
  confidence: measured
  review_status: "unverified"
  note: "Desktop with RTX 3090s, 2026-09-08. Source of the +1.34 ms per CPU-resident layer figure for gemma4:26b."
- ref: "docs/REVIEW_CALL_dense-offload-curve_2026-09-09.md"
  confidence: verified
  review_status: "unverified"
  note: "D2 withdraws the gemma4-26b per-layer constant (~1.25-1.34 ms) as a figure transferable to dense models. Source for the second Why This Exists example."
- ref: "evals/local_lane_ladder/fixtures/testbench-parity-gated-20260912/PROVENANCE.md"
  confidence: verified
  review_status: "active"
  note: "Places an RTX 3090 on the i3-9100F testbench by 2026-09-12, and records that RESULTS.md names the runner host rather than the inference host over an SSH tunnel. Source for the host note on offload-curve-moe-residency."
- ref: "/home/blueaz/Python/ppr-agent/deliver/ppr-data-atlas-v1-supervisor-packet.md"
  confidence: verified
  review_status: "active"
  note: "Authoritative registry is static in core/tool_registry.py with 15 tools. Source for the ppr-data-atlas adapter description."
- ref: "docs/PROPOSAL_LIFECYCLE.md"
  confidence: verified
  review_status: "active"
  note: "Fencing, freeze, and operator decide semantics this draft follows. Section 5 forbids new record types, which constrains the spine."
- ref: "docs/RETOOLABLE_FACTORY_ROADMAP.md"
  confidence: verified
  review_status: "draft"
  note: "Pilot phases, exit criteria, deviation logs, and the Phase 3 extraction this draft is revised against."
```
