# Operator Control Plane

A small, local, file-backed **governance ledger for multi-agent software work.** It enforces a
**narration-vs-execution partition**: an agent's *claim* ("I did X, it passes") is only as good as the
*evidence* attached to it and the *verification* by a different identity. The `operator` CLI records
tasks → claims → evidence → verifications as append-only YAML under `.operator/`, binds each write to
the executing OS identity, guards against self-verification, and ships a `doctor` consistency checker.

Built as the "engine room / logbook" enforcement substrate for [Bulkhead τ](https://bulkheadtau.com),
but it stands alone. **Contributions welcome** — especially on the open problems below.

## Quickstart

```bash
pip install -r requirements.txt        # just PyYAML
./operator --help
./operator doctor                      # consistency check over the local .operator/ ledger
pytest tests/                          # subprocess-driven tests + synthetic session fixtures
```

The ledger (`.operator/`) is gitignored — it's your work history, not the tool.

## Commands

The `operator` CLI exposes 20 subcommands across the task → claim → evidence → verification →
session → usage lifecycle. Run `./operator <command> --help` for full flags.

**Setup** — `init` create the `.operator/` ledger in the current repo.

**Tasks**
- `task-create --objective "…" [--id ID] [--repo R] [--assign A] [--review R]` — open a task.
- `task-show [ID]` — show a task's claims, evidence, and status.
- `task-list` — list all tasks with outcome summaries.

**Claims** (a claim is a typed, checkable assertion bound to a gate)
- `claim-add --type TYPE --text "…" [--task ID] [--gate GATE] [--by WHO]` — register a claim.
  Types: `file_exists, test_passes, numeric_measurement, real_data, model_output,
  firmware_behavior, deployment_state, supervision_credit, paper_or_report_claim`.
- `claim-show [ID]` / `claim-list [--task ID]` — inspect claims.

**Evidence & verification** (the core: a claim is only as good as its evidence + a different-identity sign-off)
- `evidence-attach PATH_OR_URL --claim CID --type TYPE [--status {verified,false,quarantined}] [--verified-by WHO] [--verify-cmd CMD]`
  — attach an artifact and optionally verify the claim. Evidence types: `run_log, manifest,
  database_query, test_output, git_commit, screenshot, transcript, paper_section, external_doc`.
- `verify RUN_DIR` — automated audit of a run directory's artifacts.
- `doctor [--audit]` — read-only consistency check across the ledger: flags unverified claims,
  **self-verification**, and **enforcement downgrades** (a claim that would be rejected under
  enforced identity mode but is silently accepted under `single_user`).

**Sessions** (track a coding session and its cost)
- `session-start --harness H [--task ID] [--force]`
- `session-end --outcome {useful,partial,no_go,quarantined,reverted,unknown} --cost N`
- `session-list [--open] [--task ID] [--harness H]`

**Usage / quota accounting**
- `usage-add --harness H [--model M] [--outcome …]` — capture a pasted usage snippet.
- `usage-import --harness {claude,codex,gemini-agy} [--since …] [--dry-run]` — auto-ingest
  token/usage from harness session logs.
- `usage-summary [--by-task] [--by-harness] [--by-model] [--metering]` / `usage-annotate [--cost …] [--note …]`.

**Briefs & handoff**
- `brief --for H [--task ID]` / `export-brief --for H [--task ID]` — generate a harness-specific
  brief (copy-paste for the next agent).
- `handoff-add [--task ID] [--changed …] [--verified …] [--claimed …] [--open …]` — record a closeout.

## Worked example

```bash
./operator init                                    # create .operator/ ledger in this repo

# open a task
./operator task-create --objective "Add retry to the uploader" --id up-retry --repo myapp

# an agent registers a typed, gate-bound claim
./operator claim-add --task up-retry --type test_passes \
    --text "uploader retries 3x on 5xx" --gate tests/test_upload.py

# attach evidence and verify — verifier identity must differ from the builder (guard fails closed)
./operator evidence-attach tests/out/upload.log --task up-retry --claim claim-0001 \
    --type test_output --status verified --verified-by reviewer

# read-only consistency check: unverified / self-verified claims, enforcement downgrades
./operator doctor

# track the session + its cost, then close out with a brief for the next harness
./operator session-start --task up-retry --harness claude
./operator session-end --outcome useful --cost 12.50
./operator handoff-add --task up-retry --changed "uploader.py" --verified "retry test" --open "tune backoff"
./operator export-brief --for codex --task up-retry
```

## Configuration

Operator is driven by files under `.operator/` (created by `init`); behavior is governed by a small
set of product-facing config:

- **`.operator/identity.yaml`** — the identity-enforcement policy:
  ```yaml
  mode: enforced          # or: single_user (advisory)
  uids:
    1001: reviewer
    1002: builder
  ```
  In `enforced` mode, writes bind to the executing OS uid and a claim verified by the wrong
  identity is **rejected** (impersonation guard). In `single_user` mode the binding is advisory —
  and `doctor` warns when a claim *would* be rejected under enforced mode (an enforcement downgrade).
- **`.operator/{tasks,claims,evidence,sessions}/`** — append-only YAML records (the ledger; gitignored).

This config is what makes the guarantees real: the gate, the identities, and the fail-closed
verification all read from it.

## Design specs

- [`EXECUTOR_IDENTITY_SPEC.md`](EXECUTOR_IDENTITY_SPEC.md) — process-level identity binding via `os.getuid()`.
- [`VERIFIED_BY_GUARD_SPEC.md`](VERIFIED_BY_GUARD_SPEC.md) — fail-closed on self-verification (a builder can't sign off its own claim).
- [`USAGE_AUTOIMPORT_SPEC.md`](USAGE_AUTOIMPORT_SPEC.md) — ingest per-session token/usage from Claude/Codex/Gemini harness logs without unit conflation.

## Known limitations — help wanted

These are real and known (named honestly rather than hidden — the whole point of the tool is that
unverified claims are worthless):

- **Honor-system `verified_by` in `single_user` mode.** When every agent runs under one OS user,
  identity enforcement is advisory — the builder can assert the reviewer's name. Real enforcement needs
  distinct OS users / containers, or a write-isolated reviewer. *Hard problem; ideas welcome.*
- **The ledger is local-only and unbacked.** `.operator/` is gitignored; a disk wipe loses the audit
  trail. Evidence written to `/tmp` has been lost this way. Wants a durable, tamper-evident store.
- **The policy gate is self-amendable.** Any agent with write access to the config can weaken the gate
  it's supposed to be bound by. Wants out-of-band / immutable policy.
- **Evidence binding.** Prefer binding a *re-runnable structural test* over a captured blob or a
  byte-hash of a living document (living docs drift and train reviewers to rubber-stamp).

## License

MIT.
