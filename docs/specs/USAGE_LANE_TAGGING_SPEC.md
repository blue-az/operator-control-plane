# USAGE_LANE_TAGGING_SPEC

Tag usage by **lane** so the ledger can show how much high-cost budget was *avoidable* — spent driving
work a lower-cost participant could have authored — versus *necessary*.

## Motivation

The local-LLM offload finding (2026-06-25): authoring can be cheap when the task is bounded; **the cost
is the driver, not the author.** The same bounded build cost ~**21%** of budget when an expensive driver
ran it, vs ~**1%** when a lower-cost stack ran it. So **high-cost spend on bounded/trodden work is
avoidable** — it should route to an explicitly tagged lower-cost lane.

Harness names are not ranks. `assigned_harness`, `review_harness`, and `harness_id` describe routing and
provenance; they do not make a tool a supervisor, verifier, or subordinate by brand. A participant earns
trust only through the ledger's claim -> evidence -> distinct-identity verification path.

The operator already meters usage (`usage-import` / `usage-summary`) but only `--by-harness` / `--by-model`.
It cannot answer the one question the finding raises: *how much of my frontier budget went to work that
could have been local?* This spec adds that — turning the offload from anecdote into a measured, advisory
signal.

## Schema (additive, backward-compatible)

Add two fields to usage/session records:

- **`lane`**: `local` | `frontier_driver` | `frontier_author`
  - `local` — lower-cost/local lane (may be unmetered).
  - `frontier_driver` — high-cost model **orchestrating/evaluating** (the cost that dominates).
  - `frontier_author` — high-cost model **writing code** directly.
- **`task_class`**: `bounded` | `hard` | `unknown` *(default)*
  - `bounded` — trodden / well-represented build (offload candidate).
  - `hard` — novel / reasoning-heavy (legit frontier use).

Missing fields → `unknown`. **Records with a missing lane must still appear in the summary as `unknown`,
never be silently dropped from totals** (the stack's fail-open-on-absence trap — surface the gap, don't
hide it).

## CLI changes

- `session-start … [--lane LANE] [--class {bounded,hard}]` — tag at session open.
- `usage-add … [--lane LANE] [--class …]` — tag a pasted snippet.
- `usage-import` — default `lane = unknown`, `task_class = unknown`. Never infer lane from harness brand;
  tag imported records explicitly with `usage-annotate` or set the lane at session open.
- `usage-annotate <id> [--lane …] [--class …]` — retroactively tag imported records (extends the existing
  `--cost`/`--note`).
- `usage-summary --by-lane` — new grouping: spend + token totals per `lane × task_class`, with an
  **"avoidable" rollup** = Σ(spend where `lane` starts `frontier_` AND `task_class = bounded`).

## Routing signal (phase 2)

- `usage-summary --offload-audit` → one line: *"{X}% of frontier spend went to bounded work (avoidable ->
  route to an explicit lower-cost lane)."*
- `doctor` (advisory): flag sessions tagged `frontier_driver` + `bounded` as **offload candidates**.
- Later: a `session-start` / `brief` hint when a task is tagged `bounded` ("consider an explicit
  lower-cost lane").

## Non-goals

- **Auto-detecting `task_class`.** Bounded-vs-hard is a human judgment; default `unknown`, tag explicitly.
- **Precise local metering.** gemma is ≈$0; optional wall-time capture only.
- **Enforcement / blocking.** This is *visibility + advisory routing*, not a gate. Stay fail-open — never
  block work on a missing lane tag.

## Verification (verify-by-running)

- Synthetic ledger with mixed lanes → `--by-lane` produces the correct avoidable / necessary / free split.
- `usage-import` fixtures per harness → lane defaults to `unknown` unless explicitly tagged.
- Backward-compat: records with no `lane`/`task_class` summarize as `unknown` with no crash **and are still
  counted** (not dropped).

## Honest caveat

The "avoidable" number is only as good as the human `task_class` tagging. Untagged → `unknown` → **not**
counted as avoidable (conservative). So the metric *undercounts* avoidable waste until tagging is habitual
— which is the right direction to be wrong in.
