# Issue #8 AC9 — Track C live run (desktop, 2026-07-20)

**Campaign:** `docs/DOGFOOD_AC9_CAMPAIGN.md`, Track C ("Service / outage", optional,
highest host risk)
**Result: PASS.** `service_lifecycle` and `outage_recovery` both demonstrated live
against the real, production-named `operator-control-plane-broker.service` unit
via real `systemctl` -- the exact thing the campaign doc's own gate (§9) said to
prefer skipping until Track A/B were green. They were, so this was attempted.

---

## Redeploy before Track C

`dogfood-desktop-ac9` was permanently revoked at the end of Track B. A real,
previously-unknown constraint in `dogfood_runner.validate_plan_bindings` (not a
bug -- a deliberate, consistent design choice) rejects **any** dogfood plan
against a revoked policy, not just `enrollment`: `dogfood-plan` failed closed
with `policy_revoked` on the first attempt to author a Track C plan against the
still-installed, now-terminal ledger. A second full teardown+reinstall (third
overall this campaign, same procedure as before -- accounts/throwaway ledger
repo untouched) produced a fresh, active generation-1 ledger under the same
name, confirmed via an independently-recomputed release digest
(`871ed91b63171ca3bc1c7bb133f51bc55b7186529a48d4377b36e0ea61baf320`, identical
to Track B's post-fix value, since no code changed).

## Why the crash-simulation approach was reconsidered

The rendered systemd unit sets `Restart=on-failure` with `RestartSec=1s` (see
`authority_admin.render_service`). A raw `kill -9` against the broker process
would very likely be raced and silently healed by systemd's own auto-restart
before `outage_recovery` ever observed the down state -- `Restart=on-failure`
does not fire on an intentional `systemctl stop`, only on an unexpected exit.
So the plan used `service_lifecycle` (`action: stop`) for a genuine,
administrator-intentional stop first, confirmed via `systemctl status` and the
socket file's absence, then ran `outage_recovery` against that real, verified-
down service -- exercising its actual restart-and-recover path (not just the
already-healthy short-circuit), without racing systemd's own supervisor.

---

## Log

```
Ledger id: dogfood-desktop-ac9 (generation 1, active -- third install this campaign)
Installed release digest: 871ed91b63171ca3bc1c7bb133f51bc55b7186529a48d4377b36e0ea61baf320
Plan digest: 786a269068a64dc98fec20274653275aa83b44106bdfae45160d5aed6580633e
Run id: 0ad535195e9e0d1c49deba51a9583d08
Phases: installation_verification (auto) -> service_lifecycle stop (approved) ->
  outage_recovery (approved) -> final_audit (auto)
service_lifecycle stop, verified for real: systemctl status showed
  "Active: inactive (dead)", exited status=0/SUCCESS, no auto-restart;
  /run/operator-control-plane/broker.sock absent.
outage_recovery, verified for real: systemctl status showed
  "Active: active (running)" with a fresh start timestamp matching the phase's
  own execution window; socket present again with correct
  operator-broker:operator-clients ownership.
Result: completed, all four phases, idempotent_replay correctly false for both
  mutating phases (neither had run before on this run_id).
Evidence tarball: /tmp/ac9-track-c-0ad535195e9e0d1c49deba51a9583d08.tgz
```

Two mutating phases back-to-back (`service_lifecycle` then `outage_recovery`)
each required their own separate `--approve-phase` call, live, against the real
host -- the same property proven with mocks in
`test_real_install_multi_mutating_phase_plan_requires_separate_approvals`, now
also proven with a real `systemctl` stop/start in the loop.

---

## What was proven

- **`service_lifecycle`**: a real `systemctl stop` against the real, installed
  unit name, verified down by direct inspection (not just trusting the phase's
  own return value).
- **`outage_recovery`**: given a genuinely down service, it correctly took the
  restart path (not the already-healthy short-circuit -- that was proven
  separately, with mocks, in the unit suite), performed a real
  `stop_service`+`start_service`, and confirmed health via
  `probe_socket_health` before returning success.
- **No bugs found this track.** Both phase types worked exactly as designed on
  the first live attempt (once the revoked-ledger constraint was worked around
  via redeploy).

## Campaign status after Track C

Every phase type shipped in Issue #8 (`installation_verification`,
`privilege_evidence`, `service_lifecycle`, `enrollment`, `rotation`,
`outage_recovery`, `revocation_checks`, `final_audit` -- 8 of 8 implemented
types) has now been demonstrated live against a real root install on this
desktop, across three tracks and three separate install cycles. Only
`reconciliation` remains unbuilt, by deliberate design decision (§4 of
`docs/DOGFOOD_RUNNER_OPERATIONS.md`), not because it wasn't attempted.

Per the issue's stop condition, this still does not recommend the runner for a
production ledger and does not claim the P3 authority boundary is reduced --
it recommends the runner for further disposable-ledger dogfood use, which is
what it was built for.
