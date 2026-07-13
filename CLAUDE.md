# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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
./operator --help                        # 20 subcommands; ./operator <cmd> --help for flags
./operator doctor                        # consistency check over local .operator/ ledger
pytest tests/                            # full subprocess-driven integration suite
pytest tests/test_operator.py -q         # fastest focused run
pytest tests/test_operator.py -q -k doctor   # run a single test by name pattern
ruff check .                             # lint check configured in pyproject.toml
black --check .                          # formatting check
isort --check-only .                     # import sorting check
```

`./operator init` creates a local `.operator/` ledger in the current directory — only run it in a
throwaway/intended workspace. The `.operator/` dir is gitignored; never commit its YAML records or
`ledger.sqlite3` event store.

## Architecture

**Single-file CLI.** Almost all implementation lives in the top-level `operator` script (~4700 lines,
Python 3 stdlib + PyYAML). `main()` builds an argparse subparser per command and dispatches through the
`cmd_map` dict near the end of the file (`init` → `init_cmd`, `task-create` → `task_create_cmd`, etc.).
To add or change a command, edit both the `add_parser(...)` block in `main()` and the corresponding
`*_cmd(args)` function.

**Ledger layout** (created by `init_cmd`):
`.operator/{tasks,claims,evidence,handoffs,usage,briefs}/` plus `harnesses/<id>.yaml` (the
known AI harnesses — claude, codex, gemini-agy, copilot, gemma3_local, gemma4_local; their default
definitions are hardcoded in `init_cmd`'s `harnesses_data`). `operator.yaml` holds top-level state like
`current_task`. Record IDs are sequential and zero-padded: `claim-0001`, `evidence-0001`, `usage-0001`,
`handoff-0001`. These YAML files are current projections; `.operator/ledger.sqlite3` retains immutable
full-snapshot versions for trust-relevant writes. Session commands version their `usage-XXXX` record.
`find_operator_dir()` walks upward from cwd to locate the active ledger.

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
(local-author vs frontier-driver) lives in `score_session` and the `usage-summary` code path.

## Testing

`tests/test_operator.py` is a `unittest`-style suite run under pytest that invokes the `operator` binary
as a subprocess in temp dirs (`OPERATOR_BIN` resolves the top-level script). Key test hooks — read by
`get_executor_identity()` and the usage importer — let tests simulate identities and log sources without
touching real ones:

- `OPERATOR_TEST_UID` + `OPERATOR_TEST_SENTINEL` (`1`/`true`) — override the executing uid. **Both are
  required**: a `OPERATOR_TEST_UID` without the sentinel is treated as a *spoof attempt* and `doctor`
  flags the resulting write as an Error. This is itself under test, so preserve the behavior.
- `OPERATOR_TEST_CLAUDE_DIR` / `OPERATOR_TEST_CODEX_DIR` / `OPERATOR_TEST_GEMINI_DIR` — point the usage
  importer at fixtures under `tests/fixtures/` instead of the user's home directory.

## Docs

Behavior specs are the top-level `*_SPEC.md` files (identity, verified-by guard, usage autoimport, usage
lane tagging, governed dispatch). The user-facing manual is `owners-manual/` (chapters, PBC drafts,
mermaid figures). `AGENTS.md` holds repository contribution conventions.
