# Standalone Authority Broker Specification

## Status and boundary

This document specifies the P3a component implemented for issue #4. It is a standalone Unix-socket
broker, external SQLite authority store, evidence content-addressed store (CAS), receipt log, and
projection outbox. It is not an installed P3 deployment.

The existing `operator` command does not import or call this component. The broker does not discover
`.operator`, read worktree policy, update YAML projections, or open the P0 SQLite ledger. A receipt
created by the standalone fixture confers no P3 authority on an existing Operator ledger. Issues #5,
#6, and #7 own protected policy and service installation, repo CLI/projection integration, and
enrollment/real-host dogfood respectively.

The external store is **append-only by broker contract**, not physically immutable. The broker UID can
write it. The eventual security claim is that builder and verifier UIDs cannot write the executable,
policy, socket parent, store, or CAS. Issue #4 cannot establish that host boundary by itself.

## Process model

`operator-broker serve` runs as a dedicated unprivileged process and refuses UID 0. It receives absolute
paths for its socket, database, and CAS from its process supervisor. Those paths are never selected by a
request, cwd, `HOME`, `OPERATOR_DIR`, or `OPERATOR_TEST_UID`.

The server supports Linux Unix-domain `SOCK_STREAM` plus `SO_PEERCRED`. Every connection carries one
four-byte big-endian length-prefixed JSON frame, with requests capped at 1 MiB and responses at 16 MiB.
JSON parsing rejects duplicate keys, non-finite numbers, floating-point values, unknown fields, and
nesting deeper than 32 levels. The broker records the kernel-reported PID, UID, and GID; it has no
asserted-identity field or environment fallback.

The #4 server creates its socket with mode `0600`. Cross-UID socket access and protected socket-parent
installation belong to #5. The focused suite proves that the credentials recorded for separately exec'd
clients are real kernel credentials; real cross-UID host isolation remains #7 work.

## Development fixture

The following command exists only to create an isolated #4 test/development store:

```bash
./operator-broker bootstrap-fixture \
  --store /absolute/path/authority.sqlite3 \
  --content-dir /absolute/path/content \
  --bootstrap-config /absolute/path/bootstrap.json
```

The JSON fixture has this form:

```json
{
  "policy_id": "standalone-policy",
  "policy_generation": 1,
  "ledgers": ["ledger-test"],
  "roles": {
    "1000": ["builder"],
    "1001": ["verifier"]
  }
}
```

Only `builder` and `verifier` are accepted. The normalized fixture, its SHA-256 digest, role rows, and
ledger enrollment event are retained externally. Re-running the command is idempotent only when the
stored fixture is identical. This is deliberately not a policy installation or rotation interface. It
provides no root ownership, rollback defense, service provisioning, privilege preflight, or production
enrollment; #5 must replace this fixture boundary with administrator-controlled state.

## Wire operations

Every request includes `protocol_version: 1`. Protocol version, store schema version, and policy
generation are independent values.

### Commit

A commit request contains:

```json
{
  "protocol_version": 1,
  "action": "commit",
  "ledger_id": "ledger-test",
  "operation_key": "client-persisted-key",
  "operation": {
    "kind": "claim.create",
    "task_id": "task-0001",
    "claim_id": "claim-0001",
    "claim_type": "test_passes",
    "text": "the focused test passes"
  },
  "expected": [
    {"record_type": "task", "record_id": "task-0001", "version": 0, "event_hash": null},
    {"record_type": "claim", "record_id": "claim-0001", "version": 0, "event_hash": null}
  ]
}
```

The `operation`, `expected`, and optional `blob` fields are described below. Clients cannot
send event IDs, actor identity, policy binding, commit sequence, resulting record payloads, or arbitrary
mutations.

Supported operation kinds and required roles are:

| Operation | Role | Authoritative records |
| --- | --- | --- |
| `claim.create` | builder | task and new claim |
| `evidence.attach_draft` | builder | task, claim, and new evidence |
| `evidence.attach_status` | verifier | task, claim, and new evidence |
| `task.transition` | verifier | task |

The broker constructs all resulting record snapshots. In particular, a builder cannot smuggle a task
status change through `claim.create`, and a client cannot label its own evidence `uid_isolated` or
`external_broker`.

`claim.create` accepts `task_id`, `claim_id`, `claim_type`, `text`, and optional `required_gate`.

