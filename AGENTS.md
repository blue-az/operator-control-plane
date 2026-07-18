# Repository Guidelines

## Where This Repo Sits (read before reasoning about boundaries)

One engine room; PBC above; GT-KB Logbook below; crystals are how narration
arrives; Farm is whose work arrives; LabWired is where hardware evidence comes
from. This CLI is the engine room — the enforcement middle. The **upper boundary**
is PBC (Product Behavior Contracts: what work is allowed). The **lower boundary** is the
GT-KB-derived evidence layer (the Logbook: "do not trust the narration — verify
against the evidence"). `agent-crystallize` crystals and similar session
artifacts are **narration formats arriving at** the lower boundary — untrusted
input in a parseable envelope, never a boundary and never trusted status.
Canonical taxonomy: `project-phoenix/docs/BULKHEAD_TAU_BOUNDARIES.md`. If a spec
or entry in this repo appears to contradict that doc, the doc wins — flag the
drift instead of propagating it.

Cross-repo vocabulary: **BN** = `~/Python/project-phoenix/BOTTLENECKS.md` — the
open-work board that schedules work across BT (Bulkhead Tau, which lives inside
`~/Python/project-phoenix/`) and this repo. BN's header carries the canonical
glossary; BN ≠ BT. All three harnesses (Claude Code, Codex, Antigravity) use
these names.

## Project Structure & Module Organization

This repository is a compact Python CLI project (requires Python ≥ 3.12).

| Path | Role |
|------|------|
| `operator` | Main ledger CLI (~6000 lines; most repo-local changes land here) |
| `opr` | Confirmation-gated governed REPL for local-model sessions |
| `operator-broker` / `authority_broker.py` | Standalone P3a authority broker |
| `operator-admin` / `authority_admin.py` | Root-managed P3b policy install/lifecycle |
| `authority_client.py` / `authority_projection.py` | Enrolled CLI ↔ broker integration |
| `socket_permission_helper.py` | Socket permission helpers for broker paths |
| `tests/test_operator.py` | Repo CLI integration suite (temp workspaces) |
| `tests/test_opr.py` | Governed REPL coverage |
| `tests/test_authority_*.py` | Broker, admin, integration, upgrade suites |
| `tests/fixtures/` | Synthetic harness logs and pricing fixtures |
| `*_SPEC.md` | Product/behavior contracts (source of truth for semantics) |
| `OPERATIONS_RUNBOOK.md` | Operator recovery and P3 procedures |
| `owners-manual/` | User-facing manual, chapters, PBC drafts, figures |
| `.operator/` | **Local runtime ledger only** — gitignored; never commit |

The P3a broker must remain independent of the repo-local `operator` CLI and
`.operator` state. P3b owns only root-managed installation and policy lifecycle.
`CRYSTAL_LEDGER_INTEROP_SPEC.md` is a draft proposal — nothing in that doc is
implemented yet.

## Build, Test, and Development Commands

- `pip install -r requirements.txt` installs the only runtime dependency, PyYAML.
- `./operator --help` lists the 22 repo CLI subcommands.
- `./operator doctor` checks consistency of the local `.operator/` ledger.
- `pytest tests/` runs the full subprocess-driven integration suite.
- `pytest tests/test_operator.py -q` is the fastest focused repo-CLI command.
- `pytest tests/test_authority_broker.py -q` runs the standalone broker/store suite.
- `pytest tests/test_authority_admin.py -q` runs the P3b install/policy suite.
- `pytest tests/test_authority_integration.py -q` runs CLI ↔ broker integration tests.
- `./operator-broker --help` lists the isolated P3a development surfaces.
- `./operator-admin --help` lists owner-only P3b commands. Production use requires a
  root-owned staged or installed copy; do not run it through sudo from this checkout.
- Lint/format (from `pyproject.toml`): `ruff check .`, `black --check .`, `isort --check-only .`.

Run `./operator init` only in a throwaway or intended workspace; it creates local
ledger files under `.operator/`. Re-running on an existing YAML-only ledger baselines
those records into SQLite without changing visible IDs.

## Coding Style & Naming Conventions

Use Python 3 with 4-space indentation, `from __future__ import annotations`, and
standard-library modules before third-party imports. Existing code favors small
helper functions, explicit paths via `pathlib.Path` or `os.path`, and readable CLI
output over framework abstractions. Keep record IDs in the established sequential
forms: `claim-0001`, `evidence-0001`, `usage-0001`, `handoff-0001`. CLI subcommands
and flags use kebab case, for example `task-create`, `--verified-by`, and
`task-transition`.

## Testing Guidelines

Tests use `unittest` assertions under pytest. Add repo CLI coverage in
`tests/test_operator.py` for CLI behavior, file layout, YAML contents, exit codes,
and stdout/stderr messages. Use temporary directories for ledger mutations, following
the existing `setUp` and `tearDown` pattern.

- Broker protocol, kernel-credential, transaction, CAS, and recovery coverage belongs
  in `tests/test_authority_broker.py`; it must not require sudo or simulated socket credentials.
- Administrative path, privilege-drop, policy lifecycle, preflight, and crash recovery
  coverage belongs in `tests/test_authority_admin.py`.
- Enrolled CLI transition/reconcile coverage belongs in `tests/test_authority_integration.py`.
- Put reusable synthetic logs or manifests in `tests/fixtures/`.
- Keep issue #6 repo CLI integration and issue #7 real-host dogfood out of P3b unit work
  unless the task explicitly targets them.

Test identity hooks (preserve both halves of the spoof guard):

- `OPERATOR_TEST_UID` + `OPERATOR_TEST_SENTINEL` (`1`/`true`) override the executing UID.
  UID without sentinel is a spoof attempt that `doctor` must flag as Error.
- `OPERATOR_TEST_CLAUDE_DIR` / `OPERATOR_TEST_CODEX_DIR` / `OPERATOR_TEST_GEMINI_DIR`
  redirect usage import to fixtures.
- `OPERATOR_MACHINE` overrides the `executor.machine` provenance stamp
  (see `MACHINE_PROVENANCE_SPEC.md`).

## Commit & Pull Request Guidelines

Recent commits use concise imperative subjects, such as `Add doctor checks...` or
`Refine worked example...`. Keep commits scoped to one behavioral or documentation
change. Pull requests should describe the user-visible change, list verification
commands such as `pytest tests/`, and call out ledger, identity, verification, or
authority-broker semantics that changed. Include screenshots only for rendered manual
or diagram updates.

## Security & Configuration Tips

Identity and verification behavior is governed by `.operator/identity.yaml`.
Preserve fail-closed verification semantics: only an enforced, registered verifier
OS UID distinct from the claim author is `uid_isolated`; `single_user` verification
is advisory. Evidence should prefer re-runnable commands over static blobs, but the
operator must never execute stored verification commands. In P3 mode, use
`task-transition` / `authority-reconcile` for broker-backed verified/complete state;
do not smuggle those statuses through `session-end`.

## Lane Economics

Cost is the driver's price, not the author's (see `usage-summary --by-lane`).
Transcript chores — summaries, handoff briefs, session rehydration — are
cheap-lane work and should never run in the most expensive seat at the table.
If a long-session resume or compaction is about to bill to a scarce frontier
seat, warn the operator before it starts.

Harness names are not ranks. Any agent that works under the ledger's identity,
claim, evidence, and verification rules is a participant; `assigned_harness`,
`review_harness`, `harness_id`, and `lane` are routing, provenance, and economics
fields, not a caste system. Do not infer supervisor, builder, verifier, or lane
authority from brand name alone.
