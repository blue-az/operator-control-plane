---
id: pbc_pi_operator_extension
title: "Pi Operator Extension — Behavior Contract Draft"
context: pi-operator-extension
status: draft
tags:
  - pbc
  - operator
  - pi
  - extension
  - harness
updated: 2026-09-01
---

# Pi Operator Extension — Behavior Contract Draft

> Draft PBC for a project-local Pi extension that makes Operator easier to use
> without weakening Operator's claim/evidence/verification boundary. This is a
> design guardrail for work that can spin out of the owner's easy course-correction
> range.

## Purpose

The extension should reduce the owner's memory burden when operating this repo
inside Pi. It should expose the common Operator moves as slash commands and safe
structured tools while preserving the ledger principle: narration is never a
verdict, claims require evidence, and verification remains distinct from claim
authorship.

## Scope

Covers a `.pi/extensions/operator/` project-local Pi extension for this repository.
It governs command names, default identity handling, safe wrapping of `./operator`,
and the boundary between ergonomic shortcuts and authority.

## Non-Goals

- Replacing the `operator` CLI as source of truth.
- Creating a hosted service, cross-repo dependency, or Bulkhead Tau-specific API.
- Letting the model mark its own work verified.
- Treating Pi slash command output as evidence unless it is explicitly attached.
- Solving Claude/OpenCode integration. Those may reuse the same adapter later.
- Collapsing delegation, supervisor review, and handoff into one overloaded action.

## Actors

```pbc:actors
- id: operator_user
  name: Operator user
  type: human
  description: Owns decisions, starts Pi, and decides whether proposed behavior is accepted.
- id: pi_harness
  name: Pi harness
  type: external
  description: Terminal coding harness that loads the project-local extension and runs commands/tools.
- id: pi_agent
  name: Pi agent
  type: system
  description: The model-driven assistant inside Pi. It may call extension tools but does not become a verifier by doing so.
- id: operator_cli
  name: Operator CLI
  type: system
  description: The repository's executable ledger interface, invoked as ./operator.
- id: pbc_spec
  name: PBC spec process
  type: external
  description: Upstream behavior-contract discipline used to keep ambiguous product behavior explicit before implementation.
- id: delegated_implementer
  name: Delegated implementer
  type: external
  description: Internal or external agent/harness asked to perform bounded implementation work while the current Pi agent and operator user remain in the loop.
- id: supervisor_reviewer
  name: Supervisor reviewer
  type: external
  description: Distinct agent/harness asked to review a wrapped-up session or claim set before the operator relies on it.
- id: continuity_successor
  name: Continuity successor
  type: external
  description: Agent or future session taking over because the current session is ending, usually due to token, context, or carrier continuity limits.
```

## Rules

These verified rules record live CLI constraints the extension must respect. They
are facts about the current repository, not approval of the proposed extension.

```pbc:rules
- id: POE-RUL-001
  name: Brief Generation Fails Closed For An Unrouted Harness
  rule: >
    generate_brief_markdown returns None and prints that a harness is neither
    assigned_harness nor review_harness when the target is not routed on the
    task. brief, export-brief, and session-start all depend on that path.
    assigned_harness is written by task-create --assign and by session-start
    only when the field is empty; task-route corrects --review only. Delegation
    to an implementer not already routed on the task therefore requires a new
    scoped task or an explicit routing feature not present today.
  trust: verified
- id: POE-RUL-002
  name: review-delegate Is Claim-Scoped And Requires A Verify Command
  rule: >
    review-delegate takes one positional claim, refuses to run without a recorded
    or supplied --verify-cmd, refuses broker-enrolled ledgers, and requires an
    explicit --reviewer because review_harness is routing metadata only. There
    is no current session-scoped or multi-claim review unit.
  trust: verified
- id: POE-RUL-003
  name: Three Identity Axes Only One Of Which Carries Authority
  rule: >
    --by is provenance text; harness ids under .operator/harnesses are routing
    targets for brief/session/review-delegate; identity.yaml names plus executing
    Unix uid carry verifier authority in enforced mode. The extension must not
    collapse these axes.
  trust: verified
- id: POE-RUL-004
  name: Per-Session Harness Ids Have No Adapter Profile
  rule: >
    harness_adapter profiles key on carrier ids such as claude or codex, while
    session-derived harness ids such as pi-<session> are ledger identities.
    Routing id and dispatch id are separate axes unless an adapter mapping is
    explicitly configured.
  trust: verified
- id: POE-RUL-005
  name: Dual Implementer Reviewer Targets Are Unsafe
  rule: >
    Doctor has a builder-brief poisoning check, but a harness that is both
    implementer and reviewer can be recorded as a review role rather than a
    builder role. The extension must refuse choices that make one target both
    implementer and reviewer until Operator closes that gap.
  trust: verified
```

