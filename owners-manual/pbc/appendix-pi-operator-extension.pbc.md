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
updated: 2026-09-23
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

> Historical planning record (original wave plan), kept for provenance. The shipped
> command surface differs: `/op:pbc-draft` and `/op:pbc-lint` became `/pbc:define`,
> `/pbc:feature` and `/pbc:validate`, and later commands (`/op:next-steps`,
> `/op:project`, `/op:roadmap`, `/op:targets`, `/op:popup`, `/op:verify-run`,
> `/op:crystal*`) are not listed here. See Candidate Reconciliation below and the
> extension README for the current inventory.

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
  - id: POE-FUT-003
    name: PBC lifecycle wizard
    description: Walk the owner through proposed -> frozen claim -> operator ruling -> ratified block movement, preserving the distinct-agent requirement.
  - id: POE-FUT-004
    name: Multi-claim supervisor review
    description: First-class claim-set/session review if Operator later gains a review unit broader than one claim.
  - id: POE-FUT-005
    name: Shared adapter consumer integrations
    description: "Partial: carrier-neutral client.ts already exists with fixed argv and lifecycle retry tests. Remaining scope is concrete Claude/OpenCode/MCP consumer adapters and their integration tests; do not re-extract the existing client."
  - id: POE-FUT-016
    name: Opt-in crystal capture near compaction
    description: "Optional setting, off by default: when session context reaches a threshold (owner suggestion 90%), prompt to run the existing /op:crystal capture before Pi compacts, so the pre-compaction reasoning trail survives for later audit or as a handoff draft source. Keeps crystal separate from core: handoff remains the authored continuity record; crystal is optional pre-compaction capture. Same review/redact and confirmation as /op:crystal, no automatic ledger attachment. Open before building: whether Pi exposes a context-threshold or pre-compaction event, and whether capture after compaction still sees pre-compaction entries (post-release crystal validation). Not alpha scope."
