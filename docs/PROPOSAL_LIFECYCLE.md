# Proposal Lifecycle — freezing agent proposals so an operator can rule on them

**Status:** machinery shipped 2026-08-22 (`operator decide`, `pbc_lint.py`); operator ruling on open questions still required. This document remains subject to the lifecycle it describes.
**Date:** 2026-08-09
**Author:** claude-supervisor
**Applies to:** `operator-control-plane`, and any repo using PBCs + the operator ledger

## 1. The problem, measured

Agents now write behavior proposals into PBCs faster than anyone ratifies them.
Counted 2026-08-09 across `owners-manual/pbc/`:

| | count |
|---|---:|
| `pbc:proposed-rules` / `pbc:proposed-behavior` / `pbc:proposed-outcomes` blocks | **15** |
| ratified `pbc:rules` / `pbc:behavior` blocks | 14 |

Proposals outnumber ratified content, spread across four contracts and at
least three authoring agents. Three specific gaps let that happen.

**Gap 1 — the fence is unenforced convention.** `pbc:proposed-*` was introduced
on 2026-08-07 in `appendix-opr-governed-llm-client.pbc.md` with the stated
rationale that it is fenced separately "so contract tooling does not read them
as active behavior." **No such tooling exists.** `grep` for any code parsing
`pbc:` fences returns nothing. I wrote that justification; it described a
safeguard that was not there. The convention then spread to three more
contracts on the same reasoning.

**Gap 2 — `operator_decision` has no setter.** The task record carries an
`operator_decision` field (`operator:1654`), and `task-show` prints it
(`operator:1700`), but no CLI path writes it. Every task in the ledger has
`operator_decision: None`. Rulings are being carried as prose in `next_action`
instead — `pa-evidence` currently opens with "OPERATOR RULING ON THE CONTRACT,
NOT IMPLEMENTATION" in a free-text field while the structured field sits empty.

**Gap 3 — no state between "proposed" and "verified."** `task-transition`
accepts only `verified` and `complete`. There is no representation for
*approved but not yet built*, which is exactly the state both live examples are
stuck in.

## 2. The two shapes a frozen proposal takes

Both already exist in the repo. The lifecycle must cover both without inventing
a third.

**Shape A — amendment to a live contract.**
`appendix-opr-governed-llm-client.pbc.md` is `status: active`. Proposed rules
OPR-RUL-010..018 sit inline in `pbc:proposed-rules` fences alongside ratified
OPR-RUL-001..009. The unit of approval is *a set of rule IDs*.

**Shape B — a whole draft contract.**
`appendix-prime-agent-evidence-ingestion.pbc.md` is `status: draft` with Gate 0
blocking everything and the objective stating "the plan is NOT approved." The
unit of approval is *the file*.

## 3. Proposed lifecycle — four states, one new verb

```
  DRAFTED  ──►  FROZEN  ──►  RULED  ──►  RATIFIED
  (agent)      (agent)     (operator)   (supervisor agent)
```

**DRAFTED.** An agent writes a `pbc:proposed-*` block (Shape A) or a
`status: draft` contract (Shape B). No ledger record. Costs nothing, commits
nothing. This is where the 15 blocks are today.

**FROZEN.** The proposing agent registers one claim:

```
operator claim-add --task <t> --by <agent> --type paper_or_report_claim \
  --layer design \
  --text "Proposes OPR-RUL-010..013 in appendix-opr-governed-llm-client.pbc.md" \
  --gate "Operator ruling. On approve, ratify per PROPOSAL_LIFECYCLE.md §3."
```

and attaches the PBC file as evidence. The evidence hash is the freeze — the
proposal text can no longer drift without `doctor` noticing, which it already
detects (it caught exactly this when I attached a file mid-write on
2026-08-07). **No new record type is required.** A proposal is a design-layer
claim, which is what `paper_or_report_claim` already means here; grok's
claim-0001 on `agentic-cli-tps-metrics` used it this way before this document
existed.

**RULED.** One new CLI verb, the only genuinely missing piece:

```
operator decide --task <t> --claim <c> --decision approve|reject|defer \
  --rationale "<why>"
```

Writes the existing `operator_decision` field, appends a ledger event, and
records the deciding UID. **This is the only human-gated step in the
lifecycle.** Reject and defer are first-class: a rejected proposal stays in the
file, re-fenced as `pbc:rejected-rules` with the rationale, because a contract
that shows what was considered and declined is more useful than one that shows
only survivors.

