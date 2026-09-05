# Decode tok/s does not predict task wall clock — token economy does

**Run:** desktop (dual RTX 3090), 2026-09-05. Five roster models x two E9 tasks
(`constant-and-callers`, `csv-summarize-repair`) x L2 x n=2 = 20 cells.
`num_ctx` 16384, `temperature` 0.8, `think` off, ollama 0.32.12.
Both columns measured in the same session, same conditions.

**Question:** every throughput number this program publishes is decode tok/s from
the contract-v1 probe (`num_predict 128`, `temperature 0`). An operator does not
wait on decode; they wait on a task finishing. Does the first predict the second?

## Result: no. The fastest decoder is the third-fastest model in practice.

| model | decode tok/s | **wall clock s** | output tokens | tool calls | effective tok/s |
|---|---:|---:|---:|---:|---:|
| qwen3.8:27b | 73.8 | **28.8** | 788 | 4.8 | 27.4 |
| qwen3.6:35b | 126.6 | **29.0** | 1,380 | 7.0 | 47.6 |
| gemma4:26b | **214.1** | **34.7** | 3,366 | 5.8 | 97.0 |
| gpt-oss:120b | 35.1 | 91.4 | 921 | 6.2 | 10.1 |
| gemma4:31b | 34.8 | 117.1 | 2,715 | 4.8 | 23.2 |

**`gemma4:26b` decodes 2.9x faster than `qwen3.8:27b` and finishes the same work
20% slower.** It is the fastest model on the instrument the program has been
reporting, and third of five on the thing an operator actually experiences.

The mechanism is in the fourth column: **it emits 4.3x more tokens for the same
task** (3,366 vs 788). Its speed advantage is real and it spends all of it, plus
some, on verbosity. Decode rate sets how fast tokens come out; it says nothing
about how many the model needs.

Rank correlation between the two columns is **rho = 0.6**, and it is carried
entirely by the bottom two rows. Among the three fast models, decode spans 2.9x
while wall clock spans 1.2x — **in the opposite order**.

## Decode also overstates itself by ~2-3x

`effective tok/s` is output tokens over wall clock. It is far below decode for
every model:

| model | decode / effective |
|---|---:|
| gemma4:31b | 1.5x |
| gemma4:26b | 2.2x |
| qwen3.8:27b | 2.7x |
| qwen3.6:35b | 2.7x |
| gpt-oss:120b | **3.5x** |

Roughly **half to two-thirds of a trial is not decode at all** — it is prompt
processing, tool execution, and per-turn overhead. And the ratio is not constant
across models, so decode cannot be rescaled into a wall-clock estimate by any
single factor.

`gpt-oss:120b` is worst hit: 45.6 GB resident across both cards, and 3.5x of its
decode rate disappears into overhead.

## Caveat: the decode probe itself drifted 1.6x today

`gemma4:26b` measured **133.3 tok/s** in this morning's re-baseline and **214.1**
here, same machine, same day. The configurations differ (this run pins
`num_ctx 16384`, `temperature 0.8`; the probe baseline was unconstrained), which
is a plausible cause but was not isolated.

Whatever the cause, it means **the decode column is not stable across
configurations to better than ~1.6x**, which is larger than several of the
distinctions the program has drawn with it. This is the fourth instrument problem
in a week, after ollama's Vulkan fallback, `/api/ps` VRAM misreporting, and the
hardcoded prompt path. It does not affect the wall-clock column, which is
measured directly.

## Consequence

**Report wall clock and output tokens for model-selection claims. Use decode
tok/s only for hardware comparisons of a fixed model** — same weights, same
config, different card — which is what the 8 GB and dual-card work does, and
where it remains valid.

Any past claim of the form "model X is faster than model Y" that rests on decode
tok/s is unsupported for agentic work and should be re-derived. `gemma4:26b` in
particular has been described as the roster's fast model; on task completion it
is not.

## Limits

- **n=2, two tasks, all cells passed (20/20).** Screen tier for the pass rates,
  which are not the point here. Wall clock is continuous and the model ordering
  is stable across both tasks, but n=2 means the per-model means carry real
  spread — `gemma4:26b` ran 64.0 s and 33.1 s on the same task.
- Both tasks passed for every model, so `csv-summarize-repair` did not
  discriminate here as it has previously. These are timing data, not a capability
  result.
- Tool-execution time is inside wall clock and was not separated from model time.
  A task with heavier tools would shift all five models toward each other.
- The 1.6x decode drift is unexplained and should be isolated before the decode
  column is trusted again at fine resolution.
