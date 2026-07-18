# Issue #7 Phase 0–1 run sheet (human-gated)

**Host:** z13 (dogfood)  
**Ledger:** `~/operator-dogfood-test` (`ledger_id` dogfood-test)  
**Do not touch:** production `~/.operator-usage`, do not `rm -rf` authority store  

Supervisor plan: `docs/ISSUE7_DOGFOOD_RESUME_PLAN.md`

---

## Gate: why this cannot be fully agent-driven from desktop

| Need | Status (2026-07-18) |
|------|---------------------|
| Passwordless `sudo` on z13 | **No** — password required |
| Passwordless `sudo -u operator-builder` | **No** (same) |
| Installed code has #9 incarnation | **No** — install lacks `store_incarnation` (2755-line broker, Jul 16) |
| Checkout has #9 | After sync: expect `c4ab0dd` or later in `~/operator-control-plane` |
| Broker unit | **active** |
| Builder / verifier UIDs | 971 / 970 present |
| Prior work | `p3-dogfood-task` **verified** (claim-0002); `complete-test-task` open, claim-0005 **unverified** |

**Phase 0 requires Erik at a TTY for sudo.** Phase 1 should run as `operator-builder` / `operator-verifier`, not `blueaz`.

---

## Phase 0 — Upgrade + preflight (admin TTY)

### 0.1 Stage a root-owned release from reviewed tip

On z13 (or scp from desktop after push):

```bash
# Ensure reviewed tree includes #9
cd ~/operator-control-plane
git fetch origin && git checkout master && git pull --ff-only
git log -1 --oneline   # expect c4ab0dd or later; grep store_incarnation authority_broker.py

REV=$(git rev-parse HEAD)
echo "REV=$REV"

# Root-owned stage (password once)
sudo install -d -m 0700 -o root -g root "/root/operator-control-plane-release/$REV"
sudo rsync -a --delete \
  --include='operator-admin' \
  --include='authority_admin.py' \
  --include='authority_broker.py' \
  --include='authority_client.py' \
  --include='authority_projection.py' \
  --include='socket_permission_helper.py' \
  --include='operator' \
  --exclude='*' \
  "$HOME/operator-control-plane/" \
  "/root/operator-control-plane-release/$REV/"

# Adjust includes if your install manifest expects a fixed file set — match prior dogfood stage.
sudo chmod 0700 "/root/operator-control-plane-release/$REV"
sudo find "/root/operator-control-plane-release/$REV" -type f -exec chmod go-w {} \;
```

If your prior dogfood used a fuller file list from `OPERATIONS_RUNBOOK.md`, prefer that exact stage recipe over this minimal set.

### 0.2 Atomic upgrade (preserve store)

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" upgrade \
  --release-dir "/root/operator-control-plane-release/$REV"
```

Confirm:

```bash
grep -n store_incarnation /usr/libexec/operator-control-plane/authority_broker.py | head
sudo systemctl status operator-control-plane-broker.service --no-pager
```

### 0.3 Fresh privilege evidence + preflight

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" collect-evidence
sudo "/root/operator-control-plane-release/$REV/operator-admin" preflight
```

**Stop unless** `boundary_ready: true` and evidence is fresh/policy-bound.

Save outputs under:

```text
~/operator-dogfood-evidence/2026-07-18-phase0/
```

### 0.4 Audit baseline

```bash
sudo "/root/operator-control-plane-release/$REV/operator-admin" audit | tee \
  ~/operator-dogfood-evidence/2026-07-18-phase0/audit-baseline.txt
```

Note commit count / sequences for before/after Phase 1.

**Do not** rebuild the store. **Do not** use `--acknowledge-store-reset` unless incarnation deliberately changed.

---

## Phase 1 — `complete` hole (primary blocker)

### Preferred task

Use **`p3-dogfood-task`** (status already `verified`, claim-0002 verified).  
Avoid starting from `complete-test-task` unless you first finish verify on claim-0005 as verifier.

### 1.1 PATH for constrained accounts

Installed CLI may not be on PATH. Typical pattern from prior dogfood:

```bash
export PATH="/usr/libexec/operator-control-plane:$PATH"
# or use full path to installed operator if present under release/libexec
```

Confirm which binary enrolled clients use (often a wrapper or repo-local `operator` with registry enrollment). Prior dogfood used enrolled repo + system install; use the **same** operator binary the builder used before.

### 1.2 As verifier — complete transition

```bash
sudo -u operator-verifier -H bash -lc '
  cd /home/blueaz/operator-dogfood-test
  # set PATH to installed operator as used in prior dogfood
  operator task-transition --task p3-dogfood-task --status complete
  echo exit:$?
  operator task-show p3-dogfood-task
'
```

**Expect:** success message; task `status: complete`; broker audit commit count **+1**.

Capture:

```bash
mkdir -p ~/operator-dogfood-evidence/2026-07-18-phase1
# paste full stdout/stderr of transition
# sudo audit before/after
```

### 1.3 As any enrolled client — session-end complete must fail

Open a session if needed, then:

```bash
sudo -u operator-builder -H bash -lc '
  cd /home/blueaz/operator-dogfood-test
  operator session-start --harness claude --task p3-dogfood-task --force || true
  # if session-start needs different harness id, use one present under .operator/harnesses
  operator session-end --outcome useful --cost 0 --status complete
  echo exit:$?
'
```

**Expect:** nonzero exit; message that verified/complete transitions are restricted; **audit commit count unchanged**.

Also re-check:

```bash
operator session-end --outcome useful --cost 0 --status verified
# same fail-closed expectation
```

### 1.4 If complete fails with reconcile / incarnation errors

1. Read full error.  
2. **Do not** wipe store.  
3. If message mentions `store incarnation discontinuity` after a real upgrade that recreated the DB (should not), stop and escalate — upgrade must preserve store.  
4. If `local sequence exceeds broker sequence` without incarnation (old code), **Phase 0 was incomplete** — install still pre-#9.

### 1.5 Post to GitHub #7

Minimal comment template:

```markdown
## Phase 1 evidence (complete path)

**Host:** z13 · **Ledger:** ~/operator-dogfood-test · **Release:** <REV>

### Preflight
- boundary_ready: true (artifact: ...)
- audit baseline commits: N

### task-transition --status complete
- command: ...
- exit: 0
- task-show: status complete
- audit commits: N → N+1

### session-end --status complete
- command: ...
- exit: 1
- message: ...
- audit commits unchanged: N+1 → N+1

### session-end --status verified
- (reconfirm) exit 1, commits unchanged
```

---

## Agent (Grok) vs human split

| Step | Who |
|------|-----|
| Sync git tip with #9 | Agent can push/pull |
| Stage + upgrade + collect-evidence + preflight | **Human (sudo)** |
| task-transition / session-end as builder/verifier | **Human** (or agent if passwordless sudo -u is granted) |
| Package evidence + #7 comment draft | Agent can draft after logs are in `~/operator-dogfood-evidence/` |

---

## Immediate next action for Erik

1. Unlock a z13 terminal with sudo.  
2. Run **Phase 0** from this sheet.  
3. Run **Phase 1.2–1.3**.  
4. Drop logs into `~/operator-dogfood-evidence/2026-07-18-phase1/` (or paste here) for packaging into a #7 comment.

Until Phase 0 lands #9 on the **installed** broker, Phase 1 risks repeating the old incomplete path.
