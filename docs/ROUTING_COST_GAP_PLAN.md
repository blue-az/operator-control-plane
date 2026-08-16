# Routing gap: the policy has no notion of what a turn costs

**Status:** plan, nothing implemented. Filed 2026-08-15.

## The gap

`LOCAL_LANE_ROUTER_STUDY.md` converts a classification into an assignment using
one hardware fact — decode rate — against one threshold:

```
frontier lane                     -> frontier
needs_supervision lane            -> supervised
local_ok + conversational         -> models clearing 20 tok/s
local_ok + delegated              -> any local model
```

Two holes:

1. **The frontier branches have no cost gate at all.** Once a turn is classified
   `frontier`, it goes to a paid seat regardless of how trivial it is.
2. **`tok/s` is a latency proxy, not a cost proxy.** A model can be fast and
   expensive, or slow and nearly free. The policy cannot express that.

Observed consequence (`HARNESS_TURN_COST_ANECDOTES.md`): on agy's free plan at
harness defaults, the single word `hello` costs **~0.1%** of daily quota on
GPT-OSS and **~7%** on Opus. A greeting consuming 7% of a day is a routing
outcome, not a model property.

## What makes this awkward

**The operator often cannot control reasoning budget.** Antigravity's harness
owns that setting; there is no flag to pin it. So the only available lever is
**seat choice**, not seat configuration. A plan that assumes "just turn thinking
off" does not survive contact with the harnesses actually in use.

This is the same constraint the local lane hit from the other side: there,
`--think off` is controllable and pinning it collapsed E4's 19x latency spread
to 1.2x. Where it is not controllable, the budget rides along with the seat and
has to be treated as part of the seat's cost.

## Plan

### Phase 1 — a triviality guard, no new data required

The cheapest fix, and it needs nothing measured. The router already emits
`{lane, interaction_mode, expected_tool_calls, reason}`. Add one rule:

```
frontier lane + expected_tool_calls == 0 + conversational
    -> cheapest seat clearing the floor, not the default frontier seat
```

A turn that needs no tools and no supervision is not frontier work regardless of
what the classifier said. This catches the `hello` case and everything shaped
like it, using a field the classifier already produces.

**Risk to check:** `expected_tool_calls == 0` is a prediction, not a fact. A
misclassified turn gets a weak seat. Mitigation is the existing escalation path —
if the cheap seat fails, the turn is re-run at the proper seat, which costs one
cheap turn rather than capping the day.

### Phase 2 — instrument cost per turn, per harness

The mechanism already exists and is unused for this. `usage-add` /
`usage-import` record `cost_estimate_usd`, tokens and `activity.turns` per
session; `usage-summary` groups `--by-lane` and `--by-machine`.

Needed:

- `usage-summary --by-harness` with a **cost-per-turn** column (total cost /
  total turns), so the gate reads observed history rather than a guess.
- Backfill: the 67 z13 records imported 2026-08-15 under
  `z13-historical-usage-import` are the first real corpus for this.

Then Phase 1's "cheapest seat clearing the floor" becomes measured rather than
hardcoded.

**Caveat that limits Phase 2:** quota units are not dollars. agy's "% of free
plan" is weighted by Google's pricing tiers and does not convert. Any
cross-harness cost comparison has to stay within one accounting system, or be
expressed as *"fraction of that harness's own budget"* rather than a shared
currency.

### Phase 3 — treat reasoning budget as a seat property

Where the harness owns the reasoning mode, record it as a fixed attribute of the
seat rather than a knob:

```
seat: opus-thinking      reasoning: forced-on    cost/turn: high
seat: gpt-oss-medium     reasoning: moderate     cost/turn: very low
seat: gemma4:26b (local) reasoning: controllable cost/turn: electricity only
```

That makes the un-pinnable budget visible in the routing table instead of
invisible in the bill, and it distinguishes seats where the operator *can* pin
thinking (local lanes, via `opr --think off`) from those where it rides along.

## Ordering and cost

Phase 1 is a policy edit and is worth doing on its own — it addresses the
observed failure and needs no measurement. Phase 2 is a small CLI addition plus
a backfill that already landed. Phase 3 is a schema/documentation change with no
runtime component.

None of it is urgent: local lanes cost electricity, and the expensive seats are
currently driven by hand rather than by the router. It becomes load-bearing the
moment routing is automated, or a paid subscription replaces the free tiers.
