# Machine Role Enforcement — making the seat rule structural

**Status:** proposed, not built
**Date:** 2026-08-28
**Supersedes nothing.** Extends `MACHINE_PROVENANCE_SPEC.md` with a mechanism.

## 1. Problem

`MACHINE_PROVENANCE_SPEC.md` decides the policy already: the seat does not move,
and background machines get "**No `operator init`, ever.**" That rule is correct
and is not being followed.

Observed 2026-08-28: z13 holds `~/operator-control-plane/.operator/` with 12 tasks,
and a session created `desktop-comms-postmortem-2026-08-28` in it that night. A
second store at `~/.operator-usage/.operator/` on the same machine holds 44 more
tasks (produced by the now-carved-out `opr`, whose default `ledger_root` was
`~/.operator-usage`). Neither is visible to `doctor` run at the seat.

The rule is not being defied. It is invisible:

- `operator init` and `task-create` succeed on any machine.
- Nothing compares `get_machine_identity()` against a declared seat.
- No agent reads a spec before running a command that works.

This is the same failure class the README already admits for the policy gate
being self-amendable: **policy in prose, no mechanism.** Every pass re-decides a
rule the next session will break, because the CLI in front of it works.

## 2. Position

The machine's role becomes a field the ledger carries and `doctor` checks.
Prose stays prose; the check is what binds.

Three distinct things are called "authority" in discussion. Only the third is
singular, and conflating them is why this keeps reopening:

| | Meaning | Singular? |
|---|---|---|
| Write authority | who may append records | no |
| Verification authority | whose identity makes a claim `uid_isolated` | no |
| **Seat authority** | which ledger is canonical | **yes** |

A background machine recording its own work needs write authority to a
non-canonical store. That is legitimate and already happens. It is not a
seat, and calling its store a "ledger" is what creates the guilt and the churn.

## 3. Behavior

### 3.1 `operator.yaml` carries `role`

```yaml
role: seat        # or: outbox
seat_machine: desktop
```

- `role: seat` — canonical. Exactly one such store should exist per body of work.
- `role: outbox` — records are legitimate and carry `executor.machine`, but are
  **never authoritative**. They are ingested at the seat as evidence, never merged.
- Missing `role` reads as `seat` for backward compatibility, and `doctor` emits
  one Info line naming the default so existing ledgers do not silently change
  meaning.

`seat_machine` names the machine that holds the canonical store. On an `outbox`
store it names where records are destined, so an ingesting session can find it.

### 3.2 `doctor` checks it

Read-only and structural, consistent with the existing contract — no command
execution, no network.

1. **Seat/machine agreement.** If `role: seat` and `seat_machine` is set and
   `get_machine_identity()` differs, emit an **Error** and exit 1. A seat store
   found on a machine that is not the seat is the exact condition that produced
   z13's parallel ledger.
2. **Outbox is not silently canonical.** If `role: outbox`, emit a **Warning**
   naming the record counts and `seat_machine`, so an outbox store is visible at
   every run rather than discovered months later.
3. **No downgrade of history.** Records already written keep their markings.
   `role` describes the store, never re-stamps records.

### 3.3 `init` declares it

`operator init --role {seat,outbox} [--seat-machine NAME]`. Default `seat`,
preserving current behavior. `init` on a machine whose hostname differs from an
explicitly passed `--seat-machine` requires `--role outbox` or fails, so the
z13 case cannot be created accidentally by the next session.

## 4. Non-goals

- **No hierarchy.** No machine gains rank over another. `role` describes a store's
  canonicality, not a chain of command.
- **No ledger merge.** Sequential record IDs make merging unsafe by construction
  (`MACHINE_PROVENANCE_SPEC.md`). Ingestion remains evidence-shaped.
- **No retirement of existing stores.** z13's two stores hold unique work and are
  not deleted by this change; they are labeled.
- **No change to verification semantics.** `uid_isolated` still compares verifier
  UID to the claim's recorded author UID within one store.
- **No cross-machine UID alignment.** See §6.

## 5. Cross-machine work does not need cross-machine authority

When z13 debugs the desktop, the correct move is to write to the *seat's* store
over ssh (`ssh desktop ./operator ...`), not to z13's own. Travel is a widening
of ingest lag, exactly as `MACHINE_PROVENANCE_SPEC.md` says — not a seat handoff.
Message passing between machines is `relay` (`~/.local/bin/relay`, ssh/scp,
no git, no ledger), added 2026-08-28. Neither path requires a background machine
to hold seat authority.

## 6. Why heterogeneous machines do not need aligned UIDs

Confirmed 2026-08-28: the verifier identity `luna-review-ffsi001-rowa` executes
as uid 971 inside a **container** (`claim-0092` records
`executor.machine: 31315373e9c2`, `user: uid-971`). It is not a host account, and
`getent passwd 971` on the desktop correctly returns nothing.

Container UIDs are identical on every host. The verification identity is therefore
already portable, and host account layout is irrelevant to it. This retires the
"align operator-builder UIDs across machines" question: the desktop's
`operator-builder` is uid 967, z13's is 971, and that mismatch does not matter
because neither is the verifier.

macOS has neither a matching account model nor comparable POSIX ACL inheritance.
Do not map it. Run the verifier in a container there as well, and the mac's host
structure stays outside the trust model entirely.

## 7. Acceptance

1. `operator.yaml` round-trips a `role` value; absent `role` reads as `seat`.
2. `doctor` exits 1 with an Error when `role: seat` and `seat_machine` disagrees
   with the executing machine.
3. `doctor` emits a Warning, not an Error, for `role: outbox`, and still exits on
   its own merits for unrelated issues.
4. `doctor` remains read-only: no `verification_command` execution, no network.
5. `init --role outbox --seat-machine desktop` produces a store `doctor` labels as
   outbox without erroring.
6. An existing ledger with no `role` key behaves exactly as before, plus one Info line.
7. New tests in `tests/test_operator.py` using `OPERATOR_TEST_UID` +
   `OPERATOR_TEST_SENTINEL` and `OPERATOR_MACHINE` for machine override; no real
   hostnames asserted.

## 8. Proof boundary

Shows: the seat rule can be enforced structurally rather than remembered; an
outbox store is legal and visible; heterogeneous host UIDs are irrelevant to
verification.

Does not show: that z13's two existing stores have been ingested; that anything
prevents a determined session from editing `operator.yaml` to claim seat status
(the self-amendable gate limitation is unchanged); or that ingestion of an outbox
store is automated — it is not, and remains a manual evidence-shaped step.
