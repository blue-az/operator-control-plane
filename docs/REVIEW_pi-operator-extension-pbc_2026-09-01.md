# Supervisor review: `appendix-pi-operator-extension.pbc.md`

- Ledger task: `pi-operator-extension-pbc-review`
- Reviewed file: `owners-manual/pbc/appendix-pi-operator-extension.pbc.md` (status `draft`, updated 2026-09-01)
- Reviewer: `claude` (builder-briefed on this task; this review is a design-layer artifact, not a verification)
- Method: read the PBC against the live `operator` CLI, `harness_adapter.py`, `pbc_lint.py`,
  `docs/PROPOSAL_LIFECYCLE.md`, the sibling PBCs, and this repo's actual `.operator/` ledger.
  No code was written or changed.

## Verdict on the central question

**The three-way split is sound. Keep it.** `/op:delegate`, `/op:supervisor-review`, and `/op:handoff`
are not three names for one intent: they land in three distinct ledger artifacts that already exist
independently.

| Command | Artifact it produces | Existing mechanism |
|---|---|---|
| `/op:delegate` | `brief_issued` event with `role: builder` + a brief under `.operator/briefs/` | `brief` / `export-brief` / `session-start` |
| `/op:supervisor-review` | a bundle + reviewer script under `.operator/review_delegations/` | `review-delegate` |
| `/op:handoff` | `handoffs/<task>/handoff-NNNN.yaml` | `handoff-add` |

Because `doctor` already reasons over the first two separately (it errors when a claim is verified by
an identity that was issued a *builder* brief for that task, `operator:5699`), collapsing them would
destroy a check that exists today. POE-RUL-007 is the right rule.

The problems are not in the split. They are that the review side promises scope the CLI does not have,
the delegate side has no routing path at all, and handoff is defined narrower than the record's real job.
Detail below.

---

## Findings

Ordered by severity. Each cites the file:line or command output it rests on.

### F1. All nine rules sit in the ratified fence without ever having been proposed

POE-RUL-001..009 are in a ```pbc:rules``` block with `trust: provisional`. Per
`docs/PROPOSAL_LIFECYCLE.md` §3, that pair *is* the RATIFIED state, reachable only via
DRAFTED -> FROZEN (a `paper_or_report_claim` plus the PBC attached as evidence) -> RULED
(`operator decide --decision approve`) -> RATIFIED (a **different** agent moves the block and
changes `trust: proposed` to `trust: provisional`). None of that has happened for this file.

`python3 pbc_lint.py owners-manual/pbc` exits 0 anyway, for two reasons that are both accidents of
where the rules were placed: invariant 1 matches the literal string `trust: proposed`, and invariant 2
(proposed blocks reachable from a frozen claim) only runs with `--ledger`. Putting un-ruled proposals
directly into `pbc:rules` routes around the entire gate.

This is the same failure POE-RUL-006 was written to prevent, which makes it the finding to fix first.

**Edit.** Move POE-RUL-001..009 to ```pbc:proposed-rules``` with `trust: proposed`; POE-BHV-001..003 to
```pbc:proposed-behavior```; the Acceptance Outcomes grounding block to ```pbc:proposed-outcomes```.
Then register the freeze claim and attach this PBC as evidence, and change the acceptance outcome to run
the linter *with* the ledger so invariant 2 actually binds:

```
python3 pbc_lint.py owners-manual/pbc --ledger .operator
```

### F2. `/op:supervisor-review` promises scope `review-delegate` does not have

POE-RUL-007 and the command table say supervisor-review covers "a wrapped-up session or claim set."
`review-delegate` does none of that:

- it takes exactly one positional `claim` (`operator:8053`), so there is no claim-set unit;
- it fails closed without a verification command: "no verification command is recorded; provide
  `--verify-cmd` (required_gate is an artifact path, not a command)" (`operator:2767`);
- it refuses to run at all under broker enrollment: "review-delegate is only implemented for local
  file-backed ledgers" (`operator:2696`).

Sessions are not a reviewable unit anywhere in the CLI.

**Edit.** Narrow POE-RUL-007's review clause to a single claim, add the three preconditions as a
verified rule (draft supplied in the Recommended Edits section), and either define "claim set" as N
sequential bundles or move it to Open Questions as a named CLI gap.

### F3. `/op:delegate` has no CLI path to a target that is not already routed on the task

