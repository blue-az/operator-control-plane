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

## Study worktrees and the repo path (added 2026-08-30)

A task's `repo` field records where the work happened. For a live task a missing
repo is a real blocker; for a finished one it is provenance, and the distinction
matters because `doctor` treats them differently.

**Convention: study worktrees go somewhere durable**, e.g. `~/operator-studies/<id>/`,
not under the system temp directory. A scratch tree under `/tmp` is cleared on
reboot, and a verified task then permanently points at a path that will never
exist again.

**`doctor` behaviour**, in `doctor_cmd`'s repo existence check:

| Task status | Repo under temp dir | Elsewhere |
|---|---|---|
| verified / complete / quarantined | Info -- expected | **Error** |
| anything else | Warning | Warning |

The downgrade is narrow on purpose. A missing durable repo on verified work is
still an Error, because verified work should stay inspectable. A missing temp
worktree is not a consistency failure -- it was never durable by construction --
and reporting it as a permanent unfixable Error trains readers to ignore Errors,
which costs more than the check gains. Evidence is unaffected either way: local
evidence is copied into `.operator/evidence/` after fingerprinting and is checked
separately.

Historical note: `ffsi-001-row-a` and `ffsi-001-accuracy-separation` were run
under `/tmp/operator-study-FFSI-001/` in August 2026 and are the reason this is
written down. Their claims and evidence survived; only the worktrees are gone.

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
stamp `executor.machine = desktop` (5 legacy records read `unknown`).

**z13's second ledger CANNOT simply be retired — it holds unique work.**
BOTTLENECKS Front H describes it via its *eval* event count ("z13's holds
zero"), which is true and badly misleading. Inventoried over SSH 2026-08-15:

| | z13 |
|---|---:|
| tasks | 9 (**8 exist nowhere else**) |
| claims | **23** |
| evidence | **110** |
| handoffs | **40** |

z13-only tasks: `agentic-cli-tps-metrics`, `evidence-snapshot-hardening`,
`kernelcad-forehand-incident-handoff`, `local-routing-corpus`,
`opr-continuation-loop-audit`, `pa-evidence`, `proposal-lifecycle`,
`session-coordination-protocol`.

Worse, `front-e1-gold-pack` exists on **both** machines with **different
content** (md5 `196603…` vs `05c17c…`). That is the divergence this spec's
"never `operator init` a second ledger" rule exists to prevent, and it has
already happened: one task id, two histories, two sequential-id spaces.

So the path is **migration, not deletion**, and it is not mechanical:

1. z13-only tasks can move as *evidence* into seat-side tasks — they cannot be
   copied as tasks, because their record ids collide with the seat's sequence.
2. `front-e1-gold-pack` needs a human ruling on which history is authoritative,
   or both preserved under distinct ids.
3. Only after both are resolved does z13 stop writing and become Background.

Full ledger backup taken before any of this:
`handoffs/z13_ledger_backup_20260815_142616.tar.gz` (283 entries, 356K).
**Nothing on z13 has been deleted or modified.**

`~/.claude/projects-z13` holds 68 synced log files; the usage half of the
backfill (67 records, `--machine z13`) was imported 2026-08-15 under task
`z13-historical-usage-import`. That path is safe precisely because usage
records are producer-labelled and written by the seat, so no second ledger is
involved.

## Non-goals

- No cross-machine ledger replication, locking, or ID coordination.
- No change to identity/verification semantics: OS-UID isolation remains
  meaningful only within one machine; `machine` is provenance metadata and
  confers no authority.

Coverage: `tests/test_operator.py::test_machine_provenance_and_by_machine_summary`.
