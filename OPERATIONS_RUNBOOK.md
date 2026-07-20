# Operations Runbook

## Status and scope

This is the issue #7 operational runbook: the exact commands to bring a host from nothing to an
enrolled, evidenced P3 authority boundary, and to operate it afterward. It assumes
`AUTHORITY_POLICY_SPEC.md` (installation/policy contract) and `AUTHORITY_BROKER_SPEC.md` (broker
protocol) as background and does not repeat their guarantees.

**Deployment model: fresh install only.** This runbook installs onto a host with no prior
`/usr/libexec/operator-control-plane`, `/etc/operator-control-plane`, `/var/lib/operator-control-plane`,
`/run/operator-control-plane`, `operator-broker` account, `operator-clients` group, or
`operator-control-plane-broker.service` unit. In-place upgrade of an existing, differing installation is
not implemented and is not attempted here; `operator-admin install` already refuses to mutate over a
differing deployment (`installation_conflict`), and that refusal is the enforced boundary, not a gap to
work around. See "Issue #7 deployment-model decision" in `AUTHORITY_POLICY_SPEC.md`.

Every command below that touches `/etc`, `/usr/libexec`, `/var/lib`, `/run`, or systemd requires real
root (`sudo` or a root shell). `operator-admin` enforces real+effective UID 0 and refuses to run its
privileged code path from a non-root-owned or group/other-writable location — that is why staging is
its own step below, not a detail to skip.

## 1. Provision accounts (administrator-run, not by this tooling)

Issue #7 requires builder and verifier environments to have **no usable path** to root or the broker
UID. The application must not create these accounts itself — `validate_host_accounts` only ever reads
existing accounts (`pwd.getpwuid`), it never provisions them. An administrator runs this section by
hand, on the real host, before anything else:

```bash
sudo groupadd --system operator-broker
sudo groupadd --system operator-clients
sudo useradd  --system --no-create-home --shell /usr/sbin/nologin \
    --gid operator-broker --groups operator-clients operator-broker

# One dedicated, constrained account per privilege domain. Each gets its own
# private primary group and joins operator-clients (socket access) only.
sudo useradd --system --no-create-home --shell /usr/sbin/nologin \
    --groups operator-clients operator-builder
sudo useradd --system --no-create-home --shell /usr/sbin/nologin \
    --groups operator-clients operator-verifier
```

Record the resulting UIDs — the policy file in step 3 references them by number:

```bash
id -u operator-broker
id -u operator-builder
id -u operator-verifier
```

Before continuing, confirm none of `operator-broker`, `operator-builder`, `operator-verifier` has:

- an entry in `/etc/sudoers` or `/etc/sudoers.d/*` (`sudo -n -l -U <name>` as root should print "User
  <name> is not allowed to run sudo on <host>." and exit 0 — that exit code is normal for this query
  form and does not itself mean the account has access; only the message text does);
- membership in `wheel`, `sudo`, `adm`, `docker`, `podman`, `lxd`, `incus-admin`, or `libvirt`
  (`id <name>`);
- a login shell other than `nologin`/`false`.

