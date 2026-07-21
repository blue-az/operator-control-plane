# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) and compatible harnesses
when working with code in this repository.

## What this is

A local **governance ledger for multi-agent software work**. The core idea is a
**narration-vs-execution partition**: an agent's *claim* ("I did X, it passes") is only trustworthy if
it has *evidence* attached and is *verified by a different identity*. The tool records the
task → claim → evidence → verification → session → usage lifecycle as YAML projections plus an
append-only SQLite event history under `.operator/`, binds each write to the executing OS identity,
blocks same-UID trusted verification in enforced mode, and ships a `doctor` consistency checker that
fails closed. Same-UID `single_user` verification remains usable but is explicitly advisory.

When changing verification, identity, or `doctor` semantics, keep `doctor` structural and read-only. It
may validate bindings and recompute fingerprints, but it must never execute a stored verification command.
Do not claim that structurally valid evidence is semantically meaningful (see the README's "Known
limitations").

## Commands

```bash
pip install -r requirements.txt          # only runtime dep is PyYAML
./operator --help                        # 22 subcommands; ./operator <cmd> --help for flags
./operator doctor                        # consistency check over local .operator/ ledger
pytest tests/                            # full subprocess-driven integration suite
pytest tests/test_operator.py -q         # fastest focused repo-CLI run
pytest tests/test_operator.py -q -k doctor   # run a single test by name pattern
pytest tests/test_authority_broker.py -q     # standalone P3a broker/store tests
pytest tests/test_dogfood_runner.py -q   # dogfood runner unit suite
./operator-broker --help                    # isolated P3a development surfaces
./operator-admin --help                     # root-managed P3b policy & dogfood runner surfaces
ruff check .                             # lint check configured in pyproject.toml
black --check .                          # formatting check
isort --check-only .                     # import sorting check
```

`./operator init` creates a local `.operator/` ledger in the current directory — only run it in a
throwaway/intended workspace. The `.operator/` dir is gitignored; never commit its YAML records or
`ledger.sqlite3` event store. Re-running `init` on an existing YAML-only ledger baselines records into
SQLite without changing visible IDs or files.

## Architecture

**Single-file CLI.** Most repo-local ledger logic lives in the top-level `operator` script (~6000 lines,
Python 3 stdlib + PyYAML). `main()` builds an argparse subparser per command and dispatches through the
`cmd_map` dict near the end of the file (`init` → `init_cmd`, `task-create` → `task_create_cmd`, etc.).
To add or change a command, edit both the `add_parser(...)` block in `main()` and the corresponding
`*_cmd(args)` function. Supports `--type diff` evidence attachments (generating git diffs relative to `--diff-base` or `task.created_at`) and `doctor --stale-days N` (flagging inactive assigned tasks).

**Subcommands (22):** `init`, `task-create`, `task-show`, `task-list`, `task-transition`,
`claim-add`, `claim-show`, `claim-list`, `evidence-attach`, `handoff-add`, `verify`, `doctor`,
`session-start`, `session-end`, `session-list`, `usage-add`, `usage-import`, `usage-summary`,
`usage-annotate`, `brief`, `export-brief`, `authority-reconcile`.

**Standalone P3a broker.** `operator-broker` dispatches to `authority_broker.py`, which owns the isolated
length-framed Unix socket protocol, `SO_PEERCRED` authentication, external SQLite authority history,
descriptor-backed evidence CAS, receipts, startup audit, and projection snapshots described in
`AUTHORITY_BROKER_SPEC.md`. It must not import `operator`, inspect `.operator`, or project local state.
Its `bootstrap-fixture` and raw `request` commands are test/development surfaces, not protected policy
installation or repo CLI integration.

**Root-managed P3b policy & Dogfood runner.** `operator-admin` dispatches to `authority_admin.py` and `dogfood_runner.py` for fixed-path,
root-owned installation, strict policy generations, terminal revocation, audit, conservative
privilege preflight, and typed resumable dogfood plans (`dogfood-plan`, `dogfood-run`, `dogfood-status`, `dogfood-resume`). `AUTHORITY_POLICY_SPEC.md` and `docs/DOGFOOD_RUNNER_OPERATIONS.md` are the contracts. SQLite creation and administrative
transactions execute only after dropping permanently to the broker UID. The service is not started or
enabled, and this layer must not import or modify the repo-local `operator` CLI. Initial production
installation requires a root-owned staged release because the wrapper rejects privileged execution
from a user-writable checkout.

**CLI ↔ broker integration.** `authority_client.py` and `authority_projection.py` implement the
enrolled client path described in `AUTHORITY_INTEGRATION_SPEC.md`. In P3 mode, task verification or
completion must go through `task-transition` (broker-authenticated); `authority-reconcile` applies
projection snapshots from the broker. `session-end --status verified|complete` is rejected in that
mode. See `OPERATIONS_RUNBOOK.md` for operator recovery procedures.

**Governed REPL.** `opr` is a confirmation-gated shell/REPL for local model sessions; coverage lives
in `tests/test_opr.py`. `GOVERNED_DISPATCH_SPEC.md` and `OPR_GENERALIZATION_SPEC.md` describe behavior.

**Ledger layout** (created by `init_cmd`):
`.operator/{tasks,claims,evidence,handoffs,usage,briefs}/` plus `harnesses/<id>.yaml` (the
known AI harnesses — claude, codex, gemini-agy, grok, copilot, gemma3_local, gemma4_local,
gpt-oss_local; their default definitions are hardcoded in `init_cmd`'s `harnesses_data`). `opr` derives
local harness labels from the serving model (`<model-base>_local`, e.g. gpt-oss:20b → gpt-oss_local —
defaults differ per machine), so a new local default model needs a matching `harnesses/<id>.yaml` in
existing ledgers. `operator.yaml` holds top-level state like
`current_task`. Record IDs are sequential and zero-padded: `claim-0001`, `evidence-0001`, `usage-0001`,
`handoff-0001`. These YAML files are current projections; `.operator/ledger.sqlite3` retains immutable
full-snapshot versions for trust-relevant writes. Session commands version their `usage-XXXX` record.
`find_operator_dir()` walks upward from cwd to locate the active ledger.

**Harness roles are not ranks.** Any agent can participate if its work is recorded under the ledger's
identity, claim, evidence, and verification rules. `assigned_harness`, `review_harness`, `harness_id`,
and `lane` are routing, provenance, and economics fields; never infer supervisor, builder, verifier, or
lane authority from brand name alone.

**Identity binding** (`get_executor_identity()`, EXECUTOR_IDENTITY_SPEC.md). Every write binds to
`os.getuid()`. Policy lives in `.operator/identity.yaml` as UID entries with `name` and `roles`.
`mode: enforced` requires builders for claim/draft-evidence writes and verifiers for status writes.
A status is `uid_isolated` only when the registered verifier UID differs from the claim's recorded
author UID; `--verified-by` must match the registry name. `mode: single_user` stays usable but records
every status as `advisory`. Legacy scalar UID entries normalize to both roles for compatibility.

**Verification guard** (VERIFIED_BY_GUARD_SPEC.md). `evidence-attach --status` requires `--claim`
(fail-closed), and trusted verification requires a distinct OS UID, not just a different harness name.
Evidence prefers a re-runnable
`--verify-cmd` over a static blob. Local files are copied only after their bytes are fingerprinted with
SHA-256, size, and modification time; `--hash` is treated as an expected digest and must match those bytes.
The original local locator and fingerprint are retained separately from the copied snapshot. The raw
`hash` field remains a compatibility alias for older readers.

**doctor** (`doctor_cmd`) is read-only and fails closed (exit 1) when SQLite event hashes or YAML
projections disagree, or when verified/completed records lack required evidence files, target-repo
references, matching gate/test files, valid command run hashes, or current local evidence bytes — in
addition to flagging unverified claims and self-verification. It distinguishes changed content from an
unavailable original source, reports remote evidence as uncheckable without a local snapshot, and never
executes `verification_command`.

**Usage auto-import** (`usage_import_cmd`, USAGE_AUTOIMPORT_SPEC.md). Parses per-session token/usage from
real harness logs under `~/.claude`, `~/.codex`, `~/.gemini/...`. Session scoring/lane-tagging
is explicit: imported records default to `lane: unknown`, and `usage-summary` groups/audits only tagged
lane data.

## Testing

`tests/test_operator.py` is a `unittest`-style suite run under pytest that invokes the `operator` binary
as a subprocess in temp dirs (`OPERATOR_BIN` resolves the top-level script). Other suites:

| Suite | Covers |
|-------|--------|
| `tests/test_operator.py` | Repo CLI, ledger layout, identity, doctor, usage |
| `tests/test_opr.py` | Governed REPL |
| `tests/test_authority_broker.py` | P3a protocol, CAS, recovery (no sudo) |
| `tests/test_authority_admin.py` | P3b install/policy lifecycle |
| `tests/test_authority_admin_root.py` | Privileged admin path tests |
| `tests/test_authority_integration.py` | CLI ↔ broker enrollment, transition, reconcile |
| `tests/test_authority_upgrade.py` | Authority upgrade paths |
| `tests/test_runbook.py` | Operations runbook checks |

Key test hooks — read by `get_executor_identity()` and the usage importer — let tests simulate
identities and log sources without touching real ones:

- `OPERATOR_TEST_UID` + `OPERATOR_TEST_SENTINEL` (`1`/`true`) — override the executing uid. **Both are
  required**: a `OPERATOR_TEST_UID` without the sentinel is treated as a *spoof attempt* and `doctor`
  flags the resulting write as an Error. This is itself under test, so preserve the behavior.
- `OPERATOR_TEST_CLAUDE_DIR` / `OPERATOR_TEST_CODEX_DIR` / `OPERATOR_TEST_GEMINI_DIR` — point the usage
  importer at fixtures under `tests/fixtures/` instead of the user's home directory.

## Docs

Behavior specs are the top-level `*_SPEC.md` files (identity, verified-by guard, usage autoimport,
usage lane tagging, governed dispatch, authority broker/policy/integration, local lane contract).
`CRYSTAL_LEDGER_INTEROP_SPEC.md` is a **draft proposal** (not built). The user-facing manual is
`owners-manual/` (chapters, PBC drafts, mermaid figures). `OPERATIONS_RUNBOOK.md` covers recovery.
`AGENTS.md` holds repository contribution conventions and boundary taxonomy.
