---
id: pbc_prime_agent_evidence_ingestion
title: "Prime Agent Session Evidence Ingestion — Behavior Contract"
context: operator-evidence-intake
status: draft
owners:
  - operator_user
tags:
  - pbc
  - operator
  - evidence
  - usage
  - proposed
updated: 2026-08-09
---

# Prime Agent Session Evidence Ingestion — Behavior Contract

> PBC for teaching `operator` to ingest Prime Agent session records as usage and as evidence,
> so that a claim about work done in a Prime Agent session can be checked against a structured
> execution byproduct rather than against the agent's own prose.
>
> **Nothing in the Proposed sections is implemented.** Per repository convention, all unbuilt
> behavior is fenced as `pbc:proposed-*` so tooling does not read it as active.
>
> **Status is `draft` — awaiting an operator ruling.** Per this directory's trust model, a contract
> stays `draft` until a human owner reviews and accepts it. The presence of this file authorizes no
> work. Ledger task: `pa-evidence`. If Gate 0 shows the documented session shape is wrong enough to
> change the design, rewrite this document rather than amending it (see Open Question 4).

## Why This Exists

`operator` enforces *who signs off* on a claim. It does not check that the attached evidence
corresponds to what actually executed — evidence is whatever the agent chooses to attach, and
`--verify-cmd` is explicitly inert audit metadata that `doctor` never runs. The distinct-UID
requirement raises the bar on the signature, not on the substrate.

Prime Agent is the first harness surveyed in `~/Python/Evaluation/` that emits a structured
execution record as a byproduct of running: an append-only JSONL transcript per session, kernel
state snapshots, and per-child token/cost attribution. That is a different *kind* of artifact
from a narrated handoff. It is not authored as an account of the work; it is what the work left
behind.

This PBC proposes using it as evidence intake. It does **not** claim the result is tamper-proof
(see PAE-RUL-006).

## Scope

Three phases, each gating the next:

1. **Observe.** Produce a real Prime Agent session on this machine and inspect its actual bytes.
   No schema may be frozen from documentation.
2. **Meter.** Extend `usage-import` with a Prime Agent adapter under the existing
   `USAGE_AUTOIMPORT_SPEC.md` contract, including its hard rule against conflating units.
3. **Attest.** Allow a session transcript to attach as typed evidence against a claim, with the
   fingerprinting and fail-closed behavior `doctor` already applies to local evidence.

## Non-Goals

- **No second ledger.** `MACHINE_PROVENANCE_SPEC.md` forbids it. Prime Agent's own
  `~/.prime/agent/` state is a source to read, never a parallel authority.
- **No routing or dispatch changes.** This PBC touches intake only. Nothing here may alter
  `route_task`, lane selection, or which harness gets work.
- **No `/refine` audit.** The proposed adversarial study of Prime Agent's self-gating harness
  refinement is separate work with a separate evidence bar. It shares a subject with this PBC
  and nothing else. Do not let it ride along in scope.
- **No claim that transcript evidence is adversary-proof.** See PAE-RUL-006.
- **No new identity or policy semantics.** This work is contained precisely because it needs
  none; that is the property that made the SQLite ledger lesson (COMPARISON.md Lesson 3) the one
  that actually shipped.
- **No Prime Agent fork or upstream contribution.** `origin` is PrimeIntellect-owned.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: V&V seat. The only party who may accept a phase gate or authorize harness registration.
- id: operator_cli
  name: operator CLI
  type: system
  description: The repo-local ledger CLI. Owns tasks, claims, evidence, verification, usage, doctor.
- id: prime_agent
  name: Prime Agent session
  type: external
  description: Daemon-backed coding agent. Emits JSONL transcripts and session artifacts under ~/.prime/agent/. Not authored by the operator user; upstream is PrimeIntellect-ai.
- id: usage_adapter
  name: Prime Agent usage adapter
  type: system
  description: Proposed read-only reader that maps a Prime Agent session record into an operator usage record.
```

## Rules — as verified today

```pbc:rules
- id: PAE-RUL-001
  name: Evidence Content Is Currently Unchecked
  rule: >
    operator fingerprints evidence bytes (SHA-256, size, mtime) and fails closed when a verified
    source changes, but it never evaluates whether the evidence supports the claim. --verify-cmd
    is stored as audit metadata and doctor never executes it. Verification is a signature by a
    distinct identity over an artifact of unexamined content.
  trust: verified
- id: PAE-RUL-002
  name: Three Harness Adapters Exist
  rule: >
    usage-import implements adapters for claude, codex, and gemini-agy only. Other registered
    harnesses fall back to session-start, usage-add, and manual annotation. No Prime Agent
    adapter exists in any form.
  trust: verified
- id: PAE-RUL-003
  name: Transcript Is An Existing Evidence Type
  rule: >
    evidence-attach already accepts --type transcript. Ingesting a Prime Agent session as
    evidence requires no new evidence type, no schema migration, and no change to the
    verification path.
  trust: verified
