# Operator Orchestration Repair and FastFoodAgent Crossed-Seat Study

## Summary

Create a reusable, no-copy/paste Operator study runner, then use it for two blinded crossed runs:

- Row A: Claude Code supervises; Agy implements.
- Row B: Agy supervises; Claude Code implements.
- Codex performs the end-to-end meta-review after its tokens reset.
- Grok independently cross-checks Codex after its tokens reset.
- Erik retains final V&V authority.

This compares complete model + harness + role seats, not models in isolation.

First execution action: save this plan verbatim as docs/FASTFOOD_CROSSED_SEAT_STUDY_PLAN.md. If another agent commits this Codex-authored plan, its commit message must disclose the committing agent and
any compression.

## 1. Repair Operator First

### Headless harness adapters

Refactor OPR's subprocess logic into a shared typed adapter module used by both opr and the study runner.

- Replace shell command templates with argument arrays and explicit prompt transport; never use shell=True or interpolate prompts into shell strings.
- Ship explicit headless profiles:
    - Claude: claude -p --output-format json
    - Agy: agy -p --print-timeout 30m
    - Codex: codex exec - --json --ephemeral
    - Grok: grok --prompt-file <file> --output-format json --no-subagents --no-memory

- Add role profiles:
    - supervisor and judge: read-only/plan mode.
    - implementer: edit-enabled inside its disposable worktree.

- Resolve and freeze the actual model identifier, CLI version, adapter arguments, and workspace before hashing a study plan. Abort if the selected model cannot be resolved.
- Treat nonzero exits, malformed structured output, timeout, missing executable, and quota exhaustion as distinct states. Preserve raw stdout/stderr; never turn stderr into apparent success.
- Correct Agy's current nonexistent antigravity fallback.
- Preserve legacy string configuration as deprecated argv parsing, without shell execution.

### Reusable unprivileged study runner

Add these Operator commands:

operator study-plan --plan <json>
operator study-run --plan-digest <sha256> --run-id <id> [--approve-phase <phase>]
operator study-status --run-id <id>
operator study-resume --run-id <id> [--approve-phase <phase>] [--acknowledge-quota-reset]

The runner must:

- Store digest-bound plans and checkpointed runs beneath .operator/studies/.
- Use a closed phase vocabulary: preflight, supervisor design, implementation, validation, supervisor review, repair, final verdict, blinding, judge, export.
- Reject arbitrary executables and shell strings in study plans.
- Require separate approval for each implementation or repair phase.
- Resume completed phases idempotently after interruption.
- Stop in waiting_quota without penalizing the harness; resume only after explicit acknowledgement.
- Open and close ordinary Operator sessions for every harness invocation.
- Import Claude/Agy/Codex usage by exact session ID when available and otherwise by the phase's nonoverlapping time window. Missing usage remains null, never estimated.
- Record raw transcripts, diffs, validator output, timing, CLI/model snapshots, repair packets, and verdicts as evidence.
- Detect any supervisor/judge filesystem change and invalidate that row.
- Detect writes outside the allowed implementation paths, validator changes, substrate changes, web access, or subagent use and classify them as benchmark-integrity violations.

### Meta-supervision integrity

Replace the dormant doctor --audit block with ledger-native checks for supervision_credit claims:

- Require a named supervision layer.
- Require evidence for verified supervision claims.
- Reject self-verification.
- In audit mode, treat mismatch with the task's registered review harness as an error.
- Remove the abandoned assumption that verdicts live under a hard-coded DBB directory.
- Correct the historical Phoenix document that claimed doctor --audit provided extra assurance when that code path was a no-op.

Do not change session-start; retain its current copy/paste behavior for compatibility. The new runner is the automated path.

## 2. Freeze the FastFoodAgent Packet

