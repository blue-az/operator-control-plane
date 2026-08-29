# USAGE_CACHE_WASTE_SPEC

Add one objective, log-derived cache non-reuse signal to Claude usage records, so the ledger's
subjective `outcome` tag (`useful | partial | no_go | ...`) has at least one machine-checkable signal to
be cross-referenced against instead of standing alone on the writer's word. The retained
`cache_waste` field name is a compatibility label, not a claim that permanent waste was proven.

## Motivation

Stella (an external coding-agent CLI evaluated read-only — see the eval-notes doc if this repo shares one)
records stable block identities, step manifests, citation/reference receipts, and compaction events. Those
receipts are sufficient for a later analysis to establish that a particular block left context before it
was cited; Stella does not currently surface an aggregate "provably wasted spend" metric. Operator has no
equivalent block identity: `outcome` on a usage record is set by whoever writes it, the same
unaudited-self-report shape that let a fabricated evidence trail through a green `doctor` before
(`doctor`'s existing caution to check *how* a run went green applies here too). Operator is an external log
parser, not the harness, so it cannot bind a cache read to a particular earlier write. But
`parse_claude_session_file` already sums `cache_creation_input_tokens` and `cache_read_input_tokens` per
assistant message; keeping those sums in **message order** instead of only totaling them gives one narrow,
real, computable proxy: cache-write tokens with no observed intervening cache read before the next cache
creation.

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
write at a time. A pending write is cleared when a later message has `cache_read_input_tokens > 0`. If
instead a later message writes again (`cache_creation_input_tokens > 0`) while a write is still pending,
the old pending amount is counted by this proxy. This proves only the observable sequence—write, no
intervening read, next write—not that the later write superseded the same cache entry or that the earlier
entry was permanently abandoned.

**The session's final pending write is deliberately left uncounted.** An earlier draft of this spec
counted any write with no later read anywhere in the session as wasted — but a session's last cache write
almost always has no later read within that same transcript, by construction (nothing follows the last
message). That definition flagged nearly every session's tail as "wasted" regardless of real reuse
behavior, which surfaced immediately as spurious `[Warning] high cache waste` doctor failures on ordinary
fixture sessions. The session ending does not establish abandonment—a follow-up session could still hit
that cache entry—so the final pending write remains unresolved.

This is a deliberately narrow observation, not an estimate of permanent cache waste. A write that is
simply never revisited before the transcript ends is left unresolved. Even when another write follows,
Operator's scalar counters cannot establish cache-entry identity, so the method records "no observed read
before next write" rather than actual eviction or supersession. True per-write tracking would require
cache-entry identities or an equivalent harness receipt that has not been confirmed in Claude Code's
session JSONL format. The historical method token remains `v1-superseded-no-reuse` for compatibility; its
semantics are the narrower observation defined here.

## Schema (additive, backward-compatible, Claude records only)

```yaml
cache_waste:
  wasted_cache_write_tokens: <int>      # compatibility name: write tokens counted by the v1 proxy
  wasted_cache_write_pct: <float>       # proxy count / tokens_cache_write; 0.0 if no cache writes
  method: v1-superseded-no-reuse        # historical token; semantics are pinned by this specification
field_sources:
  cache_waste: auto                     # always auto — recomputed from the session file on every
                                         # (re)import, never hand-edited via usage-annotate
```

Computed inside `parse_claude_session_file` by tracking cache-write/cache-read presence per message in
timestamp order, rather than only accumulating the existing running totals.

## CLI changes

- No new import flags — `cache_waste` is computed unconditionally for every Claude usage record.
- `usage-summary --cache-waste-audit`: one advisory aggregate, e.g. *"14% of Claude cache-write spend
  had no observed intervening read before the next write (v1-superseded-no-reuse proxy)."*

## doctor integration (advisory only)

- `[Warning] high cache non-reuse proxy`: a Claude usage record with `wasted_cache_write_pct > 0.5`. Advisory only —
  never affects `doctor`'s pass/fail exit code beyond existing warning semantics, matching
  `USAGE_LANE_TAGGING_SPEC.md`'s "visibility + advisory routing, not a gate" posture.
- **Not** wired to `outcome` automatically. `cache_waste` and `outcome` stay two independent signals side
  by side; doctor may eventually suggest "outcome: useful + wasted_cache_write_pct > 0.8 — worth a second
  look" as a phase-2 advisory, but this spec does not implement that cross-check.

## Non-goals

- **Not a citation- or cache-entry-tracking system.** This measures an ordered sequence of scalar counters,
  not whether a particular cache entry was reused or whether the model attended to the underlying content.
  Stella's identity-bearing receipts are materially stronger; Operator cannot reproduce them from these logs.
- **Not applied to codex or gemini-agy in v1.**
- **Does not modify `outcome`.** Machine-computed `cache_waste` is a cross-check, not a replacement for
  the human-set field.
- **No compaction-boundary detection in v1** — see Definition above; this is future work, gated on
  confirming the transcript format actually carries a usable marker.

## Verification (verify-by-running)

- Fixture Claude session, 3 assistant messages: msg1 writes 1000 cache tokens; msg2 writes 500 more
  cache tokens **with no observed read in between**; msg3 reports a 500-token cache read. Expect the
  compatibility field `wasted_cache_write_tokens == 1000` (msg1 only) and
  `wasted_cache_write_pct == 1000/1500`, without asserting cache-entry identity.
- Fixture with a single assistant message that writes cache tokens and nothing follows it → the write is
  the session's final unresolved write and must **not** be counted (`wasted_cache_write_tokens == 0`) —
  this is the regression case an earlier, buggier definition got wrong (see Definition above).
- Re-importing the same fixture recomputes identically (derived fresh from the full session file each
  time, not incrementally accumulated) — no double-counting on re-import.
- Fixture with `tokens_cache_write == 0` → `wasted_cache_write_pct == 0.0`, no division error.
- doctor fixture crossing the 0.5 threshold → `[Warning] high cache non-reuse proxy` fires; a fixture at
  or below the threshold does not.
- Existing `tests/test_operator.py` stays green, and the live-ledger `operator doctor` gains no new
  cache-proxy error; unrelated historical warnings are not a claim of cleanliness.

## Honest caveat

`wasted_cache_write_pct` is a compatibility field carrying an ordered-counter proxy, computed from
Operator's outside view of a session file rather than a report from inside the harness. It is not a proven
lower bound on permanent waste. State the method tag (`v1-superseded-no-reuse`) and the observable
"no intervening read before next write" next to the number everywhere it is surfaced.
