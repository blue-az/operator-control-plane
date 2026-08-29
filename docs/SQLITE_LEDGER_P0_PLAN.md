# Append-Only SQLite Ledger P0 Plan

## Scope

Keep the existing YAML-facing CLI and record IDs while adding `.operator/ledger.sqlite3` as the
durable audit history for task, claim, evidence, usage/session, and handoff writes.

## Commands Touched

- `init`: create the event store and baseline an existing YAML-only ledger.
- `task-create`, `claim-add`, `evidence-attach`, `usage-add`, `usage-import`,
  `usage-annotate`, `session-start`, `session-end`, and `handoff-add`: append a full record snapshot
  before replacing the corresponding YAML projection.
- `doctor`: verify event hashes and compare every latest event with the visible YAML record.

Sessions remain usage records (`usage-XXXX`), matching the current CLI and file layout. Their event
rows retain `session-start` or `session-end` as the source command.

## Compatibility And Authority

YAML remains the CLI read surface. SQLite records what the CLI wrote and preserves prior versions;
neither surface is silently repaired when they disagree. `doctor` reports the disagreement as an
error. A YAML-only ledger is imported as version 1 when `operator init` is rerun or before its first
subsequent trust-record write.

SQLite and YAML cannot share one transaction. A write commits the SQLite event first, then atomically
replaces the YAML projection. If the projection write fails, the command fails and `doctor` exposes
the mismatch instead of discarding the durable event.

## Tests

- Store creation and legacy-ledger bootstrap.
- Durable rows for task, claim, evidence, usage/session, and handoff commands.
- Monotonic versions, hash chaining, and database guards against row update/delete.
- `doctor` failures for changed, malformed, or missing YAML projections.
- Existing CLI integration suite remains green.

## Stop Condition

Stop after P0. Evidence staleness expansion, verifier isolation, policy hardening, and semantic gate
heuristics remain out of scope.