Use NYC DOHMH's historical MenuStat dataset as the authoritative substrate. It contains chain menu items, calories, protein, sodium, categories, and longitudinal identifiers; it is historical rather than
a claim about current menus. NYC MenuStat dataset (https://catalog.data.gov/dataset/dohmh-menustat-historical), MenuStat methodology (https://www.menustat.org/methods-for-researchers).

Deterministic substrate preparation must:

- Download the official CSV once, record URL, retrieval date, byte count, and SHA-256.
- Select the maximum available year.
- Normalize the required fields into a read-only SQLite database:
  item_id, year, restaurant, item_name, category, calories, protein_g, sodium_mg, kids_item, and shareable.

- Exclude beverages and rows missing positive calories, protein, or sodium.
- Produce a frozen database, schema manifest, row counts, and source-provenance report.
- Give both rows byte-identical scaffold and database hashes.
- Abort before model use if schema expectations or hashes fail.

The public hook is nutritional efficiency, not price:

> Which fast-food items provide the most protein within a 600-calorie budget, and what sodium accompanies that efficiency?

Required deterministic domain capabilities:

- Item lookup by chain/name/category.
- Top items under a calorie budget, with optional protein and sodium constraints.
- Protein-per-100-calorie ranking, ordered by ratio descending, sodium ascending, then restaurant and item name.
- Chain comparison using eligible-item medians and a minimum sample-size guard.
- A deterministic protein/calorie/sodium Pareto frontier.
- A provenance response that states the dataset year and historical limitation.
- JSON output plus a short Markdown consumer report; no individualized health advice.

The FDA requires covered large chains to disclose calories and make additional nutrition information available, which supports the consumer relevance without making MenuStat current. FDA menu-labeling
requirements (https://www.fda.gov/food/nutrition-food-labeling-and-critical-foods/menu-labeling-requirements).

## 3. Run the Two-Row Crossed Experiment

Create detached disposable worktrees from one pinned Project Phoenix commit:

/tmp/operator-study-FFSI-001/row-a
/tmp/operator-study-FFSI-001/row-b

Interleave phases symmetrically:

1. Claude produces Row A's supervisor design.
2. Agy produces Row B's supervisor design.
3. Agy implements Row A from Claude's design.
4. Claude implements Row B from Agy's design.
5. Run identical deterministic validators on both.
6. Each original supervisor reviews its assigned implementation.
7. Permit at most two supervisor-requested repair loops per row, each separately approved.
8. Run final validators and obtain structured supervisor verdicts.
9. Seal both evidence bundles before any judge sees them.

Use fresh headless sessions with complete phase packets rather than conversational continuation. Neither row may see the other row's artifacts.

Required validators:

- Import and compile checks.
- Frozen database hash and row-count verification.
- Tool-registry and schema checks.
- Golden tests for all five required capabilities.
- Ordering and tie-break tests.
- Missing/null/boundary input tests.
- Original-repository cleanliness and allowed-path diff audit.
- First-pass and final outputs preserved separately.

Stop or invalidate a row when:

- The supervisor or judge changes files.
- Substrate or validators change.
- The implementer writes outside the declared domain path.
- A harness uses web access or subagents.
- More than two repair loops are required.
- The model identity changes mid-run.
- Required evidence cannot be preserved.

Quota exhaustion and transport failure pause the run; they do not count as model failure.

## 4. Blind Judging and Reporting

Generate an identity-scrubbed A/B package after both rows are sealed.

- Assign blinded labels deterministically from the study-plan digest.
- Strip harness names, model names, session IDs, worktree paths, timestamps, and stylistic supervisor signatures where practical.
- Include code, diffs, first/final validators, repair history, and supervisor artifacts.
- Withhold timing and token totals until quality scoring is complete.
- Verify blinding using automated forbidden-string searches.

Judging order:

1. Codex scores both blinded rows and creates an end_to_end supervision claim.
2. Grok independently scores the same packet and verifies or challenges Codex's claim.
3. Erik performs final V&V and authorizes unblinding.

Judge rubric:

- Deterministic correctness: 40%.
- Scope and substrate integrity: 20%.
- Maintainability: 15%.
- Supervisor usefulness: 15%.
- Evidence and claim calibration: 10%.

Judges return structured scores, A/B/tie, confidence, and artifact citations. They cannot override failed deterministic gates.

After unblinding, report:

- First-pass and final validator status.
- Repair and intervention counts.
- Wall time by role.
- Imported token/usage measurements by role, with missing values explicit.
- Quality judgments before efficiency data.
- No generalized "Claude beats Agy" conclusion from two rows; report only the observed seat-by-role result.

Store the completed packet under docs/domain_runs/FFSI-001/.

## 5. Tests and Execution Gates

Before spending experimental tokens:

- Unit-test every adapter with fake CLI executables.
- Test nonzero exit, timeout, malformed output, quota pause, missing executable, prompt injection, and path escape.
- Test plan hashing, altered-plan rejection, checkpoint replay, crash recovery, and separate mutation approvals.
- Test supervisor-write and validator/substrate mutation detection.
- Test doctor --audit supervision-credit enforcement.
- Run a complete two-row fake-harness study through blinding and export.
- Confirm both source repositories are clean; Operator currently has two unpushed commits, so obtain user confirmation before pushing or layering new work onto that baseline.

After deterministic tests pass, run one explicitly approved trivial read-only smoke call through Claude and Agy. Only then begin FFSI-001.

Token scheduling:

- Preserve Claude/Agy capacity until deterministic infrastructure tests pass.
- Complete the crossed rows before the Agy subscription expires.
- Seal the rows if Codex or Grok remains quota-blocked.
- Resume only the blinded judge phases after their token resets.