## Proposed Rules

```pbc:proposed-rules
- id: POE-RUL-101
  name: Extension Is An Ergonomic Wrapper
  rule: >
    The Pi extension wraps ./operator commands. It does not create an alternate
    ledger, alternate authority model, or hidden state that can supersede files
    under .operator/.
  trust: proposed
- id: POE-RUL-102
  name: Session Identity Binds To Provenance Only
  rule: >
    The extension derives a session-scoped label for --by on claim-add, draft
    evidence-attach, and handoff-add. It never defaults --verified-by, --for,
    --harness, or --reviewer from session metadata: those resolve to registered
    harness ids and identity.yaml names (POE-RUL-003). Commands that assign or
    request review require an explicitly chosen configured target and never reuse
    the current agent as implementer or reviewer.
  trust: proposed
- id: POE-RUL-103
  name: Slash Commands Are Human Ergonomics
  rule: >
    /op:* commands are optimized for the operator user in interactive Pi. If the
    model needs the same capability, the extension exposes a structured tool with
    explicit parameters rather than relying on the model to type slash commands.
  trust: proposed
- id: POE-RUL-104
  name: Structured Tools Are Narrow And Fail-Closed
  rule: >
    Model-callable tools wrap specific Operator operations such as doctor,
    task-list, task-show, claim-add, evidence-attach, and handoff-add. A raw
    arbitrary operator command tool is out of scope until a later explicit design
    accepts the risk.
  trust: proposed
- id: POE-RUL-105
  name: Output Is Not Evidence Until Attached
  rule: >
    A successful /op:doctor run, task listing, or command notification is only
    terminal output. It becomes ledger evidence only through an explicit
    evidence-attach operation that records the artifact or rerunnable command.
  trust: proposed
- id: POE-RUL-106
  name: PBC Guards Ambiguity Before Implementation
  rule: >
    When extension behavior is ambiguous enough that the owner cannot easily
    course-correct from implementation details alone, draft or update a PBC before
    adding code. The PBC names authority boundaries, non-goals, and acceptance
    outcomes.
  trust: proposed
- id: POE-RUL-107
  name: Delegate Supervisor Review And Handoff Are Distinct Moves
  rule: >
    delegate sends bounded implementation work to another agent while the current
    agent remains in the loop, producing a brief_issued event with role builder.
    supervisor-review asks a distinct agent to review one named claim, producing
    a bundle under .operator/review_delegations/. handoff records closeout,
    always; continuity transfer is a mode of handoff in which a successor is
    named in --next-action, not a separate concept.
  trust: proposed
- id: POE-RUL-108
  name: Delegation Surface Starts As A Guided Chooser Over Registered Targets
  rule: >
    The first surface is a small stable command plus a Pi UI chooser backed by
    project configuration. Each target carries a ledger harness id that must
    exist under .operator/harnesses/ and a carrier id with an adapter profile.
    Unknown ids fail closed. The config may add model, isolation mode, and
    command template; it may not invent harness ids or override assigned_harness
    or review_harness. The chooser refuses any selection that would make one
    target both the task's implementer and its reviewer (POE-RUL-005), and never
    offers a target the CLI would reject (POE-RUL-001).
  trust: proposed
- id: POE-RUL-109
  name: Dogfood Acceptance Is A Named Artifact Set
  rule: >
    Acceptance requires a real run on this repository producing: one task id; at
    least one claim carrying --verify-cmd; ./operator doctor output attached as
    run_log evidence; one bundle under .operator/review_delegations/; one
    handoff; and either a status recorded by a registered verifier uid, or an
    outcome explicitly labeled advisory. Because this ledger is mode: enforced
    and uid 1000 holds no verifier role, a dogfood run cannot self-verify;
    whether it reaches a real verifier is the test. "The record is clearer" is
    not an acceptance criterion.
  trust: proposed
- id: POE-RUL-110
  name: Delegation Is Invocation Not Paste
  rule: >
    /op:delegate starts the target through the adapter with the exported brief on
    the command line (LID-RUL-101). Emitting a brief for the human to paste is a
    labeled fallback, not the default, and the UI states which path was taken.
  trust: proposed
- id: POE-RUL-111
  name: Reviewers Do Not Trust The Reviewed Project
  rule: >
    Supervisor-review dispatch uses the adapter's JUDGE role args such as
    --no-approve for pi, so the reviewer does not load the reviewed repository's
    project-local files, including this extension. review_delegate_cmd currently
    emits --approve; correcting it is an operator-side task, and the extension
    does not paper over it.
  trust: proposed
- id: POE-RUL-112
  name: Always Pass --task
  rule: >
    Every operator invocation the extension issues names its task explicitly and
    never relies on current_task. /op:use sets an extension-session-scoped task
    and displays it; writing the ledger's current_task requires explicit
    confirmation.
  trust: proposed
- id: POE-RUL-113
  name: Delegated Implementers Do Not Write Lifecycle
  rule: >
    Tools and dispatch templates exposed to a delegated implementer omit --status
    and --verified-by entirely rather than validating them. Existing crystal
    ingestion commands are the precedent: lifecycle/verdict authority is not an
    implementer input.
  trust: proposed
```

