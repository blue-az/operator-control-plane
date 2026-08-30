# gemma4:31b (dense) VRAM cap — density breaks the MoE resilience pattern

**Run:** desktop, 2026-08-30 (overnight), same meter as the gemma4:26b
VRAM-cap runs (`num_ctx` 16384, `temperature` 0.8, `think` off, dispatched
via `pi`). **Deliberately scoped down**: 2 tasks x n=3 = 6 cells
(`csv-summarize-repair`, `constant-and-callers`), not the standard 5-task
x n=6 = 30-cell battery. Reason: a single screening trial at this envelope
took 487.4s for a task that only needed 1984 tokens -- extrapolating that
pace to a full 30-cell run suggested 3-5+ hours, and prioritizing a real,
documented, smaller result over an unfinished large one was the right call
given this ran unattended overnight.

`num_gpu=40` -- confirmed via `ollama ps` to land at ~13 GiB VRAM, meaningfully
below gemma4:31b's ~19-21 GiB full-VRAM footprint (a comparable *relative*
severity to gemma4:26b's 12GB cap, ~67% of each model's own layer count,
though the two models are not directly comparable in absolute GB since
gemma4:31b is wider per layer).

## Headline: density does not share MoE's resilience under this constraint

| task | full-VRAM baseline (`e9-pi-rerun`) | this run (n=3, num_gpu=40) |
|---|---|---|
| constant-and-callers | 6/6 | **3/3, clean** (128.2-173.5s, 524-708 tokens) |
| csv-summarize-repair | 6/6 | **0/3, all three timed out** at exactly 600s |

decode tok/s (contract-v1 probe): **5.0** -- in the same catastrophic
territory as `deepseek-r1:70b`'s unpinned-context collapse (2.12 tok/s)
earlier this session, both dense models under severe memory pressure.

This is a genuinely different result from gemma4:26b's two VRAM-cap runs
(30/30 at 12GB, 29/30 at 8GB, *zero* timeouts even at the more severe 8GB
envelope). gemma4:26b is MoE (8 of 128 experts active); most of its
CPU-resident weight mass simply isn't touched most steps, so forcing layers
off-GPU costs throughput but not viability. gemma4:31b is dense -- every
layer's full weight matrix is read every token, on every forward pass,
regardless of GPU/CPU placement. Under the same relative severity of
constraint, that difference in architecture is the difference between
"3-4x slower, same accuracy" and "cannot finish the harder task at all
within a 10-minute budget."

## The timeout is a stall, not "ran out of time while still working productively"

The three timed-out trials produced only 79, 93, and 143 completion tokens
in over 600 seconds each -- effectively under 0.25 tok/s, far below even
the already-catastrophic 5.0 tok/s raw decode figure. Each used only 2 tool
calls. This is not a case of the model verbosely working toward a correct
answer and running out of budget (contrast with, e.g., `qwen3-next`'s
verbosity-driven slowness earlier this session, which still produced
thousands of tokens) -- it is a near-total stall, consistent with either
extremely slow prefill on this task's larger fixture context, or the model
getting stuck early in a compute-bound step it could not clear within the
window. `constant-and-callers`' clean completions (524-708 tokens, 128-174s)
confirm the model and the harness both work correctly at this same
`num_gpu` setting -- the failure is specific to `csv-summarize-repair`'s
combination of task and compute envelope, not a broken pin or a crashed
process.

**This is a distinct failure mode from an accuracy miss and should not be
read as "gemma4:31b got the CSV problem wrong."** It never got far enough to
produce a wrong answer. The finding is about practical viability at this
compute envelope, not about reasoning quality.

## Interpretation

Combined with this session's dense-vs-MoE evidence elsewhere (deepseek-r1's
unpinned-context collapse, gemma4:31b's own architectural slowness
disadvantage on the full-VRAM roster), this extends a consistent pattern:
**dense models are far more sensitive to compute-placement constraints than
sparse MoE models, to the point of practical non-viability on some tasks,
not just a proportional slowdown.** The "no accuracy cost from VRAM
constraint" finding established for gemma4:26b does **not** generalize to
dense architectures -- if anything, the evidence here points the opposite
direction for density: severe constraint can make a task **unworkable**
within a standard timeout, which is a more serious practical problem than
a modest accuracy dip would have been.

## Limits

- Deliberately scoped (n=3, 2 tasks) -- not the full battery. The clean
  `constant-and-callers` result and the uniform `csv-summarize-repair`
  timeout (3/3, effectively deterministic at this severity) are both
  strong enough signals that a larger n is unlikely to change the
  qualitative conclusion, but the exact boundary (what `num_gpu` value
  would let `csv-summarize-repair` complete, and whether other tasks
  behave like `constant-and-callers` or like `csv-summarize-repair`) is
  unmapped.
- Single severity level tested (num_gpu=40, ~13GB). Unlike gemma4:26b's
  two-level test (12GB and 8GB), this run does not establish whether a
  milder cap on gemma4:31b (e.g., 16GB) would avoid the timeout -- that
  would be the natural next screen if this line of work continues.
- The stall mechanism (prefill vs. compute-bound tool step) was not
  isolated -- worth a targeted follow-up if this matters operationally.
