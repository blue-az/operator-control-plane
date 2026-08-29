# Operator Diff Evidence + Stale-Assignment Detection — Build Spec

**For:** the implementing agent (Claude / Codex / Agy — whichever picks this up).
**Supervisor / spec author:** Claude. **Reviewer:** TBD.
**Target:** extend the existing `operator` CLI at `/home/blueaz/operator-control-plane/operator` (single-file Python, ~7,000 lines, file-backed YAML ledger under `.operator/` with an event-sourced projection layer). Match existing conventions: argparse subcommands, `find_operator_dir`, `load_yaml`/`save_yaml`, `get_next_*_id`, the `doctor` issue-list pattern (`issues`/`infos` lists, `[Error]`/`[Warning]` string prefixes), subprocess-driven tests in `tests/test_operator.py`.

---

## 0. Why this exists (do not skip)

This came out of a three-way comparison of tools evaluated on this machine: Operator, ASK-Claude-Token-Optimizer (a Claude Code token-cost hook optimizer — unrelated concern, nothing adopted from it), and **Bothread** (a live multi-agent coordination room: MCP server, file-leasing, live chat, human overseer, per-agent git diffs for review, capability-declaring agents).

Bothread's live-locking/overseer model does not fit Operator's async, often-unattended, benchmark-integrity use case, and is **explicitly not adopted** — see §5. Two of its ideas transfer without requiring any live session at all, and are the actual content of this spec:

1. **A diff is a stronger evidence artifact than a hash.** Operator's evidence is SHA-256-hashed, which catches drift after the fact but doesn't show a reviewer *what changed*. Bothread's per-agent git diff gives a reviewer something to read hunk-by-hunk.
2. **`doctor` already exists to catch "green but shouldn't be" states** (see repo `CLAUDE.md`: "a green doctor is necessary, not sufficient — check *how* it went green"). A task that's been assigned to a harness with zero claim/evidence/handoff activity for days is exactly that failure mode, and `doctor` currently has no check for it — Bothread's lease-staleness signal is the analog, just checked asynchronously instead of live.

**Explicitly not a fix for the pain point that prompted the comparison** (concurrent-agent git conflicts during high-usage "tokenmaxxing" bursts) — that's solved by running each concurrent agent in its own `git worktree`, a workflow practice, not an Operator ledger change. Out of scope here.

---

## 1. Design principles

1. **Fail open on capture, fail closed on trust.** A failed diff capture (no git, unresolvable base ref) must not block `evidence-attach` — the existing evidence write still succeeds, just without diff fields. This mirrors the existing pattern where a missing repo path on an assigned task is a `[Warning]` in `doctor`, not a hard failure.
2. **Additive, not a replacement.** Diff evidence coexists with hash-based drift detection; it doesn't replace `--hash`.
3. **`doctor` stays read-only.** Staleness is reported via the existing `infos`/`issues` accumulation in `doctor_cmd` — never as an `[Error]`, never as a ledger mutation. `doctor` is an audit script today; this must not change that.
4. **No new top-level ledger concept.** Reuse the existing `evidence_type` enum and the existing `doctor` warning-list pattern rather than inventing new record types or a new subcommand family.

---

## 2. Feature A — `diff` evidence type

### 2.1 Schema change

Add `"diff"` to the `--type` choices list in the `evidence-attach` parser (`operator`, `evidence_parser.add_argument("--type", ...)`, currently: `run_log, manifest, database_query, test_output, git_commit, screenshot, transcript, paper_section, external_doc`).

New evidence-record fields, populated only when `--type diff` (added to the `evidence_data` dict built in `evidence_attach_cmd`, alongside the existing `evidence_type`/`hash`/`notes` fields):

```yaml
evidence_type: diff
diff_base: <git ref or resolved commit sha used as the diff's start point>
diff_stat: "+42 -7 across 3 files"   # from `git diff --shortstat`, stored in the YAML record
# the full diff text is the evidence artifact itself, persisted through the existing
# local-file relocation path (evidence/<task_id>/<evidence_id>.diff) — same flow every
# other local-file evidence type already uses, no new persistence mechanism
```

### 2.2 Command surface

New optional flag on `evidence-attach`: `--diff-base <ref>`.

