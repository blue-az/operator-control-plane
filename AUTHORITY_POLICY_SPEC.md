# Root-Managed Authority Policy Specification

## Status and scope

This document specifies the issue #5 installation and policy lifecycle layered over the standalone
issue #4 authority broker. It installs root-owned code, service definitions, enrollment state, and
append-only policy generations. It does not integrate the repo-local `operator` CLI, enroll an existing
`.operator` ledger, provision accounts, start or enable the service, or claim real-host privilege
isolation. Those remain issues #6 and #7.

The external policy archive and authority store are append-only by administrative and broker contract,
not physically immutable. Root is trusted. A coherent root rollback of both `/etc` and `/var/lib`
cannot be detected by this design and is not claimed.

## Fixed layout and ownership

Production paths are fixed:

| Path | Owner | Mode | Purpose |
| --- | --- | --- | --- |
| `/usr/libexec/operator-control-plane` | root:root | `0755` | broker and admin code |
| `/etc/operator-control-plane` | root:root | `0700` | manifest, active index, policy archive |
| `/var/lib/operator-control-plane` | broker UID:GID | `0700` | SQLite store and evidence CAS |
| `/run/operator-control-plane` | broker UID:client GID | `2750` | broker socket parent |
| systemd unit and tmpfiles files | root:root | `0644` | service definition and runtime directory |
| `/etc/operator-control-plane-registry.json` | root:root | `0644` | client-side repository enrollment registry (issue #7) |

`/etc/operator-control-plane-registry.json` is a **sibling** of `/etc/operator-control-plane/`, not a
child of it — tearing down and recreating `/etc/operator-control-plane` does not clear it. A stale entry
from a previous store instance produces `enrollment_conflict` on the next enroll attempt even though the
store itself is fresh; remove it explicitly when deliberately starting over.

Root-owned ancestors are required through the install, configuration, unit, and tmpfiles paths. The
allowed owner changes only at the exact state and runtime roots. Traversal uses directory descriptors
and `O_NOFOLLOW`; file checks bind pre-open metadata to the opened inode and reject symlinks, extra
hard links, wrong owner/group/mode, writable ancestors, and inode substitution.

The production interpreter is the absolute `/usr/bin/python3`, checked as a root-owned,
non-group/other-writable executable. Python runs in isolated mode. The administrative wrapper
self-checks its interpreter and sibling code path, changes cwd to `/`, clears its inherited
environment, and imports only from its installed directory. Therefore initial installation must be run
from a root-owned staged release, never directly through `sudo ./operator-admin` in a user checkout.

## Policy schema

Every generation is strict canonical JSON with exactly:

```json
{
  "policy_schema_version": 1,
  "policy_id": "stable-policy-id",
  "ledger_id": "stable-ledger-id",
  "policy_generation": 1,
  "previous_policy_sha256": null,
  "mode": "enforced",
  "uid_names": {"1001": "builder", "1002": "verifier"},
  "roles": {"1001": ["builder"], "1002": ["verifier"]}
}
```

Unknown fields fail. Generation one requires a null predecessor. Later generations increment by
exactly one and name the prior generation's canonical SHA-256. Policy and ledger IDs never change.
Only `builder` and `verifier` roles exist, and at least one distinct builder/verifier UID pair is
required. Only `mode: enforced` is accepted.

Account names are audit labels bound to numeric IDs. Production install, rotation, audit, and preflight
re-resolve the broker account, primary group, socket group, and policy UID/name mappings. The service
unit uses numeric IDs so name reuse cannot silently redirect execution.

## Installation and execution boundary

`operator-admin install` performs a read-only preflight before creating anything. It verifies policy
and release inputs, all existing fixed-path ancestors, any existing assets, manifest, archive, and
store. A different manifest, release asset, ledger, policy, or pre-existing foreign store fails before
authority mutation.

Fresh state directories are created by root through opened parent descriptors. SQLite is never opened
by root. After directory creation, a child permanently clears supplementary groups, sets the broker
GID and UID, applies `umask 077`, then performs the first SQLite open and schema creation. Every later
administrative store action validates the database, WAL, SHM, state ancestors, content roots, inode,
link count, owner, and mode before and after the dropped-UID callback.

An exact reinstall is a read-only audit and returns an idempotent result. There is no in-place code
upgrade path in issue #5: changed assets fail closed. A manifest-less retry is accepted only when the
root-owned generation-one archive exists and the store is either empty or contains exactly the matching
single enrollment with no commits. This is the bounded interrupted-install recovery case.

The generated service is not started or enabled. It runs the unchanged broker as the dedicated
unprivileged UID with `/usr/bin/python3 -I`, cwd `/`, a sanitized Python environment, and systemd
hardening. An isolated helper removes only a validated stale socket before broker start, then waits for
the new socket and changes it from `0600` to `0660` only when its owner, group, type, and inode are
stable.

## Rotation, revocation, and transactions

Policy files are fsynced before database activation. Publication uses Linux `renameat2` with
`RENAME_NOREPLACE`; it never uses a hard-link publication window. A validated fixed-name pending file
is recoverable after a crash. An existing exact final file and its parent directory are fsynced again
before retry proceeds.

Enrollment, rotation, and revocation use the broker store's `BEGIN IMMEDIATE` serialization boundary.
Policy selection, policy snapshot/role insertion, and the policy event append happen in that
transaction, so a concurrent broker commit binds either the old or new complete generation. The latest
`ledger_policy_events` row is the sole current authority. Root-owned `active.json` is a derived audit
index and can be reconstructed after an external commit/local-index crash.

Revocation appends a terminal event referencing the current policy. The root-owned revocation intent is
durable before the transaction. A pending intent blocks rotation and can only be completed by an exact
revocation retry. Audit rejects missing, extra, or mismatched intents. Old commits and exact operation
retries retain their event-time policy and receipt; revocation does not relabel history.

## Crash outcomes

- Before pending-file fsync: no database event references the generation.
- After pending-file fsync: retry validates and removes the pending file, then restages.
- After no-replace publication but before directory fsync: retry reopens and fsyncs the exact final
  inode and parent before activation.
- During SQLite commit: SQLite recovery exposes the whole policy event or none.
- After SQLite commit but before `active.json` or manifest: an exact retry reconstructs derived state
  without a second event.
- A foreign, forked, replaced, or partially mismatched state is not repaired automatically.

## Preflight contract

`operator-admin preflight` is read-only and always returns the complete stable check catalog. A
missing, corrupt, or unsafe deployment marks protected assets failed and every blocked observation
unknown rather than aborting the report. The catalog covers administrator identity, broker binding,
agent separation and groups, protected paths, ACL visibility, sudo and cached credentials, polkit,
container groups and sockets, service delegation and overrides, mounts, capabilities/setuid helpers,
process control, credential delegation, and the live broker.

Mode/owner/link/path checks can pass locally. ACLs, alternate service control, cached credentials,
polkit, mount namespaces, capabilities, ptrace, and live-process confinement remain `unknown` until
root runs `operator-admin collect-evidence` and preflight loads a fresh, policy-bound, unforged evidence
file (see `OPERATIONS_RUNBOOK.md`); any missing, stale, mismatched, or tampered evidence file falls back
to the same conservative `unknown` result as before. Any failure or unknown keeps `boundary_ready:
false`.

## Issue #7 deployment-model decision

This host had no `/usr/libexec/operator-control-plane`, `/etc/operator-control-plane`,
`/var/lib/operator-control-plane`, `/run/operator-control-plane`, `operator-broker` account,
`operator-clients` group, or `operator-control-plane-broker.service` unit at the time issue #7 began
(verified by direct inspection, not assumed). Issue #7 therefore installs fresh and does not attempt,
test, or claim an in-place upgrade path on this host.

This is consistent with, not an exception to, the issue #5 boundary above: "there is no in-place code
upgrade path in issue #5" already fails a changed-asset reinstall closed via `installation_conflict`
before any mutation. Issue #7 does not add upgrade support on top of that. If a future host already
carries a differing installation, `operator-admin install` still refuses to mutate over it; resolving
that case is explicitly out of scope until a separate, reviewed migration design exists. Do not treat a
successful fresh install anywhere as evidence that upgrade is supported.

`OPERATIONS_RUNBOOK.md` documents the exact fresh-install sequence used to bring this host into service.

## Repository identity rebind (Issue #10)

`resolve_enrollment` binds an enrolled repository's identity by kernel device/inode, recorded in
`/etc/operator-control-plane-registry.json` at enrollment time. On filesystems that assign per-mount
"anonymous" device numbers to a subvolume (btrfs subvolume mounts, including Fedora's default root+home
layout), that device number can legitimately change across a reboot with no path, content, or inode
change at all. The fail-closed identity check has no exception for this — by design — so the only
sanctioned recovery is `operator-admin repository-rebind --ledger-id <id> --repository-path <path>`
(documented operationally in `OPERATIONS_RUNBOOK.md`).

`ledger.rebind` is a new broker operation, authorized the same way as `ledger.enroll` (root
`SO_PEERCRED` required), but requires the ledger to *already* be enrolled (the inverse precondition of
`ledger.enroll`, which requires it be the store's first commit). It commits as a normal, later
`commit_sequence` entry — a permanent, auditable broker record, not a local-only registry edit — and its
`operation_key` is a deterministic digest of its full content, giving it the same retry-after-partial-
failure idempotency `ledger.enroll` already relies on for the broker-committed/registry-write-pending
crash window.

Before committing, `operator-admin` re-validates the target ledger exactly as `enroll` does (hash-chain
integrity, append-only triggers, YAML/SQLite agreement, safe ownership) and additionally confirms every
anchor recorded at the *prior* enrollment/rebind still resolves to the same
`(record_type, record_id, version) → event_hash` in the ledger now being bound to, i.e. the anchored
history was not rewritten.

**Security model.** None of the above proves physical continuity — a byte-identical clone of the ledger
placed at the named path would pass every check. The checks establish internal consistency (the ledger
isn't corrupt or tampered) and policy continuity (the anchored past wasn't rewritten); they are not, and
are not claimed to be, proof that this is the same physical inode as before. The actual security
authority for this operation is the trusted root administrator explicitly naming `ledger_id` and
`repository_path` on the command line — the same trust boundary every other `operator-admin` mutating
command already relies on. There is no cwd discovery and nothing in this codebase invokes
`rebind_repository` automatically.

## Atomic code upgrade (Issue #11)

An in-place upgrade migrates an installed host's executable and source files (defined in `INSTALLED_SOURCE_ASSETS`) to a new candidate release digest without disturbing the database, policy, active index, or history logs.

The upgrade process is governed by a **journal-first state machine** that coordinates the service lifecycle (starting, stopping, probing) and file activation, with explicit recovery pathways for interruptions (crashes) at any phase.

### Durable States and Authoritative Digests

The upgrade journal (`upgrade.json`) tracks progress through seven durable states. Each state defines the authoritative installed code digest (on disk) and manifest digest (in `install.json`):

1. **`prepared`**
   - **Installed Digest:** `old_digest` (the active deployment prior to upgrade).
   - **Manifest Digest:** `old_digest`.
   - **Transition:** Created when a new candidate release digest is validated. Next, the broker service is stopped.

2. **`service_stopped`**
   - **Installed Digest:** `old_digest` (before file activation) or `new_digest` (after file activation).
   - **Manifest Digest:** `old_digest`.
   - **Transition:** The candidate files are activated to `install_root`. If file copying fails (e.g., disk full), the state remains `service_stopped`.

3. **`activated`**
   - **Installed Digest:** `new_digest`.
   - **Manifest Digest:** `old_digest`.
   - **Transition:** The broker service is started, and a candidate-aware health probe executes. If it fails, the service is stopped and the state transitions to `rolling_back`.

4. **`rolling_back`**
   - **Installed Digest:** `new_digest` (before file restoration) or `old_digest` (after restoration completes).
   - **Manifest Digest:** `old_digest`.
   - **Transition:** Rebuilt or recovered when rollback is initiated. Original files are restored, the manifest is restored, and the broker service is started to check rollback health.

5. **`health_verified`**
   - **Installed Digest:** `new_digest`.
   - **Manifest Digest:** `old_digest` (before write) or `new_digest` (after write).
   - **Transition:** The health probe succeeded. The active manifest (`install.json`) is overwritten with candidate metadata.

6. **`rolled_back` (Terminal)**
   - **Installed Digest:** `old_digest`.
   - **Manifest Digest:** `old_digest`.
   - **Transition:** Reached after successfully restoring the old release assets and manifest, and verifying rollback health.

7. **`completed` (Terminal)**
   - **Installed Digest:** `new_digest`.
   - **Manifest Digest:** `new_digest`.
   - **Transition:** Reached after successfully writing the new manifest.

### Crash Recovery and Rollback Guarantees

- **Journal-first loading:** Before executing any upgrade action, `upgrade_deployment` inspects the journal. If an upgrade is interrupted midway, the process resumes from the last recorded state.
- **Unambiguous interrupted rollback:** If a crash occurs during rollback (state `rolling_back` with file restoration underway), the next invocation detects the `rolling_back` state, completes the restoration of all original assets before starting the service or running health checks, and ensures the system reaches `rolled_back` cleanly.
- **Registry and database independence:** The upgrade operates independently of the ledger registration file and does not modify the SQLite store schema or policy files.
- **Competing upgrades:** An upgrade is rejected with `upgrade_in_progress` if a different candidate digest's journal is active.

## Explicit non-goals

- Modifying `authority_broker.py`, `operator-broker`, or the repo-local `operator`
- Repo CLI enrollment, projection, or session status integration
- Migrating existing ledgers or real-UID dogfood
- Provisioning users, groups, sudoers, polkit, systemd enablement, or containers
- Cryptographic signing, remote policy, semantic evidence judgment, or command execution
- Detecting a trusted root that coherently rewrites both policy and broker state
