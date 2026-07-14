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

- an entry in `/etc/sudoers` or `/etc/sudoers.d/*` (`sudo -l -U <name>` as root should report "not
  allowed to run sudo");
- membership in `wheel`, `sudo`, `adm`, `docker`, `podman`, `lxd`, `incus-admin`, or `libvirt`
  (`id <name>`);
- a login shell other than `nologin`/`false`.

This is a sanity check, not the authoritative check — `operator-admin collect-evidence` (step 5) and
`operator-admin preflight` (step 6) are authoritative and must be rerun after any account change.

## 2. Stage a root-owned release

`operator-admin` refuses to execute from `~/operator-control-plane` as root — every path component
from `/` to the running script must be root-owned and non-group/other-writable. Stage a pinned commit
into a root-owned directory first:

```bash
REV=$(git -C ~/operator-control-plane rev-parse HEAD)   # pin and record this commit
sudo install -d -m 0700 -o root -g root "/root/operator-control-plane-release/$REV"
for f in authority_broker.py authority_admin.py operator-admin socket_permission_helper.py; do
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

## 8. Ordinary operation

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

## 9. Outage diagnosis

Symptoms: `operator authority-reconcile` or `task-transition` raise a raw connection error
(`ConnectionRefusedError`/`FileNotFoundError` surfaced from `authority_broker.send_request`) instead of
a `BrokerError`.

```bash
sudo systemctl status operator-control-plane-broker.service --no-pager
sudo journalctl -u operator-control-plane-broker.service -n 100 --no-pager
sudo ls -la /run/operator-control-plane/broker.sock
sudo "/root/operator-control-plane-release/$REV/operator-admin" audit
```

There is no local fallback by design — do not treat a reachable `.operator` YAML file as a substitute
for the broker being up. Restart the unit (`sudo systemctl restart ...`) and re-run `audit` before
resuming builder/verifier work.

## 10. Rotation

```bash
sudoedit /root/operator-control-plane-policy/generation-2.json   # generation = 2, previous_policy_sha256 = generation-1's sha256
sudo chmod 0600 /root/operator-control-plane-policy/generation-2.json
sudo "/root/operator-control-plane-release/$REV/operator-admin" rotate \
    --policy /root/operator-control-plane-policy/generation-2.json
sudo "/root/operator-control-plane-release/$REV/operator-admin" collect-evidence  # evidence is policy-bound; re-collect
sudo "/root/operator-control-plane-release/$REV/operator-admin" preflight
```

Rotation records a new generation and digest in the same `BEGIN IMMEDIATE` transaction as the policy
event; it never rewrites event-time history. Because privilege evidence is bound to
`policy_generation`/`policy_sha256`, every rotation silently reverts the ten evidence-backed preflight
checks to `unknown` until evidence is re-collected — this is intentional, not a bug to route around.

## 11. Revocation

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" revoke \
    --ledger-id <ledger-id> \
    --expected-policy-sha256 <currently-active-generation-sha256>
```

Revocation is terminal for that ledger: `audit` will show `state: revoked`, and any subsequent `rotate`
fails closed with `policy_revoked`. There is no un-revoke command.

## 12. Rollback-rejection (expected failures, not incidents)

These are the fail-closed behaviors the design guarantees — reproduce at least one for the issue-linked
dogfood evidence in step 7 of the plan, don't just cite this table:

| Attempted action | Failure mode |
| --- | --- |
| `install` with generation ≠ 1 | `invalid_policy_chain` |
| `install` with changed assets/policy over an existing deployment | `installation_conflict` |
| `rotate` with a non-contiguous generation or wrong `previous_policy_sha256` | `policy_history_fork` |
| `rotate` after `revoke` | `policy_revoked` |
| `revoke` with a stale/wrong `--expected-policy-sha256` | `policy_digest_mismatch` |
| `enroll` a ledger that already has broker commits (not the store's first commit) | `enrollment_rejected` |
| `enroll` the same repository path again with a differing registration | `enrollment_conflict` |
| local `.operator` ledger fails hash-chain/append-only/YAML-agreement validation | `unsafe_enrollment` |
| tampered/stale/foreign-policy `privilege-evidence.json` | silently degrades to `unknown`, never to `pass` |

## 13. Crash / recovery

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

## Evidence to post to issue #7

For every command above actually run on this host: the exact command line, its JSON output (or
`systemctl`/`journalctl` excerpt), and the timestamp. `boundary_ready: true` from a *fresh*
`collect-evidence` + `preflight` pair is required before any dogfood claim; a stale or hand-edited
preflight report does not count as evidence.
