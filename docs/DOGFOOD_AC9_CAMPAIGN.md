# Issue #8 AC9 campaign — disposable-ledger live run

**Status:** run sheet only — **not executed**. No root, no install, no mutation until Erik approves Phase 0 and the abort table.

**Issue AC9:** *A real disposable-ledger run demonstrates review, execution, interruption, resume, final audit, and evidence export before the runner is recommended for a production ledger.*

**Stop condition (issue):** Do not claim the runner reduces the P3 privilege boundary merely because it reduces copy/paste. AC9 proves the **workflow** on a **disposable** ledger, not production readiness of every host.

---

## 0. Hard facts from this codebase (do not invent paths)

| Fact | Implication |
|------|-------------|
| `operator-admin` dogfood commands always use `InstallLayout.production()` + `DogfoodLayout.production()` | Live run hits **fixed host paths**, not a temp fixture root. There is no CLI flag for `under(root)`. |
| Production layout | `install_root=/usr/libexec/operator-control-plane`, `config_root=/etc/operator-control-plane`, `state_root=/var/lib/operator-control-plane`, `runtime_root=/run/operator-control-plane` |
| Dogfood state (sibling of broker state) | `/var/lib/operator-control-plane-admin/{dogfood-plans,dogfood-runs}/` |
| This desktop (checked 2026-07-20) | **No** `/var/lib/operator-control-plane` and **no** admin dogfood tree — **Phase 0 install is a prerequisite**, not optional |
| Non-goal of #8 | Automatically enrolling production ledgers (e.g. real work repos) |
| `revocation_checks` | Terminal for that ledger; **disposable ledger only** |

Unit tests use `InstallLayout.under(tmp)` — that proves engine mechanics, **not** AC9.

---

## 1. Abort immediately if any of these are true

| Abort if… | Why |
|-----------|-----|
| Any path under a real product ledger (desktop work tree with real claims you care about) is about to be enrolled | Non-goal; contamination risk |
| Plan `ledger_id` / policy / release digest does not match `sudo operator-admin audit` | `dogfood-plan` will reject; do not force |
| You are tempted to “just use the live dogfood ledger from #7 forever” without confirming disposable | Revocation and enrollment mutate authority state |
| `service_lifecycle` / `outage_recovery` would target a unit name that is not the dogfood/broker unit you intend | systemctl ignores disposable roots — **real host unit** |
| Session is rushed / jet-lag / multitasking | This is a campaign, not a 10-minute slice |

---

## 2. Campaign tracks (choose one for the first live pass)

### Track A — **Minimal AC9 core** (recommended first)

Demonstrates every AC9 verb without host service flip or terminal revoke:

| Step | Operation | Mutating? | Human gate |
|------|-----------|-----------|------------|
| 1 | `installation_verification` | no | auto |
| 2 | `privilege_evidence` | **yes** | `--approve-phase 2` |
| 3 | **INTERRUPT** after approve starts / mid-pending (see §5) | — | kill process |
| 4 | `dogfood-resume` (+ approve if needed) | — | resume |
| 5 | `final_audit` | no | auto |

**Proves:** review (plan), execution, interruption, resume, final audit, status/export of run tree.  
**Does not prove:** enroll, rotate, service stop/start, outage, revoke (those remain unit-tested / optional Track B).

### Track B — **Enrollment + revoke** (second session, still disposable)

Only after Track A green on the same install:

1. Create **throwaway** git repo (e.g. `/tmp/operator-dogfood-ac9-ledger/` or a dedicated empty path under `/var/tmp/…` owned appropriately).  
2. `enrollment` with that absolute `repository_path`.  
3. Optional `rotation` with a **new** policy file prepared offline (generation +1, correct previous sha).  
4. `final_audit`.  
5. **`revocation_checks` last** with `expected_policy_sha256` matching active policy — ledger dies; expected.

### Track C — **Service / outage** (optional, highest host risk)

Only if you accept **real systemctl** against the **production unit name** rendered by install (not a fake unit). Prefer **skip** until Track A/B are green. Mocked in unit tests for good reason.

---

## 3. Phase 0 — Host install (prerequisite; separate approval)

**Do not start Phase 1 until Phase 0 is complete and `audit` is green.**