## Behavior Candidate

```pbc:proposed-behavior
id: POE-BHV-001
name: Provide Operator Slash Commands In Pi
actor: pi_harness
description: >
  When this repository is trusted by Pi, the project-local extension provides
  /op:doctor, /op:status, /op:tasks, /op:use, /op:claim, /op:evidence,
  /op:delegate, /op:supervisor-review, and /op:handoff commands that call
  ./operator and display concise results in the Pi TUI.
trust: proposed
```

```pbc:proposed-behavior
id: POE-BHV-002
name: Provide Narrow Operator Tools To The Pi Agent
actor: pi_agent
description: >
  The extension exposes narrow structured tools for the model: operator_doctor,
  operator_task_list, operator_task_show, operator_claim_add,
  operator_evidence_attach, and operator_handoff_add. These tools encode safe
  defaults and do not let the model self-verify its own claims.
trust: proposed
```

```pbc:proposed-behavior
id: POE-BHV-003
name: Use PBC As A Design Brake For High-Uncertainty Extension Work
actor: operator_user
description: >
  Before adding broad automation, cross-harness routing, raw command execution,
  or lifecycle-changing behavior, the owner asks for a PBC-style contract and
  reviews the named rules/outcomes before implementation begins.
trust: proposed
```

## Candidate Command Set

```pbc:grounding
status: draft
commands:
  wave_1:
    - name: /op:doctor
      wraps: ./operator doctor
      reason: cheap consistency check before and after work
    - name: /op:status
      wraps: task-show, claim-list, session-list, doctor summary
      reason: fast orientation without reading multiple files
    - name: /op:tasks
      wraps: ./operator task-list
      reason: select and inspect work without remembering flags
    - name: /op:use
      wraps: ./operator task-use
      reason: make current-task switching explicit
    - name: /op:claim
      wraps: ./operator claim-add
      reason: claim creation with session-derived --by
    - name: /op:evidence
      wraps: ./operator evidence-attach
      reason: make evidence attachment the normal closeout path
    - name: /op:delegate
      wraps: task-create --assign when the target is not yet routed, then session-start, then adapter invocation with the brief
      reason: send bounded implementation work to an internal or external implementer while the current Pi agent remains in the loop
      interface: chooser-first; completions for task id and configured target aliases; primary path invokes the target, paste is labeled fallback only
    - name: /op:supervisor-review
      wraps: ./operator review-delegate
      reason: request distinct-agent review of one named claim after work is wrapped up
      interface: chooser-first; claim required; explicit reviewer required; verify_cmd must exist or be supplied; unavailable under broker enrollment
    - name: /op:handoff
      wraps: ./operator handoff-add
      reason: closeout record; continuity transfer is the mode where a successor is named
      interface: editor/textarea-first because handoff quality depends on prose context
  wave_2:
    - name: /op:session-start
      wraps: ./operator session-start
    - name: /op:session-end
      wraps: ./operator session-end
    - name: /op:brief
      wraps: ./operator brief or export-brief
    - name: /op:usage
      wraps: ./operator usage-summary
  wave_3:
    - name: /op:pbc-draft
      wraps: create or update a PBC draft, not ledger authority
    - name: /op:pbc-lint
      wraps: ./pbc_lint.py
    - name: /op:adapter-export
      wraps: shared adapter surface for Claude/OpenCode/MCP later
```

