# Usage-import test fixtures

Sanitized samples in the canonical on-disk shapes (verified against live logs 2026-05-29).
Build the adapters and their unit tests against these — **no live Claude/Codex/Agy run is needed**.
Expected parse results (assert these):

## `claude_session.jsonl` (metering: tokens)
Sum the two `type=="assistant"` lines' `message.usage` (per-message, NOT cumulative):
- `tokens_in` = 100 + 10 = **110**
- `tokens_cache_write` = 200 + 0 = **200**
- `tokens_cache_read` = 300 + 400 = **700**
- `tokens_out` = 50 + 20 = **70**
- `activity.turns` = **2** (assistant lines)
- `activity.tool_calls` = **3** (`tool_use` blocks: 1 + 2)
- `activity.wall_clock_s` = **595** (10:00:05 → 10:10:00)
- `model` = `claude-opus-4-8`
- `cost_estimate_usd` (with sample pricing.yaml) = (110·15 + 700·1.5 + 200·18.75 + 70·75) ÷ 1e6 = (1650 + 1050 + 3750 + 5250) ÷ 1e6 = **0.0117 USD**

## `codex_rollout.jsonl` (metering: tokens)
Token events are **cumulative** — take the **LAST** (`total_tokens` 5000), never sum (sum=8450 is WRONG):
- `tokens_cache_read` = **1500** (`cached_input_tokens`)
- `tokens_in` = 4500 − 1500 = **3000**
- `tokens_out` = **500**
- `activity.turns` = **2** (`turn_context` events)
- `activity.tool_calls` = **2** (`function_call` + `local_shell_call`)
- `activity.wall_clock_s` = **600** (11:00:00 → 11:10:00)
- `model` = `gpt-5.5` (from `turn_context`, not the token event)
- NOTE: confirm the full set of tool-call payload subtypes against real rollouts before finalizing.

## `agy_transcript.jsonl` + `agy_cli.log` (metering: activity)
- `tokens_*` and `cost_estimate_usd` = **null**
- `activity.turns` = **2** (`source=="model"` steps)
- `activity.tool_calls` = **3** (Σ `len(tool_calls)`: 2 + 1)
- `activity.wall_clock_s` = **480** (12:00:00 → 12:08:00)
- `activity.quota_events` = **1** (`quota reached` lines in `agy_cli.log`)
