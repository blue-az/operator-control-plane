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

## Addendum 2026-08-17 — 35b is in the field, on the lip

E11's seven models were 100% GPU. That transfer claim stands. It does not
mean a later model with a 4% weight lip is off the ranking. `qwen3.6:35b`
runs at 86.4 t/s with 4%/96% placement (`q36-35b-spill-tps`). G2 no longer
treats that as a veto. Cite placement; do not omit the row.

## What the second card actually unlocks

Not a re-ranking of the E11 field — that field already ran clean at full
residency. For **35b** the second card is a residency experiment (kill the
4%), not a 2× decode claim. What it also unlocks is **models that do not
load on one 24 GB card at all**, which is a different question from ranking
the ones that do (including 35b on the lip).

It does **not** address the binding constraint on ranking the current top band.
That constraint is fixture difficulty: the three fixtures sit at ~1511, ~1598 and
~1994 Elo while the top band sits near ~1800, so the band is measured only by
items that are saturated or out of reach. No amount of VRAM fixes an item gap
between 1650 and 1990.

---

## Addendum 2026-09-05 — the 3090s-to-bench swap

Planned end state: **both 3090s + the 32 GB RAM move to the testbench; the 2080
moves to the desktop; CPUs stay put.** Checked before the swap:

### Topology risk: none. Both machines are the same board.

| | desktop | testbench |
|---|---|---|
| board | **MSI MPG Z390 GAMING PLUS (MS-7B51)** | **MSI MPG Z390 GAMING PLUS (MS-7B51)** |
| CPU | i9-9900KF (8c/16t) | i3-9100F (4c/4t) |
| RAM | 31 GB | 15 GB (32 GB after swap) |

Identical boards means identical slot wiring, so the dual-card link topology
transfers exactly.

### What that topology actually is — worth knowing on its own

**The desktop's second 3090 has been running at PCIe x4 this whole time.**

```
01:00.0  max_x16  cur_x16   -> root port 00:01.0  (CPU lanes)
03:00.0  max_x16  cur_x4    -> root port 00:1b.4  (PCH)
```

This board feeds one x16 slot from the CPU; the second card lands on a chipset
x4 port. **Every dual-card result in this program was measured with card 2 on a
PCIe 3.0 x4 link** — the 45 GB residency work, `CONCURRENCY-001`, and the
co-residency experiment.

Two consequences:

1. **Layer-split decode is not PCIe-bound.** `qwen3-next` at 79.1 tok/s and
   `gpt-oss:120b` at 34.1 tok/s are split across an x4 link. Ollama splits by
   layer, so per-token inter-card traffic is one activation vector, not weights.
   The x4 does not appear to be the constraint on decode.
2. **Model load time over x4 is not measured** and is the place the narrow link
   should hurt. Loading 45–65 GB across it is likely a large share of the
   observed load latency. Untested.

If a future board offers x8/x8, that is a real variable to re-test — and it
means these numbers are a **floor**, not a ceiling.

### What transfers, per this document's own framework

Unchanged: pass/fail outcomes on deterministic postconditions. The E9 battery
has the same properties the 2026-08-14 check established — no timeout-mediated
cells, and residency now verified from daemon layer counts rather than
`ollama ps`.

**Does not transfer:** every wall-clock, tok/s and residency figure, exactly as
before. The CPU changes from 8c/16t to 4c/4t under the dual-card pool.

The one measurement bearing on that: on the 2080, the **i3 came within 1.7% of
the i9** (31.55 vs 31.02 tok/s) on heavily-offloaded MoE work
(`fixtures/rtx2080-8gb-real/`). For fully-GPU-resident models the CPU should
matter even less. **The exception is the co-residency result (RQ3)**, which was
explicitly RAM-bandwidth-bound; it is the finding most likely to move and should
not be quoted post-swap without re-running.

### Caveat on this document's original criterion 2

The 2026-08-14 residency argument rested on **279 `ollama ps` samples**. That
instrument is now known to misreport (`docs/VRAM_IS_A_BUDGET_STUB.md`). The
error direction is favourable — the two audited cases had `ollama ps` claiming
*more* CPU offload than reality — so "100% GPU" readings are conservative and
the original conclusion stands. But the evidence is weaker than it reads.

### Recommended pre-swap action

Capture a pinned-config decode baseline on the desktop **before** the cards
move, so post-swap differences are attributable to the hardware rather than to
drift or config mismatch. Three separate figures were wrong on 2026-09-05 purely
from comparing across configurations; a swap is exactly the event that generates
more of those.
