# Repository Guidelines

## Project Structure & Module Organization

This repository is a compact Python CLI project. The executable entry point is the
top-level `operator` script; most implementation changes happen there. Integration
tests live in `tests/test_operator.py` and run the CLI in temporary workspaces.
Static test inputs are under `tests/fixtures/`. Product and behavior specs live in
top-level `*_SPEC.md` files. The standalone P3a authority component lives in
`authority_broker.py` behind the separate top-level `operator-broker` executable; it must remain
independent of the repo-local `operator` CLI and `.operator` state. The user-facing manual is in
`owners-manual/` with chapters, PBC drafts, figures, and bundled data.

The runtime ledger directory `.operator/` is local state and gitignored. Do not
commit generated task, claim, evidence, session, or usage records.

## Build, Test, and Development Commands

- `pip install -r requirements.txt` installs the only runtime dependency, PyYAML.
- `./operator --help` lists available CLI commands.
- `./operator doctor` checks consistency of the local `.operator/` ledger.
- `pytest tests/` runs the subprocess-driven integration suite.
- `pytest tests/test_operator.py -q` is the fastest focused test command.
- `pytest tests/test_authority_broker.py -q` runs the standalone broker/store suite.
- `./operator-broker --help` lists the isolated P3a development surfaces.

Run `./operator init` only in a throwaway or intended workspace; it creates local
ledger files under `.operator/`.

## Coding Style & Naming Conventions

Use Python 3 with 4-space indentation, `from __future__ import annotations`, and
standard-library modules before third-party imports. Existing code favors small
helper functions, explicit paths via `pathlib.Path` or `os.path`, and readable CLI
output over framework abstractions. Keep record IDs in the established sequential
forms: `claim-0001`, `evidence-0001`, `usage-0001`, `handoff-0001`. CLI subcommands
and flags use kebab case, for example `task-create` and `--verified-by`.

## Testing Guidelines

Tests use `unittest` assertions under pytest. Add repo CLI coverage in `tests/test_operator.py`
for CLI behavior, file layout, YAML contents, exit codes, and stdout/stderr messages.
Use temporary directories for ledger mutations, following the existing `setUp` and
`tearDown` pattern. Broker protocol, kernel-credential, transaction, CAS, and recovery coverage belongs
in `tests/test_authority_broker.py`; it must not require sudo or simulated socket credentials. Put
reusable synthetic logs or manifests in `tests/fixtures/`.

## Commit & Pull Request Guidelines

Recent commits use concise imperative subjects, such as `Add doctor checks...` or
`Refine worked example...`. Keep commits scoped to one behavioral or documentation
change. Pull requests should describe the user-visible change, list verification
commands such as `pytest tests/`, and call out ledger, identity, or verification
semantics that changed. Include screenshots only for rendered manual or diagram
updates.

## Security & Configuration Tips

Identity and verification behavior is governed by `.operator/identity.yaml`.
Preserve fail-closed verification semantics: only an enforced, registered verifier
OS UID distinct from the claim author is `uid_isolated`; `single_user` verification
is advisory. Evidence should prefer re-runnable commands over static blobs, but the
operator must never execute stored verification commands.