**RATIFIED.** On approve, a *different* agent than the proposer moves the block
from `pbc:proposed-rules` to `pbc:rules`, changes `trust: proposed` to
`trust: provisional`, and cites the claim ID in the commit message. Trust only
reaches `trusted` later, by the normal evidence route — approval authorizes
implementation, it does not certify behavior.

## 4. The deterministic gate

Per `trust-the-validator.md`, the lifecycle is worth nothing if it depends on
agents remembering it. One linter, `pbc_lint.py`, enforces four invariants and
exits non-zero:

1. **No rule in `pbc:rules` carries `trust: proposed`.** Catches a
   half-finished ratification.
2. **Every `pbc:proposed-*` block is reachable from a frozen claim** — a
   proposal with no ledger record is invisible to the operator and is the
   failure this document exists to stop.
3. **No rule ID appears in both a proposed and a ratified fence.** Catches
   copy-instead-of-move.
4. **A contract with `status: active` has at least one `pbc:rules` block** —
   catches a file that is all proposal and no contract.

Wire it into the same place the existing gates run. It is a parser over
fenced blocks, not a semantic checker; it should stay under ~150 lines.
Invariant 2 requires `--ledger .operator` because claims live in the
gitignored ledger; `pytest tests/test_pbc_lint.py` checks 1/3/4 plus
invariant 2 against fixtures.

## 5. Why this is the minimum

Deliberately **not** proposed, each of which was considered:

- **A new `proposal` record type.** Claims already carry author, type, gate,
  evidence and verification status. A parallel record type would duplicate all
  of it and split the audit trail.
- **New task states.** `operator_decision` plus the existing statuses covers
  it. Adding `approved` to `task-transition` would put the same fact in two
  places.
- **Approval workflow, quorum, or sign-off chains.** One operator rules. Peer
  agents may argue in handoffs — that mechanism already works, and produced a
  real disagreement on `session-coordination-protocol` that was resolved
  append-only.
- **Auto-ratification on approve.** Moving the block is a code change and
  should be reviewable as one. It also preserves proposer ≠ ratifier.

Net new surface: **one CLI verb and one linter.**

## 6. Bulkhead Tau alignment

| BT principle | Where it lands |
|---|---|
| Trust the validator, not the model | `pbc_lint.py` is the gate; no step depends on an agent asserting it followed the process |
| Verifier ≠ author | Proposer cannot ratify; enforced by convention in §3 and checkable in commit authorship |
| Proof boundary | Each proposed block keeps its "what this does not establish" text through ratification |
| Append-only correction | Rejected proposals are re-fenced, never deleted |
| Fail closed | Linter exits non-zero; an unfrozen proposal is a lint error, not a warning |

## 7. Applying it to the two live examples

**`appendix-opr-governed-llm-client.pbc.md` (Shape A).** OPR-RUL-010..018 are
DRAFTED and unfrozen. Freeze as one claim on `opr-continuation-loop-audit`.
Note OPR-RUL-012 should be withdrawn rather than approved — its own measurement
(5/5 functional, 1/5 signalled) contradicts it, and OPR-RUL-018 supersedes it.
A lifecycle that cannot retire a proposal its evidence killed is not worth
having.

**`appendix-prime-agent-evidence-ingestion.pbc.md` (Shape B).** Already FROZEN
in substance — Gate 0 blocks implementation and the objective says the plan is
not approved. It needs the RULED step, which is precisely what its `next_action`
asks for in prose and what `operator decide` would put in the structured field.

## 8. Open questions for the operator

1. **Should `decide` require a distinct UID from the claim author?** Verification
   does. Approval is a human act, so the UID may be the operator's ordinary one
   — but then the trust model differs between the two gates, which is worth
   choosing deliberately rather than by default.
2. **Does a rejected proposal block re-proposal of the same rule ID?** Argues
   for: prevents relitigating. Against: evidence changes, and OPR-RUL-012 is a
   live case of a proposal that should change.
3. **Scope beyond `owners-manual/pbc/`?** `bulkhead-tau` PBCs share the format
   but not the ledger. Recommend starting in-repo only.

## 9. Proof boundary

Shows: three specific gaps, each traced to a file and line or a counted state
of the repo; two proposal shapes that already exist; a lifecycle whose new
surface is one verb and one linter.

Does **not** show: that the lifecycle survives contact with a proposal it was
not designed around; that ~150 lines suffices for the linter (unwritten and
unestimated against real fence variation, including the `pbc:grounding` fence
used by another session and not analysed here); or that agents will freeze
proposals without the linter forcing it — invariant 2 is the untested load
bearer, since nothing detects a proposal that was never written down at all.
