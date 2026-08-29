# GOVERNED_DISPATCH_SPEC — router → operator bridge

Make the work router's live dispatches land in the operator ledger, **auto-lane-tagged**, so every
dispatch is governed and the offload economics are measured as a byproduct of normal work.

## Motivation

Today these are two disconnected tools:
- `phoenix_work_router.py` — a planner/dispatcher that logs to its **own** ledger (`~/.phoenix/runs`).
- `operator` — the governance ledger (`.operator/`), driven separately from a terminal.

So dispatched work isn't governed (no task/claim/evidence/session), and the lane-tagging from
`USAGE_LANE_TAGGING_SPEC.md` has to be set **by hand**. This bridge connects them: a live dispatch opens
a governed, lane-tagged operator session automatically.

## The key insight (why the router is the right place to tag lanes)

The router is the **one place that already knows, at dispatch time, both**:
- the **lane** — which worker it chose (ollama/local vs frontier), and
- the **task_class** — its cheap-local-first cascade *already decided* bounded (handled locally) vs hard
  (escalated to frontier on provable failure).

So the router can populate the lane tags with **zero manual annotation** — turning the offload audit
("avoidable frontier spend") into a free byproduct of dispatch instead of a tagging chore.

## Behavior (on a *live* dispatch)

1. Create or reuse an operator **task** for the work.
2. `session-start --harness <worker>` bound to the chosen worker.
3. Auto-derive and set the tags:

   | Router decision | operator `lane` | operator `task_class` |
   |---|---|---|
   | dispatched to ollama/local | `local` | `bounded` |
   | escalated to frontier after local failure | `frontier_driver` | `hard` |
   | frontier authored directly | `frontier_author` | `hard` |

4. On completion: `session-end --outcome <result> --cost <captured/estimated>`.
5. The router's own `~/.phoenix/runs` ledger **stays** (planning artifacts); operator is the *governance*
   record, not a replacement.

## Interface

- Router gains a `--govern` flag (or config) that, on live dispatch, shells out to the operator CLI
  (the router already imports `subprocess`; keep the repos decoupled — no shared imports).
- Config: path to the operator CLI + the target ledger's `.operator/` (which repo to govern into).
- After a batch, `usage-summary --offload-audit` reports the avoidable % with **no manual tagging**.

## Non-goals

- **Not** replacing `~/.phoenix/runs` (planning artifacts live there; operator is the audit layer).
- **Not** changing operator's fail-open posture — if operator is unreachable, the dispatch **still
  proceeds**; the govern attempt is logged as a warning. Never block work on the ledger being up
  (surface the gap, don't drop the dispatch).
- **No** separate bounded/hard classifier — the cascade outcome *is* the signal. Edge cases default to
  `unknown` (per the lane-tagging spec: surface, don't guess).

## Verification (verify-by-running)

- Live dispatch to a local worker → operator shows a session `lane=local, class=bounded`.
- Escalated dispatch → operator shows `lane=frontier_*, class=hard`.
- Batch of dispatches → `usage-summary --offload-audit` reports the avoidable % with zero manual tags.
- operator unreachable → dispatch completes anyway; govern attempt logged (fail-open).

## Sequencing / honest caveat

The router is **dry-run only today** ("No live dispatch"). This bridge is meaningful only once live
dispatch exists. Order of operations:
1. Router gains live dispatch (separate work).
2. This bridge governs those live dispatches.

Until then, the bridge could optionally govern the *plan* as a `planned` session — but the real payoff
(automatic offload accounting) lands when dispatch is live. Don't ship the bridge as "governed dispatch"
while dispatch is still a dry run.