Evidence operations accept `task_id`, `claim_id`, `evidence_id`, and `evidence_type`.
`evidence.attach_status` additionally requires `verification_status` equal to `verified`, `false`, or
`quarantined`. A status-bearing attach fails when the peer UID equals the UID that created the claim.
Only the broker writes `verification_authority: uid_isolated` and
`policy_authority: external_broker` after that check succeeds.

`task.transition` accepts `status: verified` with a broker-authoritative verified claim, or
`status: complete` when the authoritative task is already verified. The verified transition binds the
claim's current event hash into the resulting task snapshot.

### Preconditions

`expected` contains exactly one entry for every record the operation will mutate:

```json
{
  "record_type": "task",
  "record_id": "task-0001",
  "version": 1,
  "event_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
}
```

Version zero plus a null hash means the record must not exist. A positive version requires the exact
current event hash. Policy selection, authorization, all precondition checks, global sequence allocation,
and the domain commit are repeated under one `BEGIN IMMEDIATE` transaction. Stale state fails without
reserving the operation key.

### Evidence descriptor

Evidence operations declare exactly one blob:

```json
{
  "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "size_bytes": 1234
}
```

The client passes the corresponding open descriptor with `SCM_RIGHTS`. The broker never opens a
client-supplied filesystem path. Unexpected, missing, multiple, non-regular, size-mismatched, or
hash-mismatched descriptors fail before metadata commit. An idempotent retry of an already committed
operation does not need to resend the descriptor.

The development client exposes descriptor passing as:

```bash
./operator-broker request \
  --socket /absolute/path/broker.sock \
  --json /absolute/path/request.json \
  --evidence-file ./result.log
```

`request` is a raw protocol exerciser, not integration with the existing `operator` CLI.

### Projection snapshot

An authorized enrolled UID can request the latest canonical record heads:

```json
{
  "protocol_version": 1,
  "action": "projection.snapshot",
  "ledger_id": "ledger-test"
}
```

The first response pins `through_commit_sequence` and returns up to 16 sorted latest records. When
`has_more` is true, the client repeats the request with that sequence and the returned `next_after`
record key. Every page carries the same total record count, streaming records digest, policy binding,
`store_incarnation_id`, and snapshot digest; commits after the pinned sequence cannot leak into later
pages. It returns current state rather than an old event delta, so a reconciler cannot apply an older
event over a newer projection. Each record head also carries the kernel actor UID and exact policy ID,
generation, and digest from the commit that produced that event; the top-level policy binding describes
the ledger's current policy. The #4 broker does not write repo paths or acknowledge/materialize a
projection; #6 owns that consumer and its operational acknowledgement behavior.

### Store incarnation (issue #9)

Each authority store mints a random `store_incarnation_id` (32 hex chars) once in `store_meta` at schema
creation (or on first post-upgrade open of a legacy store). The ID is stable for the lifetime of that
SQLite file and is included in every `projection.snapshot` payload and in the snapshot identity digest.

**What this detects:** a client journal that remembers a prior incarnation while the broker now reports a
different one — the observed dogfood failure mode where the store was rebuilt and sequence numbers
restarted low (or even advanced again) while the local `last_applied_sequence` still referred to the
dead store. Sequence comparison alone is not sufficient: a rebuild can present `broker_seq >=
last_applied` after the client journal is partially reset, which would otherwise project foreign
history as if continuous.