**Freshly created accounts are not automatically clean.** A real dogfood run on a host with pre-existing
host-specific sudoers rules found that `sudo grep -rl ALL /etc/sudoers.d/` turned up rules written as
`ALL ALL=NOPASSWD: /usr/local/bin/<tool>` — a blanket grant to *every* account on the host, including
ones that didn't exist yet when the rule was written. Run `sudo grep -rn '^ALL ' /etc/sudoers
/etc/sudoers.d/*` and rewrite any match found there to name the specific human account instead of `ALL`,
validating with `sudo visudo -cf <file>` before installing it.

This is a sanity check, not the authoritative check — `operator-admin collect-evidence` (step 5) and
`operator-admin preflight` (step 6) are authoritative and must be rerun after any account change.

## 2. Stage a root-owned release

`operator-admin` refuses to execute from `~/operator-control-plane` as root — every path component
from `/` to the running script must be root-owned and non-group/other-writable. Stage a pinned commit
into a root-owned directory first:

```bash
REV=$(git -C ~/operator-control-plane rev-parse HEAD)   # pin and record this commit
sudo install -d -m 0700 -o root -g root "/root/operator-control-plane-release/$REV"
for f in authority_broker.py authority_admin.py operator-admin socket_permission_helper.py dogfood_runner.py; do
  sudo install -m 0600 -o root -g root \
      "$HOME/operator-control-plane/$f" \
      "/root/operator-control-plane-release/$REV/$f"
done
sudo chmod 0700 "/root/operator-control-plane-release/$REV/operator-admin"
```

Stage the generation-1 policy into its own root-owned directory (policy provenance is
administrator-authored, not sourced from git):

```bash
sudo install -d -m 0700 -o root -g root /root/operator-control-plane-policy
sudoedit /root/operator-control-plane-policy/generation-1.json
sudo chmod 0600 /root/operator-control-plane-policy/generation-1.json
```

`generation-1.json` (fill in the UIDs from step 1):

```json
{
  "policy_schema_version": 1,
  "policy_id": "<stable-policy-id>",
  "ledger_id": "<stable-ledger-id>",
  "policy_generation": 1,
  "previous_policy_sha256": null,
  "mode": "enforced",
  "uid_names": {"<builder-uid>": "operator-builder", "<verifier-uid>": "operator-verifier"},
  "roles": {"<builder-uid>": ["builder"], "<verifier-uid>": ["verifier"]}
}
```

## 3. Install

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" install \
    --policy /root/operator-control-plane-policy/generation-1.json \
    --source-dir "/root/operator-control-plane-release/$REV" \
    --broker-user operator-broker \
    --socket-group operator-clients
```

This is a read-only preflight followed by fixed-path creation; a repeated identical invocation is an
idempotent no-op audit. A differing invocation (changed assets, changed policy) fails closed with
`installation_conflict` rather than mutating anything — this is the enforced no-upgrade boundary,
exercised for real the first time you accidentally rerun install after editing a staged file.

The install writes `layout.unit_path` and `layout.tmpfiles_path` but does **not** start or enable the
service.

## 4. Enable and start the broker

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now operator-control-plane-broker.service
sudo systemctl status operator-control-plane-broker.service --no-pager
sudo journalctl -u operator-control-plane-broker.service -n 50 --no-pager
```

Confirm the socket exists with the expected ownership before proceeding:

```bash
sudo ls -la /run/operator-control-plane/broker.sock
```

## 5. Collect privilege evidence

Root gathers deterministic, re-runnable evidence for the checks that cannot be proven from filesystem
metadata alone (sudo, polkit, containers, service delegation, capabilities, process control):

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" collect-evidence
```

This writes `/etc/operator-control-plane/privilege-evidence.json`, bound to the currently active
policy's `ledger_id`/`policy_id`/`policy_generation`/`policy_sha256` and stamped with a collection
timestamp. It is valid for `EVIDENCE_MAX_AGE_SECONDS` (24h) and stops being trusted the moment the
active policy rotates — rerun this command after every `rotate` (step 10) before re-running preflight.

## 6. Preflight — stop unless `boundary_ready: true`

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" preflight
```

Read every entry in `checks`. `boundary_ready` is `true` only when all twenty checks are `pass` or
`not_applicable`. Do not proceed to enrollment or dogfood if it is not — go back and fix whatever check
failed (usually: an account in a risky group, a cached sudo credential, or evidence older than 24h) and
rerun both `collect-evidence` and `preflight`. `enroll` (step 7) already enforces this refusal in code
(`privilege_precondition_unproven`); this step exists so you see *why* before enrollment tells you.

## 7. Enroll a repository

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" enroll \
    --repository-path /path/to/existing/ledger/repo
```

This is the migration step: it validates the repository's local `.operator` ledger (hash chain,
append-only triggers, YAML/SQLite agreement), then commits `ledger.enroll` as the authority store's
first event, atomically binding repository inode identity, legacy anchors, the active policy digest,
and the first broker sequence. Retrying the identical enrollment is idempotent and returns the original
receipt rather than creating a duplicate.

**`REGISTRY_PATH` lives outside the config root.** The client-side enrollment registry is
`/etc/operator-control-plane-registry.json` — a fixed path, but a *sibling* of `/etc/operator-control-plane/`,
not inside it. Tearing down and recreating the store (`rm -rf /etc/operator-control-plane
/var/lib/operator-control-plane ...`) does **not** clear it. A stale registry entry from a previous store
instance causes `enrollment_conflict` on the next enroll attempt even though the store itself is fresh —
hit live in this form during dogfood. If you are deliberately starting over (not just retrying a failed
attempt), remove it explicitly: `sudo rm -f /etc/operator-control-plane-registry.json`.

## 8. Open the repository up for builder/verifier writes

`enroll` (step 7) requires the repository and its `.operator` tree to be **owner-only** — not
group/other writable — as proof no one else could have tampered with it before migration
(`unsafe_enrollment: operator path is group/other writable` if this isn't true). Do this *before*
enrolling, not after: reopening permissions and then re-enrolling on top of stale state is exactly the
kind of sequencing mistake that produces `enrollment_conflict` against a leftover registry entry (see
the `REGISTRY_PATH` note above).

Only once `enroll` has succeeded, open the tree up for the builder and verifier accounts to write local
YAML/journal projections. Plain `chmod g+w` is not enough — it only fixes files that already exist;
directories created *after* enrollment (e.g. `.operator/evidence/<new-task>/`) inherit their creating
process's umask, not the parent's write bit, so a second account can still hit `Permission denied`
creating a new subdirectory even though the parent looks group-writable. Use a POSIX default ACL so new
entries inherit correctly regardless of umask:

```bash
sudo chgrp -R operator-clients /path/to/enrolled/repo/.operator
sudo chmod -R g+w /path/to/enrolled/repo/.operator
sudo find /path/to/enrolled/repo/.operator -type d -exec chmod g+s {} \;
sudo setfacl -d -m group:operator-clients:rwx /path/to/enrolled/repo/.operator
sudo setfacl -R -m group:operator-clients:rwx /path/to/enrolled/repo/.operator
```

This is host filesystem configuration, not something `operator-admin`/`operator` do automatically —
consistent with the explicit non-goal of not provisioning accounts, groups, or ACLs on the application's
behalf.

## 9. Ordinary operation

From inside the enrolled repository, as the **builder** or **verifier** account (not root, not
`blueaz`):

```bash
operator task-transition --task <task-id> --status verified --claim <claim-id>
operator task-transition --task <task-id> --status complete
operator authority-reconcile
```

`task-transition` is the enrolled, broker-authenticated path to `verified`/`complete` — Issue #7
requires that ordinary `operator session-end --status verified|complete` now fails closed for enrolled
repositories and that only this dedicated transition reaches those states. `authority-reconcile`
replays the broker's projection into the local `.operator` YAML/SQLite state; run it after any broker
interaction that reports `committed, projection pending`.

## 10. Outage diagnosis

Symptoms: `operator authority-reconcile` or `task-transition` print `Error: cannot determine expected
state: broker unreachable: ...` (compile_expected failed to reach the broker while gathering CAS
preconditions) or `Error: Broker dispatch failed: ...` (the broker was reachable long enough to compute
preconditions but not to accept the commit). Both fail closed with a nonzero exit and write no local
YAML claiming success; verified live by stopping the broker mid-session and confirming `task-show`
reported no change.

```bash
sudo systemctl status operator-control-plane-broker.service --no-pager
sudo journalctl -u operator-control-plane-broker.service -n 100 --no-pager
sudo ls -la /run/operator-control-plane/broker.sock
sudo "/root/operator-control-plane-release/$REV/operator-admin" audit
```

There is no local fallback by design — do not treat a reachable `.operator` YAML file as a substitute
for the broker being up. Restart the unit (`sudo systemctl restart ...`) and re-run `audit` before
resuming builder/verifier work. Retrying the exact same failed command after the broker recovers is
safe and produces exactly one commit, not a duplicate — verified live (commit count went 5→6, event
count 8→10, matching one `claim.create`'s two-record mutation, on a retry after a real outage).

## 11. Rotation

```bash
sudoedit /root/operator-control-plane-policy/generation-2.json   # generation = 2, previous_policy_sha256 = generation-1's sha256
sudo chmod 0600 /root/operator-control-plane-policy/generation-2.json
sudo "/root/operator-control-plane-release/$REV/operator-admin" rotate \
    --policy /root/operator-control-plane-policy/generation-2.json
sudo "/root/operator-control-plane-release/$REV/operator-admin" collect-evidence  # evidence is policy-bound; re-collect
sudo "/root/operator-control-plane-release/$REV/operator-admin" preflight
```

Rotation records a new generation and digest in the same `BEGIN IMMEDIATE` transaction as the policy
event; it never rewrites event-time history — verified live by querying `authority_commits` directly
after a real rotation: all five pre-rotation commits still carried the generation-1 policy digest, only
the new `ledger_policy_events` row referenced generation 2. Because privilege evidence is bound to
`policy_generation`/`policy_sha256`, every rotation silently reverts the ten evidence-backed preflight
checks to `unknown` until evidence is re-collected — this is intentional, not a bug to route around.
Generation persists across a broker restart (`systemctl restart` then `audit`), verified live.

## 12. Revocation

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" revoke \
    --ledger-id <ledger-id> \
    --expected-policy-sha256 <currently-active-generation-sha256>
```

Revocation is terminal for that ledger: `audit` will show `state: revoked`, and any subsequent `rotate`
fails closed with `policy_revoked`. There is no un-revoke command.

## 13. Rollback-rejection (expected failures, not incidents)

These are the fail-closed behaviors the design guarantees. `installation_conflict`,
`policy_history_fork`, and `policy_digest_mismatch` were each reproduced live on a real host, with
`sha256sum` of the authority store and every `/etc/operator-control-plane/*` config file confirmed
byte-identical before and after each rejected attempt — don't just cite this table, reproduce at least
one the same way for issue-linked evidence:

| Attempted action | Failure mode |
| --- | --- |
| `install` with generation ≠ 1 | `invalid_policy_chain` |
| `install` with changed assets/policy over an existing deployment | `installation_conflict` |
| `rotate` with a non-contiguous generation or wrong `previous_policy_sha256` | `policy_history_fork` |
| `rotate` after `revoke` | `policy_revoked` |
| `revoke` with a stale/wrong `--expected-policy-sha256` | `policy_digest_mismatch` (the digest must still be exactly 64 lowercase hex characters — a malformed length fails earlier with `invalid_policy` instead, which is a real but less interesting rejection) |
| `enroll` a ledger that already has broker commits (not the store's first commit) | `enrollment_rejected` |
| `enroll` the same repository path again with a differing registration | `enrollment_conflict` (also fires if `/etc/operator-control-plane-registry.json` — see the note in step 7 — holds a stale entry from a wiped-and-recreated store; delete it if you are deliberately starting over, not just retrying) |
| local `.operator` ledger fails hash-chain/append-only/YAML-agreement validation | `unsafe_enrollment` |
| tampered/stale/foreign-policy `privilege-evidence.json` | silently degrades to `unknown`, never to `pass` |

## 14. Crash / recovery

- Interrupted `install`/`rotate`/`revoke` before the pending policy file is fsynced: no database event
  references the generation; rerun the same command.
- Interrupted after the pending file is fsynced but before publication: rerun the same command; it
  validates and republishes the pending file.
- Interrupted after SQLite commit but before `active.json`/manifest: rerun the same command; it
  reconstructs derived state without creating a second event.
- Lost response after `enroll` or a broker commit: retry the same client operation. Enrollment and
  ordinary commits are idempotent on `operation_key`/receipt, not on wall-clock retry count.
- A foreign, forked, or partially mismatched state is never auto-repaired — `audit` and `preflight` will
  report it, and it requires manual, evidenced investigation, not a scripted fix.

## 15. Recover an enrolled ledger from device-identity drift (`repository-rebind`)

Symptom: every ordinary command against a previously-working enrolled repository starts failing with
`Error: enrolled ledger identity has changed`, even though nothing about the repository was moved,
recreated, or tampered with. `resolve_enrollment` binds identity by kernel device/inode, not by path
string; on filesystems that assign per-mount "anonymous" device numbers to a subvolume (btrfs subvolume
mounts, notably including Fedora's default root+home layout), that device number can change across a
reboot even though the subvolume's own inodes are stable. This is expected fail-closed behavior, not a
bug — see [Issue #10](https://github.com/blue-az/operator-control-plane/issues/10) for the full forensic
writeup that motivated this command.

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" repository-rebind \
    --ledger-id <ledger-id> \
    --repository-path /path/to/enrolled/repo
```

Both flags are explicit and required — there is no cwd discovery, so this cannot be triggered by
accident from an arbitrary directory. The command:

> **Upgrade compatibility boundary:** the previous-proof fields are mandatory in the rebind request.
> Deploy the matching broker and `operator-admin` together through the Issue #11 journaled `upgrade`
> command, which stops the broker while the full asset set is activated. Do not copy either file into
> a live installation independently. An older admin client is rejected fail-closed as
> `invalid_request` by a broker that requires the new request shape.

1. Re-validates the local ledger using a rebind-specific operational validator (`pin_operational_ledger`),
   which accepts the group-writable layout of an active deployment (group-writable directories and files
   within the socket client group, and SQLite WAL sidecars) while locking the database with `BEGIN IMMEDIATE`
   and holding the pinned file descriptors and transactions through the entire broker-commit and registry-write sequence.
2. Confirms every anchor recorded at the *prior* enrollment/rebind still resolves to the same
   `(record_type, record_id, version) → event_hash` in the ledger now being bound to — i.e. the
   previously-anchored history was not rewritten. Fails closed with `rebind_history_diverged` if not.
3. Sends the broker separate previous and new proofs. The previous proof is
   `previous_identity` + `previous_anchor_records` + `previous_legacy_anchor_sha256`, claimed from the
   registry; the new proof is `repository_identity` + the current-head `anchor_records` +
   `legacy_anchor_sha256`, derived from the pinned ledger. The broker treats its latest `ledger.enroll`
   or `ledger.rebind` commit as authoritative and requires the claimed previous proof to match it
   exactly. Registry-only identity or anchor edits therefore fail as `rebind_continuity_mismatch`
   before any commit. Current heads may advance normally from a previously anchored v1 to v2.
4. Commits `ledger.rebind` as a first-class, permanently retained broker commit visible in `audit`,
   not a silent local file edit. Requires the real root `SO_PEERCRED` identity, same as `enroll`.
5. Atomically rewrites the registry binding for this ledger, preserving
   `first_broker_sequence`/`enrollment_receipt_hash` from the *original* enrollment — a rebind is a
   recovery event layered on top of the original enrollment, not a re-enrollment.

**What this does and does not prove.** Steps 1–3 establish internal consistency (the ledger content
isn't corrupt or tampered) and policy continuity (the anchored past wasn't rewritten). They cannot and do
not prove physical continuity — a byte-identical clone of the ledger placed at the given path would pass
every one of them. The actual security authority for this operation is the trusted root administrator
explicitly naming `--ledger-id` and `--repository-path`; do not run this against a path you have not
personally verified is the genuine repository, and do not automate its invocation.

Like `enroll`, `repository-rebind` is idempotent on a deterministic `operation_key` derived from the full
operation content: if the broker commits but the subsequent registry write fails (`registry_publication_pending`,
with the receipt hash included in the error), re-running the identical command reproduces the identical
operation and hits the broker's replay path instead of minting a second rebind commit.

The rebind commit itself produces no local record mutations (nothing changed about the ledger's task/
claim/evidence history), but it does advance the broker's commit sequence, so run
`operator authority-reconcile` once afterward before `doctor` reports `status: current` again — same as
after any other broker-side event the local client hasn't caught up on yet.

Also works for an administrator-approved *move* of an enrolled repository to a genuinely different path,
not just in-place recovery — the command doesn't distinguish the two cases; it always re-validates
whatever is at the given path from scratch.

## Evidence to post to issue #7

For every command above actually run on this host: the exact command line, its JSON output (or
`systemctl`/`journalctl` excerpt), and the timestamp. `boundary_ready: true` from a *fresh*
`collect-evidence` + `preflight` pair is required before any dogfood claim; a stale or hand-edited
preflight report does not count as evidence.
