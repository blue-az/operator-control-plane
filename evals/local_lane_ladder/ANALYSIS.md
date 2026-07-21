# Local Lane Ladder — first sweep analysis

**Data:** `RESULTS.md` (generated), `state.json` (216 raw trial records).
**Grid:** 6 tasks × 3 levels (L0/L1/L2) × 4 models × 3 trials = 216 cells,
matching `LOCAL_LANE_CONTRACT_SPEC.md`'s stated minimum exactly.
**Models:** `gemma4:26b`, `gemma4:31b`, `qwen2.5-coder:32b`, `llama3.1:8b`.
**Grading:** deterministic only (grep/exec/output-match) — no LLM judging.

This addresses acceptance criterion 4 directly: *"The claim 'pass rate is
monotonic in specificity level' is either confirmed with numbers or
explicitly refuted — a negative result is an acceptable outcome."*

## Aggregate pass rate (all 6 tasks combined, /18 per cell)

| Model | L0 | L1 | L2 |
|---|---|---|---|
| gemma4:26b | 9/18 | 12/18 | 18/18 |
| gemma4:31b | 15/18 | 16/18 | 17/18 |
| qwen2.5-coder:32b | 0/18 | 12/18 | 17/18 |
| llama3.1:8b | 0/18 | 7/18 | **5/18** |

## Verdict: confirmed for 3 of 4 models, refuted for the fourth

**`gemma4:26b`, `gemma4:31b`, `qwen2.5-coder:32b`: monotonic, confirmed.**
Pass rate rises (or holds) at every step from L0 to L2 for all three. This
matches the spec's own founding evidence (the `gemma4:26b`/`31b` alias-add
experiment) and generalizes it across five more tasks and a third,
previously-untested model.

**`llama3.1:8b`: not monotonic — L2 is worse than L1 (5/18 vs 7/18).**
This is a real result, not noise from a single cell — it comes from two
separate tasks both regressing L1→L2:

| Task | L0 | L1 | L2 |
|---|---|---|---|
| function-add | 0/3 | 2/3 | 1/3 |
| grep-and-report | 0/3 | 3/3 | 2/3 |

Plausible reading: `llama3.1:8b` is the smallest model in the sweep (8B vs.
26B+ for the other three), and L2 prompts are longer and more structured
than L1 (an anchor clause, a verification clause, a scope-bounding clause,
numbered steps) — more instruction-following load per prompt. The larger
models all turn that extra structure into a reliable win; for the smallest
model here, past some point the extra structure appears to compete with
capacity rather than substitute for it. This is a hypothesis the current
data supports, not one it proves — 3 trials per cell is enough to see the
regression is real and not a single fluke, but not enough to fully rule out
trial-level variance as a contributor.

**Practical implication for lane routing (informational only — no router
changes made, per the spec's own non-goals):** if this pattern holds up
under more trials, it argues against a blanket "more specific is always
better" heuristic — a genuinely small floor-tier model may have a
complexity ceiling where L1-level specificity is closer to its actual
sweet spot than the fully-anchored L2 form.

## Other notable per-task patterns

**`multi-file-rename-reference` (the spec's designated "hard case") is
genuinely hard, and differently for each model.** `gemma4:26b` needs the
*full* L2 structure to solve it at all (1/3 → 0/3 → 3/3 — L1 alone doesn't
help, and even makes it slightly worse than L0). `qwen2.5-coder:32b` needs
only L1 (0/3 → 3/3 → 3/3). `gemma4:31b` solves it at every level (3/3 across
the board). `llama3.1:8b` never solves it at any level (0/3 → 0/3 → 0/3) —
for this model, the task appears to be beyond a specificity-phrasing fix
entirely, not a prompt-shaping problem.

**A few non-monotonic single-task dips exist even in the "confirmed"
models** (e.g. `gemma4:31b` alias-add: 3/3 → 1/3 → 3/3; `gemma4:26b`
function-add: 3/3 → 1/3 → 3/3) — always recovering by L2, and at n=3 per
cell, plausibly trial-level variance rather than a real L0-beats-L1 effect.
Worth more trials before reading anything into these specifically; they
don't change the aggregate monotonic verdict for those two models.

**`llama3.1:8b` and `qwen2.5-coder:32b` both score 0/18 at L0** — a floor
effect at the goal-only level for both, consistent with the spec's founding
principle (local models fail on degrees of freedom, not knowledge) holding
even more sharply for a coder-tuned model and a small general model than
for the two `gemma4` variants the original experiment used.

## What this does not establish

- n=3 trials per cell is the spec's stated minimum, not a large sample —
  treat single-task, single-model swings as suggestive, not conclusive.
- No claim is made about *why* `llama3.1:8b` regresses at L2 beyond the
  "prompt complexity load" hypothesis above; that would need either more
  trials targeting exactly those two tasks, or inspecting the model's own
  failed-trial transcripts (not currently captured — `opr`'s stdout is
  graded but not archived per-trial).
- No lane-routing changes were made or are implied here — `phoenix_work_router.py`
  is explicitly out of scope per the spec's non-goals.
