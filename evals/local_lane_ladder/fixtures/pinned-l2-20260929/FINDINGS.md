# pinned-l2-20260929 - the first fully pinned comparison

**Run:** 2026-09-29, desktop dispatching through pi to the testbench dual-card
endpoint. **Question:** the 2026-09-27 crystal's steps 1-3 (full sampler pin,
a preflight that refuses mismatches, re-run), and the qwen3-next retest under it.

## What was controlled

- **All 14 Ollama option fields identical within each cohort**, declared in
  `contract_A.json` (think off) and `contract_B.json` (think on): num_ctx, num_keep,
  num_predict, seed, temperature, top_k, top_p, min_p, typical_p, repeat_last_n,
  repeat_penalty, presence_penalty, frequency_penalty, draft_num_predict.
  Cohort A: temp 0.8, top_p 0.95, top_k 20, min_p 0, penalties neutral, seed 1234,
  ctx 16384, num_predict 4096. Cohort B: temp 0.6, ctx 32768, num_predict 16384.
- **Preflight before launch** (`preflight_comparison.py`, `evidence/preflight_*.json`):
  tag digest and weight blobs, every parameter, pi's actual outbound request, and
  a fresh SSH placement snapshot attributing GPU memory to the study daemon.
  All four models passed (96-109% of weight bytes allocated on the two cards).
- **Every request gated in flight** (`request_gate_proxy.py`): 740 requests, 739
  passed, 1 rejected. The rejection was the pre-run setup test (pi sent `store`;
  fixed with `compat.supportsStore: false`), not a run request.
- **Booking fixture repaired** (the intended bug restored) and every repair task
  graded untouched before dispatch (`initial_state: must_fail`).
- Same 5 L2 tasks x n=6 as `qnext-80b-e9-ceiling` and
  `qnext-nemotron-dual-l2-20260928`.

## Results

| Model | Score | csv-summarize-repair | strict-log-format | Wall clock (30 cells) | Median cell |
|---|---:|---:|---:|---:|---:|
| nemotron-3.5-lightning (A) | **30/30** | 6/6 | 6/6 | 8.6 min | 8 s |
| qwen3.6:35b, control (A) | **29/30** | 5/6 | 6/6 | 5.7 min | 7 s |
| qwen3-next Instruct (A) | **27/30** | 3/6 | 6/6 | 25.0 min | 14 s |
| qwen3-next Thinking, think medium (B) | **29/30** | 6/6 | 6/6 | 69.6 min | 147 s |

All other tasks 6/6 except Thinking's constant-and-callers (5/6).

## Reading

1. **No ranking within cohort A.** 30 vs 29 vs 27 of 30 is within chance at n=6 per
   task (30 vs 27: Fisher exact p = 0.24). The cohort is at or near ceiling on this
   battery.
2. **qwen3-next was never a 10/30 model.** Instruct 27/30 and Thinking 29/30 under a
   correct, pinned configuration, against 10/30 for the Thinking variant run with
   thinking off in a 16k context.
3. **Two apparent weaknesses were configuration.**
   - Instruct's strict-log-format went 3/6 (unpinned, top_p 0.8) to 6/6 (pinned).
   - Thinking's three 600 s timeouts on csv-summarize-repair (unpinned) are gone:
     6/6, and its longest cell in the whole run was 425 s, under the old 600 s
     limit. The raised 1,200 s limit was not needed. The earlier suggestion that a
     faster card might rescue those timeouts is superseded: the configuration did.
4. **What remains model-level:** Instruct's csv-summarize-repair 3/6 (wrong output,
   105-246 s, not timeouts) and its 3-4x wall clock, almost all on that task.
5. **Control's one miss is announce-and-stop**, not a wrong repair: it read both
   files, wrote a correct plan ("Let me rewrite `summarize_expenses`..."), and
   ended the turn without editing (see `SILENT_TURN_DIAGNOSIS.md`).
6. **Wall clock is now comparable** within cohort A (identical samplers). The
   control is fastest overall; nemotron fastest on the simple tasks.

## Limits

- n=6 per task; the battery is near ceiling and cannot separate the cohort.
- Placement was proven at preflight per model, not per cell; the run interleaved
  models on one dual-card daemon (reloads are inside the wall clock).
- Cohort B is not comparable to cohort A (different temperature, context and
  thinking) and is reported on its own.
- Sampler values are a chosen common point (near the old e9 settings), not each
  model's recommended sampler; a model tuned for other values may score differently.
