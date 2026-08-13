# E11 finding — depth resolves the ranking, and stability is bimodal

**Run:** desktop, 2026-08-13, rev `cbcd75b`, 252/252 cells, 252/252 traces, zero
CPU spill, n=12, `num_ctx 16384 · temperature 0.8 · think off`, `--on-repeat`
default. **Not UID-verified. No claim registered.**

Pools with `e9-ceiling-continued` for **n=18 / 378 cells** on the three fixtures
that carry signal. `booking-off-by-one` (42/42) and `constant-and-callers`
(36/42) were dropped as uninformative.

Last clean single-3090 baseline — a second card arrives 2026-08-14.

## Pooling was validated, not assumed

E9 and E11 ran the same fixtures at the same settings in different invocations.
Comparing them against the 11.3% per-cell noise floor measured in `e10`:

| Model | E9 (n=6) | E11 (n=12) | Δ |
|---|---:|---:|---:|
| `gemma4:26b` | 12/18 | 24/36 | **+0.0** |
| `gemma4:31b` | 12/18 | 24/36 | **+0.0** |
| `qwen3-vl:30b` | 4/18 | 8/36 | **+0.0** |
| `gemma3:27b` | 0/18 | 0/36 | **+0.0** |
| `qwen3:32b` | 1/18 | 3/36 | +2.8 |
| `qwen2.5-coder:14b` | 3/18 | 0/36 | **−16.7** |
| `qwen3.6:27b` | 12/18 | 16/36 | **−22.2** |
| aggregate | 44/126 | 75/252 | −5.2 |

**Stability is bimodal, and it lines up exactly with the flips metric.** Four
models reproduced to the decimal across separate invocations. The only two that
exceeded the noise floor are precisely the two E9 flagged as unstable
(`qwen3.6:27b` and `qwen2.5-coder:14b`, 3 of 5 coin-flip fixtures each).

That is an independent confirmation of the `flips` column: models with unstable
cells also drift in aggregate between runs, and stable models do not drift at
all. Pooling is therefore safe — for the unstable pair it averages over
instability, which is the honest treatment of a genuinely noisy quantity.

## Pooled ranking, n=18

| Model | Raw | Elo | 95% CI | width (was) |
|---|---:|---:|---|---:|
| `gemma4:26b` | 36/54 | **1814** | [1757, 1866] | 109 (265) |
| `gemma4:31b` | 36/54 | **1814** | [1767, 1869] | 102 (289) |
| `qwen3.6:27b` | 28/54 | 1689 | [1603, 1784] | 180 (605) |
| `qwen3-vl:30b` | 12/54 | 1447 | [1367, 1531] | 164 (304) |
| `qwen3:32b` | 4/54 | 1291 | [1200, 1381] | 181 (284) |
| `qwen2.5-coder:14b` | 3/54 | 1266 | [1189, 1363] | 174 (326) |
| `gemma3:27b` | 0/54 | 1178 | [1147, 1215] | 68 (247) |

Intervals narrowed by 40–70%; `qwen3.6:27b` went from 605 points wide to 180.

**Absolute Elo is not comparable to the earlier five-fixture fit** — this one is
scaled to three harder fixtures, so the whole field shifts. The CI *widths* are
comparable, and that is the point of the run.

## Five tiers now separate at ≥95%

```
gemma4:26b  ≈  gemma4:31b          P=0.49  — genuinely tied
        --- break, P=0.98 ---
qwen3.6:27b
        --- break, P=1.00 ---
qwen3-vl:30b
        --- break, P=0.98 ---
qwen3:32b  ≈  qwen2.5-coder:14b    P=0.63  — not separated
        --- break, P=0.97 ---
gemma3:27b
```

At n=6 only "both gemma4s beat the field" survived. At n=18 the middle resolves:
`qwen3.6:27b` is now clearly third and clearly below the leaders, and
`qwen3-vl:30b` clearly above the bottom tier — neither was established before.

Two ties are real rather than unresolved. `gemma4:26b` vs `gemma4:31b` at P=0.49
is a dead heat on correctness, which is why the seat rests on speed (13.2s vs
17.9s median) and trajectory quality. `qwen3:32b` vs `qwen2.5-coder:14b` at
P=0.63 is a 33B model failing to separate from a 15B one.

## Fixture difficulty

| Fixture | Elo | Rate |
|---|---:|---|
| `csv-summarize-repair` | 1994 | 5/126 |
| `strict-log-format` | 1598 | 51/126 |
| `ambiguous-anchor` | 1511 | 63/126 |

`csv-summarize-repair` sits ~180 points above the strongest model and only
`qwen3.6:27b` ever solves it (2/12 here, 3/6 in E9). It brackets the ceiling
rather than ranking within it — keep it as a marker, do not read it as ability.

The other two land within the field's range, which is what a discriminating
fixture should look like.

## Limits

n=18 on three fixtures, one machine, one prompt shape, one quantisation. The
11.3% per-cell noise floor bounds what any n can resolve here: the two remaining
non-separations (the gemma4 pair, and qwen3:32b vs qwen2.5-coder) may be genuine
ties rather than insufficient data, and more trials cannot distinguish those
cases. Seeds are not honoured on this stack, so these are independent draws.
