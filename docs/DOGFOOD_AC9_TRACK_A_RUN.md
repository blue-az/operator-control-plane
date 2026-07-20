# Issue #8 AC9 — Track A live run (desktop, 2026-07-20)

**Campaign:** `docs/DOGFOOD_AC9_CAMPAIGN.md`, Track A ("Minimal AC9 core")
**Issue AC9:** *A real disposable-ledger run demonstrates review, execution, interruption, resume, final audit, and evidence export before the runner is recommended for a production ledger.*
**Result: PASS.** All six elements demonstrated live, against a real root install, on a disposable dogfood ledger, with a genuine (not simulated) mid-handler interruption.

---

## Log

```
Date: 2026-07-20
Host: desktop (Fedora 43, fresh install -- no prior operator-control-plane artifacts)
Installed release digest: 9ce91c1727c9fc83d2734f0917d8f79203997a329bb922e80aff58aa21d375a4
Ledger id: dogfood-desktop-ac9
Policy id / gen / sha256: policy-dogfood-desktop-ac9 / 1 / 00c62be1a73c2e2089b8baffb68f21d656f287e96bd6de968c3d11a2e68d8fe0
Plan digest: 6bbccc41eaa5167aa9ef5509170b3d4c37c32d132ef2c27328ab8c060d43bd4e
Run id: 966201f6d24e02d5b5c51e57ca432a51
Interrupt method: backgrounded `dogfood-run --approve-phase 2`, polled for
  checkpoints/0002-privilege_evidence.pending.json to appear, then
  `sudo pkill -9 -f "operator-admin dogfood-run"` -- a real SIGKILL mid-handler,
  not a raised exception or a mocked fault hook.
Resume command used: `dogfood-resume --run-id 966201f6d24e02d5b5c51e57ca432a51 --approve-phase 2`
final_audit ok?: yes -- ran automatically as phase 3 immediately after phase 2 completed on resume
Evidence tarball path: /tmp/ac9-track-a-966201f6d24e02d5b5c51e57ca432a51.tgz (1382 bytes, root:root)
Anomalies: one real bug found and fixed mid-campaign -- see "Bug found" below. No other anomalies;
  abort-table conditions (campaign doc §1) never triggered.
```

## What was proven, element by element

1. **Review** — `dogfood-plan --plan /root/ac9-track-a.plan.json` validated the plan's `ledger_id`,
   `policy_binding`, and `expected_release_digest` against live installed state (independently
   recomputed, not trusted from the plan) before storing it under
   `/var/lib/operator-control-plane-admin/dogfood-plans/<plan_digest>.json`.
2. **Execution** — `dogfood-run --plan-digest ...` executed phase 1
   (`installation_verification`) automatically, then stopped before phase 2
   (`privilege_evidence`, mutating) exactly as designed, printing the required
   `--approve-phase 2` instruction.
3. **Interruption** — approving phase 2 was deliberately killed (`SIGKILL`) after its
   `pending` checkpoint was durably on disk but before `completed`/`failed` was
   written. Confirmed by direct file inspection immediately after the kill:
   `pending` present, `completed` absent.
4. **Resume** — `dogfood-resume --run-id ... --approve-phase 2` correctly identified
   phase 1 as already `completed` (idempotent replay, not re-executed), re-invoked
   phase 2 from its `pending` state exactly once, then automatically ran phase 3
   (`final_audit`). No `--acknowledge-recovered` was needed or used -- that flag
   only gates a phase left in a `failed` state, and this one was `pending`, not
   `failed`, exactly matching the design in `dogfood_runner.py`.
5. **Exact-retry idempotency** — a second, unconditional `dogfood-resume --run-id ...`
   (no `--approve-phase`) returned `idempotent_replay: true` for all three phases,
   with `status: completed` and no new mutation.
6. **Final audit** — completed as phase 3, `dogfood-status` confirms `state: completed`
   with a recorded `result_digest` for every phase.
7. **Evidence export** — `dogfood-status` (pure read, no mutation) plus a tarball of
   the full run directory (`plan.json`, `run-state.json`, `run-history.jsonl`,
   `checkpoints/*.json`) retained at the path above.

## Bug found and fixed mid-campaign

The first `sudo operator-admin install` attempt crashed with `FileNotFoundError` on
`dogfood_runner.py` before `authority_admin.main()` was even reached.
`operator-admin`'s `require_root_owned_code()` check has required
`dogfood_runner.py` since Issue #8 slice 1, but the module was never added to
`INSTALLED_SOURCE_ASSETS` -- the dict that actually controls staging, install-time
copying, and release-digest computation. Every test written across slices 1-5
called `dogfood_runner`'s functions directly in-process and never exercised the
real `operator-admin` wrapper against a real staged release directory, so this
went uncaught through 294 passing tests. Fixed in
`operator-control-plane@02c452c` (added to `INSTALLED_SOURCE_ASSETS`, updated the
runbook's staging loop, documented the module in `AGENTS.md`), re-verified with
the full suite still green, then the release was re-staged and re-installed
successfully. This is exactly the kind of gap AC9 exists to catch -- a real
install exercising the real wrapper against a real staged directory found
something 294 unit/root tests structurally could not.

## Abort-table check (campaign doc §1)

None of the abort conditions were ever true during this run: no real product
ledger was touched (ledger is `dogfood-desktop-ac9`, distinct from any real
work ledger); the plan's bindings matched live `audit` state on the first try
(after the bug fix); `service_lifecycle`/`outage_recovery` were not exercised in
Track A; the session was not rushed.

## What this does not prove yet

Per the campaign doc, Track A deliberately excludes `enrollment`, `rotation`,
`service_lifecycle`, `outage_recovery`, and `revocation_checks` -- those are
Track B (and the optional, higher-risk Track C for real `systemctl` against the
production unit name). Per the issue's own stop condition, this run does not
recommend the runner for a production ledger and does not claim the P3
authority boundary is reduced.
