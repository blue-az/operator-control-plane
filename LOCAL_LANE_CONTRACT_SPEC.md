# Local Lane Contract Spec (task shaping for local models)

Status: SPEC — not yet implemented. Written 2026-07-02.
Implementation target: a fresh agent with no prior context. Everything needed is in this file
plus the referenced code. Read this repo's `AGENTS.md` before starting.

## Purpose

Local models routed through `opr` fail **goal-shaped** tasks but succeed **plan-shaped** ones.
This spec defines (1) a written contract for what "plan-shaped" means, (2) a deterministic
linter that checks a task prompt against that contract, and (3) an eval ladder that measures,
per model, how much task specificity is required — so lane routing can be evidence-based
instead of vibes-based.

Operating principle the whole spec rests on: **local models fail on degrees of freedom, not
knowledge.** Every hop where the model must decide what to do next (which file? which tool?
am I done?) is an opportunity to loop or stall. Pre-making those decisions converts search
into lookup. Frontier models supply their own search; local models need it supplied.

## Evidence (2026-07-02, n=1 per cell — the eval ladder exists to firm this up)

Experiments run via `opr` (REPL mode) against the user's dotfiles repo, task: "add an alias
`200` for `sudo nvidia-smi -pl 200`":

- **gemma4:26b, goal-shaped** ("please change my alias file. Add 200 for ..."): called
  `list_dir .`, received the listing, then repeated the identical `list_dir` call and was
  stopped by opr's loop guard. Never reached step 2 of discovery. FAIL.
- **gemma4:31b, goal-shaped**: also failed (different failure mode).
- **gemma4:31b, plan-shaped** (file named): used `grep_search` to locate
  `bash/.bash_aliases:111: alias nv='nvidia-smi'`, then issued a correct anchored
  `patch_file` (target_content = the unique existing alias line, replacement = that line plus
  the new alias). PASS — clean surgical edit.
- Corroborating: gemma4:31b completed a full multi-step OpenWiki `--init` docs run (discovery
  → plan file → writes → cleanup) under OpenWiki's ~80-line process-discipline system prompt.
  Same model that fails unscaffolded discovery succeeds when the process is dictated.

## Context: the code this builds on

- `opr` (this repo, and the live original at
  `/home/blueaz/Python/project-phoenix/scripts/opr`): governed LLM CLI. Tools exposed to the
  model: `read_file`, `write_file`, `patch_file`, `run_command`, `list_dir`, `grep_search`,
  `tree_dir`. Terminal tools (`write_file`, `patch_file`, `run_command`) require interactive
  `[y/N]` confirmation. Sessions are tagged into the operator ledger with `lane`
  (`local` / `frontier_author` / `frontier_driver`) and `task_class` (`bounded` / `hard`).
- `phoenix_work_router.py` (project-phoenix): routes tasks to
  `lane_0_deterministic` / `lane_1_local_repair` / `lane_2_local_strict` /
  `lane_3_strong_model`. The contract score from this spec is a natural future routing input,
  but **do not modify the router in this work** (see Non-goals).
- Local inference: Ollama at `http://localhost:11434`. Relevant models installed:
  `gemma4:26b`, `gemma4:31b`, `qwen2.5-coder:32b` (expected best-in-class here: coder-tuned
  tool calling), plus smaller ones for floor-finding (`qwen2.5:14b`, `llama3.1:8b`).
- `USAGE_LANE_TAGGING_SPEC.md` (this repo): how lane/task_class tagging works in the ledger.

## Deliverable 1 — the contract (`LOCAL_LANE_CONTRACT.md`)

A short prose document, rules numbered for citation. A task prompt is **contract-compliant**
when it satisfies R1–R6:

- **R1 — Exact paths.** Every file to be read or modified is named by exact repo-relative
  path. No "my alias file", no "the config".
