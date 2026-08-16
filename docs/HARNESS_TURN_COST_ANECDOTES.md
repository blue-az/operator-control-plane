# Harness turn cost — anecdotes, not measurements

Backup data. Filed so a future investigation starts from a record instead of a
memory, and knows what to control for. **Nothing here is citable as a model
comparison.**

---

## 2026-08-15 — Antigravity CLI, Google free plan, one-word turn

Operator sent the single prompt `hello` to five model settings and read the
free-plan quota consumed by each.

| Model setting | Quota per `hello` |
|---|---:|
| GPT-OSS 120B (Medium) | **~0.1%** |
| Gemini 3.7 Flash (High) | <1% |
| Gemini 3.1 Pro (Low) | ~1% |
| Claude Sonnet 4.6 (Thinking) | ~5% |
| Claude Opus 4.6 (Thinking) | **~7%** |

### Why this is not a model comparison

**Reasoning mode varies across the rows and cannot be held constant.** The
settings are `(Thinking)`, `(Medium)`, `(Low)`, `(High)` — different reasoning
budgets, not one setting applied uniformly. The transcript shows the cost
directly: Gemini 3.1 Pro spent **485 thinking tokens** deciding how to answer
`hello`.

This is the same confound as `--think` in the local ladder, where uncontrolled
reasoning produced a 5–32x token spread and collapsed E4's 19x latency gap to
1.2x once pinned. The ~70x Opus-to-GPT-OSS ratio here is reasoning budget times
quota weighting, not model economics.

**Other limits, recorded so nobody re-derives them:**

- n=1 per setting.
- Gemini 3.7 Flash was measured in a **separate fresh session**, not by
  switching in place, so its accumulated context differs from the rest.
- "% of free plan" is a **quota unit**, weighted by Google's own pricing tiers.
  It is not tokens and not dollars.
- Antigravity's harness owns the reasoning mode; the operator cannot pin it.
  That is why this stays an anecdote rather than becoming an experiment.

### What it does support

Read as a **harness** observation rather than a model one, it is sound and
useful — and the harness-at-defaults question is the operationally relevant one,
since defaults are what actually gets paid:

> On agy's free plan at harness defaults, a trivial turn costs ~0.1% on GPT-OSS
> and ~7% on Opus.

No reasoning-mode claim attached. Order-of-magnitude gaps from n=1 are good
enough to route on; a 70x gap does not need a p-value to justify keeping
transcript chores off the expensive seat.

The routing consequence is real and currently unhandled: the policy in
`LOCAL_LANE_ROUTER_STUDY.md` gates `conversational` versus `delegated` on
**tok/s**, and has no notion of reasoning budget or quota cost per turn. A
one-word greeting costing 7% of a daily quota is a routing gap, not a model
property.

### What would make it an experiment

Only worth doing if the harness ever exposes the control:

1. Same prompt, same fresh-session state for every row.
2. Reasoning **off** on all of them, or pinned to one identical level.
3. n>=3.
4. Record the quota unit's definition, or convert to tokens via the harness log
   and use `usage-import`.

Until then it stays here.
