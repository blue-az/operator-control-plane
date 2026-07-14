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
issue #7 supplies real-host evidence. Any failure or unknown keeps `boundary_ready: false`.

## Explicit non-goals

- Modifying `authority_broker.py`, `operator-broker`, or the repo-local `operator`
- Repo CLI enrollment, projection, or session status integration
- Migrating existing ledgers or real-UID dogfood
- Provisioning users, groups, sudoers, polkit, systemd enablement, or containers
- Cryptographic signing, remote policy, semantic evidence judgment, or command execution
- Detecting a trusted root that coherently rewrites both policy and broker state
