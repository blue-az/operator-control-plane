# USAGE_ROLE_TAGGING_SPEC

Tag usage/session records with the **role** (`builder` / `reviewer`) the harness held on that task, so
cost can be rolled up by role, not just by harness identity or model.

## Motivation

`usage-summary` currently groups by `--by-harness` / `--by-model` (and, per `USAGE_LANE_TAGGING_SPEC.md`,
`--by-lane`). It cannot answer *"how much did building cost vs. reviewing across the bake-off?"* — a task's
`assigned_harness` (builder) and `review_harness` (reviewer) already exist on the task record, and
`generate_brief_markdown` already derives a builder/reviewer role from them (see
`ROLE_SCOPED_BRIEF_SPEC.md` §1), but that derivation is inlined in one function and never reaches the
usage ledger. This spec reuses the same derivation for usage records instead of re-deriving it ad hoc.

**Prerequisite refactor:** factor the inline role logic in `generate_brief_markdown` (operator:~4326-4341)
into a shared helper:

```python
def derive_role_for_task(task: dict, harness_id: str) -> str:
    """Returns 'builder', 'reviewer', 'both', or 'unassigned'. Never raises."""
```

`generate_brief_markdown` keeps its own fail-closed-on-neither / degrade-to-reviewer-on-both behavior at
the call site (that's a disclosure-boundary decision specific to briefs, see Non-goals below) — only the
lookup itself moves into the shared helper, both call sites read `task["assigned_harness"]` /
`task["review_harness"]` through it.

## Schema (additive, backward-compatible)

Add to usage/session records:

- **`role`**: `builder` | `reviewer` | `both` | `unassigned`
  - `both` — `harness_id` is both `assigned_harness` and `review_harness` for the task (e.g. `single_user`
    mode or deliberate self-review). Unlike the brief-generation degrade-to-`reviewer` rule, usage tagging
    reports `both` plainly — a usage record isn't a disclosure boundary, so there is no anchoring risk to
    guard against by hiding information.
  - `unassigned` — `harness_id` matches neither field (ad hoc usage, reassigned task, no task association).
    Never dropped from `usage-summary` totals, mirroring `USAGE_LANE_TAGGING_SPEC.md`'s
    fail-open-on-absence rule — surface the gap, don't hide it.
- `field_sources.role: auto | manual`, same provenance mechanism as every other field in
  `USAGE_AUTOIMPORT_SPEC.md` §2.

## CLI changes

- `usage-import` / `usage-add` / `session-start`: auto-populate `role` via `derive_role_for_task(task,
  harness_id)`, `field_sources.role = auto`.
- `usage-annotate <id> --role {builder,reviewer,both,unassigned}`: manual override, tags
  `field_sources.role = manual`. Manual wins for display/summary purposes; the auto value is retained
  (same retain-don't-clobber rule as every other manual override).
- `usage-summary --by-role`: cost + token totals per role, composable with `--by-lane` / `--metering`
  (e.g. `--by-role --metering` shows role rollups within each metering block).

## doctor integration (new rule, advisory only)

- **`[Warning] stale role tag`**: a usage record's stored `role` no longer matches
  `derive_role_for_task(task, harness_id)`'s current result for that task (the task's `assigned_harness` /
  `review_harness` changed after the usage record was written) — **and** `field_sources.role == auto`.
  Never fires against a `manual` role (a manual override is an intentional statement, not staleness).
  Advisory only; does not fail `doctor`'s exit code beyond existing warning semantics.

## Non-goals

- **Not an access-control or disclosure signal.** A `role` tag on a usage record grants nothing and
  reveals nothing about brief content — it is a cost-attribution label only. The brief-generation
  fail-closed / degrade-to-reviewer behavior in `ROLE_SCOPED_BRIEF_SPEC.md` is unchanged and unrelated.
  Deriving them from the same helper is a DRY convenience, not a merger of the two concerns.
- **Not a behavioral audit.** `role` reflects the task's role assignment at tagging time — it says nothing
  about what the harness actually did in that session (a `reviewer`-tagged session could contain code
  written by that harness). See the honest caveat below.
- **No auto-detection for `unassigned` → a guessed role.** A record with no task association, or whose
  `harness_id` matches neither field, stays `unassigned`; never inferred from `--task-id`-less context.

## Verification (verify-by-running)

- Fixture task with `assigned_harness=codex`, `review_harness=claude` → import usage for both harnesses →
  `codex` role = `builder`, `claude` role = `reviewer`.
- Fixture task with `assigned_harness == review_harness == claude` (self-review / `single_user`) → role =
  `both`, not silently collapsed to `reviewer` (explicit divergence from the brief-generation rule —
  assert this in the test so a future refactor doesn't accidentally unify the two behaviors).
- `usage-import` against a task with no `assigned_harness`/`review_harness` set → `role = unassigned`,
  still appears in `usage-summary --by-role` totals (not dropped).
- doctor fixture: import usage as `builder`, then flip the task's `assigned_harness` to a different
  harness, rerun `doctor` → `[Warning] stale role tag` fires. Set the same usage record's role manually
  via `usage-annotate --role` first → rerun `doctor` → warning does not fire (manual wins).
- Existing `tests/test_operator.py` and `operator doctor` on the live ledger stay clean.

## Honest caveat

`role` is routing provenance derived from the task record, not a measurement of what happened in the
session. A harness tagged `reviewer` that used its turn to draft code anyway will still show as
`reviewer` in cost rollups — this spec answers "which lane was the spend routed through," not "what was
the spend actually used for."
