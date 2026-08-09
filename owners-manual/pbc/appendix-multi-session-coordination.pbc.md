---
id: pbc_multi_session_coordination
title: "Multi-Session Coordination — Behavior Contract"
context: multi-agent-operation
status: draft
owners:
  - operator_user
tags:
  - pbc
  - operator
  - coordination
  - identity
  - proposed
updated: 2026-08-09
---

# Multi-Session Coordination — Behavior Contract

> PBC for two concurrent Claude sessions and a Codex harness operating one `.operator/` ledger
> as peers, so that the record says who did what and concurrent writes do not corrupt provenance.
>
> **Nothing in the Proposed sections is enforced.** These are conventions between agents; the
> tool validates none of them. Per repository convention they are fenced as `pbc:proposed-*` so
> tooling does not read them as active.
>
> **Status is `draft` — awaiting an operator ruling** on the identity labels in MSC-RUL-101.
> Both Claude sessions have signed off (`session-coordination-protocol` handoff-0001, 0002, 0003).
> Ledger task: `session-coordination-protocol`.

## Why This Exists

The ledger's product is provenance. On 2026-08-08/09 it stopped delivering that, silently.

Two Claude sessions ran concurrently against one ledger, both writing `--by claude` at uid 1000.
Twelve handoffs record an author that does not identify an agent. Nothing failed, no check fired,
and the loss is not recoverable from the record — only from two conversations that agree with each
other and will not survive.

It produced three concrete failures in two days:

1. The operator attributed a `doctor` warning about `claim-0006` to the wrong session. Not
   carelessness — the ledger genuinely says both sessions are `claude`.
2. An `evidence-attach` landed on the wrong task because `current_task` had silently moved when
   the other session created one.
3. One session proposed a coordination rule (`R1`) that would have relabeled the other session's
   work as `codex`, because it assumed two actors when there were three. It was caught in review
   by the session it would have mislabeled — not by any check.

The third is the load-bearing one: **the misdiagnosis was made by an agent reading the same ledger
this contract governs, and the ledger supplied no signal that would have prevented it.**

## Scope

Conventions for concurrent agents sharing one ledger, one repository, one GPU and one model server:
distinct authorship, safe write targets, symmetric verification, and resource announcement.

## Non-Goals

- A second `.operator/` ledger. `MACHINE_PROVENANCE_SPEC.md` forbids it; sequential record IDs make
  merging unsafe by construction.
- Cross-session locking or transactions. `ledger.lock` exists; nothing here extends it.
- Tooling enforcement. Every rule below is honored voluntarily. If an agent ignores one, nothing
  detects it — see Open Question 1.
- Any change to `EXECUTOR_IDENTITY_SPEC.md`. UID isolation is the authority mechanism; `--by` is a
  provenance label and confers nothing.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Sole party who may ratify these conventions or overrule them. Runs both sessions.
- id: claude_consultant
  name: claude-consultant session
  type: system
  description: One Claude session. Wrote the gate, delegate-brief, machine tagging, pass 2, the repeat-guard tests, and the doctor identity fix.
- id: claude_supervisor
  name: claude-supervisor session
  type: system
  description: The other Claude session. Created opr-continuation-loop-audit and pa-evidence, ran pilot passes 1 and 3.
- id: codex_harness
  name: Codex harness
  type: external
  description: A real third actor, not an alias for either session. Wrote handoff-0003 and evidence-0008 on opr-continuation-loop-audit.
- id: operator_builder
  name: operator-builder (uid 971)
  type: system
  description: Isolated OS identity used for verification. Not a session; carries authority under mode enforced.
```

## Rules — as verified today

```pbc:rules
- id: MSC-RUL-001
  name: --by Is Unvalidated Free Text
  rule: >
    claim-add, evidence-attach and handoff-add accept any --by string with no registry check.
    Tested in a throwaway ledger: claude-consultant and claude-supervisor were accepted, recorded
    verbatim, and doctor reported 0 errors. Corroborated live — operator-builder wrote handoff-0008
    and is absent from .operator/harnesses/. Distinct identity labels therefore need no registry
    change and no code change.
  trust: verified
