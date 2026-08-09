---
id: pbc_local_routing_corpus
title: "Local Routing Corpus — Behavior Contract"
context: local-lane-routing
status: draft
tags:
  - pbc
  - owner-manual
  - routing
  - corpus
  - proposed
---

# Local Routing Corpus — Behavior Contract

> PBC for building a corpus of *real* tasks from this machine, measuring what they cost to
> complete, and deciding which could be routed to a local model.
>
> **Nothing in the Proposed sections is implemented.** Per repository convention, all
> unbuilt behavior is fenced as `pbc:proposed-*` so tooling does not read it as active.
> The one `pbc:rules` block below documents the router that ships **today**, which is not
> the router described in `docs/LOCAL_LANE_ROUTER_STUDY.md`.

## Scope

Three questions, in order, each gating the next:

1. **What work actually happens on this machine?** Harvest tasks from real harness logs
   (`~/.claude`, `~/.codex`, `~/.grok`) rather than authoring a corpus.
2. **How complex is each task?** Along axes that predict local-model success — shape,
   tool-call count, state-carrying, data locality — not "difficulty."
3. **Which could have run locally?** Answered by *executing* candidates against
   deterministic postconditions, not by asking a classifier for an opinion.

## Non-Goals

- Routing on estimated difficulty. `LOCAL_ROUTER_STUDY §5.5` rejects it and the failure
  data contradicts it.
- Replacing `evals/local_lane_ladder/`. The ladder measures execution on synthetic
  fixtures; this corpus measures what real work looks like. They answer different questions.
- Automatic routing changes. No corpus result may alter dispatch until it clears the
  evidence bar in the proposed rules below.
- A second `.operator/` ledger. `MACHINE_PROVENANCE_SPEC.md` forbids it.
- Any claim that classification accuracy predicts execution success. The study's §6 states
  it does not.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Owns the machine whose logs are harvested, and the only party who may authorize a routing change.
- id: corpus_harvester
  name: Corpus harvester
  type: system
  description: Extracts candidate task units from harness transcripts, with provenance and scrubbing.
- id: task_classifier
  name: Task classifier
  type: system
  description: Local model in the router seat, emitting lane, interaction mode, and expected tool calls.
- id: opr_router
  name: opr router (shipped)
  type: system
  description: route_task/get_routing_for_model as implemented today. Keyword matching, not the studied classifier.
- id: ladder_harness
  name: Ladder harness
  type: system
  description: Executes a task against a disposable fixture and grades it with a deterministic postcondition.
- id: operator_ledger
  name: Operator ledger
  type: system
  description: Records corpus claims, evidence, and verification.
```

## Rules — as shipped today

```pbc:rules
- id: TRC-RUL-001
  name: Shipped Routing Is Keyword Matching
  rule: >
    route_task selects frontier only when the prompt text literally contains one of
    "claude", "codex", "gpt-4", "gpt-o" AND config.frontier.enabled is true; otherwise it
    returns config.default_model unconditionally. Lane 1 versus Lane 2 is chosen by the
    literal substring "strict json". No task-shape, capability, or tool-count signal
    participates.
  trust: verified
- id: TRC-RUL-002
  name: The Shape Contract Is Advisory Only
  rule: >
    print_local_lane_lint_verdict emits one task_lint verdict line before local dispatch and
    never changes routing, the model chosen, or whether dispatch proceeds.
  trust: verified
- id: TRC-RUL-003
  name: The Router Study Is Not Installed
  rule: >
    docs/LOCAL_LANE_ROUTER_STUDY.md recommends the 26b router seat, numeric
    expected_tool_calls, a data-locality feature, and lane-gated mode inference. None are
    implemented. Its prototype (~/Documents/local/routing/route.py) shares no code with opr
    in either direction, and the study has no task, claim, or evidence in the ledger.
  trust: verified
```

## Proposed Rules

```pbc:proposed-rules
- id: TRC-RUL-004
  name: A Turn Is Not A Task
  rule: >
    Harvested transcript turns are conversational by default and most are not self-contained.
    Observed examples: "does xy compare with graphify", "so graphify might be able to use xy,
    but not vice versa?" — turns 3 and 4 of a thread, unroutable without their predecessors.
    A turn may enter the corpus as a task unit only if it is independently executable, or if
    it is admitted together with the reconstructed context it depends on and labeled as such.
    The exclusion rate must be reported as a headline figure, not a footnote.
  trust: proposed
