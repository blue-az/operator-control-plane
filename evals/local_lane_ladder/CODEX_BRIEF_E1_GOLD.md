# Codex brief — Front E next pack under GOLD_STANDARD (plan-shaped)

**From:** Grok (supervisor) · **For:** Codex (implementer)  
**Date:** 2026-08-11  
**Read first (in order):**

1. `evals/local_lane_ladder/GOLD_STANDARD.md` ← **new; binding**
2. `LOCAL_LANE_CONTRACT.md` (R1–R6)
3. `fixtures/e0-desktop-pack-consultant-review/FINDING.md` (E0 is not routability evidence)
4. `docs/LOCAL_LANE_ROUTER_STUDY.md` §5–6 (26b router; proof boundary)

**Do not:** re-run E0 as “Front E data”; merge ledgers; open Front F/G; rewrite Alignerr PDFs into fixtures.

---

## Goal

Scaffold the **first post-E0 Front E pack** that obeys `GOLD_STANDARD.md`, so a later
desktop/3090 run can produce **verified** routability-relevant evidence (or an honest
negative), not another July replay.

## Deliverables (stop when these exist and lint clean)

### D1 — Pack skeleton

Create:

```
evals/local_lane_ladder/fixtures/e1-gold-pack/
  MANIFEST.md      # question, non-goals, models, n, machine, grading rule
  RUN.md           # exact commands to execute on desktop
  tasks/           # 3–6 task YAMLs (prefer reusing existing task defs if still valid)
  grading notes pointer to shared grading.py
```

**MANIFEST.md must state:**

- **Question:** e.g. “On desktop 3090, for plan-shaped (L2) local-lane fixtures, how do
  pass rates compare across gemma4:26b, gemma4:31b, and qwen2.5-coder:14b (or installed
  14b-class), n=3, postcondition-only grading?”
- **Not the question:** “Did harness fixes change July L2?” (already answered: no)
- **Gold standard:** link to `../GOLD_STANDARD.md`
- **Ledger:** run/record on **one** machine; name it (desktop preferred for 3090); do not
  assume z13 ledger has eval history (Front H)

### D2 — Tasks are L2 + Alignerr-style postconditions

Each task YAML must include:

- L2 / plan-shaped prompt body satisfying R1–R6 (or `task_lint` clean if wired)
- **`postcondition`** (or existing grader keys) that a script can check without reading
  model prose
- Optional `trajectory_hint` list (3+ single actions) for humans — not scored as gold

Prefer **reusing** 3 tasks from the main ladder that still have solid postconditions
(`alias_add`, `config_value_change`, `grep_and_report` are E0’s set — OK to reuse **only if**
MANIFEST says this is a **model comparison on L2**, not a harness-fix study, and harness
is post-`890d595`).

### D3 — Grading honesty

- Document that grading uses **deterministic postconditions only** (Alignerr spirit).
- Require **traces retained** (or point to runner flags that keep them) so fails are not
  confounded like pre-890d595.
- If the current `runner.py` cannot retain traces, **stop and report** — do not invent a
  full new harness in this brief; file a blocker note in MANIFEST.md.

### D4 — Models

Default matrix (adjust only if a model is not installed; note in MANIFEST):

| Model | Seat |
|-------|------|
| `gemma4:26b` | fast local / router-class executor |
| `gemma4:31b` | high local tester |
| `qwen2.5-coder:14b` or best **100% GPU** qwen on box | floor |

Do **not** require dual-3090 or 32b-if-spilling for E1. Optional later row: 32b if
`ollama ps` shows 100% GPU for the run.

### D5 — Smoke (required)

On the machine you use for implement:

1. `python -c "import yaml"` / existing runner import smoke
2. Dry-run or single-cell: one task × one model × one trial if cheap; else document
   “run deferred to desktop” with exact `RUN.md` commands
3. Do **not** burn a full matrix unless operator asks

### D6 — Handoff

Write `fixtures/e1-gold-pack/HANDOFF.md`:

- what was created
- what was not run
- any blocker (traces, models missing, Front H)
- suggested operator next: desktop full matrix under Grok/Claude supervise

---

## Explicit non-goals

- Full 216-cell re-sweep
- Router re-implementation
- Committing large binary logs
- Changing `GOLD_STANDARD.md` philosophy without operator note
- “Fixing” E0 by re-labeling it as routability evidence

## Success check

- [ ] `GOLD_STANDARD.md` unchanged unless a factual fix is required (prefer not)
- [ ] `e1-gold-pack/` exists with MANIFEST, RUN, tasks, HANDOFF
- [ ] MANIFEST cites gold standard + non-E0 question
- [ ] Postconditions are machine-checkable
- [ ] No claim that Front E now has verified routability evidence until a matrix is run and verified

## Seat / cost

Codex implementer; keep the pack **S**. Full GPU matrix is a **later desktop** job (free 3090).
