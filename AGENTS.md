# Repository Guidelines

## Core Philosophy: Narration vs Execution
Operator enforces a strict partition: an agent's *claim* ("I did X") is only trustworthy if it has *evidence* attached and is *verified by a distinct identity*. The system records the task → claim → evidence → verification → session → usage lifecycle.

## Standalone Boundary
Operator is a standalone, domain-neutral support/control plane. It is **not** Bulkhead Tau, Project Phoenix, or an internal component of another product. 
- **Dependency Direction:** One-way. Bulkhead Tau may use Operator; Operator must **never** import or require Bulkhead Tau code or domain semantics.
- **External Context:** BT, BN, PBC, etc., are external consumers/inputs, not architectural components.
- **Harnesses:** peers (Claude Code, Codex, etc.); `assigned_harness` and `lane` are for routing and economics, not authority.

## Concurrent Sessions & Ledger Identity
To avoid identity drift in multi-session environments:
- Use **session-derived IDs** (e.g., `claude-019KSo7K`) for `--by`, `--assign`, and `--review`, not role labels (`claude-builder`).
- Session IDs are stable for the session; role continuity should be tracked manually in handoffs if the session ID changes upon resume.
- Registering a harness in `.operator/harnesses/<id>.yaml` is only required for `--assign`/`--review`.

## Project Structure
Compact Python CLI (Python ≥ 3.12).
| Path | Role |
|------|------|
| `operator` | Main ledger CLI (~6000 lines; primary logic) |
| `opr` | Deprecated stub. Use OpenCode (`opencode run`) as the local implementer. Restore the old REPL from git (`fe4211b`). |
| `operator-broker` / `authority_broker.py` | P3a authority broker (Isolated; no `.operator` access) |
| `operator-admin` / `authority_admin.py` | P3b policy install/lifecycle (Root-managed) |
| `authority_client.py` / `authority_projection.py` | CLI ↔ broker integration |
| `dogfood_runner.py` | Resumable dogfood plan engine |
| `tests/test_operator.py` | Main CLI integration suite |
| `tests/test_authority_*.py` | Broker, admin, and integration suites |
| `*_SPEC.md` | Source of truth for semantics/contracts |
| `.operator/` | Local runtime ledger (Gitignored; never commit) |

## Build, Test, and Development Commands
- `pip install -r requirements.txt` (Only dependency: PyYAML)
- `./operator doctor` (Consistency check of local `.operator/` ledger)
- `pytest tests/` (Full suite)
- `pytest tests/test_operator.py -q` (Focused CLI tests)
- `pytest tests/test_operator.py -q -k doctor` (Targeted doctor tests)
- `pytest tests/test_authority_broker.py -q` (P3a broker tests)
- `./operator-broker --help` / `./operator-admin --help` (P3a/P3b surfaces)
- `ruff check .` / `black --check .` / `isort --check-only .` (Lint/Format)
- `./operator init` (Creates local ledger; use only in intended workspaces)

## Coding Style & Naming
- Python 3, 4-space indent, `from __future__ import annotations`.
- Favor small helpers and explicit paths (`pathlib.Path`).
- **IDs:** Sequential, zero-padded forms: `claim-0001`, `evidence-0001`, `usage-0001`, `handoff-0001`.
- **CLI:** Subcommands and flags use kebab-case (`task-create`, `--verified-by`).

## Testing Guidelines
- Use `unittest` assertions under `pytest`. Use temp directories for ledger mutations.
- **Identity Hooks (Do not remove):**
  - `OPERATOR_TEST_UID` + `OPERATOR_TEST_SENTINEL` (`1`/`true`): Overrides executing UID. UID without sentinel is a spoof attempt and must be flagged as Error by `doctor`.
  - `OPERATOR_TEST_CLAUDE_DIR` etc.: Redirects usage imports to `tests/fixtures/`.
  - `OPERATOR_MACHINE`: Overrides `executor.machine` provenance.

## Security & Integrity
- **Fail-Closed:** Verification is only `uid_isolated` if the registered verifier UID differs from the claim author's UID. `single_user` mode is advisory.
- **Evidence:** Prefer re-runnable commands (`--verify-cmd`) over static blobs.
- **P3 Mode:** Use `task-transition` / `authority-reconcile` for broker-backed state; avoid smuggling statuses via `session-end`.
- **Doctor:** Must remain read-only; it validates bytes/hashes but never executes stored verification commands.
- **Git:** Local-model seats do not `git commit`, rebase, or rewrite history unless the human is explicitly running a git experiment. Recaps of hygiene are narration; `git status` and `git log` are the record. See `docs/HARNESS_TURN_COST_ANECDOTES.md` 2026-08-23 and `HARNESS_REQUIREMENTS_SPEC.md` R7.

## Lane Economics
- **Billing:** Cost is the driver's price, not the author's (`usage-summary --by-lane`).
- **Efficiency:** Transcript chores (summaries, rehydration) are "cheap-lane" work; do not run them in expensive seats.
- **Harnesses:** Name $\neq$ Rank. Do not infer authority from brand names.

