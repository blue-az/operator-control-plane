# Operator `verified_by` Guard — Build Spec

**For:** the implementing agent (Agy / Antigravity). **Reviewer:** Claude (this time the reviewer actually verifies).
**Target:** extend `the operator CLI in this repo`. Match existing conventions.

---

## 0. Why (general integrity, not the bake-off)

The operator's core task model is `assigned_harness` (builder) + `review_harness` (reviewer). Right now a claim's `verification_status` can be flipped to verified by **anyone** — including the claim's own maker — and the ledger doesn't record *who* verified it. That makes `VERIFIED` untrustworthy for **every** task (domains, papers, deploys, audits), not just any one experiment. Concretely: `claim-0007`/`claim-0008` were made *and* verified by `gemini-agy`; nothing caught it.

This guard closes the **default self-verification footgun** and makes the verifier auditable. It does **not** attempt cryptographic identity — a deliberately falsified `--verified-by` is out of scope (that's an identity problem, not a ledger-integrity one). Scope is intentionally small: **one field, one doctor rule family, one brief-text change.** Do not build a roles/permissions system.

---

## 1. Schema change (claim records, `.operator/claims/claim-*.yaml`)
Add one field:
```yaml
verified_by: <actor|null>   # who set a terminal verification status; null = not yet / legacy
```

## 2. Command change — `evidence-attach`
- Add arg `--verified-by ACTOR`.
- When `--status` is supplied (`verified|false|quarantined`):
  - record `claim["verified_by"] = args.verified_by`.
  - **`--verified-by` is REQUIRED when `--status` is set.** If absent → error and exit non-zero: `Error: --verified-by is required when setting --status (the verifier must identify themselves).` Do **not** silently default it to `assigned_harness` (the current footgun) or to `review_harness` (that would launder a builder's self-verification as reviewer-signed).
- Keep the existing `--by` (evidence *producer*) separate and unchanged. Producer ≠ verifier.

## 3. `doctor` rules (added)
For each claim, let `made = made_by`, `vby = verified_by`, `verified = (verification_outcome == "verified") or (verification_status truthy)`, and `review = its task's review_harness`:
- `verified and vby == made` → **`[Error]` claim X is self-verified by '<made>' (maker cannot verify own claim)**. ← the core guard.
- `verified and vby and review and vby != review` → **`[Warning]` claim X verified by '<vby>', not the task's review harness '<review>'**.
- `verified and not vby` → **`[Info]`** (legacy claim, verifier unknown — does NOT count as an issue; use the existing `infos` list, not `issues`, so `doctor` still exits 0).
- `false`/`quarantined` outcomes are exempt from the self-verification Error (admitting your own claim is wrong/unproven is fine); still record `verified_by` for them.

**Migration / back-compat:** existing claims have no `verified_by`, so they hit the `[Info]` branch and `doctor` stays clean (exit 0). Do NOT backfill `verified_by` from anywhere — legacy verifiers are unknown. `claim-0007`/`claim-0008` will show as `[Info]` until they are re-verified through the corrected flow (a separate manual step by the reviewer, not part of this build).

## 4. Brief generator (`generate_brief_markdown`) text change
In the evidence/handoff guidance, replace the "verify your claims" framing with the split:
- "**Builders attach evidence but do NOT set `--status`.** Register claims and attach evidence (`evidence-attach --claim ... --by <you>`). Leave verification to the review harness."
- "**Only the review harness verifies**, with `evidence-attach --status verified --verified-by <reviewer>`."

## 5. Tests (`tests/test_operator.py`, subprocess style — no fixtures needed, pure ledger logic)
1. **self-verify blocked by doctor:** task(assign=codex, review=claude); claim made_by codex; `evidence-attach --status verified --verified-by codex` → `verified_by==codex`; `doctor` → `[Error]` self-verified, exit 1.
2. **reviewer verify clean:** same claim, `--verified-by claude` → `doctor` clean (exit 0).
3. **wrong verifier warns:** `--verified-by gemini-agy` (≠ review_harness claude) → `doctor` `[Warning]`, no Error from this rule.
4. **missing --verified-by rejected:** `evidence-attach --status verified` (no `--verified-by`) → exits non-zero with the required-arg error; claim unchanged.
5. **legacy is Info, not failure:** hand-write a claim with `verification_status: true` and no `verified_by` → `doctor` prints `[Info]` and exits **0**.
6. existing `tests/test_operator.py` still passes; `operator doctor` clean on the live ledger (the legacy `claim-0007/0008` land in the Info branch).

## 6. Out of scope (do NOT add)
- No roles/permissions/ACL system; no identity verification of `--verified-by`.
- No auto-backfill of legacy `verified_by`.
- Do not change quarantine/verified status semantics beyond recording `verified_by`.

---
*Continues the operator integrity-hardening lane (quarantine-inverse rule, FR-12). General control-plane property; surfaced by the usage-autoimport task's self-verified claims.*
