# 3.6 vs 3.8 on a second exact-contract fixture — hypothesis not supported

**Measured:** 2026-08-15, `strict-table-render`, L2, n=18 per model,
`num_ctx 16384`, `temperature 0.8`, `think off`. 36 cells, single RTX 3090 320W.
**Not UID-verified. No claim registered.**

## The question

`strict-log-format` moved 16.7% → 83.3% from `qwen3.6:27b` to `qwen3.8:27b`
(p=0.0005). One fixture is one axis, so the claim "3.8 is better at exact output
contracts" needed an independent test with *different* traps: half-up rounding,
ellipsis-inclusive truncation, a missing-value sentinel, an exact joiner, and no
trailing newline. All four were verified to bite independently before running.

## Result

| Model | Pass | Detail |
|---|---:|---|
| `qwen3.6:27b` | **18/18** | — |
| `qwen3.8:27b` | 14/18 | 2 no-op, 2 timeout |

Raw 14/18 vs 18/18: **p=0.104**. Excluding the two timeouts as unscored per the
failure taxonomy (`TIMEOUT` is not `MODEL_FAILURE`): 14/16 vs 18/18, **p=0.214**.
Neither is significant.

## Finding 1 — zero contract violations, from either model

**Not one cell in 36 failed a contract assertion.** Every trap the fixture was
built around — banker's-vs-half-up rounding, the 8-character ellipsis width, the
`-` sentinel, the trailing newline — went unfired against both models.

Every `qwen3.8` failure was a failure to *produce code at all*:

| Cell | Calls | What happened |
|---|---:|---|
| t1 | 1 | `read_file` only, then stopped. File left at `raise NotImplementedError`. |
| t12 | 3 | read, read, `patch_file` **failed**, did not retry |
| t17 | **0** | no tool call, 601.7s timeout |
| t18 | **0** | no tool call, 601.8s timeout |

So this is evidence **against** the hypothesis, not merely absent evidence for
it. If 3.8 held a real contract-fidelity edge, `qwen3.6` should have violated
some contract rule somewhere in 18 attempts. It violated none.

**`strict-log-format` remains a single unreplicated axis.** The p=0.0005 result
there is not withdrawn — it was measured and the fixture was checked for drift —
but it has now failed to generalise to a second contract fixture, and should be
described as specific to that item rather than as a property of the model.

## Finding 2 — the real difference is recovery, and it favours 3.6

Both models hit failed tool calls. They handle them differently:

| | cells with ≥1 failed call | recovered | did not |
|---|---:|---:|---:|
| `qwen3.6:27b` | 13/18 | **13** | 0 |
| `qwen3.8:27b` | 7/18 | 6 | 1 |

`qwen3.6` hits *more* failed calls and recovers from **all** of them — the
typical trajectory is read → read → patch(fail) → patch(ok), consistently 3–4
tool calls, never fewer. `qwen3.8` hits fewer but has three cells where it barely
engaged: one read-and-stop, and two with no dispatch at all.

Call-count distributions make it plain:

```
qwen3.6   {3: 5, 4: 13}                    never below 3
qwen3.8   {0: 2, 1: 1, 3: 4, 4: 10, 5: 1}  three cells under 3
```

This is a completion-reliability difference, not a capability one, and at
p=0.104 it is not established either. It points the same direction as the stub
run, which graded 3.6 higher (8.0 vs 7.5) as a code AGENTS.

## Finding 3 — the two timeouts match the silent-turn pattern

t17 and t18 are **consecutive**, at the end of the `qwen3.8` block, both with
**zero tool calls** and both running the full 600s. Not a repeat loop
(`stopped_repeat: False`), not a dispatch failure (`no_dispatch: False`) —
simply no output.

That is the same shape as the unexplained silent turns seen on 2026-08-14
(gemma4:31b producing `Thought: 12.2s` then nothing). Two theories were tested
and refuted then, and this is a third instance with a clean trace attached, so
it is now the best-documented occurrence available for diagnosis.

**These cells should not be charged to the model** until that is understood.

## Consequence for claim-0042

`claim-0042` states the ladder ranking transfers across the pending GPU upgrade,
evidenced by 0 of 306 cells being timeout-mediated with the slowest at 206.3s
against a 600s limit. That remains true **of those 306 cells**. It is no longer
true that no fixture produces timeout-mediated outcomes: this one produced two.
A reviewer re-deriving 0042 should treat "no cell is near the limit" as a
property of the three fixtures measured, not of the battery.

## Limits

n=18 per model, one fixture, one level, one machine. Nothing here reaches
significance. The fixture is new and has no measured difficulty; `gemma4:26b`
went 3/3 on it in preflight, so it sits well below `csv-summarize-repair` and
is not a ceiling instrument.

## Finding 4 — the one defensible tooling difference: 3.8 verifies, 3.6 never does

Tool-call census across all 36 cells:

| | read_file | patch_file | run_command | patch success |
|---|---:|---:|---:|---:|
| `qwen3.6:27b` | 36 | 31 | **0** | 18/31 (58%) |
| `qwen3.8:27b` | 31 | 21 | **6** | 14/21 (67%) |

**`qwen3.8` runs the test to verify; `qwen3.6` never once does.** Cells using
`run_command`: 5/18 vs 0/18, Fisher **p=0.0455**. The L2 prompt explicitly says
*"Verify by running python3 tests/check_render.py"*, so this is conformance to a
stated plan step, and 3.6 skipped it in all eighteen attempts.

Patch success rate is **not** separable: 67% vs 58%, p=0.575.

**The verification did not pay off.** 3.6 went 18/18 without ever verifying;
3.8 went 14/18 while verifying in 5 cells. Trajectory conformance and outcome
diverge here, which is exactly why the deterministic postcondition stays the
gate and the trajectory score is reported beside it rather than folded in.

Contamination check: only 2 `qwen35.go` parse-failure events occurred during the
run window against 20 failed `patch_file` calls, so the failure counts are
overwhelmingly genuine model-side patch failures, not the server bug in
`SILENT_TURN_DIAGNOSIS.md`.

Caveats: one fixture, p=0.0455 is marginal, and 5/18 means 3.8 does not verify
reliably either — only more often than never.