## Acceptance Outcomes

```pbc:proposed-outcomes
- The extension can be loaded from .pi/extensions/operator/index.ts in a trusted project.
- /op:doctor runs ./operator doctor and shows success or failure without modifying the ledger.
- /op:claim records a claim using a session-derived author id by default.
- /op:evidence can attach an artifact together with a rerunnable --verify-cmd to a named claim or active task.
- The model can call narrow Operator tools, but no exposed tool marks its own claim verified.
- No exposed tool or dispatch template accepts --status or --verified-by.
- /op:delegate, /op:supervisor-review, and /op:handoff are separate commands with separate help text and records.
- python3 pbc_lint.py owners-manual/pbc --ledger .operator succeeds.
- A dogfood run on this repo produces the named artifact set in POE-RUL-109.
```

## Product Shape vs Future Features

```pbc:grounding
status: draft
product_shape:
  definition: The project is a Pi-native Operator extension that standardizes existing ledger workflows without replacing Operator authority.
  included_now:
    - project-local Pi slash commands for common Operator moves
    - narrow model-callable Operator tools
    - explicit separation of delegate, supervisor-review, and handoff
    - chooser-first delegation surfaces where flags would overfit unstable options
    - dogfood-driven acceptance on this repository
  not_the_same_as_future_features: Future features are candidate expansions after the basic workflow proves useful; they are not required for the project to be coherent.
  candidate_pbc_commands:
    - name: /pbc:define
      purpose: Define or revise the product/project shape, scope, non-goals, actors, and load-bearing rules before implementation.
    - name: /pbc:feature
      purpose: Add a future feature candidate or issue-backed feature slice without making it part of the current acceptance gate.
```

## Future Feature Candidates

```pbc:grounding
status: draft
future_features:
  - id: POE-FUT-001
    name: PBC define command
    command: /pbc:define
    description: Guided creation or update of the product/project shape sections from an owner prompt, producing draft/proposed blocks but not ratifying them.
  - id: POE-FUT-002
    name: PBC feature command
    command: /pbc:feature
    description: Add a future feature candidate or issue-backed feature slice with source links and next steps without making it part of the current acceptance gate.
  - id: POE-FUT-003
    name: PBC lifecycle wizard
    description: Walk the owner through proposed -> frozen claim -> operator ruling -> ratified block movement, preserving the distinct-agent requirement.
  - id: POE-FUT-004
    name: Multi-claim supervisor review
    description: First-class claim-set/session review if Operator later gains a review unit broader than one claim.
  - id: POE-FUT-005
    name: Shared adapter export
    description: Extract stable Operator integration logic for Claude/OpenCode/MCP after the Pi extension reveals the minimum useful surface.
  - id: POE-FUT-006
    name: Delegation target registry UI
    description: Manage aliases, harness ids, carrier commands, models, isolation modes, and brief formats through a chooser/editor.
  - id: POE-FUT-007
    name: Verifier authorization prompt
    description: Use a user-visible authorization prompt for distinct-UID verification instead of requiring agents to improvise sudo commands or silently fall back to same-UID advisory review.
  - id: POE-FUT-008
    name: Operator roadmap command
    command: /op:roadmap
    description: Show the current implementation ladder, verified steps, active blockers/decisions, next recommended action, and future feature candidates without mixing future scope into the current acceptance gate.
  - id: POE-FUT-009
    name: Trusted verifier run command
    command: /op:verify-run
    description: Launch a generated review_delegations verifier script through a visible human authorization prompt, stream/report failures, and attach verifier run logs when possible, so users do not copy/paste sudo bash while still preserving the no-silent-cross-UID boundary.
  - id: POE-FUT-010
    name: Operator next-steps command
    command: /op:next-steps
    description: Turn the active task's ledger state into a short prioritized action list: current next_action first, then unverified claims, missing review/verification gates, recent dogfood issues, and recommended future slices.
  - id: POE-FUT-011
    name: Operator project dashboard
    command: /op:project or /op:roadmap --project <prefix>
    description: Visualize a multi-task project prefix as phases: task id, status, verified claims versus total claims, evidence count, handoff count, stale next_action warnings, latest verified claim, latest open issue, and recommended next phase. Intended for dogfood/project-level orientation before moving the extension to other repos.
```

