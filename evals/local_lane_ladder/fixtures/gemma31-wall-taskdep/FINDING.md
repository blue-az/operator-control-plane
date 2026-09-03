# The dense VRAM "wall" is a stochastic stall with task-varying probability — not a wall, and not a slowdown

**Run:** desktop, 2026-09-03. `gemma4:31b` at `num_gpu=40` (~13.9 GiB, the
setting that produced 2/2 timeouts on `csv-summarize-repair`), L2, n=3 on the
three E9 tasks never tested at that cap. Same daemon throughout — verified by
process uptime, since a daemon swap was attempted mid-run and did not take.

**Question:** `gemma31-vramcap-e9` established a viability boundary between
`num_gpu` 40 and 45 using `csv-summarize-repair` alone. Is that boundary a
property of the model, or of the model *and* the task?

## Result: the boundary is task-dependent, and three tasks clear it cleanly

| task | result at `num_gpu=40` | wall |
|---|---|---|
| ambiguous-anchor | **3/3 pass** | 178-249s |
| booking-off-by-one | **3/3 pass** | 341-395s |
| strict-log-format | **1/3 pass**, 2 timeouts | 371s / 608s |
| csv-summarize-repair *(prior run)* | **0/2**, both timeout | 602s |

The same model, same envelope, same pin: two tasks are entirely unaffected,
one is mostly broken, one is completely broken. **`gemma31-vramcap-e9`'s
boundary is not a model property.**

## The mechanism is a stall, not a slowdown — and both prior framings were wrong

| outcome | tool calls | completion tokens | wall |
|---|---:|---:|---:|
| completions | 4-6 | **692-1600** | 178-395s |
| timeouts | **2** | **79-193** | 600s+ |

Timeouts produce roughly **0.3 tok/s**; completions run at roughly **4 tok/s**
on the same setting. The failing trials generate an order of magnitude *fewer*
tokens, and always stop after exactly **two tool calls**.

This rules out the two obvious readings:

- **Not a hard viability wall.** Three of four tasks clear the same envelope.
- **Not a uniform slowdown crossing a fixed deadline.** That predicts failures
  generate *more* tokens than successes before running out of clock. They
  generate far fewer.

**And it is not task-determined either.** `strict-log-format` produced a clean
1,557-token completion in 371s *and* two 190-token stalls, at the same
`num_gpu`, same prompt, same daemon. The stall is **stochastic**, with a
probability that varies by task: 0/3, 0/3, 2/3, 3/3.

## Working mechanism: prefill on a grown context

Every stall halts after two tool calls — the point at which the model has read
fixture files and its context has grown substantially. The original
`gemma31-vramcap-e9` write-up floated "extremely slow prefill on this task's
larger fixture context" as one of two candidate explanations and could not
separate them with one task. This run supports it: the tasks that stall are the
ones whose solution requires ingesting more file content before acting, and the
stall occurs precisely after ingestion rather than during generation.

If that is right, the operative variable is **context size at the moment of the
next forward pass**, not task difficulty and not total work — and the failure is
a prefill cost that becomes catastrophic once enough layers are CPU-resident.

**Not confirmed.** Prefill time was not measured directly. The competing
explanation — that the model enters a degenerate compute state that some
prompts trigger more often — is not excluded by this data.

## Consequences

1. **`gemma31-vramcap-e9`'s boundary claim must be scoped to
   `csv-summarize-repair`.** As written it reads as a model-level property. It
   is not.
2. **The `ARCHITECTURE_PREDICTS_THE_WALL` stub is overclaiming in its title.**
   There is no wall; there is a stall whose probability depends on the task.
   Dense-vs-MoE still predicts *throughput* under constraint, which is real and
   mechanistic — but "the wall" is the wrong object.
3. **A 600s timeout scored as FAIL conflates a stall with a wrong answer**, the
   same conflation already flagged for `no_dispatch`. A near-zero-token,
   two-call, full-timeout cell is an operational failure, not a capability
   measurement, and `RESULTS.md` cannot currently distinguish them.

## Limits

- n=3 per task, screen tier. The 2/3 stall rate on `strict-log-format` is
  consistent with anything from ~20% to ~95% true.
- One model, one `num_gpu` setting. Whether stall probability rises smoothly as
  `num_gpu` falls, or switches on at a threshold, is untested.
- Prefill is inferred from the two-call signature, not measured. Timing the
  prefill phase directly would confirm or kill the mechanism in one run.
- `csv-summarize-repair`'s numbers come from the earlier fixture, a different
  run on the same setting — not re-run here.