- id: PAE-RUL-004
  name: The Session Schema Is Documentation, Not Observation
  rule: >
    ~/.prime does not exist on this machine; Prime Agent has never been run here. Every
    statement in this PBC about session layout, entry shape, or usage attribution derives from
    packages/coding-agent/docs/ in a v0.7.1 checkout, not from inspected bytes. Per repository
    verification discipline, that is a claim about what existed when written.
  trust: verified
- id: PAE-RUL-005
  name: The Session Format Is Pre-1.0 And Migrating
  rule: >
    The documented session format is at version 3, with versions 1 and 2 auto-migrated on load.
    The daemon protocol carries its own DAEMON_PROTOCOL_VERSION and DAEMON_SCHEMA_REVISION.
    Any adapter is reading a moving target from a 0.x upstream that owes this repo no stability.
  trust: verified
- id: PAE-RUL-006
  name: A Transcript Is Byproduct, Not Proof
  rule: >
    A session transcript is adversary-independent only in the weak sense that it is a structured
    byproduct rather than a narrated summary. It is written by the same process whose claims it
    would support, on disk the agent can reach. It raises the cost of a false claim; it does not
    make one impossible. No behavior in this PBC may be described to a reviewer as proof of
    execution.
  trust: verified
```

## Proposed Behavior

```pbc:proposed-behavior
- id: PAE-BEH-001
  name: Import a Prime Agent session's usage into the ledger
  actor: operator_user
  outcome: >
    A completed Prime Agent session appears as an operator usage record with per-field
    provenance, keyed for idempotent re-import, without any manual transcription.
- id: PAE-BEH-002
  name: Attach a session transcript as evidence for a claim
  actor: operator_user
  outcome: >
    A claim about work performed in a Prime Agent session can carry that session's transcript as
    fingerprinted evidence, so a later doctor run fails closed if the transcript changed after
    verification.
```

## Proposed Rules

```pbc:proposed-rules
- id: PAE-RUL-007
  name: Observed Bytes Gate The Schema
  rule: >
    No field mapping may be implemented from documentation. Phase 0 must produce at least one
    real session containing a subagent spawn and at least one compaction, and the adapter must be
    written against those captured bytes. The captured fixture lands in tests/fixtures/ as the
    adapter's regression basis, following the existing synthetic-harness-log convention.
  trust: proposed
- id: PAE-RUL-008
  name: Own Usage And Aggregate Usage Are Different Units
  rule: >
    Prime Agent persists child_usage_attributed entries that fold a subagent's tokens into the
    parent assistant turn, so a parent message carries an aggregate that already contains its
    children. Summing message usage naively double-counts. The adapter must record which
    quantity it took — own usage or subtree aggregate — in field_sources, and must never emit a
    number whose unit is ambiguous. This is the USAGE_AUTOIMPORT_SPEC hard rule applied to a
    tree-shaped source it was not written for.
  trust: proposed
- id: PAE-RUL-009
  name: Tool Calls Remain The Comparable Metric
  rule: >
    tool_calls stays the cross-harness comparable. Prime Agent routes most work through a single
    IPython tool, so its tool-call count is not commensurate with a harness that exposes a dozen
    discrete tools. The adapter must record the count and flag the metering asymmetry rather than
    silently placing it in a column that invites comparison.
  trust: proposed
- id: PAE-RUL-010
  name: Unknown Models Cost Null
  rule: >
    Prime Agent sessions may run models absent from .operator/pricing.yaml. Missing model implies
    cost_estimate_usd null and a doctor flag. No price is guessed.
  trust: proposed
- id: PAE-RUL-011
  name: Adapter Pins The Session Version It Read
  rule: >
    Each imported record stores the session-format version observed at import. An import from an
    unrecognized version warns and refuses rather than parsing optimistically.
  trust: proposed
- id: PAE-RUL-012
  name: Read-Only Against Prime Agent State
  rule: >
    The adapter opens ~/.prime/agent/ read-only. It never writes, moves, migrates, or deletes
    Prime Agent state, and never invokes the prime-agent binary as a side effect of import.
  trust: proposed