- **R2 — Anchored edits.** Every modification specifies an anchor: a unique, verbatim
  fragment of existing file content to patch against (maps directly to `patch_file`
  `target_content`). Appends specify the anchor line to append after, or state
  "append at end of file".
- **R3 — One tool call per step.** The task is an ordered list of steps, each executable as a
  single tool call. No step requires the model to choose between tools or invent a substep.
- **R4 — Explicit success criterion.** The task states a machine-checkable postcondition
  ("the file now contains the line X"; "command Y exits 0") so the model can self-terminate
  and the grader can verify.
- **R5 — Imperative, closed vocabulary.** Commands, not goals. No negations doing load-bearing
  work, no "figure out", "appropriately", "as needed", "etc."
- **R6 — Bounded scope.** The task enumerates every file that may be touched. Anything else
  is out of bounds.

Each rule gets 2–3 sentences of rationale tied to the failure mode it prevents (R1/R3 prevent
discovery loops — the gemma4:26b failure; R2 prevents misplaced edits; R4 prevents
non-termination wandering).

## Deliverable 2 — the linter (`task_lint.py` + `opr lint` surface)

A deterministic checker (no LLM calls) that takes a task prompt (string or file) and emits
per-rule PASS/FAIL/WARN plus an overall verdict: `plan-shaped` (all R1–R6 pass),
`semi-shaped` (R1 passes, others mixed), `goal-shaped` (R1 fails).

Heuristics, not NLU — accept imperfection, bias toward WARN over FAIL when unsure:

- R1: prompt contains at least one path-like token (`[\w.-]+/[\w./-]+` or a known-extension
  filename) for a task that mentions changing/creating anything; words like "my X file",
  "the config" with no path ⇒ FAIL.
- R2: for edit-verbs (add/change/replace/insert/patch), presence of a quoted verbatim anchor
  or an "after the line …" / "append at end" clause ⇒ PASS; edit-verb with no anchor ⇒ FAIL.
- R3: numbered/bulleted steps ⇒ PASS; single-sentence multi-verb tasks ⇒ WARN.
- R4: presence of a verification clause ("should now contain", "verify", "exits 0") ⇒ PASS,
  else FAIL.
- R5: flag ban-list tokens ("figure out", "appropriately", "as needed", "somehow", "etc").
- R6: "only touch/modify the files listed" clause or every mentioned path unique ⇒ PASS,
  else WARN.

CLI: `task-lint <file|-> [--json]`. Exit 0 = plan-shaped, 1 = semi, 2 = goal-shaped.
Unit tests: the three evidence prompts above land in the right buckets (the 26b goal-shaped
prompt ⇒ `goal-shaped`; the successful parsed prompt ⇒ at least `semi-shaped`), plus ~10
synthetic cases per rule.

## Deliverable 3 — the eval ladder (`evals/local_lane_ladder/`)

The measurement instrument. Grid: **task × specificity level × model**.

Specificity levels (same underlying task, three phrasings):

- **L0 goal-shaped** — intent only: "add an alias 200 for sudo nvidia-smi -pl 200 to my
  alias file"
- **L1 file-named** — L0 plus exact path(s): "...in `bash/.bash_aliases`"
- **L2 plan-shaped** — fully contract-compliant: path + anchor + steps + success check

Task suite (6–10 tasks, each defined in a YAML file with the three phrasings, fixture repo
setup, and a deterministic postcondition):

1. alias-add (recreates the original experiment)
2. config value change (edit a key in a small INI/YAML)
3. function-add (add a pure function to an existing Python module)
4. doc fix (correct a stale command in a README)
5. multi-file rename reference (update an import after a file moved — hard case)
6. grep-and-report (read-only: find and quote a value — no writes, tests discovery alone)

Fixture: a purpose-built throwaway git repo generated by the runner in a temp dir per trial
(a few dirs deep, ~15 files, distractor files present — discovery must be non-trivial at L0).
Never run against a real repo.

Runner requirements:

