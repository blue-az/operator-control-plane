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

## Seat modes and travel (added 2026-08-15)

The model above says "exactly one `.operator/` seat (the supervisor's machine)"
but never says what happens when the supervisor physically changes machines.
That gap is why a second ledger exists on z13 (BOTTLENECKS.md **Front H**).

**The seat does not move.** Merging is unsafe by construction, so a travelling
supervisor must not open a ledger on the travel machine and reconcile later.
Instead every machine is permanently in one of two modes:

| Mode | Machine | Behaviour |
|---|---|---|
| **Seat** | desktop | Holds the only `.operator/`. All tasks, claims, evidence, handoffs. |
| **Background** | z13, and any other | **No `operator init`, ever.** Produces git commits and harness logs. Nothing else. |

Background machines contribute two ways, both already supported:

1. **Work products** — commit to git. The seat ingests them as evidence,
   referencing the commit, exactly as any other artifact.
2. **Usage/economics** — harness logs sync to a seat-visible path, then:
   `operator usage-import --harness claude --source-dir ~/.claude/projects-z13 --machine z13`
   The `--machine` flag labels the **producer**, not the importer, so a
   background machine's cost is attributed correctly without it ever writing
   to the ledger itself.

**Travel is not a mode change.** It is a widening of the ingest lag. While
away, z13 accumulates commits and logs; on return they are ingested. The
"transition period" is that queue draining, not a seat handoff. If the seat
machine is unreachable from the road, the queue simply grows — which is safe,
because nothing on the background machine is authoritative in the first place.

**Consequence for verification.** `uid_isolated` is meaningful only within one
machine, so a claim produced on a background machine cannot be verified by that
machine's own session in any way the seat recognises. It arrives as evidence and
is verified at the seat by a distinct UID, like any other outside input.

**Current state (2026-08-15).** Desktop is the seat: 948 of 953 task records
stamp `executor.machine = desktop` (5 legacy records read `unknown`). z13 holds
a second `.operator/` in violation of this spec; it should be retired rather
than merged. `~/.claude/projects-z13` exists with 68 synced log files that have
**never been imported** — no `z13` row appears in `usage-summary --by-machine`.

## Non-goals

- No cross-machine ledger replication, locking, or ID coordination.
- No change to identity/verification semantics: OS-UID isolation remains
  meaningful only within one machine; `machine` is provenance metadata and
  confers no authority.

Coverage: `tests/test_operator.py::test_machine_provenance_and_by_machine_summary`.
