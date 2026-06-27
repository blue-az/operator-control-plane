# USAGE_LANE_TAGGING_SPEC

Tag usage by **lane** so the ledger can show how much frontier budget was *avoidable* — spent driving
work a local model could have authored — versus *necessary*.

## Motivation

The local-LLM offload finding (2026-06-25): authoring is cheap (local gemma-31b ≈ $0); **the cost is the
driver, not the author.** The same bounded build cost ~**21%** of budget when a frontier agent (codex)
drove it, vs ~**1%** when the cheap stack (Agy) drove it. So **frontier spend on bounded/trodden work is
avoidable** — it should route to the cheap stack.

The operator already meters usage (`usage-import` / `usage-summary`) but only `--by-harness` / `--by-model`.
It cannot answer the one question the finding raises: *how much of my frontier budget went to work that
could have been local?* This spec adds that — turning the offload from anecdote into a measured, advisory
signal.

## Schema (additive, backward-compatible)

Add two fields to usage/session records:

- **`lane`**: `local` | `frontier_driver` | `frontier_author`
  - `local` — authored by a local model (≈$0; may be unmetered).
  - `frontier_driver` — frontier agent **orchestrating/evaluating** (the cost that dominates).
  - `frontier_author` — frontier agent **writing code** directly.
- **`task_class`**: `bounded` | `hard` | `unknown` *(default)*
  - `bounded` — trodden / well-represented build (offload candidate).
  - `hard` — novel / reasoning-heavy (legit frontier use).

Missing fields → `unknown`. **Records with a missing lane must still appear in the summary as `unknown`,
never be silently dropped from totals** (the stack's fail-open-on-absence trap — surface the gap, don't
hide it).

## CLI changes

- `session-start … [--lane LANE] [--class {bounded,hard}]` — tag at session open.
- `usage-add … [--lane LANE] [--class …]` — tag a pasted snippet.
- `usage-import` — **default `lane` from the harness** (heuristic: `gemini-agy` → cheap/local-ish driver;
  `codex`/`claude` → `frontier_driver`), `task_class = unknown`. Never guess the class.
- `usage-annotate <id> [--lane …] [--class …]` — retroactively tag imported records (extends the existing
  `--cost`/`--note`).
- `usage-summary --by-lane` — new grouping: spend + token totals per `lane × task_class`, with an
  **"avoidable" rollup** = Σ(spend where `lane` starts `frontier_` AND `task_class = bounded`).

## Routing signal (phase 2)

- `usage-summary --offload-audit` → one line: *"{X}% of frontier spend went to bounded work (avoidable →
  route to the cheap stack)."*
- `doctor` (advisory): flag sessions tagged `frontier_driver` + `bounded` as **offload candidates**.
- Later: a `session-start` / `brief` hint when a task is tagged `bounded` ("consider the local stack").

## Non-goals

- **Auto-detecting `task_class`.** Bounded-vs-hard is a human judgment; default `unknown`, tag explicitly.
- **Precise local metering.** gemma is ≈$0; optional wall-time capture only.
- **Enforcement / blocking.** This is *visibility + advisory routing*, not a gate. Stay fail-open — never
  block work on a missing lane tag.

## Verification (verify-by-running)

- Synthetic ledger with mixed lanes → `--by-lane` produces the correct avoidable / necessary / free split.
- `usage-import` fixtures per harness → lane defaults correctly.
- Backward-compat: records with no `lane`/`task_class` summarize as `unknown` with no crash **and are still
  counted** (not dropped).

## Honest caveat

The "avoidable" number is only as good as the human `task_class` tagging. Untagged → `unknown` → **not**
counted as avoidable (conservative). So the metric *undercounts* avoidable waste until tagging is habitual
— which is the right direction to be wrong in.