- Drive the same tool loop `opr` uses. If `opr` has no non-interactive mode, add an
  `--eval-auto-confirm` flag that auto-confirms terminal tools **only when the workspace root
  is under the runner's temp directory** — hard-fail otherwise. Do not weaken confirmation
  for normal use.
- Caps per trial: max 15 tool calls, 10-minute wall clock, existing loop-guard stays on.
- Grading is deterministic only: run the task's postcondition (grep/exit-code) against the
  fixture after the trial. No LLM judging.
- ≥3 trials per cell (local models are high-variance; single trials mislead — see Evidence).
- Record each trial into the operator ledger (`lane=local`, `task_class=bounded`) with model,
  task, level, pass/fail, tool-call count, wall-clock. Follow `USAGE_LANE_TAGGING_SPEC.md`.
- Output: a markdown results matrix (rows = model, columns = L0/L1/L2, cells = pass rate)
  written to `evals/local_lane_ladder/RESULTS.md`.

Models for the first sweep: `gemma4:26b`, `gemma4:31b`, `qwen2.5-coder:32b`, `llama3.1:8b`
(floor). Expected-but-unproven gradient: pass rate rises monotonically with level for every
model; the 26b/31b gap shows mainly at L0/L1. The eval exists to confirm or kill this.

## Deliverable 4 — wiring (small)

- `opr` prints the lint verdict when dispatching to a local lane: one line, e.g.
  `[contract: goal-shaped — local models likely to flail; consider L2 phrasing or a frontier lane]`.
  Warning only. **No routing changes.**
- README section in this repo linking contract → linter → ladder.

## Phases (implement in order; each lands independently)

1. **Phase 1 — contract + linter + tests.** Pure deterministic Python, no model calls.
   Smallest reviewable unit; everything else depends on the rule definitions stabilizing here.
2. **Phase 2 — ladder: fixtures, runner, grading, first sweep.** Needs Phase 1 (L2 prompts
   must lint clean; L0 must lint goal-shaped — the linter validates the eval's own inputs).
   Produces RESULTS.md + ledger records.
3. **Phase 3 — opr lint surface + README.** Trivial after Phase 1; do last.

## Hardware constraints (will bite you if ignored)

- The 3090 must be power-capped before any sweep: check
  `nvidia-smi --query-gpu=power.limit --format=csv,noheader`; if it reads above 200 W, stop
  and ask the user to run `sudo nvidia-smi -pl 200` (uncapped sustained load crashes the
  machine — marginal PSU). The cap resets on reboot.
- `gemma4:31b` uses ~23.9/24 GB VRAM. Run one model at a time; `ollama ps` to check what is
  resident. Sweeps are slow at 200 W (~minutes per trial for 30B models) — budget accordingly
  and make the runner resumable (skip cells already recorded in the ledger).

## Non-goals

- No changes to `phoenix_work_router.py` or any project-phoenix routing/lane policy.
- No LLM-based grading or LLM-based linting — determinism is the point.
- No goal→plan "compiler" (frontier model rewriting L0 tasks into L2). Deliberately deferred:
  the ladder must first establish that L2 phrasing is what buys the pass-rate delta.
- No prompt tuning of the local models themselves (system-prompt scaffolding a la OpenWiki is
  a separate, complementary lever — out of scope here).

## Acceptance criteria

1. `task-lint` classifies the three evidence prompts correctly (unit-tested).
2. Ladder sweep completes for ≥4 models × ≥6 tasks × 3 levels × ≥3 trials with zero manual
   confirmations and zero writes outside temp fixtures.
3. RESULTS.md matrix exists; every trial has a ledger record with lane/task_class tags.
4. The claim "pass rate is monotonic in specificity level" is either confirmed with numbers
   or explicitly refuted in RESULTS.md — a negative result is an acceptable outcome.
5. `opr` shows the one-line lint verdict on local-lane dispatch; behavior otherwise unchanged.
