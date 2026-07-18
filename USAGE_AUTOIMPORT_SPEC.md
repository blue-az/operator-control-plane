# Operator Usage Auto-Import + Activity + Manual-Override — Build Spec

**For:** the implementing agent (Agy / Antigravity).
**Original spec author/reviewer:** Claude. Historical author labels are provenance only; they do not
define standing supervisor status for any harness.
**Target:** extend the existing `operator` CLI at `the operator CLI in this repo` (single-file Python, file-backed YAML ledger under `.operator/`). Match the existing code conventions (argparse subcommands, `find_operator_dir`, `load_yaml`/`save_yaml`, `get_next_*_id`, the `doctor` issue-list pattern, subprocess-driven tests in `tests/test_operator.py`).

---

## 0. Why this exists (do not skip)

This is the prerequisite for a multi-agent **domain bake-off experiment**: one or more assigned
harnesses build a tau-bench domain on public data, one or more distinct review identities judge the
result, and the operator must track **usage automatically** so the experiment's cost/effort numbers are
evidence, not pasted claims. **Build this system before running the experiment.**

**Hard rule — never conflate units.** Three harnesses expose different things. The system must keep them in separate, provenance-tagged fields and must never sum unlike units into one number.

| Harness | Token/cost | Activity | Notes |
|---|---|---|---|
| claude | EXACT tokens → estimated $ | yes | richest |
| codex | EXACT tokens → estimated $ | yes | token events are **cumulative** |
| gemini-agy | **none on disk** | yes (activity only) | quota-metered; cost is manual-only |

---

## 1. Design principles

1. **Auto is the workhorse, manual is a long-session supplement/override.** Manual entry's cost is fixed-per-session, so it's only economical on long sessions. Never require manual entry for routine capture.
2. **The common comparable metric is `tool_calls`.** Turns and wall-clock duration are NOT cross-comparable (a Claude "assistant message" ≠ a Codex "turn_context"; verified 285 vs 45 for comparable work). Capture turns and duration, but mark them harness-internal — never cross-compare them in summaries.
3. **Per-field provenance.** Every measured field carries `source: auto | manual`. Manual overrides auto for that field, but the auto value is **retained**, never clobbered.
4. **Cost is a list-price estimate, not billing.** Token counts are exact; dollars are `tokens × price_table`. State this in provenance. Subscriptions make the dollar a proxy.
5. **Idempotent imports.** Re-importing the same session updates the same record (keyed on `source_session_ref`), never appends a duplicate.

---

## 2. Record schema (`.operator/usage/<date>.yaml`, list of records)

Extend the existing usage record. New/changed fields marked ★.

```yaml
- usage_id: usage-0001
  task_id: amkor-build
  harness_id: gemini-agy
  model: <string|null>
  started_at: <iso8601>            # auto from logs OR manual override
  ended_at:   <iso8601|null>
  metering: tokens | activity      # ★ tokens => has token/cost; activity => activity only
  # --- token layer (null unless metering==tokens) ---
  tokens_in:          <int|null>   # ★
  tokens_out:         <int|null>   # ★
  tokens_cache_read:  <int|null>   # ★
  tokens_cache_write: <int|null>   # ★ (claude only)
  cost_estimate_usd:  <float|null> # derived from tokens×price_table; null for activity
  # --- activity layer (ALL harnesses) ---
  activity:                        # ★
    tool_calls:      <int>         #   THE comparable metric
    turns:           <int>         #   harness-internal; DO NOT cross-compare
    wall_clock_s:    <int>         #   last_ts - first_ts; confounded by idle
    active_s:        <int|null>    #   manual-only; null unless human-entered
    quota_events:    <int|null>    #   agy only; from cli log "quota reached"
  # --- provenance ---
  field_sources:                   # ★ per-field source map
    tokens_in: auto
    cost_estimate_usd: auto
    active_s: manual
    # ... one entry per populated measured field
  source_session_ref: <path-or-id> # ★ idempotency + provenance key
  raw_payload: <string>            # existing; manual notes / pasted snippet
  outcome: useful|partial|no_go|quarantined|reverted|unknown
```

