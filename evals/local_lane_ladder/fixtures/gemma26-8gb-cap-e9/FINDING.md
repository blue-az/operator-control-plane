# gemma4:26b at an 8GB VRAM cap — the more extreme envelope

> ## ⚠️ ENVELOPE FRAMING IS WRONG — corrected 2026-09-05
>
> **`num_gpu` caps layer count, not VRAM, and for an MoE model those are very
> different constraints.** A real RTX 2080 (8 GB) fits **31/31 layers of
> gemma4:26b in 7.4 GB** and decodes at **31.0 tok/s** — because the 128 experts
> dominate the model's 18 GB and stream from RAM regardless. The `num_gpu=12`
> cap used here forced **12 of 30** layers off the GPU, which is far more
> constrained than the card it was meant to simulate, and produced 23.5 tok/s.
>
> **The accuracy conclusions below stand** — pass rates genuinely did not move
> under this constraint. **The "GB envelope" language does not.** Do not read the
> tok/s figures here as predictions for real hardware of that VRAM.
> See `../rtx2080-8gb-real/FINDING.md`.


**Run:** desktop, 2026-08-30, same meter as `gemma26-12gb-cap-e9`
(`num_ctx` 16384, `temperature` 0.8, `think` off, dispatched via `pi`).
Full 5-fixture x n=6 = 30-cell E9 battery. `num_gpu=12` -- the "8GB
envelope" calibrated in `gemma4-26b-16gb-cap/FINDING.md` (23.1 tok/s
measured there). Follow-on to `gemma26-12gb-cap-e9` (the 12GB/moderate
envelope, 30/30) -- this is the more severe envelope originally set aside
as "a stretch" before starting with 12GB.

## Result: 29/30, still no accuracy collapse -- and no timeouts despite close calls

| condition | E9 pass | decode tok/s | wall_clock_s (mean) |
|---|---|---:|---:|
| full VRAM (`e9-pi-rerun`) | 28/30 | 137.3 | 37.1 |
| 12GB cap (`num_gpu=20`) | 30/30 | 35.3 | 125.0 |
| **8GB cap (`num_gpu=12`)** | **29/30** | **23.5** | **207.5** |

Decode fell further, to 17% of full-VRAM speed (137.3 -> 23.5 tok/s,
matching the original calibration's 23.1 almost exactly), and wall-clock
more than doubled again versus the 12GB run. One `csv-summarize-repair`
trial hit 597.8s against the harness's 600s timeout ceiling -- genuinely
close, but it completed and passed; no cell in this run actually timed out
(`timed_out: False` confirmed on every record, including the one failure).

The single failure (`strict-log-format` trial 4) is the exact same
scope-creep mode (created an out-of-scope file) already characterized at
n=100 in `gemma26-csv-n100-baseline` -- not a new failure mode introduced
by the more severe constraint.

## Reading this against the n=100 baseline, not in isolation

This session's own `gemma26-csv-n100-baseline` (run earlier the same night)
found gemma4:26b's *true* rate on `csv-summarize-repair` alone is 75%
(95% CI [66.5%, 83.5%]), not the 83-100% every small sample had suggested.
Against that baseline, this run's 6/6 on `csv-summarize-repair` specifically
has a **17.8% chance of happening by pure chance at the true rate** -- not
strong evidence the 8GB cap is *cleaner* than baseline, just not evidence it
is worse either. The aggregate 29/30 across all five tasks is a more
informative number than any single task's 6/6, but the same caution from
`gemma26-12gb-cap-e9`'s own Limits section applies here too, now backed by
a concrete number rather than a general caveat: **small-sample pass rates on
this model should be read as consistent with a range, not as point
estimates.**

## Per-task token/turn/wall-clock breakdown

| task | tokens (mean, range) | turns (mean) | wall_clock_s (mean, range) |
|---|---|---:|---|
| csv-summarize-repair | 6700 (4891-9878) | 6.7 | 392.0 (277.2-597.8) |
| strict-log-format | 6170 (2781-8949) | 5.0 | 357.8 (158.1-530.8) |
| ambiguous-anchor | 2318 (1955-2582) | 9.7 | 137.6 (117.7-151.0) |
| booking-off-by-one | 1483 (824-1954) | 5.2 | 89.4 (55.5-114.9) |
| constant-and-callers | 860 (625-1329) | 9.3 | 60.8 (46.8-89.6) |

Token counts here sit inside the same broad ranges as the full-VRAM and
12GB-cap runs -- no systematic verbosity increase from the more severe
compute constraint. Wall-clock scaling is roughly proportional to the
decode-speed drop (about 5.9x slower decode than full VRAM, and wall-clock
correspondingly grew, though not perfectly linearly since tool-execution
and prefill time don't scale with `num_gpu`).

## Interpretation

Combined with `gemma26-12gb-cap-e9` (30/30) and the mechanistic argument
already made there (compute placement changes *where* arithmetic happens,
not *what* it computes), this extends the "no accuracy cost from VRAM
constraint" finding to a second, more severe envelope on the same model.
The pattern now holds at two independent severity levels (12GB and 8GB),
both clean, both explainable by mechanism, and both now correctly
contextualized against a real noise floor rather than an assumed
near-100% baseline. This is stronger than either capped run alone, though
still short of a properly powered (n=100-per-condition) comparison.

## Limits

- Same model (gemma4:26b, MoE) as the 12GB run -- density generalization is
  a separate, still-open question (see Phase 3 of this session's work).
- n=6 per cell; per the n=100 baseline finding above, a 1-2 cell difference
  in either direction on any single task is not distinguishable from
  chance at this sample size.
- One trial came within 2.2s of the 600s timeout ceiling. This run did not
  cross that line, but a harder task or an unluckier draw plausibly could
  at this compute envelope -- worth flagging as an operational risk for any
  future 8GB-envelope run, independent of the accuracy question.
