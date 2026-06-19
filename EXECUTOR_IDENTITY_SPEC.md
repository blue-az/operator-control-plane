# Operator Executor-Identity Binding — Build Spec

**For:** the implementing agent (Agy / Antigravity). **Reviewer:** Claude.
**Target:** extend `the operator CLI in this repo`. Match existing conventions.
**Premise memory:** `project_operator_verifier_identity.md` — `verified_by` is honor-system; impersonation was demonstrated 2×.

---

## 0. READ THIS FIRST — what this task can and cannot do

The `verified_by` guard records whatever string is typed into `--verified-by`. The goal here is to bind verification to the **actual executor** so a builder can't stamp the reviewer's name. **But be honest about the ceiling:**

> **Software in the operator CLI cannot, by itself, prevent impersonation when all agents run as the same OS user with shell access.** Such an agent can read any env var, any key file, and set any identity. Real enforcement requires an **isolation boundary the agent cannot cross** — distinct OS users, containers, or a credential store outside the agent's reach. That boundary is *infrastructure*, not code.

So the operator's job is narrow and achievable: **consume an unforgeable identity source, reconcile it against the claimed verifier, and FAIL CLOSED when identity can't be established.** Passing tests **do not** mean impersonation is prevented — they mean the operator correctly enforces identity *given* the isolation boundary. State this explicitly in the handoff; do not claim "impersonation solved."

**Anti-goal:** do not build something that *looks* like enforcement but isn't (e.g., trusting a spoofable env var as identity). That would be worse than the current honest honor-system, because it would launder false confidence.

---

## 1. The unforgeable primitive — stamp the real executor on every write
On every ledger write (claim creation, evidence attach, verification, usage), record:
```yaml
executor:
  uid: <int>          # os.getuid() — the kernel-enforced, process-unforgeable signal
  user: <string>      # pwd.getpwuid(os.getuid()).pw_name  (NOT $USER/$LOGNAME — those are spoofable)
```
Use `os.getuid()` + `pwd.getpwuid()`. **Do not** derive identity from `getpass.getuser()` or `$USER`/`$LOGNAME` — those honor env and are forgeable by the agent. uid is the authoritative key.

## 2. Identity map — `.operator/identity.yaml`
```yaml
# Maps unforgeable OS uids to agent identities. Maintained by the operator (human), not agents.
mode: enforced | single_user      # see §5
uids:
  1000: blueaz-supervisor          # example
  1001: gemini-agy
  1002: codex
  # the reviewer's uid -> claude
```

## 3. Verification binding (`evidence-attach --status`)
When `--status` is set:
1. Resolve `actual = uids[os.getuid()]` from the identity map.
2. If the uid is **not in the map** → **fail closed**: error `refusing to record verification: executor uid <n> is not a known identity`, exit non-zero. (Don't default, don't guess.)
3. Set `verified_by = actual` (derived from the unforgeable uid). If `--verified-by` is also passed and **≠ actual** → error `--verified-by '<x>' does not match the executing identity '<actual>'`. (So `--verified-by` becomes a redundant assertion that must agree, not a free input.)
4. Continue to record the `executor` block (§1) on the verification evidence.

## 4. `doctor` rules
- Verified claim where `verified_by != uids[executor.uid]` (claimed verifier ≠ who actually ran it) → **`[Error]` verification identity mismatch (possible impersonation)**.
- Verified claim with `verified_by == made_by` → keep the existing self-verification `[Error]`.
- Verified claim with **no `executor` block** (legacy, pre-this-feature) → `[Info]` (don't fail; back-compat — `claim-0007/0008/0009/0010` predate this).
- `identity.yaml mode: single_user` OR missing → every verification gets `[Warning] verification is NOT identity-enforced (single-user mode); see EXECUTOR_IDENTITY_SPEC §5`. This makes the honest limitation **visible in the ledger** rather than hidden.

## 5. The honest mode switch (`single_user` vs `enforced`)
Today all three CLIs likely run as the **same OS user** → uid is identical for builder and reviewer, so uid **cannot distinguish them**. Don't pretend otherwise:
- `mode: single_user` (default until the infra exists): the operator still stamps executor + records `verified_by`, but `doctor` **warns** that verification is not identity-enforced. No false confidence.
- `mode: enforced` (set only once agents run under distinct uids / containers): `doctor` upgrades the mismatch check to `[Error]` and the fail-closed in §3.2 is active.
- **The operational prerequisite for real enforcement** (run each agent under its own OS user or container) is documented here as out-of-band setup the operator consumes; it is NOT something this build can create.

## 6. Test-hook honesty
Tests need to simulate different uids without privileges. If you add a test override (e.g. `OPERATOR_TEST_UID`), it is itself a **spoof vector** — the operator MUST ignore it unless an explicit test sentinel is set, and `doctor` MUST `[Error]` if a real ledger contains writes made while a test-override was active (record a flag on the executor block when the override was used). A test hook that production silently honors would re-open the exact hole we're closing.

## 7. Acceptance tests (`tests/test_operator.py`, subprocess; simulate uids via the guarded test hook)
1. **executor stamped:** any write records `executor.uid`/`executor.user`.
2. **derive + match:** with identity map {1001: gemini-agy, 1002: claude}, simulated uid 1002 setting `--status verified` → `verified_by == claude`; `doctor` clean (mode enforced).
3. **mismatch rejected:** simulated uid 1001 with `--verified-by claude` → error (≠ resolved gemini-agy); claim unchanged.
4. **unknown uid fails closed:** uid not in map + `--status` → non-zero error, no write.
5. **doctor impersonation catch:** hand-write a verified claim with `verified_by: claude` but `executor.uid` mapping to gemini-agy → `[Error]` mismatch.
6. **single_user honesty:** `mode: single_user` → verification produces `doctor` `[Warning]` (not silent), exit still 0 if that's the only finding... **decision point:** confirm with reviewer whether single_user warning should keep exit 0 (consistent with `[Info]`/`[Warning]` not failing) or force a deliberate ack. Default: warning, exit 0.
7. **test-hook guard:** a ledger write made under `OPERATOR_TEST_UID` without the test sentinel → `doctor` `[Error]`.
8. existing tests pass; `doctor` clean on the live ledger (legacy claims → `[Info]`, single_user → `[Warning]` — confirm the live ledger stays exit 0).

## 8. Out of scope (do NOT build / do NOT claim)
- Do not claim impersonation is "prevented" — it is prevented **only** under `mode: enforced` with real uid isolation, which this build does not create.
- No cryptographic signing scheme this pass (a verifier key still reduces to "can the agent read the key" = isolation). Note it as a future option, don't build it.
- Do not trust `$USER`/`$LOGNAME`/any env as identity.
- Do not auto-set `mode: enforced` — that's a human decision made after the OS-user/container isolation is actually in place.

---
*Continues the operator integrity-hardening lane. The honest framing in §0/§5 is the load-bearing part — a green test suite here is necessary but not sufficient for real enforcement.*