```

## Candidate Reconciliation

This is an implementation inventory, not ratification or a new verification verdict.
The future list above contains only remaining implementation scope. IDs are preserved;
implemented items are not renamed as unspecified "enhancements".

| ID | Reconciled status | Basis / remaining acceptance |
|---|---|---|
| POE-FUT-001–002 | Implemented; not independently accepted | `/pbc:define` and `/pbc:feature` edit structured drafts, validate a temporary candidate, preview and confirm an append-only `pbc:grounding` proposal. Existing rules are unchanged; no ratification. |
| POE-FUT-003 | Not implemented | No lifecycle wizard. |
| POE-FUT-004 | Not implemented | Supervisor review remains scoped to one named claim. |
| POE-FUT-005 | Partially implemented | `client.ts` exports `CarrierNeutralOperatorClient`; `selftest.ts` tests argv and lifecycle retries. Consumer adapters remain. |
| POE-FUT-006 | Implemented; not independently accepted | `/op:targets` lists/adds/edits/removes target configuration with field prompts and confirmed preview. New/edited targets require a registered harness and resolved model; task routing and reviewer authority are untouched. |
| POE-FUT-007 | Prompt implemented; owner-confirmed popup success | The owner confirms the GUI popup worked; reviewer execution then failed on provider authentication. The popup itself does not set status, but launched code has verifier permissions. Its authorization dialog now shows the complete shell-quoted argv; only compact transcript reports abbreviate it. Read-only inspection of `.operator/tasks/review-delegate-gui-auth-popup.yaml` during release preparation still shows `assigned` with empty claims/evidence; this historical task is not closed by that observation. |
| POE-FUT-008 | Implemented | `/op:roadmap` reports ladder, current task, issues and futures; loader/handler selftests cover it. No new enhancement scope inferred. |
| POE-FUT-009 | Implemented; live privileged acceptance pending | `/op:verify-run` (labeled `[experimental]`; its dialog discloses that author-writable code runs under the verifier account) reuses GUI askpass, invokes a distinct-UID helper with confirmed input hashes (a freshness check, not code signing), retains private logs, and the helper itself attaches only after a reviewer decision file approves. The helper, `operator` and the verification command come from the author-writable checkout and run with the verifier's permissions and credentials, so author-controlled code can still write verifier evidence without a decision; a resulting `uid_isolated` status shows a distinct UID launched the run, not independence from author code. No live sudo/model review is established by automated tests; see `docs/specs/VERIFY_RUN_SPEC.md`. |
| POE-FUT-010 | Implemented; local task verified | `/op:next-steps` exists; local `pi-operator-extension-next-steps` records verified status and claim-0157. |
| POE-FUT-011 | Implemented | `/op:project` and `/op:roadmap --project`. |
| POE-FUT-012 | Implemented | Cross-project installer and explicit ledger contract; consumer project trust remains a human step. |
| POE-FUT-013 | Closed as guidance-only | Optional `/op:next-steps` modes; do not add `/op:mode` or a new gate. |
| POE-FUT-014 | Implemented; not independently accepted | `/pbc:validate [path]` uses the pinned Route C wrapper with fixed argv; no upstream `--profile`. |
| POE-FUT-015 | Implemented; not independently accepted | `/op:crystal` captures reviewed current-session notes via installed crystallize 0.1.16; `/op:crystal-attach [path]` and `/op:crystal-import [path]` wrap draft-only backends. Chooser only when attach/import omit a path. No automatic download or attachment. |
| POE-FUT-016 | Not implemented; idea recorded 2026-09-23 | Opt-in crystal prompt near a context threshold (suggested 90%) before compaction. Depends on post-release crystal validation and a Pi compaction/threshold hook. |

### Suggested implementation order

The first three slices are now implemented in `workflows/commands.ts` and registered
in `index.ts`. `tests/pi_operator_workflows.ts` covers temporary-ledger workflows;
installed capture/validator smoke checks explicitly skip if dependencies are absent.
These implementation/test facts do not constitute independent acceptance.

1. **014 — `/pbc:validate`: implemented.** Fixed wrapper invocation, explicit path, separated upstream/local findings; no invented flags.
2. **015 — crystal shortcuts: implemented.** Direct capture shortcut, direct attach/import paths, chooser only for omitted paths. Explicit session/task provenance and confirmation; narration remains draft/untrusted.
3. **001 then 002 — `/pbc:define`, `/pbc:feature`: implemented.** Validated draft-only append proposals, preview and confirmation. These are guided authoring flows, not assumed upstream subcommands.
4. **006 — target registry editor: implemented.** `/op:targets [list|add|edit <alias>|remove <alias>]` validates the existing registry axes, previews exact config and saves atomically after confirmation. Symlinks, stale previews and changed harness/model resolution are refused. `tests/pi_operator_targets.ts` covers config-only changes and routing preservation.
5. **009 — trusted verifier orchestration: implemented; acceptance pending.** `/op:verify-run` and the verifier-only helper provide bounded review/log/decision/attachment handling. Automated tests cover refusal and mocked UID/process paths. The 007 popup acceptance task and a live, explicitly authorized distinct-UID/provider run remain open. The author-side command exposes no verdict/status inputs, but that is not an enforcement boundary: author-writable code launched under the verifier account can attach verifier evidence.
6. **004 — multi-claim review:** only after defining an Operator claim-set review contract; do not merely loosen the one-claim Pi UI.
7. **005 — additional carrier adapters:** reuse the existing client when a concrete consumer needs it; validate each carrier rather than building speculative adapters.
8. **003 — lifecycle wizard:** last, once draft authoring and review paths are exercised; transitions must retain distinct-agent requirements and never equate validation with ratification.

This order prioritizes the requested PBC/crystal shortcuts, reuses existing backends,
and defers authority-sensitive or speculative expansions. It is a recommendation,
not task assignment. Existing static HTML boards are snapshots and need regeneration
to reflect this inventory; `/op:roadmap` reads this source directly.

> Release-preparation note (2026-09-23; not a ratification, acceptance or lifecycle change):
> The `0.1.0-alpha.1` boundary, prerequisites and disclosures are in
> `docs/releases/pi-operator-0.1.0-alpha.1.md`; `package.json` holds the frontend
> allowlist. Distribution is a tag of the public source repository, so recipients get
> the whole tracked tree, not only that allowlist. Core is orientation, task selection
> and confirmed claim/evidence/handoff shortcuts; delegation, reviews, target editing,
> PBC authoring/validation, crystals and the GUI/UID launchers are optional. Before
> counting a `/op:verify-run` or `/op:popup` status toward the step 5 dogfood gate,
> inspect what actually ran: a distinct verifier UID alone does not show independence
> from author-writable code.
>
> Factual implementation note (2026-09-05; amended 2026-09-16; not a ratification or lifecycle change):
> `/op:next-steps`, `/op:project`, and `/op:roadmap --project` exist as read-only orientation commands.
> POE-FUT-011 is implemented by those project-dashboard commands and is no longer a future candidate.
> POE-FUT-012 is implemented by `scripts/install-operator-extension.py` plus `.pi/operator-ledger.json` (`wired_into_findLedger: true`). There is no `/op:install` command. GitHub issue #18 is the tracking issue for that helper; it is not a remaining product gap beyond live Pi trust of the consumer project.
> POE-FUT-013 is closed as guidance-only; do not add `/op:mode`.
> POE-FUT-014 Route C is recorded as a compatibility-route choice only. The check is local wrapper `scripts/pbc_validate_operator.py` around the pinned pbc-spec CLI. The upstream CLI has no `--profile`. `proposed-*` fences are not canonical upstream types. The subsequently implemented `/pbc:validate` shortcut uses this wrapper; `/pbc:define` and `/pbc:feature` write draft proposals only.
>
> POE-ISS-001 closed 2026-09-16 (F1 re-fence already on disk; not a ratification of the extension).
> `pbc:rules` holds verified CLI facts POE-RUL-001–005 (`trust: verified`). Proposed extension
> material is `pbc:proposed-rules` POE-RUL-101–113, `pbc:proposed-behavior`, and `pbc:proposed-outcomes`.
> `python3 pbc_lint.py owners-manual/pbc/appendix-pi-operator-extension.pbc.md --ledger .operator` exits 0.
> This file remains `status: draft`. Do not treat the PBC as an acceptance gate for unratified `/op:*` behavior.
>
> POE-ISS-015 closed 2026-09-16. Review routing is distinct-agent only (`doctor` checks
> verifier UID vs author UID). Review-call packets must not use "cross-family" as a
> route/unrouteable gate. Remaining live wording is in `docs/REVIEW_CALL_*` section-5/7
> (decode packet already stated this; gptoss and dense-offload packets corrected).
>
> POE-ISS-011 closed 2026-09-16. `/op:doctor` and `/op:status` notify before the Operator
> read and `setStatus` then clear it in `finally`. Selftest covers that sequence. This does
> not make doctor faster; it makes the wait visible.
>
> POE-ISS-009 closed 2026-09-16. `/op:handoff` defaults to a generated closeout from
> task context (no editor). `/op:handoff go` is an alias for that draft, not a literal
> next_action. Empty editor drafts are refused; `/op:handoff edit` is the manual path.
>
> POE-ISS-010 closed 2026-09-16. Common-path `/op:claim [text]` and `/op:evidence [path]`
> default task/author from the session, type/gate/verify from opinionated defaults, and
> bind evidence to the latest unverified claim. `/op:claim edit` and `/op:evidence edit`
> keep the extra prompts.
>
> POE-ISS-013 and POE-ISS-014 closed 2026-09-17. Review prompts now describe model/persona
> targets separately from Pi carrier and verifier UID; Pi session harnesses are not offered
> as personas. `review-delegate` resolves Grok to `xai/grok-4.6` (unless explicitly overridden),
> records that command in the bundle, and doctor reports Grok delegations routed to another provider.
>
> POE-ISS-002, POE-ISS-003, POE-ISS-004, POE-ISS-007, and POE-ISS-008 closed 2026-09-17
> after reconciliation against the live extension and 604-pass selftest. Supervisor review is
> claim-scoped; unrouted delegation creates a scoped child task; harness/carrier/persona and
> verifier-UID axes are explicit; trusted sudo authorization is visible; and verifier-only
> evidence paths are fail-closed and labeled separately from builder drafts.
>
> POE-ISS-012 closed 2026-09-17. Generated review launches now fail closed unless the target
> seat has a home directory, `pi` on PATH, and provider auth via the target auth file or
> provider environment. They disable pytest's cache provider to avoid verifier-owned cache
> writes and instruct evidence attachment with the executing `$(whoami)` identity.
>
> POE-ISS-005 closed 2026-09-17. Reviewer launches use Pi's `--no-approve` JUDGE posture,
> preventing the project under review from steering its own reviewer through trusted local
> configuration or extensions. Regression coverage confirms `--approve` is absent.
>
> POE-ISS-006 closed 2026-09-17. `scripts/check_poe_dogfood_gate.py` evaluates the required
> artifact set as a binary result: task, claim with verify command, run-log evidence, review
> bundle, handoff, and distinct-UID verification or explicit advisory outcome. The live Step 5
> task reports `DOGFOOD GATE: PASS`; lifecycle status remains separately governed by broker policy.

## Dogfood Issue Backlog

```pbc:grounding
status: draft
issues:
```

## Implementation Ladder

> Historical ladder. Steps 1-4 are implemented; step 5 (falsifiable dogfood run with
> distinct-UID verification) is not established. Later work (PBC/crystal shortcuts,
> target editor, verify-run) is tracked in Candidate Reconciliation, not as ladder steps.

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

> Status note (2026-09-23): #3, #4, #5 and #8 have de facto answers in the implementation -
> PBC authoring ships in this extension (`/pbc:*`); `/op:delegate` dispatches through
> `harness_adapter` IMPLEMENTER with paste as a labeled fallback; `targets.json` uses
> alias, harness id, carrier id, model, isolation and brief format; and `review-delegate`
> launches Pi with `--no-approve`. They are left open here because none is ratified.

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

The extension is implemented (see Candidate Reconciliation); implementation and
automated tests are not independent acceptance.

Does not show: that the implemented behavior is ratified, that the command set is
complete, that the identity format is final, that end-to-end cross-UID,
provider-authenticated verifier runs work, or that Claude/OpenCode/MCP integration
should share all of the same affordances. The owner separately confirms GUI popup
success; that launch reached Pi and then failed on provider authentication. This
observation is not a completed reviewer run or formal closure of the ledger task.
