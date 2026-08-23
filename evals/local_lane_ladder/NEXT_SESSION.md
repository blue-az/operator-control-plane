# Local-lane eval — next session

**Written:** 2026-08-13, desktop, rev `a244930`, by `claude-01FSgUqu`.
**Read order:** this file → `GOLD_STANDARD.md` → the `FINDING.md` of whichever
pack you touch.

Nine packs, **825 graded cells**, all traced, **independently re-derived by a
distinct UID**. The instrument works and its numbers are verified. This file says
what is settled and what to do next.

**Top of the queue is now item 3 — the repetition finding** — since the re-derive
that used to block everything is closed.

---

## Where it stands

**The seat pick is `gemma4:26b` on both chips (RTX 3090 and Ryzen AI MAX 390).** — 24/30 on the ceiling battery, tied with
`gemma4:31b` on the postcondition but 1.5x faster, perfectly stable (every cell
0/6 or 6/6 across five fixtures), and reaching 17 of its 24 passes with a clean
trajectory against 31b's 12. Nothing in 825 cells justifies the larger model on
this workload.

**`qwen3.6:35b` is on both machines** (2026-08-17). Desktop: 86.4 t/s,
4% lip, E9 **14/30**. z13: **59.2 t/s, 100% GPU at 32k**, E9 **18/30**
vs same-run 26b **24/30** (`q36-35b-e9-z13`). Inversion: 35b is faster
than 26b on z13 and slower on the 3090. Seat unchanged. Power on z13
was AC/`balanced`/`powersave` (no sudo for `performance`).

Supporting: `qwen3.6:27b` is the only model that solved any `csv-summarize-repair`
cell, so keep it for genuinely messy repair — but gate it, 3 of its 5 fixtures
are coin-flips. Below ~12B is not viable: the floor capability is carrying an
exact literal path.

`qwen3-vl:30b` is the image grader (paper 1.37 / Comfy stills), not a seat.
Do not put it on Elo or L0–L2 tables. Packs: `fixtures/vl-smoke`,
`fixtures/vl-casestudy`. Rule: `GOLD_STANDARD.md` “Out of field.”

**Standing run config.** `--num-ctx 16384 --temperature 0.8 --think off`,
`--trace-dir` always, residency sampled. Never `temperature 0` — it is not a
neutral control for agentic loops (`e3`: 1/6 vs 6/6 on the same cell). Seeds are
not honoured by this Ollama build, so cells are independent draws.

---

## 1. ~~BLOCKING~~ — the distinct-UID re-derive is DONE (2026-08-13)

**Closed.** Verified by **uid 971 (`operator-builder`)**, `verification_authority:
uid_isolated`, `verification_mode: enforced`, via `rederive_pack.py`.

**The E9 ranking re-derived exactly** — `claim-0020`:

> gemma4:31b 24/30, gemma4:26b 24/30, qwen3.6:27b 19/30, qwen3-vl:30b 16/30,
> qwen2.5-coder:14b 14/30, qwen3:32b 13/30, gemma3:27b 12/30 (overall 122/210)

Independent totals match the authored ones cell for cell. Coverage across
`claim-0015`…`claim-0023`: `e1` 25/27, `e4` 62/63, `e5` floor totals, `e6` on
72/72 and off 72/72, `e7` 126/126, `e8` 55/210 (freeze integrity only — its
`FINDING` records the `OPR-RUL-008` confound and E9 supersedes it as the
ranking), `e9` 122/210.

Two things worth carrying forward, because both are the process working rather
than incidental:

- **`claim-0014` came back `false`** and was superseded by `claim-0018`: its
  `required_gate` was free text rather than a filesystem path, so the gate was
  not machine-checkable. The first filing was rejected on form, not on substance,
  and redone correctly. That is the ledger refusing an unverifiable claim.
- **The verification ran on z13 against desktop-produced artifacts.** That is
  stronger than same-machine verification, not weaker — a different UID *and* a
  different host, made possible because the traces sync by git while `.operator/`
  deliberately does not (Front H). The claims record `machine: z13` for the
  executor and "Producer desktop" in the text, so the split is explicit rather
  than blurred.

**Consequence:** the E9 ranking is now registered evidence, not an authored
assertion. `e1`–`e8` remain harness records — `e8`'s claim is scoped to freeze
integrity precisely so it cannot be mistaken for a ranking.

**Read the re-derive on disk, not in a ledger.** The verifier committed its own
artifacts, so they sync by git and are the portable record:

- `evals/local_lane_ladder/REDERIVE_E1_E9.md` — span aggregate, `Verdict: PASS`
- `fixtures/<pack>/REDERIVE.md` — per-pack, all six `PASS`, `mismatches=0`
- `rederive_pack.py` / `rederive_e1_e9.py` — the checker, re-runnable by anyone

Independent totals match the authored ones on every pack: `e1` 25/27, `e1x`
14/18, `e2` 17/18, `e3` 60/63, `e4` 62/63, `e5` 65/90, `e6` 72/72 + 72/72, `e7`
126/126, `e8` 55/210, `e9` 122/210.

**Desktop ledger note:** the *claims* live on **z13's** ledger, so the desktop
ledger still shows `front-e1-gold-pack` with no claims — Front H forbids merging
the two, and that is working as intended rather than a gap. Anyone reading the
desktop ledger alone will not see the verification; the committed artifacts above
are the cross-machine record.

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

