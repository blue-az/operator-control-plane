# Dogfood runner operations

**Repo:** `blue-az/operator-control-plane`
**Issue:** [#8](https://github.com/blue-az/operator-control-plane/issues/8) — *Operations: Add a typed, resumable privileged dogfood runner*
**Module:** `dogfood_runner.py`, wired into `operator-admin dogfood-plan|dogfood-run|dogfood-status|dogfood-resume`
**Status:** Slices 1 and 2 shipped (5 of 9 phase types). See §4 for exactly what that does and does not cover.

This module replaces the manual `sudo` relay used during Issue #7 dogfood
with a typed, digest-bound, checkpointed plan/run model. It is **operational
tooling that sits next to the P3 authority boundary** (`authority_broker.py`
/ `authority_admin.py`) — it reuses that boundary's atomic-write, path-safety,
and digest primitives directly, and does not extend, weaken, or become part
of the P3 security claim itself. `require_root()` gates every dogfood
subcommand identically to every other `operator-admin` command; there is no
separate privilege path.

## 1. Concepts

**Plan.** A reviewed, canonical JSON document naming an enumerated,
sequential list of phases, each a typed operation with a fixed argument
schema — no shell strings, no arbitrary executables. Five operations exist
so far: `installation_verification`, `privilege_evidence`, `final_audit`
(empty args), `service_lifecycle` (one field, `action`, a closed enum of
`stop`/`start`/`restart` — not a free-form string), and `enrollment` (one
field, `repository_path`, validated as a non-empty absolute path). Every
operation's args are validated both by key-set (`require_exact_keys`) and,
where the schema is non-empty, by value (`PhaseSpec.validate_args`) before a
plan is ever stored — an unrecognized `action` or a relative
`repository_path` fails at parse time, not at execution time. A plan
is bound to a `ledger_id`, a `policy_binding` (policy id/generation/sha256),
an `expected_release_digest`, and the four fixed `InstallLayout` paths.
`operator-admin dogfood-plan` parses, validates those bindings against live
installed state, and stores the plan under
`/var/lib/operator-control-plane-admin/dogfood-plans/<plan_digest>.json` —
digest-named and self-describing, the same pattern staged releases already
use.

**Run.** `operator-admin dogfood-run --plan-digest <digest>` starts (or
continues) a run under
`/var/lib/operator-control-plane-admin/dogfood-runs/<run_id>/`, structurally
a **sibling** of the broker's own `state_root`
(`/var/lib/operator-control-plane`), never a subpath — the separation the
issue asks for is enforced by path structure, not just convention. Each run
freezes an immutable copy of its bound plan (`plan.json`) and persists one
checkpoint file per phase attempt under `checkpoints/`, plus a
`run-state.json` summary and an append-only `run-history.jsonl` transition
log. Every write goes through `authority_admin.write_protected_file` (atomic
temp-file + `renameat2(RENAME_NOREPLACE)` + fsync) — the same primitive
`authority_admin.py`'s own protected state uses.

**Checkpoint states.** Each phase attempt is `not_started` → `pending` →
`completed` or `failed`. `dogfood-status` always recomputes overall state by
scanning checkpoint files directly — `run-state.json` is a convenience cache,
never the source of truth, so status reporting is correct even after an
interrupted or failed phase left it momentarily stale.

**Idempotency.** Every phase attempt has an `operation_key` (stable per
run+phase, never attempt-numbered) and a `request_digest` (a hash of
plan digest + phase id + operation + args). An exact retry against a
`completed` checkpoint returns the stored result without re-invoking the
handler (`idempotent_replay: true`). A retry whose recomputed
`request_digest` disagrees with what's on disk fails closed with
`plan_replaced` — this is what stops a plan or run binding from being
silently swapped out from under a resume.

## 2. Command reference

```
operator-admin dogfood-plan --plan <path>
operator-admin dogfood-run --plan-digest <digest> [--run-id <id>] [--approve-phase N]
operator-admin dogfood-status --run-id <id>
operator-admin dogfood-resume --run-id <id> [--approve-phase N] [--acknowledge-recovered]
```

All four require real root, exactly like `install`/`audit`/`enroll`/etc. —
`operator-admin`'s `require_root_owned_code()` wrapper check also covers
`dogfood_runner.py` now, so a doctored copy of this module is rejected the
same way a doctored `authority_admin.py` would be.

## 3. Workflow

**Review.** Author a plan JSON by hand (or generate one) naming the ledger,
the currently-active policy's id/generation/sha256, the currently-installed
release digest, the four fixed host paths, and an ordered phase list. Run
`dogfood-plan` — it independently recomputes the release digest from live
installed assets and cross-checks ledger/policy state against a fresh
`audit_deployment` call, rather than trusting anything the plan claims. A
plan that doesn't match live state is rejected before it is ever stored.

**Execution.** `dogfood-run --plan-digest <digest>` with no `--run-id`
starts a new run and executes every consecutive read-only phase
automatically. It stops **immediately before** the first phase marked
`mutating: true`, prints that phase's id/operation, and does not touch it.
Re-invoke with `--run-id <id> --approve-phase <N>` to authorize exactly that
one phase; execution then continues automatically until the next mutating
phase (if any) or the end of the plan. A plan with several mutating phases
back-to-back (e.g. `service_lifecycle` then `privilege_evidence`) needs a
separate `--approve-phase` call for each one — approving one mutating phase
never authorizes the next.

**Interruption.** If the process dies between the durable `pending`
checkpoint write and the phase's own completion, the next `dogfood-run` or
`dogfood-resume` against the same run sees `pending` (not `not_started`) and
re-invokes the handler — no duplicate authority commits or evidence records.
`installation_verification`/`final_audit`/`privilege_evidence` are safe to
re-invoke because their underlying `authority_admin` calls are read-mostly or
content-comparing; `service_lifecycle`'s safety rests on a different,
explicitly noted assumption instead — `systemctl stop`/`start` are
themselves no-ops against a service already in the target state, so retrying
`stop`/`start`/`restart` is safe, but this is an assumption about `systemctl`
being well-behaved, not something this module independently re-verifies.

**Recovery from a failed phase.** A phase whose handler raised leaves a
`failed` checkpoint and halts the run. Neither `dogfood-run` nor
`dogfood-resume` will silently advance past it. `dogfood-resume
--run-id <id> --acknowledge-recovered` is required to retry it — one
explicit administrator decision per failed gate, never automatic.

**Evidence export.** `dogfood-status --run-id <id>` is a pure read: it never
mutates run state, so handing its JSON output to an unprivileged supervisor
for review carries no mutation risk. In this slice that is still an
admin-mediated export (the command itself still requires root) rather than a
separately-readable path — see §4.

## 4. What's implemented, and what's still open

Five phase types are wired:

- `installation_verification`, `final_audit` — wrap `authority_admin.audit_deployment` (read-only).
- `privilege_evidence` — wraps `authority_admin.collect_evidence_deployment` (mutating: writes `layout.evidence_path`).
- `service_lifecycle` (slice 2) — wraps `stop_service`/`start_service`/`probe_service_active`/`probe_socket_health`, one typed `action` field (`stop`/`start`/`restart`). Mutating.
- `enrollment` (slice 2) — wraps `enroll_repository`, gated by the same policy-state and `privilege_preflight`/`boundary_ready` checks `authority_admin.main()`'s own `enroll` command already enforces (re-homed into a phase handler, not weakened). One typed `repository_path` field. Mutating.

Adding the remaining phase types the issue names —
`reconciliation`, `rotation`, `outage_recovery`, `revocation_checks` — is
still just a `PHASE_CATALOG` entry plus a thin handler against this same
engine, not an architectural change; each already has an existing
`authority_admin.py` function to wrap (`rotate_deployment`,
`revoke_deployment`). Slice 2 is the confirmation of that claim: two more
phase types landed with zero changes to the checkpoint/idempotency engine,
`execute_run`, or the command entry points — only new `PHASE_CATALOG`
entries, handlers, and `validate_args` functions. Slice 2 also proved
something slice 1 couldn't: a plan with several mutating phases in a row
requires a *separate* `--approve-phase` for each one, not one approval that
silently covers the rest (`tests/test_dogfood_runner_root.py`'s
`test_real_install_multi_mutating_phase_plan_requires_separate_approvals`).

A known, deliberate testing gap: `stop_service`/`start_service`/
`probe_service_active` shell out to real `systemctl` against a unit *name*
that does not respect a disposable test root — unlike the rest of this
module's primitives, they cannot be safely exercised for real under a temp
`InstallLayout.under(root)` fixture (a real `systemctl` call there would
target whatever unit happens to be registered on the real host under that
name, if any). The pre-existing `authority_admin.py` test suite already
avoids this for the same reason; `dogfood_runner`'s tests follow the same
convention and always mock these three functions. `probe_socket_health` is
exempt from this concern (it is a plain Unix-socket connect that does
respect the test root) and is exercised for real elsewhere in the suite.

| # | Acceptance criterion (issue #8) | Status | Why |
|---|---|---|---|
| 1 | Complete disposable-ledger sequence, fewer relays | **Not met** | 5 of 9 phase types exist; reconciliation/rotation/outage-recovery/revocation-checks still missing |
| 2 | Unknown ops/fields, arbitrary-command attempts fail before state change | **Met** | Enumerated catalog, exact-key **and** value-level validation (`validate_args`), no shell/exec surface; unit-tested |
| 3 | Bindings can't be redirected by cwd/env/symlink/repo state/agent UID | **Met** for bindings this module touches | Independent recomputation against live state, path-safety primitives reused unchanged |
| 4 | Exact retries idempotent; interruption resumes without duplicates | **Met** for all five implemented phase types | `operation_key`/`request_digest`, fault-injection-tested crash recovery; `service_lifecycle`'s idempotency rests on an explicitly noted `systemctl` behavior assumption (§3) rather than content-comparison |
| 5 | Failed assertions stop the phase; resume can't skip a failed gate | **Met** | Enforced by the completed-checkpoint scan every phase goes through; proven with multiple back-to-back mutating phases in slice 2 |
| 6 | Run-state/evidence writes atomic, durable, race-resistant, auditable | Atomicity/durability **met**; unprivileged-read auditing **deferred** | `dogfood-status` still requires root — export today is admin-mediated, not a separate read path |
| 7 | Builder/verifier accounts can't gain privileged access through the runner | **Met, proven with a real root test** | `require_root()` gates every dogfood subcommand identically to every existing admin command |
| 8 | Focused tests + guarded real-root tests | **Met** for the phase types/attack classes implemented so far | `tests/test_dogfood_runner.py` (52 tests), `tests/test_dogfood_runner_root.py` (4 tests) |
| 9 | Real disposable-ledger run before production recommendation | **Not met** | Requires the remaining phase types |

Per the issue's own stop condition: this module does not claim the P3
boundary is reduced. It replaces the manual relay only for the phase types
implemented so far, under the same `require_root()` / root-owned-code
boundary that already existed.

## 5. Running the tests

```
python3 -m pytest tests/test_dogfood_runner.py -v          # unprivileged, hermetic
sudo python3 -m pytest tests/test_dogfood_runner_root.py -v  # guarded, real root required
```

The root-gated suite proves the non-root-UID denial (acceptance criterion 7),
a real end-to-end plan/run/approve/status/resume flow against a genuinely
root-owned install, the separate-approval-per-mutating-phase property with
multiple mutating phases in one plan, and a real crash-window recovery via
`write_protected_file`'s fault hook against genuinely root-owned files; it is
skipped automatically when not run as root. `sudo` must invoke the project
venv's interpreter directly (`sudo /path/to/venv/bin/python3 -m pytest ...`)
— the system Python `sudo` defaults to under most distros won't have pytest
installed.
