# Machine Provenance (multi-machine support)

## Model

The ledger is **single-machine by design**: exactly one `.operator/` seat (the
supervisor's machine) holds tasks, claims, evidence, and usage. Other machines
participate through git — they commit work products; the ledger seat ingests
them as evidence. Multi-machine support is therefore **provenance, not
distribution**: every record says WHERE it was produced, and nothing attempts
ledger sync or merge (sequential record IDs make merging unsafe by
construction — never `operator init` a second ledger for the same work).

## Semantics

- `executor.machine` — stamped on every new record via executor identity
  (claims, evidence, usage, sessions). Resolution order: `OPERATOR_MACHINE`
  env override (also the test hook) → short hostname → `"unknown"`. Legacy
  records without the field read as `"unknown"`.
- `usage-import --source-dir PATH` — parse harness logs from an alternate
  directory (e.g. `~/.claude/projects-z13`, synced from the laptop). Missing
  path fails loudly.
- `usage-import --machine NAME` — label imported records with the **producer**
  machine, not the importer: sets `executor.machine = NAME` and
  `executor.machine_source = "manual"` on the imported records.
- `usage-summary --by-machine` — group by `executor.machine` × `harness_id`
  (runs, cost, tokens), mirroring `--by-lane`.

## Non-goals

- No cross-machine ledger replication, locking, or ID coordination.
- No change to identity/verification semantics: OS-UID isolation remains
  meaningful only within one machine; `machine` is provenance metadata and
  confers no authority.

Coverage: `tests/test_operator.py::test_machine_provenance_and_by_machine_summary`.
