# USAGE_CACHE_WASTE_SPEC

Add one objective, log-derived "wasted spend" number to Claude usage records, so the ledger's
subjective `outcome` tag (`useful | partial | no_go | ...`) has at least one machine-checkable signal to
be cross-referenced against instead of standing alone on the writer's word.

## Motivation

Stella (an external coding-agent CLI evaluated read-only — see the eval-notes doc if this repo shares one)
treats context evicted from a session before it was ever cited as **provably wasted** spend, not a
heuristic guess. Operator has no equivalent: `outcome` on a usage record is set by whoever writes it, the
same unaudited-self-report shape that let a fabricated evidence trail through a green `doctor` before
(`doctor`'s existing caution to check *how* a run went green applies here too). Operator can't replicate
stella's exact mechanism — it's an external log parser, not the harness, so it has no visibility into
which context blocks the model actually attended to. But `parse_claude_session_file` already sums
`cache_creation_input_tokens` and `cache_read_input_tokens` per assistant message; keeping those sums in
**message order** instead of only totaling them gives one narrow, real, computable proxy: cache-write
spend that was never redeemed by a later cache-read in the same session.

## Scope: Claude only, v1

- **Codex**: token events are cumulative running totals (§4.2 of `USAGE_AUTOIMPORT_SPEC.md`) — no
  per-write/per-read sequence is recoverable from the last-event-only data Operator captures. Out of
  scope until a different capture strategy exists.
  - **Correction needed:** `parse_codex_session_file` currently reads only the **last** token event, per
    `USAGE_AUTOIMPORT_SPEC.md` §4.2 — recovering a write/read sequence would require reading every token
    event in the file, not the current parsing strategy. Out of scope for this spec regardless.
- **gemini-agy**: activity-only metering, no token data at all. Out of scope, unchanged.

## Definition (v1-superseded-no-reuse method)

Within one Claude session file, walk assistant messages in timestamp order, tracking one "pending" cache
write at a time. A pending write is cleared (counts as reused, not wasted) the moment a later message has
`cache_read_input_tokens > 0`. If instead a later message writes again (`cache_creation_input_tokens > 0`)
while a write is still pending — i.e. a new cache write happens before the old one was ever read back —
the old pending amount is **wasted**: proof the earlier cached content was paid for and then abandoned,
not merely proof it went unread so far.

**The session's final pending write is deliberately left uncounted.** An earlier draft of this spec
counted any write with no later read anywhere in the session as wasted — but a session's last cache write
almost always has no later read within that same transcript, by construction (nothing follows the last
message). That definition flagged nearly every session's tail as "wasted" regardless of real reuse
behavior, which surfaced immediately as spurious `[Warning] high cache waste` doctor failures on ordinary
fixture sessions. The session ending doesn't prove abandonment — a follow-up session could still hit that
cache entry — so only a *later write that supersedes it* counts as proof.

This is a deliberate **undercount**, not an estimate: a write superseded by another write with **no**
intervening read is unambiguous; a write that is simply never revisited before the transcript ends is
left as "unresolved," not "wasted." True per-write eviction tracking would need a compaction-boundary
marker in the transcript, which has not been confirmed to exist in Claude Code's session JSONL format —
v1-superseded-no-reuse is what's measurable without one. This mirrors `USAGE_LANE_TAGGING_SPEC.md`'s own
principle: undercounting waste is "the right direction to be wrong in."

## Schema (additive, backward-compatible, Claude records only)

```yaml
cache_waste:
  wasted_cache_write_tokens: <int>      # 0 if tokens_cache_write == 0
  wasted_cache_write_pct: <float>       # wasted / tokens_cache_write; 0.0 if tokens_cache_write == 0
  method: v1-superseded-no-reuse                   # explicit tag so a future compaction-aware v2 never silently
                                         # changes the meaning of records computed under v1
field_sources:
  cache_waste: auto                     # always auto — recomputed from the session file on every
                                         # (re)import, never hand-edited via usage-annotate
```

Computed inside `parse_claude_session_file` by tracking cache-write/cache-read presence per message in
timestamp order, rather than only accumulating the existing running totals.

## CLI changes

- No new import flags — `cache_waste` is computed unconditionally for every Claude usage record.
- `usage-summary --cache-waste-audit`: one advisory line per harness/task, e.g. *"14% of cache-write
  spend (~$0.32) was never reused in-session (v1-superseded-no-reuse method, Claude only)."*

## doctor integration (advisory only)

- `[Warning] high cache waste`: a Claude usage record with `wasted_cache_write_pct > 0.5`. Advisory only —
  never affects `doctor`'s pass/fail exit code beyond existing warning semantics, matching
  `USAGE_LANE_TAGGING_SPEC.md`'s "visibility + advisory routing, not a gate" posture.
- **Not** wired to `outcome` automatically. `cache_waste` and `outcome` stay two independent signals side
  by side; doctor may eventually suggest "outcome: useful + wasted_cache_write_pct > 0.8 — worth a second
  look" as a phase-2 advisory, but this spec does not implement that cross-check.

## Non-goals

- **Not a citation-tracking system.** This measures whether a cache entry was ever billed-and-reused, not
  whether the model actually read or used the underlying content — that's stella's actual mechanism and
  Operator has no equivalent visibility into the harness internals to replicate it.
- **Not applied to codex or gemini-agy in v1.**
- **Does not modify `outcome`.** Machine-computed `cache_waste` is a cross-check, not a replacement for
  the human-set field.
- **No compaction-boundary detection in v1** — see Definition above; this is future work, gated on
  confirming the transcript format actually carries a usable marker.

## Verification (verify-by-running)

- Fixture Claude session, 3 assistant messages: msg1 writes 1000 cache tokens; msg2 writes 500 more
  cache tokens **with no read in between** (supersedes msg1's still-pending write — proof of abandonment);
  msg3 reads 500 cache tokens (redeems msg2's pending write). Expect `wasted_cache_write_tokens == 1000`
  (msg1 only), `wasted_cache_write_pct == 1000/1500`.
- Fixture with a single assistant message that writes cache tokens and nothing follows it → the write is
  the session's final pending write and must **not** be counted as wasted (`wasted_cache_write_tokens ==
  0`) — this is the regression case an earlier, buggier definition got wrong (see Definition above).
- Re-importing the same fixture recomputes identically (derived fresh from the full session file each
  time, not incrementally accumulated) — no double-counting on re-import.
- Fixture with `tokens_cache_write == 0` → `wasted_cache_write_pct == 0.0`, no division error.
- doctor fixture crossing the 0.5 threshold → `[Warning] high cache waste` fires; a fixture at or below
  the threshold does not.
- Existing `tests/test_operator.py` and `operator doctor` on the live ledger stay clean.

## Honest caveat

`wasted_cache_write_pct` is a strict lower bound, computed from Operator's outside view of a session file,
not a report from inside the harness. State the method tag (`v1-superseded-no-reuse`) next to the number everywhere
it's surfaced, so it is never read with the confidence of a directly-observed measurement the way
`outcome` currently is trusted without one.