- id: MSC-RUL-002
  name: The Ledger Cannot Distinguish Same-Label Sessions
  rule: >
    Authorship is recorded as the --by string plus executor uid. Two sessions run by the same
    person on the same machine share a uid and, by default, a label. Nothing in the record
    separates them and doctor raises nothing. Twelve handoffs are currently affected.
  trust: verified
- id: MSC-RUL-003
  name: current_task Is Global Mutable State
  rule: >
    operator.yaml holds one current_task for the whole ledger. task-create sets it as a side
    effect. Any command omitting --task lands wherever another session last pointed it. Observed
    three times in two days, once causing a misdirected evidence-attach.
  trust: verified
- id: MSC-RUL-004
  name: review_harness Is Write-Once
  rule: >
    review_harness is assigned at task-create (operator:1651) and mutated nowhere. A task whose
    reviewer designation becomes wrong cannot be corrected through the CLI.
  trust: verified
- id: MSC-RUL-005
  name: Record IDs Interleave Silently
  rule: >
    Claim, evidence and handoff IDs are sequential per ledger. Concurrent sessions interleave
    them with no marker — evidence-0013 was written by one session between another session's
    0012 and 0014. ID order implies chronology, never authorship.
  trust: verified
- id: MSC-RUL-006
  name: Caller Provenance Does Not Reach The CLI
  rule: >
    OPERATOR_INITIATOR_HARNESS and OPERATOR_INITIATOR_SESSION_ID appear zero times in the operator
    script; they exist only in harness_adapter.py and study_runner.py. Direct CLI writes carry no
    caller provenance, so the existing mechanism cannot solve MSC-RUL-002.
  trust: verified
```

## Proposed Rules — the working agreement

Agreed by both Claude sessions. Not enforced by anything.

```pbc:proposed-rules
- id: MSC-RUL-101
  name: One Label Per Actor
  rule: >
    Each actor writes a distinct --by value: claude-consultant, claude-supervisor, and codex
    reserved exclusively for the real Codex harness. Never label a Claude session codex — it
    both misattributes that session's work and makes Codex's genuine contributions
    indistinguishable. This rule replaces a withdrawn earlier version that made exactly that
    error. Labels are provenance only and confer no authority.
  trust: agreed-pending-operator
- id: MSC-RUL-102
  name: Always Pass --task
  rule: >
    Every ledger command names its task explicitly. Never rely on current_task. Follows directly
    from MSC-RUL-003, which has already misdirected one write.
  trust: agreed
- id: MSC-RUL-103
  name: Write To Another Session's Task By Handoff Only
  rule: >
    A session may always add a handoff to any task. It does not claim-add or evidence-attach on a
    task another session is driving without saying so in a handoff first. Disagreement belongs in
    the handoff chain where it is legible, not in an edit that overwrites context.
  trust: agreed
- id: MSC-RUL-104
  name: Verification Crosses Sessions
  rule: >
    No session verifies a claim it authored. Mechanical gates run as uid 971. This is what makes
    the arrangement peer rather than hierarchical — each session is the other's verifier,
    symmetrically, and neither reviews by rank.
  trust: agreed
- id: MSC-RUL-105
  name: Name The Reviewer At Create Time
  rule: >
    task-create sets --review to an actor other than the one creating the task. Because
    review_harness is write-once (MSC-RUL-004), a task created without this cannot be repaired,
    and a task whose author is also its designated reviewer forces doctor to emit either a
    self-verification Error or a reviewer-mismatch line no matter who verifies.
  trust: agreed
- id: MSC-RUL-106
  name: Announce Long Jobs In The Ledger
  rule: >
    Post a handoff before starting work that holds ollama, the GPU, or the test suite for an
    extended period. One machine, one model server. One session held ollama roughly four hours
    across three pilot passes and announced it only in conversation.
  trust: agreed
