# Does the ranking survive the second GPU?

`run_e11_depth.sh` says: *"Last clean single-3090 baseline: a second card arrives
2026-08-14, after which timings and residency limits are not comparable to
anything measured here."*

Read literally that warning is about **timings and residency**. It has been
misread in this session as "the ranking expires", which would throw away 306
cells of work. Checked 2026-08-14, before the card was installed:

## The two things that would break transfer

**1. Timeout-mediated outcomes.** If a cell failed because it ran out of wall
clock rather than because its postcondition failed, faster hardware changes the
result.

| | cells | timed out |
|---|---:|---:|
| `e11-depth` | 252 | **0** |
| `q38-ladder` | 54 | **0** |

Slowest cell overall 206.3s against a 600s limit; slowest *passing* cell 179.8s;
**zero cells above 50% of the limit**. Nothing was close enough for a speed
change to flip it.

**2. Residency.** If a model was partly CPU-placed, more VRAM changes its
behaviour rather than just its speed.

279 `ollama ps` samples across E11, **all `100% GPU`**, zero CPU placement, for
all seven models — including `qwen3:32b`, which had needed the `--num-ctx` pin
in `017d672` to fit. Nothing in the field was spilling while it was scored.

## Conclusion

**The Elo ranking transfers.** Pass/fail rests entirely on deterministic
postconditions, none of which were mediated by time or placement. The second
card does not invalidate E11, e9, or the qwen3.8 run, and fixture work done now
compounds rather than being thrown away.

**What does not transfer:** wall-clock timings, tok/s, residency percentages,
and the power-limited throughput figures. Anything in a results table with a
seconds or a percent-GPU column is single-3090 only.

## What the second card actually unlocks

Not a re-ranking of the current field — that field already ran clean at full
residency. What it unlocks is **models that do not fit in 24 GB at all**, which
is a different question from ranking the ones that do.

It does **not** address the binding constraint on ranking the current top band.
That constraint is fixture difficulty: the three fixtures sit at ~1511, ~1598 and
~1994 Elo while the top band sits near ~1800, so the band is measured only by
items that are saturated or out of reach. No amount of VRAM fixes an item gap
between 1650 and 1990.
