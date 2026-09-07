# Pre-swap wall-clock baseline — cold and warm separated, per task

**Run:** desktop, 2026-09-05. Six models x two L2 tasks x **4 trials** (trial 1
cold after load, trials 2–4 warm), `e9pin ctx16384 t0.8` — the same pinned path
as `preswap-baseline-2026-09-05/baseline.json`, so the two halves are comparable.
i9-9900KF, 31 GB, dual 3090 (x16/x4), ollama 0.32.12.

**Why:** decode is the stable column (±1% here) and is *not* what the hardware
swap will change for day-to-day use. Wall clock is, and it is a far worse
instrument — it mixes load, prefill, decode, tool execution, and how many tokens
the model chose to emit. The earlier `roster-walltime-2026-09-05` snapshot used
n=2 and averaged a cold and a warm trial into one mean, which hid a spread of up
to 3.3x. **Those means must not be used as the pre-swap reference.** These
replace them.

## Baseline — do not average across tasks

### constant-and-callers (short)

| model | cold t1 | warm mean | warm range | out tok | calls | decode | pass |
|---|---:|---:|---|---:|---:|---:|---:|
| gemma4:26b | 15.8 | **15.0** | 14.9–15.1 | 711 | 8.0 | 236.0 | 4/4 |
| gemma4:31b | 60.0 | **39.2** | 29.3–44.8 | 657 | 7.7 | 36.2 | 4/4 |
| qwen3.8:27b | 35.4 | **17.9** | 15.3–19.9 | 577 | 5.0 | 70.6 | 4/4 |
| qwen3.6:35b | 31.1 | **13.0** | 11.9–14.6 | 862 | 7.7 | 130.5 | 4/4 |
| qwen3-next | 130.0 | **73.6** | 57.8–102.2 | **4,669** | 4.0 | 79.1 | 4/4 |
| gpt-oss:120b | 120.5 | **36.1** | 32.8–40.2 | 717 | 8.0 | 34.2 | 4/4 |

### csv-summarize-repair (long)

| model | cold t1 | warm mean | warm range | out tok | calls | decode | pass |
|---|---:|---:|---|---:|---:|---:|---:|
| gemma4:26b | 59.3 | **46.0** | 37.7–60.5 | 7,004 | 6.0 | 225.0 | **3/4** |
| gemma4:31b | 137.9 | **168.5** | 129.0–232.4 | 5,063 | 4.0 | 36.5 | 4/4 |
| qwen3.8:27b | 48.9 | **29.7** | 21.0–37.3 | 1,362 | 4.7 | 78.8 | 4/4 |
| qwen3.6:35b | 33.2 | **21.2** | 16.6–29.7 | 1,858 | 4.0 | 132.2 | 4/4 |
| qwen3-next | 202.7 | **319.3** | 162.5–532.8 | **21,309** | 5.3 | 78.8 | **2/4** |
| gpt-oss:120b | 180.8 | **78.3** | 61.5–109.5 | 1,862 | 7.0 | 33.9 | 4/4 |

## Cold trial 1 inflates by up to 3.3x

| cell | cold/warm |
|---|---:|
| gpt-oss:120b · constant | **3.34x** |
| qwen3.6:35b · constant | 2.39x |
| gpt-oss:120b · csv | 2.31x |
| qwen3.8:27b · constant | 1.97x |

Any n=2 mean that includes trial 1 is a blend of two different measurements.
**`gemma4:31b` on csv inverts** — warm (168.5) is *slower* than cold (137.9) —
so "discard trial 1" is not universally right either; label it, do not assume it.

## L2 is not saturated. That claim was an artifact of n=2.

The earlier n=2 run returned 20/20 and was read here as the L2 ceiling being
reached. At n=4, two cells fail: **`gemma4:26b` 3/4** and **`qwen3-next` 2/4** on
`csv-summarize-repair`. The failures are genuine postcondition failures, not
timeouts — `qwen3-next` emitted `"$1` into a field the checker parses as a float.

`csv-summarize-repair` still discriminates. **Two extra trials, not a harder
task, was the difference.**

## qwen3-next is a verbosity outlier and it is why it fails

**21,309 output tokens** on csv against 1,362–7,004 for every other model, and
4,669 on the short task where peers emit 577–862. Its 319 s warm mean is
overwhelmingly self-inflicted: at 78.8 tok/s decode it is not slow, it simply
will not stop.

This is the token-economy finding at its extreme — and here verbosity does not
merely cost time, it **costs correctness**, since the two failures are the runs
that rambled furthest.

**One cell reached 532.8 s against the harness's 600 s limit.** On the bench's
slower CPU that same cell would likely time out, which would be recorded as a
different failure mode for the same underlying behaviour. Watch for it.

## How to compare after the swap

1. Re-run this exact command (`--trials 4`, same two tasks, same pins).
2. Compare **per task**, **warm-only**, against the warm range — not the mean.
3. **Check output tokens first.** If wall clock moved and token count did not,
   that is the hardware. If token count moved, it is sampling, not the cards —
   the models are at `temperature 0.8`.
4. Ignore pass/fail deltas below n=30; these cells are Screen tier.

## Limits

- n=3 warm per cell. Ranges are wide enough that only large moves will be
  readable — `qwen3-next` csv spans 162.5–532.8 s and can detect almost nothing.
- `temperature 0.8` means token count varies by sampling between runs, which is
  the noise source criterion 3 above depends on. A temperature-0 variant would
  be a tighter instrument and was not run.
- Tool-execution time is still inside `wall_clock_s` and unseparated.