A separate price table `.operator/pricing.yaml`:
```yaml
# $ per 1,000,000 tokens
claude-opus-4-8: { input: 15.0, output: 75.0, cache_read: 1.5, cache_write: 18.75 }
gpt-5.5:         { input: 0.0,  output: 0.0,  cache_read: 0.0 }   # fill real rates
```
If a model is missing from the table, leave `cost_estimate_usd: null` and let `doctor` flag it (do NOT guess a price).

---

## 3. Commands

### 3.1 `operator usage-import`
```
operator usage-import --harness {claude,codex,gemini-agy}
                      [--task ID] [--session-id ID]
                      [--since ISO] [--until ISO] [--dry-run]
```
- Resolves the harness log location (§4), selects the session(s) by **window** (default: the matching operator session's `started_at`→`ended_at` for this harness+task; else `--since/--until`; else most-recent session). `--session-id` forces an exact source session.
- Parses → builds/updates a usage record (idempotent on `source_session_ref`).
- `--dry-run` prints the record it would write; writes nothing.

### 3.2 Manual override (extend existing `usage-add`, or add `usage-annotate`)
```
operator usage-annotate <usage_id>
        [--active-start ISO] [--active-end ISO]   # => active_s, source=manual
        [--cost USD] [--quota-events N] [--note TEXT]
```
- Sets only the fields provided, tags each in `field_sources` as `manual`.
- Manual overrides auto in display/summaries but the auto value stays in the record (e.g. keep `wall_clock_s` even when `active_s` is set manually).

### 3.3 `operator usage-summary --metering`
- Add a `--metering` split so token/cost records and activity-only records are reported in **separate blocks**. Agy's activity must never appear inside a dollar total. Always report `tool_calls` as the cross-harness comparable; show `turns`/`wall_clock_s` only within a harness, labeled "not cross-comparable."

---

## 4. Per-harness adapter contracts (verified against live logs 2026-05-29)

### 4.1 claude  (metering: tokens + activity)
- **Location:** `~/.claude/projects/<cwd-with-/replaced-by->/<sessionId>.jsonl` (one file per session; filename = sessionId; `cwd` also in each line).
- **Tokens — SUM over lines where `type=="assistant"`**, reading `message.usage` (PER-MESSAGE, not cumulative):
  - `tokens_in += input_tokens`
  - `tokens_cache_write += cache_creation_input_tokens`
  - `tokens_cache_read += cache_read_input_tokens`
  - `tokens_out += output_tokens`
- **model:** `message.model` (e.g. `claude-opus-4-8`).
- **Activity:** `turns` = count of `type=="assistant"` lines; `tool_calls` = count of content blocks with `type=="tool_use"` across those messages (parallel calls in one message count individually); `wall_clock_s` from first/last `timestamp`.
- **cost:** `Σ bucket × price_table[model][bucket]`.
- Fixture line (canonical shape):
```json
{"type":"assistant","timestamp":"2026-05-29T06:11:33.621Z","cwd":"<workspace>","sessionId":"f49ed474-...","message":{"model":"claude-opus-4-8","usage":{"input_tokens":2272,"cache_creation_input_tokens":10958,"cache_read_input_tokens":8605,"output_tokens":2539},"content":[{"type":"tool_use","name":"Bash"}]}}
```

### 4.2 codex  (metering: tokens + activity)
- **Location:** `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`.
- **Tokens — token events are CUMULATIVE running totals. Take the LAST token event, NEVER sum** (verified: first 29,111 → last 16,981,711 total in one session; summing inflates ~100×). Fields on the token event: `input_tokens` (includes `cached_input_tokens`), `output_tokens` (includes `reasoning_output_tokens`), `total_tokens`.
  - `tokens_cache_read = cached_input_tokens`
  - `tokens_in = input_tokens - cached_input_tokens`
  - `tokens_out = output_tokens`
- **model:** from the `turn_context` event's `model` (e.g. `gpt-5.5`) — NOT on the token event.
- **Activity:** `turns` = count of `turn_context` events; `tool_calls` = count of `response_item` events that are tool/function invocations — **confirm the exact payload subtypes against fixtures** (candidates: `function_call`, `local_shell_call`, `custom_tool_call`, `mcp_tool_call`); do not use a crude substring match. `wall_clock_s` from first/last event timestamp.
- **cost:** `(tokens_in)×input + cached×cache_read + tokens_out×output`.

### 4.3 gemini-agy  (metering: activity ONLY)
- **Location:** `~/.gemini/antigravity-cli/brain/<id>/.system_generated/logs/transcript.jsonl` (+ `~/.gemini/antigravity-cli/log/cli-*.log`).
- **No tokens, no cost** — `tokens_*` and `cost_estimate_usd` stay `null`; `metering: activity`.
- **Activity:** transcript lines have keys `content, created_at, source, status, step_index, tool_calls, type`. `tool_calls` = Σ `len(tool_calls)` over lines that have it; `turns` = count of model-source steps; `wall_clock_s` from first/last `created_at`; `quota_events` = count of `quota reached` in the cli log within the window.
- The only path to Agy **cost** is manual (`usage-annotate --cost`, read off the UI/screenshot) — by design.

---

## 5. Session ↔ task association
- Primary key: **harness_id + time-window overlap** with the operator session (`session-start`/`session-end` already bracket it).
- Tie-breakers: cwd (claude has it; codex via project dir; agy via brain id). `--session-id` forces exact match when same-kind sessions overlap.
- Store the resolved CLI session id/path in `source_session_ref`.

## 6. doctor integration (new rules)
- tokens-metered record with `cost_estimate_usd == null` and a model NOT in price table → `[Warning] price table missing model X`.
- `source_session_ref` file no longer exists → `[Warning]` (mirror the existing evidence-hash-drift check).
- a record with `metering: activity` that has a non-null `cost_estimate_usd` whose `field_sources.cost_estimate_usd == auto` → `[Error]` (activity cost can only be manual).
- manual vs auto divergence: if both a manual and an auto value exist for the same logical field and differ by >2× → `[Warning] manual/auto divergence on <field>`.

## 7. Acceptance criteria (tests — subprocess style, like `tests/test_operator.py`)
Build against **fixture session files** committed under `tests/fixtures/` (sanitized snippets in the canonical shapes above) so no live Claude/Codex/Agy run is needed:
1. **claude import**: fixture with 3 assistant messages → `tokens_in/out/cache_*` equal the **sum**; `tool_calls` counts `tool_use` blocks; `cost` matches price-table math; `metering: tokens`.
2. **codex import**: fixture with 3 cumulative token events → record equals the **LAST** event (not the sum); model pulled from `turn_context`; `metering: tokens`.
3. **agy import**: fixture transcript → `tool_calls`/`turns`/`wall_clock_s` populated, `tokens_*` and `cost` **null**, `metering: activity`.
4. **idempotency**: importing the same fixture twice → one record, not two.
5. **manual override**: `usage-annotate --active-start/--active-end` → `active_s` set, `field_sources.active_s == manual`, `wall_clock_s` retained.
6. **doctor**: missing-price model → warning; activity record with auto cost → error.
7. **summary**: `--metering` puts agy in a separate block; `tool_calls` shown as the cross-harness metric; `turns`/`wall_clock_s` labeled not-cross-comparable.
8. existing `tests/test_operator.py` still passes; `operator doctor` clean on the live ledger.

## 8. Out of scope / residual risks (do NOT silently "fix")
- Dollar cost is a list-price estimate, not billing.
- Turn counts and raw wall-clock duration are NOT cross-harness comparable — surface them, never compare them.
- Agy cost/quota is manual-only; there is no on-disk token data.
- Concurrent same-kind sessions need `--session-id` to disambiguate.
- Claude cache-write has 1h vs 5m ephemeral rates; a single blended `cache_write` rate is an accepted approximation — note it, don't model both.

---
*Formats verified against live logs on 2026-05-29. Confirm Codex tool-call payload subtypes against fixtures before finalizing 4.2 activity.*
