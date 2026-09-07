# Verification-mandate ablation on qwen3-next — no effect on correctness, 28% more wall clock

**Run:** desktop, 2026-09-06. `qwen3-next:latest`, `csv-summarize-repair` L2,
n=6, `e9pin ctx16384 t0.8`, `think` off, dispatched via `pi`. Baseline is the
same task/model/pins from `preswap-wallclock-2026-09-05` (n=4, same day, same
box). Patched prompt preserved as `patched_task.yaml`; the canonical task YAML
was restored from git after the run.

**Question:** `qwen3next-brevity-001` found that a brevity instruction made this
model *worse* (6/6 → 3/6), and attributed the regression to **under-verification**
— the instruction read as pressure to rush to a first attempt. Its Limits section
noted no second wording was tried. Today's default-prompt run failed 2/4 with the
same shape, including one trial that emitted 35,026 tokens and **never ran bash
at all**. So: does mandating the verification loop — the opposite intervention —
fix it?

**Addendum tested:**

> After making the edit, run the verification command and read its output. Do not
> finish your turn until you have run it and seen it pass. If it fails, fix the
> code and run it again.

## Result: no. Same pass rate, materially slower.

| | baseline (n=4) | +verify mandate (n=6) |
|---|---|---|
| **passed** | 2/4 (50%) | **3/6 (50%)** |
| wall clock mean | 290.2 s | **371.4 s (+28%)** |
| wall clock range | 162.5–532.8 | 157.7–**603.9** |
| **timeouts** | 0 | **1** |
| output tokens mean | 18,252 | 16,931 (−7%) |
| token range | 9,084–35,026 | 3,874–32,409 |
| ran bash | 3/4 (75%) | 4/6 (67%) |

**Pass rate is identical at 50%.** With these sample sizes nothing is
distinguishable — Fisher exact p = 1.0 — so the honest reading is **no detectable
correctness effect, at a measurable cost in wall clock**, including the first
600 s timeout this cell has produced.

## The intervention did not do the thing it was designed to do

The mandate targeted verification behaviour. **It did not increase it** — bash
usage went 75% → 67%. The instruction was followed no more often than the
task's own step 3, which already said to run the verification command.

## My diagnosis was over-fitted to one trial

I proposed this fix after seeing baseline t2 emit 35,026 tokens with **no bash
call**, and read the failure mode as "doesn't check its work." Checking both
baseline failures:

| baseline failure | ran bash | tokens |
|---|---|---:|
| t2 | **no** | 35,026 |
| t4 | **yes** | 18,097 |

**Only one of the two failures skipped verification.** I generalised from the
more vivid trial. The mandate run confirms it — two of its three failures *did*
run bash (32,409 and 24,819 tokens) and failed anyway.

Under-verification is real but is not the controlling variable. What both
datasets actually show is that **failures are the long runs**: every failure in
both arms is at or above ~18,000 tokens except the timeout, and every pass is
below. The model does not fail because it skips checking; it fails because it
writes itself into a state it cannot recover from, and checking does not save it.

## Combined with the brevity result

Two prompt-level interventions in **opposite directions** have now been screened
on this model and this failure shape:

| intervention | direction | pass rate | wall clock |
|---|---|---|---|
| brevity (`qwen3next-brevity-001`) | say less | **6/6 → 3/6** | +10% |
| verify mandate (this) | check more | 50% → 50% | **+28%** |

Telling it to talk less broke it. Telling it to verify more did nothing but cost
time. **On current evidence qwen3-next's verbosity is not reachable from the
prompt in either direction**, and it should be selected or rejected on its
measured behaviour rather than prompt-tuned.

## Operator consequence

`qwen3-next` is not a good seat for `csv-summarize-repair`-shaped work at 50%
and ~300 s. `qwen3.6:35b` does the same task at **21.2 s warm and 4/4**. The
verbosity is the model's, not the prompt's.

## Limits

- Baseline n=4, ablation n=6, different sessions. Pass/fail rests on
  deterministic postconditions so session state does not affect it, but the
  wall-clock comparison crosses sessions and inherits thermal drift (~5%,
  `gemma4-26b-ctx-default-split` addendum). The +28% is larger than that but not
  by a wide margin.
- Single task, single model. Screening scale, same as the brevity result.
- One wording. A third phrasing could differ, though two opposed attempts both
  failing is weak evidence that the lever itself is wrong.
- `temperature 0.8`, so token counts vary by sampling between trials.