1. ~~**ShowcaseAgent seam sets**~~ — **BLOCKED, and the recorded result is
   suspect. Do not run this until the harness is fixed.**

   Attempted 2026-08-13. `--routing-only --llm-routing` **never calls the
   model**: 10/10 queries returned in 0.0s recorded as `method: rule`. The
   benchmark's own warning caught it (*"10/10 rows fell back to non-LLM routing
   methods"*), which is good design — but it means the run measures the rule
   router, not the model.

   Not a threshold problem: rule confidence on these queries is **0.10–0.20**,
   far below the 0.5 default, so the LLM path should fire on every one. Raising
   `--routing-threshold` to 1.0 changed nothing, and `llm_router` imports
   cleanly, so it is not the `ImportError` fallback either. The gate is
   somewhere between `benchmark.py --routing-only` and
   `HybridDomainRouter.route()`.

   **Consequence for the prior result:** the recorded "5/10 for both rule-routing
   and forced-LLM" was probably never a model measurement. Two identical scores
   across supposedly different methods is exactly what a silent fallback
   produces. Treat that 5/10 as unverified.

   Also note `HybridDomainRouter` hands the LLM a fixed confidence of 0.8 and
   returns whichever result scores higher — so even when the model *is* consulted,
   a rule hit above 0.8 discards its answer and records `method: rule`. A pure
   LLM-routing mode does not currently exist.

   Fixing this needs work in `project-phoenix/domains/ShowcaseAgent/router/`,
   which is another component's code — raise it by handoff rather than patching
   it from here.
2. **PTS-001** (`project-phoenix/scripts/pts_001_runner.py`) — the strongest
   single deterministic discriminator on disk (`gemma3:27b` 6/6, `gemma4:31b` 5/6,
   `gemma4:26b` parse_fail). Runner already iterates a fixtures directory; add
   2–3 more fixtures in the same shape.
3. **All 22 PROTO probes**, not the 6 used for the headline — re-baseline first,
   a 2026-04-28 drift addendum shows the old 4/6 already moved to 6/6.

---

## 5. Adding a new model (e.g. `qwen3.8:27b`, expected 2026-08-14)

**One command:** `./evals/local_lane_ladder/new_model_gate.sh <tag>`

It runs five gates in order and refuses to continue on a failure rather than
producing a number that looks fine. Every gate exists because skipping it already
cost this programme a run:

| Gate | Why |
|---|---|
| 0 — no sweep running | GPU contention silently distorts every timing |
| 1 — weights fit | `nemotron-3.5-lightning` is 25 GB of *weights* on a 24 GB card; no context tuning fixes that. Distinct from `qwen3:32b`, whose spill was KV cache and which fits at `num_ctx ≤ 24576` |
| 2 — lands on GPU at ctx 16384 | refuse CPU-only / failed load. A few-percent weight lip is a host row (`qwen3.6:35b` 86.4 t/s at 4%/96%). KV-default spill is still a confound — pin ctx, do not veto the model |
| 3 — think support **and obedience** | `qwen3-vl:30b` ignores `think=false`, emitting 11,407 chars of reasoning at 52x the tokens. A leaky "off" row measures nothing |
| 4 — one graded cell | proves the harness can drive it, and that a trace is retained |

On success it prints the battery command with **`qwen3.6:27b` included as a
same-run control**. That matters: 3.6 is the direct predecessor at the same size
class, and running it fresh alongside avoids comparing across invocations —
cross-invocation drift already produced one false regression here.

**Compare against `e9-ceiling-continued`, not `e10-repeat-ab`** (e10 varies
`--on-repeat`; the gate command uses the default).

### What to actually look for in `qwen3.8:27b`

`qwen3.6:27b` scored **19/30** in E9 — third place, and interesting in two
specific ways that give 3.8 a sharp test rather than a vague one:

1. **It was the only model to solve any `csv-summarize-repair` cell** (3/6 of the
   fixture's 3/42 total). That fixture brackets the top of the current ladder, so
   if 3.8 improves anywhere, that is where headroom exists.
2. **It bought its rank with instability** — 3 of 5 fixtures were coin-flips,
   against zero for both `gemma4` models. If 3.8 keeps the capability and fixes
   the variance, it is a genuine seat contender. If it is merely a little better
   on average and still flip-prone, it is not: `gemma4:26b` wins the seat on
   determinism, not on peak score.

Also worth checking, cheaply, because both have bitten: whether it obeys
`think=false` (Gate 3 answers this), and whether it emits one tool call per
response or several — the two-object emission pattern is what the extractor fix
in `5be7db5` had to handle.

**No claim from a first run.** One model, n=6, one epoch is a smoke test, not
evidence — and per `MSC-RUL-107` it cannot revise a seat decision on its own.

## 6. Housekeeping

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

### Standing hazard: patterns matching text that contains the pattern

This bit **four separate times in one session**, in four different tools, and
each time it produced a confident wrong answer rather than an obvious error:

| Where | The match | Consequence |
|---|---|---|
| `task_lint` R5 ban-list | `etc` inside `src/fetcher.py` | plan-shaped prompt linted semi-shaped; would have aborted the runner |
| failure taxonomy | `connection` inside a fixture's *"Drain connections."* | 19 model failures misfiled as INFRA |
| `pkill -f` / `pgrep -f` | the pattern appears in the watcher's **own** command line | killed my own chain launcher; a wait-loop that could never exit; a duplicate run launched |
| monitor filter | `Traceback` inside a *fixture's* test output | fired on every expected exec failure, drowning real signal |

The unifying cause: **grader detail, fixture content, and process command lines
all quote the thing being searched for.** Substring matching against them is a
false-positive generator, not a bug to be fixed with a better pattern.

Structural fixes, in preference order:
1. Read the signal from a source that *cannot* contain it — infra status from the
   harness's own stdout, never from grader text.
2. Identify processes by PID or `/proc/<pid>/cmdline` inspection, never `pgrep -f`
   on a string your own process also carries.
3. Word-bound the match (`(?<![a-z])etc(?![a-z])`) only when 1 and 2 are unavailable.