`generate_brief_markdown` fails closed for an unrouted harness: "Error: Harness 'X' is neither
assigned_harness nor review_harness for task 'T'" and returns `None` (`operator:4554-4558`).
`brief`, `export-brief`, and `session-start` all go through it. Meanwhile:

- `assigned_harness` is written in exactly one place outside `task-create --assign`: `session_start_cmd`,
  and only when the field is empty (`operator:7099`);
- `task-route` corrects `--review` only (`./operator task-route --help`).

So delegating to an implementer who is not already this task's assigned or review harness is not
possible without creating a new task. A chooser that lists targets freely will offer choices the CLI
rejects.

**Edit.** Record the constraint as a verified rule, and make POE-RUL-008's chooser either (a) restrict
targets to the ones already routed on the task, or (b) be explicit that delegating to a new implementer
means `task-create --assign` plus a scoped objective. Do not let the chooser present unroutable targets.

### F4. The chooser must never make one target both assigned and review harness

`doctor` errors when a claim's `verified_by` was issued a builder brief for that task
(`operator:5699-5702`). But `record_brief_issued` stores the role that `derive_role_for_task` returns,
and that helper returns `"both"` when a harness is both assigned and reviewer (`operator:4518-4520`),
which `generate_brief_markdown` then emits as `"reviewer"` (`operator:4548-4553`). The doctor check only
fires on `role == "builder"`. A delegate that is also the reviewer therefore slips past the
builder-brief poisoning check silently.

**Edit.** Add a fail-closed rule: the chooser refuses a selection that would make one target both the
task's implementer and its reviewer, and `/op:delegate` refuses a target equal to `review_harness`.

### F5. Session-derived identity is already live here, and already breaks under `mode: enforced`

This is the load-bearing finding for "do session-derived identity defaults blur implementer/reviewer
targets." They do, but not where the PBC expects. The practice is already in production in this ledger:

```
.operator/identity.yaml     mode: enforced; uid 1000 -> name pi-01a03792, roles [builder, operator]
                                             uid 971  -> luna-review-ffsi001-rowa, roles [verifier]
                                             uid 966  -> operator-verifier,        roles [verifier]
.operator/harnesses/        pi-01a03792.yaml, pi-01a05bf2.yaml, claude-019KSo7K.yaml (kind: pi / claude)
this task's review_harness  pi-01a05bf2
```

Three consequences, all checkable:

1. **A session-derived `--verified-by` is rejected outright.** Under `mode: enforced`,
   `evidence-attach --status` requires `--verified-by` to equal the identity-registry name for the
   *executing uid* (`operator:2461-2467`). uid 1000's registered name is frozen at `pi-01a03792`. A
   session `pi-01a05bf2` running at uid 1000 that defaults `--verified-by` to its own session id gets
   "does not match the executing identity 'pi-01a03792'".
2. **uid 1000 cannot verify at all.** It holds `builder` and `operator`, not `verifier`
   (`require_executor_role`, `operator:2456`). The reviewer named on this very task, `pi-01a05bf2`,
   is a uid-1000 session. Verification has to reach uid 971 or 966 regardless of any label.
