# qwen3.8:27b on the ladder — E11-matched

**Measured:** 2026-08-14, `num_ctx 16384`, `temperature 0.8`, `think off`, L2,
n=18, 54 cells. Config copied from `run_e11_depth.sh`.
**Not UID-verified. No claim registered.**

## Result

| Fixture | qwen3.8:27b (n=18) | qwen3.6:27b (E11, n=12) | Fisher |
|---|---|---|---|
| `ambiguous-anchor` | 16/18 (88.9%) | 12/12 (100%) | p=0.503 |
| `csv-summarize-repair` | 3/18 (16.7%) | 2/12 (16.7%) | p=1.000 |
| `strict-log-format` | **15/18 (83.3%)** | **2/12 (16.7%)** | **p=0.0005** |
| **total** | **34/54 (63.0%)** | 28/54 pooled (51.9%) | p=0.331 |

Against the pooled n=18 field (/54): `gemma4:26b` 36, `gemma4:31b` 36,
**`qwen3.8:27b` 34**, `qwen3.6:27b` 28, `qwen3-vl:30b` 12, `qwen3:32b` 4,
`qwen2.5-coder:14b` 3, `gemma3:27b` 0.

## Finding 1 — the whole gain is output-contract fidelity

The total (34 vs 28) does not separate from `qwen3.6:27b`, p=0.331. The
per-fixture split does, and it is concentrated in exactly one place:
`strict-log-format` moves 16.7% → 83.3%, **p=0.0005**, which survives Bonferroni
across the three fixtures (α=0.0167).

That fixture's annotated trap is precisely this: *"the output contract
(zero-padded hour, fixed ungrammatical plural), not the logic. Models solve the
counting and ship a nicer format."* `qwen3.6` solved the logic and improvised the
format. `qwen3.8` obeys the literal contract.

The two fixtures that test reasoning rather than compliance are unchanged —
`ambiguous-anchor` flat (p=0.50, if anything slightly down), and
`csv-summarize-repair` identical at 16.7%.

**Read this as an instruction-following improvement, not a capability
improvement.** For seat selection that is the more useful of the two: exact
output contracts are what R1–R6 and the L2 plan shape are made of.

The 3 remaining `strict-log-format` failures are genuine — the battery exits 1
on a traceback, i.e. the model shipped code that crashes, not a format
deviation.

## Finding 2 — statistically level with the gemma4 pair

34/54 vs 36/54 is p=0.840. `qwen3.8:27b` is indistinguishable from both
`gemma4:26b` and `gemma4:31b` on this battery. It is the first qwen model to
reach that band; `qwen3.6:27b` at 28/54 did not.

This does **not** make it the seat. `gemma4:26b` holds the ranking on other
grounds already recorded (speed, zero-flip stability across E10/E11), and a
p=0.84 non-difference is not evidence of equivalence — it is the absence of
evidence of difference at n=18.

## Finding 3 — `csv-summarize-repair` still brackets the field

3/18. The fixture is annotated CEILING MARKER at ~1994 Elo, roughly 180 points
above the strongest model tested, and `qwen3.8` does not move it. Everything
from `gemma4:26b` (0/12 in E11) to here sits at or near its floor. The ceiling
of this battery is still above the whole local field.

## Comparability

- **Hardware:** E11's script warns its baseline holds only until a second card
  lands 2026-08-14. Checked at launch: 1× RTX 3090, 320W, second card **not
  installed**. Baseline intact. This window closes on installation.
- **Fixture drift:** `strict_log_format.yaml` was modified after E11 ran
  (`d9e3bd4`, 18:40 vs E11's 12:45 launch). Diffed before trusting the
  comparison: 3 added lines, all `#` comments, no change to prompts or
  postconditions.
- **Harness:** preflight cell PASS 11.5s, trajectory `read_file` → `patch_file`,
  `n_failed_calls` 0, `no_dispatch` False — the runner parses this model.

## Limits

- `qwen3.6`'s per-fixture baseline is **E11 alone (n=12)**; the pooled n=18
  per-fixture breakdown is not in that RESULTS.md. Totals use pooled /54,
  per-fixture uses /12. The two bases differ and the row totals will not add.
- This n=18 is a **single run**; the field's n=18 is pooled from e9 (n=6) and
  E11 (n=12) on different days. Different sampling structure, same settings.
- One model, one level (L2), three fixtures, one machine. `qwen3.8:27b` has not
  been run at L0/L1, so nothing here says whether it needs plan-shaped input.