## Dogfood Issue Backlog

```pbc:grounding
status: draft
issues:
  - id: POE-ISS-001
    source: docs/REVIEW_pi-operator-extension-pbc_2026-09-01.md F1
    summary: POE rules are currently in a ratified pbc:rules fence even though they have not gone through proposal lifecycle.
    next_step: Re-fence proposed material before relying on the PBC as a gate.
  - id: POE-ISS-002
    source: docs/REVIEW_pi-operator-extension-pbc_2026-09-01.md F2
    summary: /op:supervisor-review promises session or claim-set review, while review-delegate currently accepts one claim and needs a verify command.
    next_step: Narrow wave-1 supervisor-review to one claim, or explicitly model claim-set review as repeated single-claim bundles.
  - id: POE-ISS-003
    source: docs/REVIEW_pi-operator-extension-pbc_2026-09-01.md F3
    summary: /op:delegate has no general CLI route to an implementer that is not already assigned or reviewing the task.
    next_step: Restrict chooser targets to routable harnesses or make new implementer delegation create a scoped child task.
  - id: POE-ISS-004
    source: docs/REVIEW_pi-operator-extension-pbc_2026-09-01.md F5/F7
    summary: Session-derived harness ids, carrier ids, and authority identities are separate axes and current adapters do not map all of them cleanly.
    next_step: Decide the minimum identity/target config before implementing delegate launch.
  - id: POE-ISS-005
    source: docs/REVIEW_pi-operator-extension-pbc_2026-09-01.md F10
    summary: review-delegate may launch reviewing Pi with --approve, which can trust the project-local extension being reviewed.
    next_step: Open a separate Operator task for the review-delegate approval/isolation defect.
  - id: POE-ISS-006
    source: docs/REVIEW_pi-operator-extension-pbc_2026-09-01.md F11
    summary: Dogfood acceptance must be falsifiable, not just a prose judgment that the ledger is clearer.
    next_step: Define a binary dogfood gate such as non-self-verification plus required ledger artifacts.
  - id: POE-ISS-007
    source: pi-operator-extension-step1 dogfood handoff-0005
    summary: Distinct-UID verification currently blocks on ad hoc sudo/auth state; the correct UX is a human-visible authorization prompt, not a hidden agent retry or same-UID downgrade.
    next_step: Add a supervisor-review/verifier-auth design slice that prompts the user explicitly when a verifier UID run is needed and records advisory vs trusted outcome distinctly.
  - id: POE-ISS-008
    source: pi-operator-extension-step2 dogfood handoff-0006
    summary: Verifier-only identities cannot attach draft/no-status evidence because evidence attachment without verification requires builder authority; verifier rerun logs must be attached as verified evidence or supplied through a builder-produced artifact path.
    next_step: Make /op:supervisor-review distinguish advisory review notes, builder-owned draft artifacts, and verifier-owned status-setting evidence so the UI does not offer an impossible no-status verifier attach path.
  - id: POE-ISS-009
    source: pi-operator-extension-step5 live TUI dogfood handoff-0004
    summary: /op:handoff treated a one-word user input "go" as a literal next_action and recorded an empty handoff with null fields instead of generating a useful closeout from current task context.
    next_step: Change /op:handoff UX so it generates a deterministic draft from task/status/recent handoffs first, defaults to generated closeout without requiring "go", and refuses near-empty handoffs unless the user explicitly uses manual edit mode.
  - id: POE-ISS-010
    source: pi-operator-extension-step5 live TUI dogfood
    summary: /op:claim and /op:evidence work but ask too many questions for the common path; Step 5 needs opinionated defaults so normal dogfood does not require the owner to re-specify obvious task, author, type, claim, and verify command fields.
    next_step: Add a defaults pass for authoring flows: infer current task and session author, suggest claim type and gate from recent context, prefer the active/recent claim for evidence, and keep advanced fields behind an edit/details path.
  - id: POE-ISS-011
    source: pi-operator-extension-step5 live TUI dogfood
    summary: /op:doctor and /op:status are slow on large ledgers and previously showed no visible progress while running.
    next_step: Add visible working/status notifications before long Operator reads and clear them when the command finishes.
  - id: POE-ISS-012
    source: pi-operator-extension-step5 verifier run dogfood
    summary: Generated review_delegations scripts are not yet reliable end-to-end: operator-verifier may lack Pi provider credentials/home setup, sudo resets PATH so pytest may be unavailable, pytest cache writes warn under the verifier UID, and the generated prompt still suggests --verified-by reviewer even though evidence-attach requires the executing verifier identity.
    next_step: Implement /op:verify-run or repair review-delegate generation so the verifier launch validates home/provider/PATH first, uses a writable cache or disables pytest cache, and instructs verifier evidence attachment with the executing verifier identity.
  - id: POE-ISS-013
    source: pi-operator-extension-target-ux-cleanup
    summary: Review/delegation UI exposed too much harness plumbing: users reason in terms of model/persona targets such as Claude/Luna/Grok, while Pi is a carrier runtime and operator-verifier is a separate Unix authority identity.
    next_step: Rename prompts/docs around model/persona targets, remove Pi as a default delegation target, and keep reviewer labels distinct from verifier Unix users in generated review instructions.
```

