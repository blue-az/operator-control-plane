# Issue #8 AC9 — Track B live run (desktop, 2026-07-20)

**Campaign:** `docs/DOGFOOD_AC9_CAMPAIGN.md`, Track B ("Enrollment + revoke"), plus the
optional rotation step
**Result: PASS.** `enrollment`, `rotation`, and terminal `revocation_checks` all
demonstrated live against the same disposable ledger, on the same desktop install
Track A used (redeployed once mid-campaign — see "Redeploy" below).

---

## Redeploy between Track A and Track B

A real bug (`acknowledge_recovered` — see below) was found and fixed mid-campaign,
requiring a code change to `dogfood_runner.py`. Rather than exercise
`operator-admin upgrade`'s digest-named release-directory mechanism for the first
time live under time pressure, the disposable install was torn down completely
(service stopped/disabled, `/etc/operator-control-plane`,
`/var/lib/operator-control-plane`, `/var/lib/operator-control-plane-admin`,
`/usr/libexec/operator-control-plane` removed) and reinstalled fresh from the
fixed commit. System accounts (`operator-broker`/`-builder`/`-verifier`) and the
throwaway ledger repo (`/tmp/operator-dogfood-ac9-ledger`) were untouched by this
and did not need to be redone. Track A's own results and evidence
(`docs/DOGFOOD_AC9_TRACK_A_RUN.md`) remain valid and unaffected — that run never
exercised `acknowledge_recovered`, so the bug fixed here never had a chance to
affect it.

## Bug found and fixed mid-campaign: `acknowledge_recovered`