Rough sequence (details live in install/runbook docs and prior #7 package — follow those, do not improvise):

1. Stage a **root-owned** release of this repo (wrapper rejects user-writable checkout for privileged ops).  
2. `sudo operator-admin install …` with a **dogfood-only** policy (fixture builder/verifier UIDs or dedicated dogfood UIDs — not your daily desktop ledger identity if that would mix concerns).  
3. Confirm:
   ```bash
   sudo ./operator-admin audit   # from installed path / staged release
   ls -la /var/lib/operator-control-plane
   ls -la /var/lib/operator-control-plane-admin   # may appear after first dogfood-plan
   ```
4. Record: release digest, policy id/generation/sha256, ledger_id from audit JSON.

**Binding rule:** every field in the plan’s `policy_binding`, `expected_release_digest`, `ledger_id`, and `host_paths` must be **copied from live audit / install**, never guessed.

---

## 4. Plan template (Track A)

Fill placeholders from live `audit` after Phase 0. Save as root-readable path e.g. `/root/ac9-track-a.plan.json` (mode 0600).

```json
{
  "plan_schema_version": 1,
  "created_at": "REPLACE_ISO8601_Z",
  "created_by_uid": 0,
  "ledger_id": "REPLACE_FROM_AUDIT",
  "policy_binding": {
    "policy_id": "REPLACE",
    "generation": 1,
    "sha256": "REPLACE_64_HEX"
  },
  "expected_release_digest": "REPLACE_64_HEX",
  "host_paths": {
    "install_root": "/usr/libexec/operator-control-plane",
    "config_root": "/etc/operator-control-plane",
    "state_root": "/var/lib/operator-control-plane",
    "runtime_root": "/run/operator-control-plane"
  },
  "phases": [
    {
      "phase_id": 1,
      "operation": "installation_verification",
      "args": {},
      "mutating": false
    },
    {
      "phase_id": 2,
      "operation": "privilege_evidence",
      "args": {},
      "mutating": true
    },
    {
      "phase_id": 3,
      "operation": "final_audit",
      "args": {},
      "mutating": false
    }
  ]
}
```

Note: `mutating` flags **must** match the catalog (`privilege_evidence` true; verify/final false) or plan parse fails closed.

---

## 5. Execution script (Track A) — after plan fills

All commands from the **installed** root-owned tree (not a dirty user checkout), as root.

```bash
# Review + store plan
sudo operator-admin dogfood-plan --plan /root/ac9-track-a.plan.json
# → record plan_digest from JSON stdout

# Start run: phase 1 auto; stops before phase 2
sudo operator-admin dogfood-run --plan-digest "$PLAN_DIGEST"
# → record run_id

# Status (root today; AC6 unprivileged export still deferred)
sudo operator-admin dogfood-status --run-id "$RUN_ID"

# Approve mutating phase 2 — INTERRUPT once pending is durable:
# Option: run in one terminal, kill -9 after "pending" checkpoint appears under
#   /var/lib/operator-control-plane-admin/dogfood-runs/$RUN_ID/checkpoints/
sudo operator-admin dogfood-run --plan-digest "$PLAN_DIGEST" --run-id "$RUN_ID" --approve-phase 2
# kill mid-flight if not already interrupted

# Resume (acknowledge recovered if runner requires it after pending)
sudo operator-admin dogfood-resume --run-id "$RUN_ID" --approve-phase 2 --acknowledge-recovered
# or dogfood-run with same approve if resume path says so — follow live CLI error text

# Should complete phase 2 then auto-run phase 3 final_audit
sudo operator-admin dogfood-status --run-id "$RUN_ID"
# overall status must be completed
```

### Evidence export (admin-mediated)

```bash
RUN=/var/lib/operator-control-plane-admin/dogfood-runs/$RUN_ID
sudo tar -C /var/lib/operator-control-plane-admin/dogfood-runs -czf \
  /tmp/ac9-track-a-${RUN_ID}.tgz "$RUN_ID"
# Copy off-host or into a throwaway Operator ledger as evidence (not production claims)
sudo cp -a "$RUN" /tmp/ac9-run-copy-$RUN_ID
# Expect: plan.json, run-state.json, run-history.jsonl, checkpoints/*.json
```

Optional: attach tarball under Evaluation `.operator/` as **evidence only** (no claim required), task id e.g. `issue8-ac9-track-a`.

---

## 6. Interruption criteria (what “counts”)

| Required | Method |
|----------|--------|
| At least one **pending → resume** cycle | Kill after checkpoint `pending` for phase 2; resume without duplicate privilege evidence |
| Exact retry idempotent | Second approve/resume on completed phase 2 should show `idempotent_replay` / no second mutation (per status/checkpoint fields) |
| Failed gate not skippable | Optional negative: force a failed phase in a **second** throwaway plan only if safe |

---

## 7. Pass / fail for AC9

**Pass Track A if all hold:**

1. `dogfood-plan` accepted against live install (review).  
2. Run executed with **one human approve** for the mutating phase (fewer relays than #7).  
3. Interrupt + resume completed without manual checkpoint surgery.  
4. `final_audit` completed in the same run.  
5. Run directory / tarball retained as export evidence.  
6. Write-up: short `docs/domain_runs` or issue comment with digests, run_id, timestamps, abort list empty.

**Still does not automatically close #8** until issue AC wording is checked: if AC1 is read as “full disposable sequence” including enroll/rotate/revoke, complete Track B before closing. Ops doc currently treats AC9 as the live workflow demo; reconcile with issue text when filing the close comment.

---

## 8. What we are **not** doing in this first campaign

- Production recommendation of the runner  
- Claiming P3 is “easier” or weaker  
- Enrolling real work ledgers  
- Building a temp-root CLI (would be a product change)  
- Re-opening reconciliation as a phase  

---

## 9. Decision gate (Erik)

| Question | Answer before any sudo install/run |
|----------|-------------------------------------|
| Track A only first? | **Default yes** |
| Phase 0 install on this desktop OK? | Need explicit yes (touches real `/etc`, `/var/lib`, units) |
| Prefer install on a throwaway VM / z13 instead? | Safer isolation; paths still production-layout on that host |
| Track B (enroll/revoke) same day? | Default **no** — second session |

**Next action after Erik answers the gate:** execute Phase 0 only, or rewrite plan with live digests and run Track A.

---

## 10. Log template (fill during run)

```
Date:
Host:
Installed release digest:
Ledger id:
Policy id / gen / sha256:
Plan digest:
Run id:
Interrupt method:
Resume command used:
final_audit ok?:
Evidence tarball path:
Anomalies:
```