- id: MSC-RUL-107
  name: No Single-Trial Corrections
  rule: >
    No session revises another's finding on an n=1 result. Pilot passes 1 through 3 taught this
    twice in opposite directions: pass 2 revised pass 1 on n=1, then pass 3 at n=5 restored pass
    1's per-model ratios and showed pass 2's revision was the noisier reading.
  trust: agreed
```

## Ledger Registration

The coordination task exists; do not pre-register claims. The only claim worth making here is
about adherence, and it cannot be evidenced until records accumulate under distinct labels.

```bash
# already open
./operator task-create --id session-coordination-protocol \
    --assign claude --review codex \
    --objective "Working agreement between concurrent agent sessions"

# once records exist under distinct labels, verified from a distinct UID
./operator claim-add --task session-coordination-protocol --type file_exists \
    --text "every ledger write since <date> carries a distinct actor label" \
    --gate owners-manual/pbc/appendix-multi-session-coordination.pbc.md
```

## Open Questions Requiring An Operator Ruling

1. **Should any of this be enforced rather than agreed?** Every rule is voluntary and nothing
   detects a violation. A `--by` allowlist, or refusing a write when `current_task` was set by a
   different label, would make MSC-RUL-101/102 real. That is a code change to a governance tool on
   the strength of a two-day incident, and may be an overcorrection.
2. **Are `claude-consultant` and `claude-supervisor` the right labels?** They encode the operator's
   own words, but "supervisor" implies rank in an arrangement the operator asked to be peer.
   Cheap to change now, expensive after many records.
3. **Should the twelve mislabeled handoffs be annotated?** They cannot be rewritten — the durable
   event store would flag it, correctly. A joint attribution handoff is the only available remedy
   and depends on memory that is already degrading. It is proposed as the first joint action and
   has not been written.
4. **Does `current_task` deserve to exist?** It is a convenience that has caused one misdirected
   write and three surprises. Removing it is a breaking change; MSC-RUL-102 works around it.

## Provenance

```pbc:provenance
- ref: ".operator/handoffs/session-coordination-protocol/handoff-0001.yaml"
  confidence: verified
  review_status: "superseded"
  note: "Original proposal. Its R1 assumed two actors and would have relabeled the other session as codex; withdrawn in handoff-0003."
- ref: ".operator/handoffs/session-coordination-protocol/handoff-0002.yaml"
  confidence: verified
  review_status: "active"
  note: "claude-supervisor's counter-proposal. Caught the two-actor error and established codex as a real third actor."
- ref: ".operator/handoffs/session-coordination-protocol/handoff-0003.yaml"
  confidence: verified
  review_status: "active"
  note: "Acceptance. Settled MSC-RUL-001 empirically in a throwaway ledger."
- ref: ".operator/handoffs/opr-continuation-loop-audit/handoff-0003.yaml"
  confidence: verified
  review_status: "active"
  note: "by: codex, 2026-08-08T06:18:35. Evidence that codex is a distinct actor, alongside evidence-0008 produced_by codex."
- ref: "operator:1651"
  confidence: verified
  review_status: "active"
  note: "review_harness assigned at task-create and mutated nowhere. Source of MSC-RUL-004."
- ref: "EXECUTOR_IDENTITY_SPEC.md"
  confidence: verified
  review_status: "active"
  note: "Names and harness assignments do not create isolation. Why --by labels are provenance only."
- ref: "MACHINE_PROVENANCE_SPEC.md"
  confidence: verified
  review_status: "active"
  note: "Single-ledger constraint behind the Non-Goals."
```

## Open Risks

- **The remedy for the existing damage is memory, and memory is the thing failing.** Both sessions
  independently reconstructed the same attribution split, which is reassuring and is not evidence.
  If the joint attribution handoff is not written while both can still recall it, twelve records
  stay permanently ambiguous.
- **These conventions are self-reported compliance by the parties they constrain**, recorded in a
  ledger built on the premise that self-reported compliance is insufficient. That tension is not
  resolved here and is the substance of Open Question 1.
- **A third Claude session, or a resumed one, would arrive knowing none of this.** Nothing loads
  this contract at session start.
