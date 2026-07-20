# Dogfood runner operations

**Repo:** `blue-az/operator-control-plane`
**Issue:** [#8](https://github.com/blue-az/operator-control-plane/issues/8) — *Operations: Add a typed, resumable privileged dogfood runner*
**Module:** `dogfood_runner.py`, wired into `operator-admin dogfood-plan|dogfood-run|dogfood-status|dogfood-resume`
**Status:** Slice 1 (P0+P1) shipped. See §4 for exactly what that does and does not cover.

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
sequential list of phases (`installation_verification`, `privilege_evidence`,
`final_audit` in this slice), each a typed operation with a fixed (currently
empty) argument schema — no shell strings, no arbitrary executables. A plan
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
one phase; execution then continues automatically through any trailing
read-only phases (in this slice, `final_audit`).

**Interruption.** If the process dies between the durable `pending`
checkpoint write and the phase's own completion, the next `dogfood-run` or
`dogfood-resume` against the same run sees `pending` (not `not_started`) and
re-invokes the handler — no duplicate authority commits or evidence records,
because the handlers this slice wraps (`audit_deployment`,
`collect_evidence_deployment`) are themselves read-mostly or
content-comparing.

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

## 4. What this slice implements, and what's still open

Three phase types are wired: `installation_verification` and `final_audit`
(both wrap `authority_admin.audit_deployment`), and `privilege_evidence`
(wraps `authority_admin.collect_evidence_deployment`, the one mutating phase
type in this slice — it writes `layout.evidence_path`). Adding the
remaining phase types the issue names — `service_lifecycle`, `enrollment`,
`reconciliation`, `rotation`, `outage_recovery`, `revocation_checks` — is a
`PHASE_CATALOG` entry plus a thin handler against this same engine, not an
architectural change; each already has an existing `authority_admin.py`
function to wrap (`stop_service`/`start_service`/`probe_*`,
`enroll_repository`, `rotate_deployment`, `revoke_deployment`).

| # | Acceptance criterion (issue #8) | Status | Why |
|---|---|---|---|
| 1 | Complete disposable-ledger sequence, fewer relays | **Not met** | Only 3 of 9 phase types exist |
| 2 | Unknown ops/fields, arbitrary-command attempts fail before state change | **Met** | Enumerated catalog, exact-key validation, no shell/exec surface; unit-tested |
| 3 | Bindings can't be redirected by cwd/env/symlink/repo state/agent UID | **Met** for bindings this slice touches | Independent recomputation against live state, path-safety primitives reused unchanged |
| 4 | Exact retries idempotent; interruption resumes without duplicates | **Met** for the one mutating phase type that exists | `operation_key`/`request_digest`, fault-injection-tested crash recovery |
| 5 | Failed assertions stop the phase; resume can't skip a failed gate | **Met** for slice-1 phases | Enforced by the completed-checkpoint scan every phase now goes through |
| 6 | Run-state/evidence writes atomic, durable, race-resistant, auditable | Atomicity/durability **met**; unprivileged-read auditing **deferred** | `dogfood-status` still requires root — export today is admin-mediated, not a separate read path |
| 7 | Builder/verifier accounts can't gain privileged access through the runner | **Met, proven with a real root test** | `require_root()` gates every dogfood subcommand identically to every existing admin command |
| 8 | Focused tests + guarded real-root tests | **Met** for the phase types/attack classes this slice covers | `tests/test_dogfood_runner.py`, `tests/test_dogfood_runner_root.py` |
| 9 | Real disposable-ledger run before production recommendation | **Not met** | Requires the remaining phase types |

Per the issue's own stop condition: this slice does not claim the P3
boundary is reduced. It replaces the manual relay only for the phase types
implemented so far, under the same `require_root()` / root-owned-code
boundary that already existed.

## 5. Running the tests

```
python3 -m pytest tests/test_dogfood_runner.py -v          # unprivileged, hermetic
sudo python3 -m pytest tests/test_dogfood_runner_root.py -v  # guarded, real root required
```

The root-gated suite proves the non-root-UID denial (acceptance criterion 7)
and a real crash-window recovery via `write_protected_file`'s fault hook
against genuinely root-owned files; it is skipped automatically when not run
as root.
