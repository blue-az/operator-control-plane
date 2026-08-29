# Operator `verified_by` Guard — Build Spec

> **Historical P1 spec.** This document preserves the original string-level guard contract.
> [`EXECUTOR_IDENTITY_SPEC.md`](EXECUTOR_IDENTITY_SPEC.md) is the current authority for roles,
> executor binding, distinct-UID isolation, and advisory verification. Where the two differ, the
> executor-identity spec supersedes this file.

**For:** any implementing harness. **Reviewer:** a distinct verifier identity selected for the task.
**Target:** extend `the operator CLI in this repo`. Match existing conventions.

---

## 0. Why (general integrity, not the bake-off)

The operator's core task model is `assigned_harness` (builder) + `review_harness` (reviewer). Right now a claim's `verification_status` can be flipped to verified by **anyone** — including the claim's own maker — and the ledger doesn't record *who* verified it. That makes `VERIFIED` untrustworthy for **every** task (domains, papers, deploys, audits), not just any one experiment. Concretely: `claim-0007`/`claim-0008` were made *and* verified by `gemini-agy`; nothing caught it.

This P1 guard closed the **default self-verification footgun** and made the verifier string auditable.
It did not attempt executor identity or roles. P2 subsequently added those controls under the
distinct-UID boundary defined in `EXECUTOR_IDENTITY_SPEC.md`.

---

## 1. Schema change (claim records, `.operator/claims/claim-*.yaml`)
Add one field:
```yaml
verified_by: <actor|null>   # who set a terminal verification status; null = not yet / legacy
```

## 2. Command change — `evidence-attach`
- Add arg `--verified-by ACTOR`.
- When `--status` is supplied (`verified|false|quarantined`):
  - record `claim["verified_by"] = args.verified_by` in `single_user`; in `enforced`, require the
    assertion to match the registered executing verifier and record the registry name.
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
- "**Builders attach evidence but do NOT set `--status`.** Register claims and attach evidence (`evidence-attach --claim ... --by <you>`). Leave verification to a distinct verifier identity."
- "**Only the verifier verifies**, with `evidence-attach --status verified --verified-by <reviewer>`."

## 5. Tests (`tests/test_operator.py`, subprocess style — no fixtures needed, pure ledger logic)
1. **self-verify blocked by doctor:** task(assign=codex, review=claude); claim made_by codex; `evidence-attach --status verified --verified-by codex` → `verified_by==codex`; `doctor` → `[Error]` self-verified, exit 1.
2. **reviewer verify clean:** same claim, `--verified-by claude` → `doctor` clean (exit 0).
3. **wrong verifier warns:** `--verified-by gemini-agy` (≠ review_harness claude) → `doctor` `[Warning]`, no Error from this rule.
4. **missing --verified-by rejected:** `evidence-attach --status verified` (no `--verified-by`) → exits non-zero with the required-arg error; claim unchanged.
5. **legacy is Info, not failure:** hand-write a claim with `verification_status: true` and no `verified_by` → `doctor` prints `[Info]` and exits **0**.
6. existing `tests/test_operator.py` still passes; `operator doctor` clean on the live ledger (the legacy `claim-0007/0008` land in the Info branch).

## 6. Historical P1 exclusions
- Roles and executor identity were excluded from P1 and added later by P2. ACL provisioning remains
  out of scope.
- No auto-backfill of legacy `verified_by`.
- Do not change quarantine/verified status semantics beyond recording `verified_by`.

---
*Continues the operator integrity-hardening lane (quarantine-inverse rule, FR-12). General control-plane property; surfaced by the usage-autoimport task's self-verified claims.*