## Implementation Ladder

```pbc:grounding
status: draft
ladder:
  - step: 0
    name: Repair PBC lifecycle shape
    gate: Proposed rules/behavior/outcomes are fenced as proposed material, this file passes pbc_lint with --ledger, and the review findings are represented as issue backlog.
  - step: 1
    name: Read-only orientation commands
    gate: /op:doctor, /op:status, /op:tasks, and /op:use run without ledger authority changes beyond explicit task-use.
  - step: 2
    name: Claim/evidence/handoff commands
    gate: /op:claim, /op:evidence, and /op:handoff create the expected ledger records with session-derived author defaults and no self-verification.
  - step: 3
    name: Supervisor-review command
    gate: /op:supervisor-review handles one claim with explicit reviewer and verify command, preserving review-delegate's fail-closed behavior.
  - step: 4
    name: Delegate chooser
    gate: /op:delegate presents only routable choices or creates a scoped child task; no target is silently both implementer and reviewer.
  - step: 5
    name: Falsifiable dogfood run
    gate: A real repo task uses at least one delegate/supervisor-review loop, produces claims/evidence/handoffs, and reaches a verifier identity distinct from the author where verification is claimed.
```

## Open Questions

1. Should Operator itself read Pi initiator/session environment variables (for example the values resolved by `resolve_initiator_identity()` / MSC-RUL-006), or should the extension pass a session-scoped `--by` explicitly on every write?
2. Should `/op:status` be purely read-only, or should it offer guided follow-up actions through Pi UI prompts?
3. Should PBC drafting be a command in this same extension, or remain a manual/spec workflow until the basic Operator commands prove useful?
4. Should the Pi extension dispatch through `harness_adapter.py`, or bypass it as `evals/local_lane_ladder/runner.py` does?
5. What is the smallest stable delegation target config: alias, kind, harness id, model, command template, isolation mode, and default brief format; or fewer fields?
6. Should supervisor-review support claim sets as a first-class Operator concept, or should wave 1 intentionally model them as repeated single-claim reviews?
7. Is a per-session `.operator/harnesses/<id>.yaml` the intended long-term shape, given that those ids have no adapter profile and the registry grows without bound?
8. Should `review_delegate_cmd` gain a no-approve reviewer mode, and is that a blocker for `/op:supervisor-review`?

## Proof Boundary

Shows: a proposed safe shape for a Pi-native Operator extension and the role PBC
should play when implementation detail exceeds easy owner correction.

Does not show: that the extension has been implemented, that the proposed command
set is complete, that the identity format is final, or that Claude/OpenCode/MCP
integration should share all of the same affordances.