- id: TRC-RUL-005
  name: Provenance On Every Unit
  rule: >
    Each corpus entry records source harness, session id, timestamp, cwd, git branch where
    available, and producing machine. Machine is mandatory: routing conclusions are
    decode-rate dependent and decode rate depends on how much of a model fits in VRAM on that
    host.
  trust: proposed
- id: TRC-RUL-006
  name: Selection Bias Is Stated, Not Corrected
  rule: >
    A corpus harvested from frontier harness logs contains the tasks the operator chose to
    give a frontier model. Work that would naturally have gone to a local model is
    systematically absent. This biases any "fraction routable locally" estimate downward and
    must be disclosed wherever that fraction is reported. Do not attempt to correct it by
    reweighting; there is no unbiased denominator available.
  trust: proposed
- id: TRC-RUL-007
  name: Routability Is Established By Execution
  rule: >
    A task may be labeled locally-routable only after a local model has executed it against a
    deterministic postcondition and passed. A classifier's lane label is a candidate, never a
    result. Tasks that cannot be reduced to a disposable fixture are classification-only and
    are excluded from any routability percentage.
  trust: proposed
- id: TRC-RUL-008
  name: Pre-890d595 Evidence Is Inadmissible As Negative
  rule: >
    Any historical record of a local model failing a task, produced through opr before
    890d595, cannot distinguish model failure from harness truncation and must not be used as
    evidence that the task is unroutable. This applies to the founding anecdote of
    LOCAL_LANE_ROUTER_STUDY §1 — the three-step git task — which post-fix measurement shows
    was harness truncation.
  trust: proposed
- id: TRC-RUL-009
  name: Repeat Before Reporting
  rule: >
    Every executed cell runs n>1 trials per configuration. The confound pilot established
    that at n=1 a single flip is indistinguishable from variance, with 4 of 17 cells failing
    to reproduce on replay. Single-trial routability labels may not be published.
  trust: proposed
- id: TRC-RUL-010
  name: Scrub Before Commit
  rule: >
    Harness transcripts contain file contents, absolute paths, credentials, and third-party
    material. No corpus artifact derived from them may be committed or attached as evidence
    until scrubbed, and the scrubbing pass is itself reviewable. Provenance fields keep
    session ids and paths; those are internal-only unless separately cleared.
  trust: proposed
- id: TRC-RUL-011
  name: Mode Is A Flag Until Proven Inferable
  rule: >
    Interaction mode (conversational vs delegated) is supplied by the caller. The study
    inferred it from phrasing cues its own corpus supplied, and its single mode error fell on
    the one task lacking a cue. Until a cue-free corpus shows otherwise, the classifier is
    asked for lane only.
  trust: proposed
```

## Proposed Behaviors

```pbc:proposed-behavior
id: TRC-BHV-001
name: Harvest Candidate Task Units
actor: corpus_harvester
description: Extract user turns from ~/.claude/projects (109 transcripts), ~/.codex (124), and ~/.grok/sessions (17), with provenance, and triage each as self-contained, context-dependent, or non-task.
trust: proposed
```

```pbc:proposed-outcomes
- Every extracted unit carries harness, session, timestamp, cwd, branch, machine.
- Triage counts are reported before any classification runs.
- Slash commands, pasted output, and tool results are excluded as non-tasks.
- No artifact leaves the harvest stage unscrubbed.
```

```pbc:proposed-behavior
id: TRC-BHV-002
name: Classify Lane And Tool-Call Band
actor: task_classifier
description: Ask the router-seat model for lane and a numeric expected_tool_calls per self-contained unit.
trust: proposed
```

```pbc:proposed-outcomes
- Output is strict JSON; parse failures are counted, not retried into silence.
- expected_tool_calls 0-1 suggests local, >=3 suggests supervised; the 1-2 band is
  explicitly unresolved and must not be forced.