`execute_run`'s loop reset `acknowledge_recovered = False` unconditionally after
*every* phase it processed, including phases already `completed` that take the
pure idempotent-replay path inside `execute_phase` without ever consulting the
flag. In this run's own enrollment plan, phase 1
(`installation_verification`) succeeded first; processing it silently cleared
the flag before phase 2 (`enrollment`, the phase that actually needed
acknowledgement after an earlier real failure) was ever reached — so
`dogfood-resume --run-id ... --approve-phase 2 --acknowledge-recovered` was
rejected with `failed_phase_requires_acknowledgement` even though the flag was
correctly passed. Fixed in `operator-control-plane@8edb17f` (only clear the flag
once it reaches a phase that wasn't already completed); a new regression test
(`test_acknowledge_recovered_survives_past_an_earlier_completed_phase`) was
verified to fail with the identical error message on the unfixed code and pass
with the fix, before this run continued on the corrected, redeployed install.

This is the second real bug this AC9 campaign has found that 294+ passing unit
tests did not — both classes of gap (a missing install-asset entry, a
control-flow ordering bug only visible across multiple phases in one resume
call) are exactly what a live, multi-phase, multi-session run is positioned to
catch that isolated unit tests structurally cannot.

## What triggered `acknowledge_recovered` live: `process.control`

The *first* enrollment attempt (before the redeploy, and again immediately
after it) failed closed with `privilege_precondition_unproven`, naming
`process.control` (post-redeploy: all ten evidence-backed checks, since a fresh
install has no `privilege-evidence.json` yet) as unresolved. `process.control`
reads `/proc/sys/kernel/yama/ptrace_scope`, requiring `>= 1` (restricted); this
Fedora 43 desktop ships it at `0` (permissive) via
`/usr/lib/systemd/../sysctl.d/10-default-yama-scope.conf`. Per the issue's own
security boundaries, host-hardening decisions like this are explicitly **not**
something the runner automates — this was raised to Erik, approved explicitly,
and applied by hand:

```
sudo sysctl -w kernel.yama.ptrace_scope=1
echo 'kernel.yama.ptrace_scope = 1' | sudo tee /etc/sysctl.d/60-yama-ptrace-restrict.conf
sudo sysctl --system
```

(`60-` sorts after the vendor's `10-default-yama-scope.conf`, so the override
wins on every boot.) `sudo operator-admin collect-evidence` was then re-run to
populate fresh evidence before enrollment was retried.

---

## Log — enrollment

```
Ledger id: dogfood-desktop-ac9
Policy id / gen / sha256 (at enrollment): policy-dogfood-desktop-ac9 / 1 / 00c62be1a73c2e2089b8baffb68f21d656f287e96bd6de968c3d11a2e68d8fe0
Installed release digest (post-redeploy): 871ed91b63171ca3bc1c7bb133f51bc55b7186529a48d4377b36e0ea61baf320
Plan digest: becce6e27b515b4ccfeff76923fa5040a2cae0748ef5d8e36e540d3224f38554
Run id: 9ae95c2fe04944e19f13594497f5d54d
Throwaway ledger repo: /tmp/operator-dogfood-ac9-ledger (operator init, WAL/SHM
  sidecars checkpointed away via PRAGMA journal_mode=DELETE before enrollment --
  validate_local_ledger fails closed on an active SQLite sidecar)
First attempt: privilege_precondition_unproven (process.control, then all ten
  evidence checks post-redeploy) -- recorded as a failed checkpoint
Second attempt: after ptrace_scope fix + collect-evidence, blocked again on the
  acknowledge_recovered bug (see above)
Final attempt: dogfood-resume --approve-phase 2 --acknowledge-recovered -- completed
Evidence tarball: /tmp/ac9-track-b-9ae95c2fe04944e19f13594497f5d54d.tgz
```

Registry confirmation (`/etc/operator-control-plane-registry.json`):
real device/inode identity recorded for `/tmp/operator-dogfood-ac9-ledger`,
`first_broker_sequence: 1`, a real `enrollment_receipt_hash`, policy binding
generation 1.

## Log — rotation (optional step, also completed)

```
Plan digest: a441826c92c91cdfac2bb693c8d0200f607ac98463418cc1fa20912f5468e92c
Run id: 0e7346362ffda551ca284b42a53f8111
New policy: /root/operator-control-plane-policy/generation-2.json (generation 2,
  previous_policy_sha256 = generation 1's sha256)
Result: completed in one pass, no failures
Post-rotation audit: policy_generation: 2, policy_sha256:
  2a66e9e97b002225c6f38d3bd32d2368a1510f2d598844cfc8f49e1fcedfde90,
  policy_events: 2, commits: 1 (the enrollment commit survived the rotation intact)
Evidence tarball: /tmp/ac9-track-b-0e7346362ffda551ca284b42a53f8111.tgz
```

## Log — revocation_checks (terminal)

```
Plan digest: 371ca9fd807601afa826afadaed8f24671301c3dca7226f228f4a9e013b4e5a9
Run id: 2097bec7d3566788d58b5ffe04bd50c9
expected_policy_sha256: 2a66e9e97b002225c6f38d3bd32d2368a1510f2d598844cfc8f49e1fcedfde90 (generation 2's, current at time of revocation)
Result: completed in one pass, no failures
Post-revocation audit: state: revoked, policy_events: 3, policy_generations: 2
Evidence tarball: /tmp/ac9-track-b-2097bec7d3566788d58b5ffe04bd50c9.tgz
```

`ledger_id` was deliberately **not** a `revocation_checks` phase argument (see
`dogfood_runner.phase_revocation_checks`'s own design note) -- it was derived
fresh from a live `audit_deployment` call each time, not trusted from the plan.

---

## What was proven

- **Enrollment**: a real, root-privileged `enroll_repository` call against a
  genuinely `operator init`-created local ledger, gated correctly by both
  policy-state and `privilege_preflight`/`boundary_ready` (which failed closed,
  for real, on a real unmet host-hardening precondition before ever reaching
  the broker).
- **Rotation** (optional): a real policy generation bump, verified not to
  disturb prior commit history.
- **Revocation** (terminal): a real, irreversible policy revocation, verified
  terminal via `audit`.
- **Recovery from a genuine failure requiring acknowledgement**: the
  `privilege_precondition_unproven` failure and the subsequent
  `--acknowledge-recovered` retry were both real, unplanned, and are exactly
  the AC5 "failed gate, explicit administrator decision to retry" property
  working under real conditions -- not simulated in a test fixture.

## What this does not prove

Per the campaign doc, Track C (`service_lifecycle`/`outage_recovery` against
the real, production unit name via real `systemctl`) was not attempted --
still deliberately skipped as the highest-host-risk, lowest-necessary-value
track, matching the campaign doc's own recommendation ("Prefer skip until
Track A/B are green"). Per the issue's stop condition, this run does not
recommend the runner for a production ledger and does not claim the P3
authority boundary is reduced.

## Disposition of this disposable install

The ledger `dogfood-desktop-ac9` is now permanently revoked (no un-revoke
exists). The install itself (`operator-broker`/`-builder`/`-verifier` accounts,
the broker service, `/etc`, `/var/lib`, `/usr/libexec` state) is left in place
as of this write-up -- tearing it down is a separate decision, not implied by
this campaign's completion.