```

## Phase Gates

Each gate is an operator decision, not a test result, and is recorded in the task's
`operator_decision` field. Work does not proceed past an unaccepted gate.

Review of this contract is open to any cold peer agent at a UID distinct from the author's. No
harness is designated. Harnesses are peers, not ranked brands (`AGENTS.md`), and the ledger's
trust condition is `verifier UID != claim-author UID` — it says nothing about vendor. A cold
same-vendor agent satisfies it exactly as well as a cross-vendor one; coldness, not brand
difference, is the property doing the work.

**Gate 0 — Observation.** Prime Agent installed and run to produce a real session including a
subagent spawn and a compaction. Actual JSONL inspected and a fixture captured. Deliverable is
the fixture plus a one-page diff between documented and observed shape. *If the observed shape
matches the docs, say so; that is a result, not a formality.*

**Gate 1 — Metering.** `usage-import --harness prime-agent` implemented against the Gate 0
fixture, with `--dry-run` parity, idempotent re-import keyed on `source_session_ref`, and the
own-vs-aggregate decision from PAE-RUL-008 recorded in `field_sources`. Tests follow the existing
subprocess-driven pattern in `tests/test_operator.py`.

**Gate 2 — Attestation.** A worked end-to-end: a claim registered against work done in a Prime
Agent session, its transcript attached via `evidence-attach --type transcript`, verified by a
distinct UID under enforced mode, and a `doctor` run that fails closed after the transcript is
mutated. The failing-closed demonstration is the deliverable — not the passing one.

## Ledger Registration

Open the task now; do **not** pre-register claims for unbuilt phases. `doctor` flags unverified
claims, and a ledger seeded with claims that cannot yet be evidenced degrades exactly the signal
this repo exists to protect. Register each claim as its gate closes.

```bash
# now
./operator task-create --id pa-evidence \
    --objective "Ingest Prime Agent session records as operator usage and evidence" \
    --repo operator-control-plane

# at Gate 0, once the fixture exists
./operator claim-add --task pa-evidence --type file_exists \
    --text "captured Prime Agent session fixture with subagent spawn and compaction" \
    --gate tests/fixtures/prime_agent_session.jsonl

# at Gate 1
./operator claim-add --task pa-evidence --type test_passes \
    --text "usage-import --harness prime-agent is idempotent on re-import" \
    --gate tests/test_operator.py

# at Gate 2 — the fail-closed demonstration, verified from a distinct UID
./operator claim-add --task pa-evidence --type test_passes \
    --text "doctor fails closed when a verified Prime Agent transcript is mutated" \
    --gate tests/test_operator.py
```

## Open Questions Requiring An Operator Ruling

These are decisions no agent should make alone — not because a reviewing agent outranks a
drafting one, but because they set metering semantics and standing obligations that belong to
the human V&V seat.

1. **Does Prime Agent become a registered harness peer?** Registering a fourth harness is not a
   config change — `AGENT_AUDIT_PROTOCOL.md` expects each active agent's failure-mode and
   strengths catalogs to be written by the *other* active agents, and adding a peer adds that
   obligation to the rotation. Metering a harness and admitting it to the rotation are separable;
   this PBC needs only the former. Confirm they stay separate.

2. **Own usage or subtree aggregate?** PAE-RUL-008 forces the choice to be explicit but does not
   make it. Own usage keeps records additive across harnesses; subtree aggregate matches what the
   session actually cost. Recommend own usage in the token layer with the aggregate retained in a
   distinct field, but this is a metering-semantics call that belongs to the V&V seat.

3. **Is transcript attachment manual or hooked?** `CRYSTAL_SESSION_BRIDGE_SPEC.md` establishes a
   session-end hook pattern for crystals. Reusing it for transcripts would be consistent, but that
   spec is draft and unimplemented, and building on an unimplemented spec is how a plan acquires a
   dependency nobody scheduled. Recommend manual attachment for Gate 2.

4. **Does this PBC land at all?** It adds ~200 lines to a repo whose specification surface is
   already large relative to its ~6000-line CLI. If Gate 0 shows the documented shape is wrong
   enough that the design changes, this document should be rewritten rather than amended.

```pbc:provenance
- kind: doc
  ref: packages/coding-agent/docs/session-format.md
  detail: JSONL layout, ~/.prime/agent/sessions/<id>.jsonl path, and v1-v3 migration behavior.
  confidence: inferred
  rationale: Read from a v0.7.1 checkout. No session has been produced on this machine; see PAE-RUL-004.
- kind: doc
  ref: packages/coding-agent/docs/rlm-runtime.md
  detail: child_usage_attributed entries and parent-aggregate accounting behind PAE-RUL-008.
  confidence: inferred
  rationale: Documentation only. The double-counting hazard is derived from the described behavior, not observed in a transcript.
- kind: runtime
  ref: "shell: ls -d ~/.prime"
  detail: ~/.prime absent; Prime Agent has never run on this machine.
  confidence: verified
- kind: code
  ref: operator-control-plane/README.md
  detail: usage-import adapter coverage, transcript evidence type, doctor fail-closed and fingerprint behavior, inert --verify-cmd.
  confidence: verified
- kind: doc
  ref: operator-control-plane/USAGE_AUTOIMPORT_SPEC.md
  detail: usage record schema, per-field provenance, idempotency key, never-conflate-units hard rule.
  confidence: verified
- kind: doc
  ref: Python/Evaluation/eval-notes/COMPARISON.md
  detail: Lesson 3 containment reasoning reused as the scoping argument for this PBC.
  confidence: verified
- kind: inference
  ref: this document
  detail: The claim that a session transcript is a materially better evidence substrate than a narrated handoff.
  confidence: assumed
  rationale: Untested. It is the load-bearing assumption of the whole plan and Gate 2 is the first thing that would challenge it.
```