Behavior when `--type diff`:
- Resolve `<task.repo>` from the task record (already loaded as `task["repo"]`).
- If `--diff-base` given, use it directly. If omitted, resolve the nearest commit at-or-before `task["created_at"]` via `git -C <repo> log -1 --before="<created_at>" --format=%H`; if that also fails (no git repo, no matching commit), print a warning to stderr and attach evidence **without** diff fields rather than aborting (principle 1) — the caller can re-run with an explicit `--diff-base`.
- Run `git -C <repo> diff <base>...HEAD`, write the raw output to the evidence artifact path using the same local-file persistence block already in `evidence_attach_cmd` (the `if os.path.isfile(path_or_url):` relocation logic) — for this type, generate the diff to a temp file first, then let it flow through that same relocation path so hashing/persistence stays uniform with every other evidence type.
- Run `git -C <repo> diff --shortstat <base>...HEAD` for the `diff_stat` summary field.
- Any git subprocess failure (non-zero exit, git missing, timeout) → stderr warning, evidence-attach continues without diff fields. Never a hard error — matches the fail-open behavior the hook scripts in `ASK-Claude-Token-Optimizer/hooks/` use for the same reason (a lower-stakes feature must not be allowed to break a higher-stakes flow).

### 2.3 `doctor` integration

None needed — diff evidence is validated through the same generic hash/path checks `doctor` already runs over all evidence records.

---

## 3. Feature B — stale-assignment detection in `doctor`

### 3.1 Rule

For each task where `assigned_harness` is set and `status` is not in the terminal set `{"verified", "complete", "quarantined"}`:

1. Compute `most_recent_activity` = max of: `task["updated_at"]`, the `made_at` of the task's most recent claim (if any), the `produced_at` of its most recent evidence record (if any), the `created_at` of its most recent handoff (if any).
2. If `now - most_recent_activity > stale_days` (default **3**, overridable), append:
   `infos.append(f"[Warning] Task {task_id} assigned to {assigned_harness} with no claim/evidence/handoff activity in {days_idle} days (last activity: {most_recent_activity})")`

Always an `infos` warning, never an `issues` error (principle 3) — this is informational staleness, not a consistency violation, and matches the existing severity split already used for the repo-path check (`assigned`/active tasks get `[Warning]`, only `verified`/`complete` tasks get `[Error]` on a missing repo).

### 3.2 CLI flag

Add `--stale-days N` (default `3`) to `doctor_parser` (`operator`, next to the existing `--audit` flag).

### 3.3 Tests (`tests/test_operator.py`, subprocess style)

- `test_doctor_flags_stale_assignment`: create a task with `--assign codex`, hand-edit its `tasks/<id>.yaml` to backdate `updated_at` (no claims/evidence/handoffs added), run `doctor --stale-days 0`, assert the warning string is present in stdout.
- `test_doctor_silent_on_fresh_assignment`: create and assign a task, immediately run `doctor` with the default threshold, assert no staleness warning appears.
- `test_doctor_stale_ignored_for_terminal_status`: same as above but task status is `verified`/`complete`/`quarantined` — assert no staleness warning regardless of how old `updated_at` is.

---

## 4. Acceptance criteria

- `evidence-attach --type diff` on a task with a real repo produces an evidence record with populated `diff_base`/`diff_stat` and an artifact file containing the raw diff.
- `evidence-attach --type diff` on a task with no resolvable repo/git state degrades to a normal (non-diff) evidence write with a stderr warning — exit code `0`, not `1`.
- `doctor --stale-days N` flags exactly the tasks whose most recent activity (across task/claim/evidence/handoff timestamps) is older than `N` days, and only for non-terminal-status tasks.
- Existing `doctor` and `evidence-attach` tests in `tests/test_operator.py` continue to pass unmodified.

---

## 5. Out of scope / residual risks (do NOT silently "fix")

- **Blocking/contention primitive** (e.g. `task-block --on <task-id>`), the analog of Bothread's `request_handoff`. Deferred — no observed case yet of a task actually blocked on another task; Operator sees light day-to-day use, so building this ahead of an observed need would be speculative. Revisit only if a real blocked-task scenario shows up.
- **Harness capability declaration + mismatch warning on `task-create --assign`.** Deferred for the same reason. `harnesses/*.yaml` already carries free-text `strengths` / `known_failure_modes`; formalizing that into a structured capability enum with mismatch-checking is premature without an observed real assignment-mismatch incident.
- **Live human-in-the-loop pause/approve** (Bothread's overseer model). Different product shape — a live session concept — not attempted here; Operator's async ledger model is not being changed to support it.
- **git-worktree-per-concurrent-agent workflow.** This is the actual mitigation for the concurrent-agent git-conflict pain point that prompted this whole comparison, but it's an operating practice (or, for Claude-spawned subagents, the `Agent` tool's `isolation: "worktree"` option), not an Operator code change — not part of this spec.