3. **The three identity axes are not the same axis.** POE-RUL-002 lumps "role labels such as builder,
   reviewer, or claude" together, but harness ids are load-bearing routing, not role labels:
   `brief --for`, `session-start --harness`, and `review-delegate --reviewer` all require a registered
   harness id, and `--reviewer` is explicitly *not* satisfied by `review_harness` ("review_harness is
   routing metadata and cannot supply verifier identity", `operator:2723`).

**Edit.** Split POE-RUL-002 into the three axes explicitly:

- `--by` on `claim-add` / draft `evidence-attach` / `handoff-add`: session-derived is correct and safe.
  It is unvalidated free text (MSC-RUL-001, verified) and confers no authority.
- harness id on `--for` / `--harness` / `--reviewer`: must resolve to an existing
  `.operator/harnesses/<id>.yaml`. The extension may create one per session, as this ledger already does,
  but must never invent one at call time.
- `identity.yaml` name on `--verified-by`: fixed per uid, never session-derived. The extension must not
  default it.

### F6. Session-derived `--by` weakens `doctor`'s name-based self-verification check

`doctor` errors on `verified_by == made_by` when authority is not `uid_isolated`
(`operator:5704-5708`, and again at `operator:6301-6309`). Two Pi sessions run by one person at one uid
produce two different labels, so the string comparison passes while the UID is identical. Under
`mode: enforced` the UID check still catches it; under `single_user` nothing does, and `single_user` is
the documented-usable mode.

Making distinct session labels the frictionless default therefore erodes one of the two
self-verification checks, in exchange for the provenance win MSC-RUL-002 wants. The trade is probably
worth it, but the PBC should say so rather than acquire it silently.

**Edit.** Add a rule: the Pi UI never presents a distinct session label as satisfying reviewer
distinctness. Where the extension shows a review as complete, it shows the recorded
`verification_authority` (`uid_isolated` or `advisory`) next to it.

### F7. Per-session harness ids cannot be dispatched by the adapter

`harness_adapter.PROFILES` keys on carrier id (`pi`, `claude`, `codex`, `opencode`, ...) and
`get_profile()` looks up `harness_id` directly (`harness_adapter.py:269-271`). `get_profile("pi-01a05bf2")`
raises `AdapterError`. The session records do carry `kind: pi`, but nothing maps `kind` to a profile.

So under the current session-derived scheme, a chooser target can be briefed but not launched: routing
resolves, dispatch does not. This is the concrete implementer/reviewer blur the brief asks about.

**Edit.** Require each chooser target to carry both a ledger harness id (routing, must exist under
`.operator/harnesses/`) and a carrier id with an adapter profile (dispatch), or to resolve dispatch
through the record's `kind` field. Fold this into Open Question 5, which currently lists the fields
without naming this split.

### F8. `/op:delegate` as written re-legitimizes paste dispatch

The command table has `/op:delegate` wrapping "`./operator brief` or `export-brief`". `export-brief`
exists specifically to format a brief for copy-paste, and this task's own record shows where that leads:

```
next_action: Paste .operator/briefs/pi-operator-extension-pbc-review.claude.export.md
  into Claude Code and ask it to return concrete findings and recommended edits only.
```

LID-RUL-101 ("Brief Is The Dispatch") already says the implementer is *started with* the exported
brief, not handed it in chat, and LID-RUL-002 ("Recaps Are Not Results") records what happened the last
time dispatch went through a human paste. The owner's stated design position is the same: delegation is
programmatic invocation, and paste dispatch is a rejected design.

**Edit.** State it as a rule: `/op:delegate` invokes the target through the adapter with the brief on
the command line. Emitting a brief for the human to paste is a labeled fallback, not the default path,
and the UI says which one happened.

### F9. `/op:handoff` is defined narrower than what `handoff-add` is actually for

POE-RUL-007 defines handoff as continuity transfer "because the current session is ending or should stop
carrying the work." But `handoff-add` is the universal closeout record: every generated brief's §7 tells
the harness to produce one on completion, and the task's `handoffs:` list is the audit trail whether or
not anything transfers. Reserving `/op:handoff` for continuity transfer will under-record ordinary
closeouts, which is the one part of this taxonomy that is already required practice.

**Edit.** Restate: `handoff-add` always records closeout. Continuity transfer is a *mode* of it (the
successor is named in `--next-action`), not a separate concept. Keep `/op:handoff` as one command with
a "transferring to" field that may be empty.

### F10. The reviewer bundle launches `pi` with `--approve`, contradicting the adapter's JUDGE role

`review_delegate_cmd` builds the reviewer command as:

```
pi --provider <p> --model <m> --thinking medium --session-id <r>-<claim> --name <r> --approve --print -- <prompt>
```
(`operator:2793-2796`)

`harness_adapter.py` says the opposite for a reviewing pi, and says why:

```python
# A reviewer should not let the reviewed project's own config steer it;
# --no-approve is the documented lever for that.
Role.JUDGE.value: ("--no-approve",),
Role.IMPLEMENTER.value: ("--approve",),
```
(`harness_adapter.py:181-186`)

This matters more once this extension exists than it does today. `--approve` means "trust
project-local files for this run." The extension under review would live at
`.pi/extensions/operator/`, inside the reviewed project. A supervisor review dispatched through
`review-delegate` would load the extension it is reviewing, with the extension's own tools available to
the reviewer.

**Edit.** Add a rule that supervisor-review dispatch uses the JUDGE role args (`--no-approve`). The
underlying `review_delegate_cmd` fix is operator-side, not extension-side, and should be its own ledger
task rather than something the extension papers over.

### F11. Dogfood acceptance is stated but not falsifiable

POE-RUL-009 is explicit that dogfooding is the acceptance test, and that mock tests cannot validate
workflow semantics. That part is right and should stay. The problem is the criterion: "confirm that the
ledger record is clearer than the equivalent manual process." That is a narration verdict, which is the
exact thing this repo's thesis says not to trust. The acceptance-outcomes block names no claim type, no
evidence type, and no verifier.

There is a better test available for free: this ledger is in `mode: enforced` with no verifier role on
uid 1000, so a dogfood run *cannot* self-verify. Whether the run reaches a real verifier is a binary,
checkable outcome.

**Edit.** Restate the dogfood acceptance as a named artifact set: one task id; at least one claim
carrying `--verify-cmd`; `./operator doctor` output attached as `run_log` evidence; one bundle under
`.operator/review_delegations/`; one handoff; and either a status recorded by uid 971 or 966, or the
record explicitly labeled `advisory` with that stated as the outcome.

### F12. `/op:use` makes a known hazard cheaper to trigger

`task-use` writes the ledger-global `current_task`. MSC-RUL-003 (trust: verified) records this causing a
misdirected `evidence-attach`, and MSC-RUL-102 is "Always Pass `--task`". Two Pi sessions already share
this ledger. A one-keystroke task switch makes the hazard easier to hit, not harder.

**Edit.** Rule: every operator invocation the extension issues passes `--task` explicitly and never
relies on `current_task`. `/op:use` sets the *extension's* session-scoped task and displays it; writing
the ledger's `current_task` requires explicit confirmation.

### F13. Chooser config sits next to POE-RUL-001's hidden-state ban without being reconciled

POE-RUL-008 puts delegation targets in "project configuration" without saying where it lives or how it
relates to `.operator/harnesses/`. POE-RUL-001 bans "hidden state that can supersede files under
`.operator/`". Routing config is exactly the kind of state that can drift from the ledger.

**Edit.** Aliases must resolve to an existing `.operator/harnesses/<id>.yaml` and fail closed on an
unknown id. The config may add model, isolation mode, and command template. It may not invent harness
ids or override `assigned_harness` / `review_harness`.

### F14. Smaller consistency items

- **`owners-manual/pbc/README.md` does not index this appendix.** Every other appendix has an entry with
  its ledger task. Add one naming `pi-operator-extension-pbc-review`.
- **No "Ledger Registration" section.** Siblings carry one; F1's freeze claim needs somewhere to be cited.
- **No verified-facts block.** Siblings split `## Rules — as verified today` (`trust: verified`) from
  proposals. This PBC has no verified block at all, though everything it wraps is inspectable today.
  Draft content supplied below.
- **"Bulkhead Tau-specific API" in Non-Goals is unglossed.** BT appears in this repo only inside evidence
  files, as a separate product. Either gloss it in one clause or drop the phrase.
- **Acceptance outcome about `/op:evidence` is not achievable as worded.** "attach a rerunnable
  verification command to a named claim or active task" reads as command-only attachment, but
  `evidence-attach` requires the positional `path_or_url`. Reword to "attach an artifact together with a
  rerunnable `--verify-cmd`".
- **Open Question 1 is partly already answered.** `harness_adapter.resolve_initiator_identity()` reads
  `OPERATOR_INITIATOR_HARNESS` / `OPERATOR_INITIATOR_SESSION_ID` as declared-never-inferred provenance
  (`harness_adapter.py:251-266`), and MSC-RUL-006 (verified) records that those never reach the
  `operator` CLI. That is the natural carrier for the full session id, and the gap is named.
- **Open Question 4 is posed backwards.** `harness_adapter.py` already is the shared adapter, with a
  `Role` enum and per-carrier profiles. The real question is whether the Pi extension calls it or
  bypasses it, not whether to extract a new one. `evals/local_lane_ladder/runner.py` and this repo's own
  dispatch have bypassed it before.

---

## Recommended edits

### 1. Add a verified-facts block (new, before the proposed rules)

These are the constraints the extension will hit on day one. All were checked against the working tree
on 2026-09-01.

```pbc:rules
- id: POE-RUL-001
  name: Brief Generation Fails Closed For An Unrouted Harness
  rule: >
    generate_brief_markdown returns None and prints "Harness 'X' is neither assigned_harness nor
    review_harness" (operator:4554). brief, export-brief and session-start all depend on it.
    assigned_harness is written only by task-create --assign and by session-start when the field is
    empty (operator:7099); task-route corrects --review only. Delegation to an implementer not already
    routed on the task therefore requires a new task.
  trust: verified
- id: POE-RUL-002
  name: review-delegate Is Claim-Scoped And Requires A Verify Command
  rule: >
    review-delegate takes one positional claim (operator:8053), refuses to run without a recorded or
    supplied --verify-cmd (operator:2767), refuses to run under broker enrollment (operator:2696), and
    requires an explicit --reviewer because review_harness is routing metadata only (operator:2723).
    There is no session-scoped or multi-claim review unit.
  trust: verified
- id: POE-RUL-003
  name: Three Identity Axes, Only One Of Which Carries Authority
  rule: >
    --by is unvalidated free text (MSC-RUL-001). A harness id must exist under .operator/harnesses/ for
    brief --for, session-start --harness, and review-delegate --reviewer. Under mode: enforced,
    --verified-by must equal the identity.yaml name registered for the executing uid (operator:2461),
    and the executing uid must hold the verifier role (operator:2456). In this ledger uid 1000 holds
    builder and operator only; verification requires uid 971 or 966.
  trust: verified
- id: POE-RUL-004
  name: Per-Session Harness Ids Have No Adapter Profile
  rule: >
    harness_adapter.PROFILES keys on carrier id and get_profile() looks up harness_id directly
    (harness_adapter.py:269). get_profile("pi-01a05bf2") raises AdapterError. The session records carry
    kind: pi, but nothing maps kind to a profile. Routing id and dispatch id are separate axes.
  trust: verified
- id: POE-RUL-005
  name: Doctor's Builder-Brief Check Does Not Fire On A Dual-Role Target
  rule: >
    doctor errors when verified_by was issued a builder brief for the task (operator:5699), but
    record_brief_issued stores the role from derive_role_for_task, which returns "both" for a harness
    that is both assigned and reviewer (operator:4520) and is emitted as "reviewer" (operator:4548).
    A target that is both implementer and reviewer escapes the check.
  trust: verified
```

### 2. Re-fence the existing rules as proposals and revise the ones named above

Rename the current POE-RUL-001..009 to POE-RUL-101..109 (IDs must not appear in both a proposed and a
ratified fence; `pbc_lint.py` invariant 3), move them into ```pbc:proposed-rules```, and set
`trust: proposed`. Then revise these four and add three:

```pbc:proposed-rules
- id: POE-RUL-102
  name: Session Identity Binds To Provenance Only
  rule: >
    The extension derives a session-scoped label for --by on claim-add, draft evidence-attach, and
    handoff-add. It never defaults --verified-by, --for, --harness, or --reviewer from session
    metadata: those resolve to registered harness ids and identity.yaml names (POE-RUL-003).
    Commands that assign or request review require an explicitly chosen configured target and never
    reuse the current agent as implementer or reviewer.
  trust: proposed
- id: POE-RUL-108
  name: Delegation Surface Starts As A Guided Chooser Over Registered Targets
  rule: >
    The first surface is a small stable command plus a Pi UI chooser backed by project configuration.
    Each target carries a ledger harness id that must exist under .operator/harnesses/ and a carrier id
    with an adapter profile. Unknown ids fail closed. The config may add model, isolation mode, and
    command template; it may not invent harness ids or override assigned_harness / review_harness.
    The chooser refuses any selection that would make one target both the task's implementer and its
    reviewer (POE-RUL-005), and never offers a target the CLI would reject (POE-RUL-001).
  trust: proposed
- id: POE-RUL-107
  name: Delegate Supervisor Review And Handoff Are Distinct Moves
  rule: >
    delegate sends bounded implementation work to another agent while the current agent remains in the
    loop, producing a brief_issued event with role builder. supervisor-review asks a distinct agent to
    review one named claim, producing a bundle under .operator/review_delegations/. handoff records
    closeout, always; continuity transfer is a mode of handoff in which a successor is named in
    --next-action, not a separate concept.
  trust: proposed
- id: POE-RUL-109
  name: Dogfood Acceptance Is A Named Artifact Set
  rule: >
    Acceptance requires a real run on this repository producing: one task id; at least one claim
    carrying --verify-cmd; ./operator doctor output attached as run_log evidence; one bundle under
    .operator/review_delegations/; one handoff; and either a status recorded by a registered verifier
    uid, or an outcome explicitly labeled advisory. Because this ledger is mode: enforced and uid 1000
    holds no verifier role, a dogfood run cannot self-verify; whether it reaches a real verifier is the
    test. "The record is clearer" is not an acceptance criterion.
  trust: proposed
- id: POE-RUL-110
  name: Delegation Is Invocation, Not Paste
  rule: >
    /op:delegate starts the target through the adapter with the exported brief on the command line
    (LID-RUL-101). Emitting a brief for the human to paste is a labeled fallback, not the default, and
    the UI states which path was taken.
  trust: proposed
- id: POE-RUL-111
  name: Reviewers Do Not Trust The Reviewed Project
  rule: >
    Supervisor-review dispatch uses the adapter's JUDGE role args (--no-approve for pi), so the
    reviewer does not load the reviewed repository's project-local files, including this extension.
    review_delegate_cmd currently emits --approve (operator:2796); correcting it is an operator-side
    task, and the extension does not paper over it.
  trust: proposed
- id: POE-RUL-112
  name: Always Pass --task
  rule: >
    Every operator invocation the extension issues names its task explicitly and never relies on
    current_task (MSC-RUL-003, MSC-RUL-102). /op:use sets an extension-session-scoped task and displays
    it; writing the ledger's current_task requires explicit confirmation.
  trust: proposed
- id: POE-RUL-113
  name: Delegated Implementers Do Not Write Lifecycle
  rule: >
    Tools and dispatch templates exposed to a delegated implementer omit --status and --verified-by
    entirely rather than validating them (LID-RUL-104). crystal-attach and crystal-import are the
    existing precedent: they reject --verified-by and --verdict outright (operator:2857) instead of
    accepting and ignoring them.
  trust: proposed
```

### 3. Command table corrections

- `/op:supervisor-review`: change `interface` to note the claim is required and a `--verify-cmd` must
  exist or be supplied, and that the command is unavailable under broker enrollment.
- `/op:delegate`: change `wraps` from "brief or export-brief" to name the actual sequence
  (`task-create --assign` when the target is not yet routed, then `session-start`, then adapter
  invocation with the brief). Drop `export-brief` from the primary path.
- `/op:handoff`: change `reason` to "closeout record; continuity transfer is the mode where a successor
  is named."

### 4. Acceptance outcome corrections

- Replace `Running ./pbc_lint.py owners-manual/pbc succeeds` with
  `python3 pbc_lint.py owners-manual/pbc --ledger .operator succeeds` (F1).
- Reword the `/op:evidence` outcome to "attach an artifact together with a rerunnable `--verify-cmd`".
- Replace the dogfood outcome with the artifact set in POE-RUL-109.
- Add: "No exposed tool or dispatch template accepts `--status` or `--verified-by`."

### 5. Open Questions

- Rewrite OQ1 to cite `resolve_initiator_identity()` and MSC-RUL-006, and to ask the narrower remaining
  question: whether `operator` should read the initiator env vars, since today they never reach it.
- Rewrite OQ4 as "should the Pi extension dispatch through `harness_adapter.py`, or bypass it as
  `evals/local_lane_ladder/runner.py` does?"
- Add OQ6: is a per-session `.operator/harnesses/<id>.yaml` the intended long-term shape, given that
  those ids have no adapter profile and the registry grows without bound?
- Add OQ7: should `review_delegate_cmd` gain a `--no-approve` reviewer mode (F10), and is that a
  blocker for `/op:supervisor-review`?

### 6. `owners-manual/pbc/README.md`

Add to the file list:

```
- `appendix-pi-operator-extension.pbc.md` — draft contract for a project-local Pi extension wrapping
  the Operator CLI. Ledger task: `pi-operator-extension-pbc-review`. POE-RUL-101–113 are proposed and
  unratified; the verified block POE-RUL-001–005 records the CLI constraints they must respect.
```

---

## Proof boundary

**Shows:** that the delegate / supervisor-review / handoff split is grounded in three distinct ledger
artifacts and should be kept; and fourteen specific places where the draft's rules, command table,
acceptance outcomes, or fence placement disagree with the CLI, the adapter, the proposal lifecycle, or
this repo's live ledger. Every claim above cites a file:line or a command output.

**Does not show:** that the corrected contract is complete; that the extension is implementable as
scoped; that any Pi extension API detail in the draft (`.pi/extensions/operator/index.ts`, chooser UI
affordances, completion behavior) is accurate, since Pi's extension API was not inspected; or that
the proposed edits have been ratified. Nothing here is a verification of any claim.
