# Operator Telemetry v1

## Purpose and boundary

Operator telemetry records a small, opt-in, timestamped account of host resource state while an existing Operator session is open. Its purpose is provenance/context, not performance scoring or proof that a task succeeded.

The collector reads only the host on which `operator telemetry capture` runs. It does not inspect prompts, transcripts, command lines, network traffic, or other processes. Host metric collection does not use environment variables; event actor attribution uses Operator's existing executor-identity hook, including its documented test-identity overrides. It does not launch or stop workloads, call services, modify configuration, or authorize work. Process-level telemetry, remote collection, GPU metrics, dashboards, and automatic start/stop hooks are out of scope.

## Interface

```sh
operator telemetry capture --usage usage-0001 \
  [--interval-seconds 5] [--duration-seconds 60]
operator telemetry show --usage usage-0001
```

Capture is explicit, bounded, and requires an existing open usage/session record associated with a task. Both interval and duration are limited to 1–3600 seconds. The first sample is taken immediately. Each invocation gets a unique `capture_id` repeated on its start, snapshot, completion, interruption, or partial events, so concurrent/repeated captures on one session remain distinguishable. Capture currently refuses broker-enrolled ledgers rather than writing around broker authority; the local ledger is the only supported telemetry store in v1. Capture appends a start event, host snapshots, and a completion event. Ctrl-C appends an interruption marker; a read failure appends a partial-capture marker when possible. Re-running capture creates another append-only capture sequence; it does not replace earlier data. Capture does not close or otherwise mutate the session/task.

## Snapshot fields

On Linux, snapshots currently include UTC capture time, hostname, OS release and architecture, boot ID when available, uptime, 1/5/15-minute load averages, CPU busy percentage since the prior sample (null for the first sample), and total/available/used memory bytes. Missing optional values are represented as `null`. The collector reads `/proc` and the standard library only; unsupported hosts fail with a clear error before recording a capture.

These are observations from the collector host. They do not identify a specific application, model, process, or cause of resource use.

## Storage and integrity

Events are stored in `.operator/ledger.sqlite3` in a dedicated `telemetry_events` table, associated to the existing `usage_id` and `task_id`. They are not YAML projections or trust records and do not change claim/evidence/task status. The SQLite schema migrates from version 1 to version 2 when Operator initializes/first writes the ledger. Broker-enrolled telemetry is intentionally unsupported until a broker-owned append path exists; the projection/schema understands the table and enforces its triggers but does not accept local telemetry writes.

Each row is timestamped in UTC and hash-linked to the preceding telemetry event for that session. SQLite triggers reject updates and deletes. `operator doctor` verifies canonical payload encoding, event hashes, per-session chain links, and that the referenced usage/session and task exist. This is local tamper evidence, not protection against an administrator who can replace the whole database or rewrite schema/triggers.

`telemetry show` emits JSON Lines in sequence order with `capture_id` on every event. The output is observational data; neither capture nor show interprets it as verification.

## Acceptance tests

- Capture requires a known, open session with a task association; unknown, closed, or taskless sessions are rejected without telemetry rows.
- A bounded capture writes UTC start/snapshot/completion events linked to the correct usage and task, with host metric fields and first-sample CPU represented as null.
- `telemetry show` returns those events in order with capture IDs; concurrent captures on one session remain partitionable, and a clean telemetry chain passes `operator doctor`.
- SQLite rejects update/delete of telemetry rows; tampered payload/hash or broken link is reported by `doctor`.
- A v1 ledger migrates to schema v2 without losing existing ledger records.
- Capture uses no subprocess/network calls and makes no changes to task/usage projections or workload processes.
