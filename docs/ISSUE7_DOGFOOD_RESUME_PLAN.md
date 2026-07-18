# Issue #7 resume plan — for supervisor

**Date:** 2026-07-18  
**Audience:** supervisor / captain driving remaining P3d dogfood  
**Repo:** `blue-az/operator-control-plane`  
**Issue:** [#7](https://github.com/blue-az/operator-control-plane/issues/7) — *P3d: Migrate ledgers and dogfood the authority boundary*

This is an **evidence campaign**, not a feature-invention sprint. Most implementation for migration, enrollment, transitions, and preflight already exists. What remains is **honest, issue-linked live proof** of the gaps named in the 2026-07-15 dogfood comment — plus deployment of post-#10/#11 code onto the dogfood host without destroying store history.

---

## 0. Current dependency picture (do not re-litigate)

| Issue | State | Role for #7 |
|-------|--------|-------------|
| **#10** device-number rebind | **Closed** (code + tests) | Live-host rebind demo was deferred on #11; may still want one live rebind proof on z13 after upgrade |
| **#11** atomic code upgrade | **Closed** | Unblocks installing reviewed digests onto the dogfood host **without** wiping `/var/lib/operator-control-plane` |
| **#9** stale reconcile after rebuild | **Closed 2026-07-18** (`c4ab0dd`) | Store `store_incarnation_id` + fail-closed reconcile + `--acknowledge-store-reset`. Removes the *reason* `complete` was never reached in the prior dogfood session |
| **#7** | **Open** | Remaining = dogfood evidence gaps, not greenfield design |

**Host residual (z13, checked 2026-07-18):**

- `~/operator-dogfood-test` still present with `.operator/`
- Broker unit **active**; store **exists**
- `operator-builder` (971), `operator-verifier` (970) still provisioned
- Prior dogfood used disposable ledger `dogfood-test` only — **not** production `~/.operator-usage`

**Do not:** tear down the store “for cleanliness.” Use `operator-admin upgrade` (or the #11 path) to move code, then continue on the same ledger when possible.

---

## 1. Honest bars (split so the day is schedulable)

### Bar A — “#7 closable” (goal of this campaign)

Every **real-host dogfood acceptance** item in the issue body has issue-linked evidence, **or** an explicit, supervisor-signed “N/A with reason” that does not paper over a fail-open path.

Minimum hard blockers called out by prior dogfood (must green):

| ID | Acceptance | Prior status | Required evidence |
|----|------------|--------------|-------------------|
| **D3** | Builder authors via broker; distinct verifier produces `uid_isolated` + `external_broker` | **Partial** — `verified` E2E done; **`complete` not done** | `task-transition --status complete` success under verifier UID + broker audit commit count + task YAML |
| **D5a** | `session-end --status verified` fails closed | **Done** live | Keep prior evidence; re-run after upgrade if code moved |
| **D5b** | `session-end --status complete` fails closed | **Missing** | Same pattern as verified: exit 1, no new broker commit |
| **D8** | Injected post-commit projection failure → pending + retry/reconcile | **Unit only** | Live or integration-grade repro with receipt reuse, no duplicate authority event |
| **D9** | CAS evidence survives local projection/artifact deletion | **Unit only** | Delete local evidence projection; broker CAS + re-project still holds |
| **D10** | Stored verify commands inert; sentinels absent | **Partial** | Explicit check list against dogfood ledger + doctor never executes verify-cmd |
| **D4** | Adversarial substitution/forgery | **Unit/integration only** | Either re-run subset live under builder/verifier UIDs **or** attach test names + “not re-live, coverage X” with supervisor OK |
| **D11** | Full tests + lint/static | **Done** on tree at prior freeze | Re-run on **post-upgrade** tree before close |
| **D12** | Evidence posted to #7 | Ongoing | This plan’s run log + artifacts |

Privilege-precondition (`boundary_ready: true` from fresh `collect-evidence` + `preflight`) is a **gate before any new dogfood claim**, not optional.

### Bar B — “Farm-through-Operator demo” (after Bar A only)

Only after Bar A is honest:

- Farm pass uses Operator as **ledger/gate**, disposable target (see `~/farm-eval-evidence/pass2b/`)
- Verdict language: Farm under Operator-governed capture — **not** “P3 incomplete with holes”

Do **not** start Farm as a substitute for D3/D5b.

---

## 2. Phased execution plan

### Phase 0 — Preflight (supervisor + admin, ~30–60 min)

**Owner:** human admin (`blueaz`) + constrained UIDs for agent steps.

1. Confirm #9/#10/#11 commits are on the release you will install (`c4ab0dd` or later for #9).
2. Build a **root-owned staged release** pin (digest) per runbook — **not** sudo-from-checkout.
3. `operator-admin upgrade` (or #11 equivalent) on z13 dogfood host → preserve store.
4. Fresh:
   ```bash
   operator-admin collect-evidence …
   operator-admin preflight …
   ```
   Require `boundary_ready: true`, evidence age &lt; 24h, bound to **current** policy generation.
5. Record: release digest, preflight JSON path, `systemctl status`, `operator-broker audit` commit count baseline.

**Stop if:** preflight not boundary_ready; upgrade mixed-state; store missing.

### Phase 1 — Close the `complete` hole (primary blocker) (~1–2 h)

**Why first:** Prior session failed here because of #9-class reconcile bookkeeping after rebuilds. With #9 fixed and **no store rebuilds**, this should be runnable.

Order:

1. As **builder** UID: ensure an enrolled task with a verified claim path ready for completion (or create task + claim + evidence draft + verifier `verified` if needed — do not skip verifier isolation).
2. As **verifier** UID:  
   `operator task-transition --task <id> --status complete`  
   Expect success; capture stdout, `task-show`, broker `audit` / commit sequence before+after (+1).
3. As **builder** (or any enrolled client):  
   `operator session-end … --status complete` (and re-check `--status verified` if re-proving after upgrade)  
   Expect **fail closed**, exit ≠ 0, **commit count unchanged**.
4. Attach all artifacts under e.g. `~/operator-dogfood-evidence/2026-07-18-complete/` and post summary to #7.

**Explicitly avoid:** `rm -rf` store, reinstall loops, `--acknowledge-store-reset` unless a real intentional rebuild (should not need it).

**Unit already green (do not count as live D3/D5b):**  
`test_task_transition_routing`, `test_session_end_rejection` in `tests/test_authority_integration.py`.

### Phase 2 — Projection pending + CAS survival (D8, D9) (~1–2 h)

Prefer **deterministic integration-style** first if a safe live inject is hard; then one live confirm if feasible.

| Item | Approach |
|------|----------|
| **D8** | After a successful broker commit, force projection failure (e.g. inject journal `committed` not `projected`, or break local write once); confirm client reports pending; `authority-reconcile` completes from **same receipt**, no duplicate commit sequence |
| **D9** | Attach evidence with CAS blob; delete local evidence YAML/copy; confirm broker CAS still has blob; reconcile/re-materialize or document recovery path |

Post commands + digests to #7.

### Phase 3 — Inert commands / sentinels (D10) (~30–45 min)

On dogfood ledger:

1. Attach evidence with a stored `--verify-cmd` that would be dangerous if executed (e.g. `touch /tmp/operator-sentinel-should-not-exist`).
2. Run `doctor` (and any status paths).
3. Assert sentinel file **absent**; doctor output does not imply execution.
4. Record command list + hashes.

### Phase 4 — Adversarial / substitution (D4) — choose one track

**Track 4a (preferred if time):** Re-run a **minimal live** subset under builder/verifier:

- Local journal forgery / higher version (mirror `test_reconcile_rejects_higher_local_forgery`)
- Symlink substitution of enrolled path (mirror integration test)

**Track 4b (supervisor-approved):** Cite integration/admin tests by name + commit SHA; state “not re-exercised live this host”; only acceptable if D3/D5b/D8/D9/D10 are live-solid.

### Phase 5 — Optional live #10 rebind proof (~30–60 min)

If post-reboot device numbers still match, **do not force a reboot** just for theater. If identity is healthy:

- Document “rebind N/A — identity stable after upgrade”
- Or: admin-only dry rebind path if runbook supports no-op/idempotent proof

If identity is broken: run `operator-admin repository-rebind` per runbook; capture receipt + registry.

### Phase 6 — Close package (~30 min)

1. Re-run full `pytest tests/ -q` (or documented subset + ruff/black/isort) on release tree.  
2. Single #7 comment: table of acceptance IDs → evidence paths → pass/fail.  
3. **Close #7 only if** no remaining fail-open gaps and privilege bar still holds.  
4. Then — and only then — schedule **Farm-through-Operator** (`farm-governed-delegation-drill` / `pass2b/`).

---

## 3. What is already “good enough” from prior dogfood (do not redo unless upgrade invalidates)

Treat as **carried evidence** (re-verify only if code upgrade or host policy changed):

- Privilege accounts + many `boundary_ready` collectors (re-collect after upgrade)
- Failed enrollment leaves unenrolled; successful enroll atomic; pre-enrollment not promoted
- Enroll idempotency / registry collision behavior
- Builder→broker claim path; verifier `verified` via `task-transition`
- Broker outage fail-closed on claim-add (and CAS-precondition fix)
- Policy rotation generation + history + fork rejection
- Rollback rejection table cases in runbook
- Full unit suite green at prior freeze

---

## 4. Explicit non-goals for this resume

- Implementing Crystal↔Ledger Phase 1  
- Farm-on-Operator (Farm editing operator source)  
- Closing #7 with unit tests alone for D3/D5b  
- Store teardown “to get a clean slate”  
- Claiming physical immutability of the broker store  
- Using `blueaz` as builder/verifier isolation proof  

---

## 5. Suggested day schedule (if “have the day”)

| Block | Focus |
|-------|--------|
| Morning | Phase 0 upgrade + preflight |
| Mid | Phase 1 `complete` + `session-end --status complete` |
| Afternoon | Phase 2 D8/D9 + Phase 3 D10 |
| Late | Phase 4 track choice + Phase 6 #7 comment |
| Later day / next | Farm-through-Operator only if #7 closed |

If the day slips: **ship Phase 1 evidence alone** as the highest-value #7 comment — that was the named blocker.

---

## 6. Success criteria for supervisor sign-off

- [ ] Fresh `boundary_ready: true` after code upgrade  
- [ ] Live `task-transition --status complete` with audit delta  
- [ ] Live `session-end --status complete` rejection with no commit  
- [ ] D8 and D9 have evidence beyond “unit exists”  
- [ ] D10 sentinel check recorded  
- [ ] D4 either live subset or explicit supervisor waiver  
- [ ] #7 comment is a closure package, not a progress diary  
- [ ] Farm demo not started until above holds  

---

## 7. Pointers

| Resource | Path |
|----------|------|
| Runbook | `OPERATIONS_RUNBOOK.md` |
| Prior dogfood narrative | GitHub #7 comments (2026-07-15) |
| #9 fix | commit `c4ab0dd` |
| Farm-after plan | `~/farm-eval-evidence/pass2b/MODE.md` |
| Integration tests (not live substitutes for D3) | `tests/test_authority_integration.py` |

---

*Plan only. Does not authorize store destruction, production ledger enrollment, or Farm Connect.*