**What this does not claim:** a coherent root rewrite that preserves both the SQLite file identity and
all sequence numbers remains outside the design (same framing as policy-spec "root rewrite is
undetectable and unclaimed"). Incarnation is a store-lifetime signal, not a cryptographic seal against
a malicious broker UID.

**Client behavior:** enrolled `authority-reconcile` / projection recovery compares the broker
incarnation to `client_journal` metadata key `store_incarnation_id`. On mismatch it **fails closed**
(no success message, no empty projection loop). Operators who intentionally rebuilt a disposable store
must pass `--acknowledge-store-reset`, which drops local sequence progress, adopts the new incarnation,
and re-projects from the new store's history. Ordinary outages, policy rotation, and revocation keep
their existing distinct error paths.

## Idempotency and receipts

The operation key and canonical request digest are distinct. The digest covers the protocol version,
ledger, operation, preconditions, and blob declaration, but excludes the operation key and all
server-assigned fields.

Accepted operation keys are globally retained and bound to the enrolled ledger and authenticated peer
UID:

- Same key, same ledger/UID, and same digest returns the exact stored receipt without reauthorization,
  another append, or another evidence descriptor.
- Same key and a changed digest is `operation_key_conflict`.
- Cross-ledger or cross-UID reuse is `operation_key_scope_conflict`; it never reveals another UID's
  receipt.
- Rejected requests do not reserve a key.

A receipt means **committed to the external authority store**. It does not mean locally projected. It
binds protocol version, `status: committed`, `projection_status: pending`, ledger, global
`commit_sequence`, operation kind/key/digest, kernel actor credentials, policy ID/generation/digest,
event IDs/versions/hashes, retained evidence, the previous commit hash, commit hash, and receipt hash.

## Transaction and durability boundary

Before opening the metadata transaction, the broker:

1. performs preliminary enrollment, role, relationship, and precondition checks;
2. streams the passed regular-file descriptor into a mode-`0600` temporary file;
3. verifies the declared SHA-256 and size;
4. fsyncs the file, publishes it without replacing an existing digest path, fsyncs the shard directory,
   and re-reads the retained bytes for verification.

The broker then opens SQLite with foreign keys enabled, WAL journaling, `synchronous=FULL`, and a busy
timeout. Under `BEGIN IMMEDIATE`, it repeats authorization and state validation and atomically appends:

- all domain events and per-record versions/hash links;
- the broker-assigned monotonic global `commit_sequence` and global commit hash link;
- the kernel actor and selected policy binding;
- the operation-key/request-digest mapping;
- CAS metadata and commit/blob links;
- the append-only stored receipt; and
- one pending projection-outbox row containing the authoritative transaction projection.

Only after `COMMIT` does the server send the receipt. A failed transaction can leave an unreferenced CAS
blob, but cannot leave partial authority metadata. Garbage collection of unreferenced blobs is deferred.

Crash outcomes are explicit:

- Before CAS fsync: no authority metadata can reference the temporary bytes.
- After CAS publication but before SQLite commit: an unreferenced blob may remain.
- During SQLite commit: SQLite recovery yields either the whole transaction or none of it.
- After commit but before response: retry returns the stored original receipt and one outbox row.
- After external commit but before local projection: `projection.snapshot` recovers current canonical
  state without another authority event.

## Store and audit

Schema version 1 uses separate tables for store metadata, policy snapshots and roles, ledger-policy
events, authority commits, authority events, CAS blobs, commit/blob links, and projection outbox rows.
Authority tables have `UPDATE` and `DELETE` rejection triggers. Record heads are derived from the
append-only event history rather than trusted as mutable authority.

The database file must be owned by the broker UID with no group/other permission bits; the CAS root has
the same ownership rule and mode `0700`. `bootstrap-fixture` creates the database as `0600`. Protected
parents and cross-UID socket policy remain #5 responsibilities.

`serve` performs a full audit before binding the socket. `audit` can be run separately:

```bash
./operator-broker audit \
  --store /absolute/path/authority.sqlite3 \
  --content-dir /absolute/path/content
```

The audit verifies application/schema identity, required tables and append-only triggers, SQLite
integrity and foreign keys, normalized policy digests/roles, ledger-policy hash chains, contiguous global
commit sequences, commit/request/receipt bindings and hashes, per-record versions/hash chains, event-to-
commit bindings, CAS paths/bytes, commit/blob references, and every projection-outbox payload. Missing,
unsupported, unsafe, or divergent state fails before the listener starts.

## Explicit non-goals

Issue #4 does not provide:

- `/etc` or `/var` installation, root-owned executables/configuration, systemd, a service UID/group,
  socket ACLs, policy rotation/revocation/rollback, or privilege-path proof (#5);
- edits, imports, or subcommands in `operator`, `.operator` discovery, local operation-key persistence,
  YAML/P0 projection, `doctor` integration, session-end changes, or a projection worker (#6);
- existing-ledger enrollment/migration or real constrained builder/verifier host dogfood (#7);
- root execution, remote transport, signatures/keys, semantic evidence judgment, stored verification
  command execution, orchestration, rooms, or UI.

The P0-P2 CLI and ledger formats remain untouched by this component.
