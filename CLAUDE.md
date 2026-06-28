# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A local, file-backed **governance ledger for multi-agent software work**. The core idea is a
**narration-vs-execution partition**: an agent's *claim* ("I did X, it passes") is only trustworthy if
it has *evidence* attached and is *verified by a different identity*. The tool records the
task → claim → evidence → verification → session → usage lifecycle as append-only YAML under
`.operator/`, binds each write to the executing OS identity, blocks self-verification, and ships a
`doctor` consistency checker that fails closed.

When changing verification, identity, or `doctor` semantics, the guiding principle is: **enforce that a
check exists and runs, never claim it is meaningful.** Structural verification only (see the README's
"Known limitations").

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
throwaway/intended workspace. The `.operator/` dir is gitignored; never commit task/claim/evidence/
session/usage records.

## Architecture

**Single-file CLI.** Almost all implementation lives in the top-level `operator` script (~3900 lines,
Python 3 stdlib + PyYAML). `main()` builds an argparse subparser per command and dispatches through the
`cmd_map` dict near the end of the file (`init` → `init_cmd`, `task-create` → `task_create_cmd`, etc.).
To add or change a command, edit both the `add_parser(...)` block in `main()` and the corresponding
`*_cmd(args)` function.

**Ledger layout** (created by `init_cmd`, all append-only YAML):
`.operator/{tasks,claims,evidence,handoffs,usage,sessions,briefs}/` plus `harnesses/<id>.yaml` (the
known AI harnesses — claude, codex, gemini-agy, copilot, gemma3_local, gemma4_local; their default
definitions are hardcoded in `init_cmd`'s `harnesses_data`). `operator.yaml` holds top-level state like
`current_task`. Record IDs are sequential and zero-padded: `claim-0001`, `evidence-0001`, `usage-0001`,
`handoff-0001`. `find_operator_dir()` walks upward from cwd to locate the active ledger.

**Identity binding** (`get_executor_identity()`, EXECUTOR_IDENTITY_SPEC.md). Every write binds to
`os.getuid()`. Policy lives in `.operator/identity.yaml`: `mode: enforced` rejects a claim whose
`--verified-by` doesn't match the executing uid (impersonation guard); `mode: single_user` makes the
binding advisory, and `doctor` warns when a claim *would* be rejected under enforced mode (an
"enforcement downgrade").

**Verification guard** (VERIFIED_BY_GUARD_SPEC.md). `evidence-attach --status` requires `--claim`
(fail-closed), and a builder cannot sign off their own claim. Evidence prefers a re-runnable
`--verify-cmd` over a static blob; files are SHA-256 hashed (`calculate_file_hash`).

**doctor** (`doctor_cmd`) is read-only and fails closed (exit 1) on verified/completed records that lack
required evidence files, target-repo references, matching gate/test files, or valid command run hashes —
in addition to flagging unverified claims and self-verification.

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