- Classification is recorded as a candidate label, never as a routability result.
```

```pbc:proposed-behavior
id: TRC-BHV-003
name: Execute Routability Candidates
actor: ladder_harness
description: For units reducible to a disposable fixture, run a local model n>1 times against a deterministic postcondition.
trust: proposed
```

```pbc:proposed-outcomes
- Fixtures are disposable and built under tempfile.gettempdir(); no real repo is touched.
- Both the current harness defaults and the trial count are recorded per cell.
- A pass rate with a spread is reported; a bare point estimate is not.
- Cells that cannot be fixtured are reported as excluded, with the count.
```

```pbc:proposed-behavior
id: TRC-BHV-004
name: Report Routable Fraction
actor: corpus_harvester
description: Publish what fraction of real observed work a local model completed, with every exclusion and bias stated.
trust: proposed
```

```pbc:proposed-outcomes
- The denominator is stated explicitly and is not the raw turn count.
- Selection bias per TRC-RUL-006 appears wherever the fraction appears.
- The result is registered as a ledger claim with a re-runnable gate, and is advisory until
  verified by a distinct UID.
```

## Provenance

```pbc:provenance
- ref: "opr:438-477"
  confidence: verified
  review_status: "active"
  note: "get_routing_for_model and route_task. Source of TRC-RUL-001: keyword list at 471, 'strict json' substring at 456, unconditional default_model at 477."
- ref: "opr:1228-1230"
  confidence: verified
  review_status: "active"
  note: "The dispatch site. route_task runs when neither --frontier nor --model is given, so the shipped router is live on every unqualified dispatch."
- ref: "opr:480-495"
  confidence: verified
  review_status: "active"
  note: "print_local_lane_lint_verdict. Source of TRC-RUL-002; its docstring states it never changes routing."
- ref: "docs/LOCAL_LANE_ROUTER_STUDY.md"
  confidence: measured
  review_status: "unverified"
  note: "16/16 assignment for both models, n=1 per model at temperature 0, corpus authored by the party defining ground truth. No ledger record. Section 6 disclaims that routing accuracy predicts execution success."
- ref: "evals/local_lane_ladder/PILOT_CONFOUND_FINDINGS.md"
  confidence: measured
  review_status: "unverified"
  note: "Source of TRC-RUL-008 and TRC-RUL-009. 4 of 13 reproducing cells were harness artifacts; 4 of 17 did not reproduce at all."
- ref: "MACHINE_PROVENANCE_SPEC.md"
  confidence: verified
  review_status: "active"
  note: "Single-ledger constraint and machine-as-provenance semantics behind TRC-RUL-005."
- ref: "~/.claude/projects, ~/.codex, ~/.grok/sessions"
  confidence: verified
  review_status: "active"
  note: "250 transcript files surveyed 2026-08-08. User turns carry cwd, gitBranch, sessionId, timestamp. Sampled turns confirm TRC-RUL-004: real prompts are largely conversational follow-ups."
```

## Open Risks

- **The corpus may not contain enough fixturable tasks to answer question 3 at all.** Real
  work mutates real repos and references files that have since changed. If the fixturable
  subset is small, the honest output is a *classification* study with an execution footnote,
  not a routability percentage. This should be checked early, on a sample, before the full
  harvest is built.
- **Selection bias may dominate the result.** Per TRC-RUL-006 the denominator is
  frontier-chosen work. A low routable fraction would be partly an artifact of where the
  logs came from, and the study cannot distinguish that from a genuine capability ceiling.
- **Ground truth for "should have been local" does not exist.** Execution establishes that a
  local model *can* complete a task, never that routing it there would have been the right
  call — latency, supervision cost, and the operator's ~20 tok/s conversational floor are
  outside what a postcondition measures.
- **The classifier and the executed model may be the same model**, which makes the pipeline
  self-assessing. Whether the router seat may also hold the worker seat is unresolved.
- **Scrubbing is unbuilt and easy to get wrong.** Until TRC-RUL-010 has an implementation,
  every corpus artifact stays local and uncommitted.
- The shipped router (TRC-RUL-001) will keep making keyword decisions throughout this work.
  Nothing here changes dispatch, so corpus findings and live behavior will diverge until a
  separate, authorized change lands.
