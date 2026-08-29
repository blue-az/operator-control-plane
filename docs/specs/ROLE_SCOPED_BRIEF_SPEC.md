# Operator Role-Scoped Brief Specification

> **P2 Spec.** This document specifies the role-scoping contract for task brief generation, brief variants (builder vs reviewer), auditable brief issuance event recording, and cross-audit enforcement in `doctor`.

**For:** any implementing harness.
**Target:** extend the operator CLI in this repo. Match existing conventions (`VERIFIED_BY_GUARD_SPEC.md`, `EXECUTOR_IDENTITY_SPEC.md`).

---

## 0. Why

The operator enforces that a claim is only trustworthy when verified by a distinct identity (`verified_by` guard under UID isolation). However, `generate_brief_markdown` previously generated identical brief outputs regardless of whether a builder or reviewer harness requested it.

Because brief output contained builder-authored text (the builder's `next_action`, free-text handoff closeouts, and unverified claim text), a reviewer would read the builder's narrative before forming an independent verdict. This created anchoring risk and weakened the cross-audit boundary. Furthermore, brief generation wrote directly to disk without recording events in the event store (`ledger_events`), rendering brief issuance un-auditable by `doctor`.

---

## 1. Role Derivation Rule

`generate_brief_markdown(op_dir, task_id, harness_id, role=None)` derives the role directly from the task record:

- `harness_id == task["review_harness"]` -> `reviewer`
- `harness_id == task["assigned_harness"]` -> `builder`
- **Neither:** fail closed. Brief generation fails and returns `None` / non-zero error.
- **Both:** (`harness_id == task["assigned_harness"]` AND `harness_id == task["review_harness"]`, e.g. `single_user` or self-review): emit the `reviewer` variant and emit a warning to `stderr`. The degraded case degrades toward less information, not more.

---

## 2. Brief Variants

### Builder Variant (`role: builder`)
Unchanged from existing brief generation output. Contains:
1. Objective
2. Active Phase Rules & Constraints
3. Current Task State & Recommended Next Action (`status`, `next_action`, `open_assumptions`)
4. Latest Harness Handoff Closeout (builder narrative)
5. Claims & Verification Gates (full table with `Claim ID`, `Made By`, `Status`, `Type`, `Text`, `Required Gate`)
6. Required Evidence
7. Handoff Guidelines

### Reviewer Variant (`role: reviewer`)
Omits all builder narrative and conclusions, presenting only claims, rubrics, and raw evidence locators for re-derivation.

**Omitted entirely:**
- The Latest Harness Handoff Closeout section
- The `next_action` recommended-action section
- The `text` and `Status` columns of the claims table

**Fenced builder-authored text:**
- Task `open_assumptions` are wrapped in explicit provenance envelopes:
  `<unverified-assertion by="{assigned_harness}">{assumption_text}</unverified-assertion>`

**Claims table output:**
- Columns: `Claim ID`, `Type`, `Required Gate`, `Evidence`
- Per claim: `claim_id`, `type`, `required_gate`, and attached evidence paths with their recorded SHA-256 hashes (`path_or_url (hash: <sha256>)`).
- **Required Evidence section:** Preserved verbatim as the fixed rubric.

---

## 3. Auditable Brief Issuance

All brief file writes are routed through `atomic_write_text`.

Upon generating and writing a brief (via `brief`, `export-brief`, or `session-start`), a durable ledger event of type `brief_issued` is recorded via `append_record_events`:

- `record_type`: `"brief_issued"`
- `record_id`: `"<task_id>/<harness_id>"`
- `payload`:
  ```json
  {
    "task_id": "<task_id>",
    "harness_id": "<harness_id>",
    "role": "<builder|reviewer>",
    "executor_identity": { ... },
    "timestamp": "<iso_timestamp>"
  }
  ```

---

## 4. `doctor` Audit Rule

`doctor` inspects `ledger_events` for `brief_issued` records:

- **Rule:** If a claim's `verified_by` harness was issued a `builder`-role brief for that task, `doctor` flags it as an Error:
  `[Error] claim <cid> verified by '<vby>' who was issued a builder brief for task '<task_id>'`

This prevents a harness that received builder-oriented brief narrative from acting as the verifier for claims on that task.
