# repo-turns — 26b vs 31b on real Evaluation repos, no agent files

**Status:** pack scaffold. Not run. Not UID-verified. Not a seat claim.

**Hypothesis:** on a foreign repo with `AGENTS.md` / `CLAUDE.md` stripped,
`gemma4:31b` reaches a bounded edit in fewer tool calls than `gemma4:26b`.
That is the informal observation this pack exists to measure. E11 already
tied them on L2 pass/fail (36/54, p=0.49); this is a different instrument
(turns-to-done on a real tree).

**Not dual-card.** Sequential on one 3090 is the same information.

## Repos (5)

Three already have no root agent files. Two are stripped **in the temp copy
only** — live `~/Python/Evaluation` trees are not mutated.

| # | Repo | Agent files in live tree | Why it is in |
|---|---|---|---|
| 1 | `ProjectKitty` | nested `research/gemini/agents.md` only (not a harness file) | Go, Andrii, already clean at root |
| 2 | `code-stick` | none | TS, 8.7k LOC, tests, already clean |
| 3 | `groundtruth` | none | Py, 5.2k LOC, already clean |
| 4 | `ollm` | none | Py, 2.9k LOC, already clean |
| 5 | `bothread` | root `CLAUDE.md` + nested `AGENTS.md` | TS, 12k LOC; strip in copy |

Disposable-if-you-want-to-strip-live: `bothread`, `openwiki`,
`ASK-Claude-Token-Optimizer`, `claude-code-best-practice`. Do not strip
`opencode`, `graphify`, `tau`, `consumer-api-cost`, `kernelCAD-web`,
`pbc-spec`, `nimbalyst`, `ruflo`.

## Method

- Copy each repo into `tempfile` (opr `--eval-auto-confirm` refuses a live tree).
- Drop `node_modules`, `.git`, `dist`, `target`, `__pycache__`.
- Unlink every `AGENTS.md` / `AGENT.md` / `CLAUDE.md` / `GEMINI.md` /
  `.cursorrules` in the copy.
- L1 only (human-typed: names the symbol, not the path). L0 is in the yaml
  for later. No L2 — that is the battery they already tied on.
- Models: `gemma4:26b` `gemma4:31b`. n=3. `num_ctx 16384`, temp 0.8, think off.
- `--continue-steps 2` so a verify after the write is legal. Reads are free
  under OPR-RUL-008; the metric is all tool calls, not writes.

## Metrics

1. **Primary:** `trajectory.n_calls` on passing cells. 31b "wins" only if it
   passes *and* uses fewer calls.
2. **Gate:** deterministic postcondition (grep / all_of). A cheap wander
   that never edits does not win.
3. **Reported, not ranked:** wall-clock (26b is 3.9× faster — do not
   launder that as fewer turns), `n_failed_calls`, `stopped_repeat`.

A 54/54 this is not. 5 repos × 2 models × 3 = 30 cells.

## Run

```bash
cd /home/blueaz/operator-control-plane/evals/local_lane_ladder
python3 run_repo_turns.py --dry-run
python3 run_repo_turns.py \
  --models gemma4:26b gemma4:31b \
  --trials 3 --num-ctx 16384 --temperature 0.8 --think off --no-ledger \
  --trace-dir fixtures/repo-turns/traces
```
