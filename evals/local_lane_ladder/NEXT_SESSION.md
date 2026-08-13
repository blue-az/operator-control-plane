# Local-lane eval — next session

**Written:** 2026-08-13, desktop, rev `a244930`, by `claude-01FSgUqu`.
**Read order:** this file → `GOLD_STANDARD.md` → the `FINDING.md` of whichever
pack you touch.

Nine packs, **825 graded cells**, all traced. The instrument works now. This file
says what is settled, what is blocked, and what to do next.

---

## Where it stands

**The seat pick is `gemma4:26b`** — 24/30 on the ceiling battery, tied with
`gemma4:31b` on the postcondition but 1.5x faster, perfectly stable (every cell
0/6 or 6/6 across five fixtures), and reaching 17 of its 24 passes with a clean
trajectory against 31b's 12. Nothing in 825 cells justifies the larger model on
this workload.

Supporting: `qwen3.6:27b` is the only model that solved any `csv-summarize-repair`
cell, so keep it for genuinely messy repair — but gate it, 3 of its 5 fixtures
are coin-flips. `qwen3-vl:30b` is accurate but unsteerable (ignores `--think off`,
~9x the seat pick's latency). Below ~12B is not viable: the floor capability is
carrying an exact literal path.

**Standing run config.** `--num-ctx 16384 --temperature 0.8 --think off`,
`--trace-dir` always, residency sampled. Never `temperature 0` — it is not a
neutral control for agentic loops (`e3`: 1/6 vs 6/6 on the same cell). Seeds are
not honoured by this Ollama build, so cells are independent draws.

---

## 1. BLOCKING — the distinct-UID re-derive

**Nothing here is a registered claim, and nothing should be until this happens.**
It now spans `e1`–`e9`. `MSC-RUL-104`: no session verifies a claim it authored,
and every pack in this programme was authored by one session.

Everything needed is retained: 825 traces, per-cell `state.json`, residency logs,
pre-run provenance, and `FINDING.md` per pack. A verifier should re-derive
postcondition totals, trace completeness, model tags, residency and machine
provenance — then register the E9 result, and only that one.

**Do not register `e1`–`e8`.** They are harness records, not comparisons; each
`FINDING.md` says why.

---

## 2. Retire `booking-off-by-one`, and hold `csv-summarize-repair`

Fixture quality, measured on the same 42 cells each:

| Fixture | Rate | Action |
|---|---:|---|
| `booking-off-by-one` | **42/42** | **Retire or harden.** It looked like E8's sharpest discriminator and was measuring a harness cap. |
| `constant-and-callers` | 36/42 | Keep. Mild but real. |
| `ambiguous-anchor` | 23/42 | Keep — best discriminator in the set. |
| `strict-log-format` | 18/42 | Keep. Trap is the output contract, not the logic. |
| `csv-summarize-repair` | 3/42 | Keep as a **ceiling marker**, do not read as a ranking. |

Already retired earlier: `config-value-change` (6/6 at 3.4B, zero information).
The six original fixtures are all saturated above 14B — `e4` and `e7` between them
established that for every one.

---

## 3. The finding worth acting on: repetition, not knowledge

Two independent instruments agree. Failure-mode classification: **32 of 88**
failures were loop-guard stops. Trajectory rule violations: **`no_blind_repeat`
61**, the largest of any rule. A model reads a file, then re-issues the identical
read instead of advancing.

This is now a **product question rather than an eval question**, and it is the
highest-value open item after the re-derive:

- `opr`'s repeat-guard converts a repeat into a hard stop. Is that the right
  response, or should the harness feed the model back *"you already ran that, its
  output was X"* and let it continue?
- The guard is doing real work — a model re-issuing an identical call *is* stuck —
  but the eval number is "failed to advance state, **given a guard that stops
  repeats**", not "failed to advance state" in the abstract. That caveat should
  not survive into a product decision unexamined.
- Cheap experiment: one fixture, one model, guard-stop vs feed-back-and-continue.

Second-largest signal: `read_before_write` violated 39 times — blind patching is
common, and it is exactly what Batch 5's anti-anchoring rule exists to prevent.

---

## 4. Phase 4 of the plan was never run

Three deterministic instruments already exist and were scoped but not executed:

1. **ShowcaseAgent seam sets** — `hard_cases_extended` + `borderline_cases` +
   `tie_breaker_cases` + `showcase_seam_routing_mini`, 33 queries, exact-match
   graded. Sits at **5/10** and has only ever been run against `llama3.1:8b`.
   Highest information-per-minute available anywhere in this programme.
2. **PTS-001** (`project-phoenix/scripts/pts_001_runner.py`) — the strongest
   single deterministic discriminator on disk (`gemma3:27b` 6/6, `gemma4:31b` 5/6,
   `gemma4:26b` parse_fail). Runner already iterates a fixtures directory; add
   2–3 more fixtures in the same shape.
3. **All 22 PROTO probes**, not the 6 used for the headline — re-baseline first,
   a 2026-04-28 drift addendum shows the old 4/6 already moved to 6/6.

---

## 5. Housekeeping

- **The published report is stale.** `fixtures/e1-gold-pack/OPERATOR_REPORT.html`
  (artifact `728a6afb-965e-406c-a152-c51152d84689`) reflects the `e5` floor
  result and predates `e7`/`e8`/`e9` — it does not contain the ranking, the
  continuation confound, or the trajectory scoring. Republish to the **same URL**.
- **20 pre-existing test failures** in `tests/test_authority_integration.py`,
  unrelated to the ladder, confirmed on a clean tree, never triaged.
- **`python3 -m unittest discover -s tests` now exceeds 5 minutes.** Run focused
  suites (`test_ladder_grading`, `test_trajectory_score`, `test_opr*`,
  `test_task_lint`) unless a full sweep is the point.
- **`nemotron-3.5-lightning`** is a genuine dual-card case: 32.9B at Q4_K_M is
  ~25 GB of *weights*, so no context tuning fits it on one 24 GB card. Distinct
  from `qwen3:32b`, whose spill was KV cache and which fits at `num_ctx ≤ 24576`.

---

## The meta-finding, and the thing to be most careful about

**Six harness confounds were found in this programme, and every one first
presented as a model difference:**

1. greedy brace-span tool extraction (5 of 45 cells, two model families)
2. system prompt gated on `"26b" in model`
3. no sampling or context control at all
4. no `think` control — every model ran with reasoning on
5. `OPR-RUL-008` capping every cell at one state change
6. plus two substring false-positives I introduced *while fixing the above*
   (`etc` inside `src/fetcher.py`; `connection` inside a fixture's "Drain
   connections.")

`multi-file-rename-reference` is the cautionary tale: recorded as the only
fixture ever producing per-model *shape* differences, it scores 6/6 for all
seven models under a fixed harness. The apparent capability ladder was
substantially artifact.

**Working rule for the next session:** when a model difference appears, assume
the harness until the trace proves otherwise. The trajectory parse now makes that
check mechanical rather than a manual read — use it before writing anything down.
