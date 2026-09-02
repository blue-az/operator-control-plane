# HANDOFF — E9 at L1 under `pi` (screen)

**Launched:** 2026-09-02, desktop. **Status when written:** running.
**Read this before interpreting `RESULTS.md`.**

## The question

Does the E9 battery discriminate at **L1**, under the **current `pi` harness**?

Not "is L1 harder than L2" — that is known. The question is whether the
`opr` → `pi` harness upgrade lifted L1 into saturation the way it
demonstrably did to L2.

## Why this run exists

`e9-full-battery-saturation/FINDING.md` (2026-08-31) concluded the battery
no longer discriminates for the current roster. **That finding is
L2-specific**, and every run it drew on used L2. L0/L1 were never run under
`pi` at all.

Prior L1 evidence exists but is **`opr`-era and cannot be carried forward**
(`q38-shape`, 2026-08-14, n=6):

| level | gemma4:26b | qwen3.8:27b | note |
|---|---:|---:|---|
| L0 | 2/18 | 1/18 | floor — both fail, no signal |
| **L1** | **14/18** | **7/18** | Fisher two-sided **p = 0.0409** |
| L2 (pi-era) | 30/30 | 30/30 | ceiling — no signal |

**Why that L1 result is not trustworthy here:** `q38-shape` ran under `opr`.
The `pi` migration moved gemma4:26b at L2 from **18/30 to 28/30**, and
`e9-pi-rerun` concluded outright that "opr-era harness quality was the real
bottleneck, not model capability." `opr` was suppressing pass rates by
roughly the margin that separated those two models. A 14/18-vs-7/18 gap
measured under a harness that was itself failing could easily become
17/18-vs-16/18 under `pi`.

Checked and **ruled out** as the explanation: OPR-RUL-008 (the
exit-after-first-state-change cap). `--continue-steps` *is* present in
`q38-shape`'s argv, and its failures show genuine per-trial variation rather
than the all-cells-fail signature that exposed that bug in E8. The confound
here is the harness *generation*, not that specific defect.

## What is running

```
OPERATOR_MACHINE=desktop python3 -u runner.py \
  --models gemma4:26b gemma4:31b qwen3.8:27b gpt-oss:120b \
  --tasks ambiguous-anchor booking-off-by-one constant-and-callers \
          csv-summarize-repair strict-log-format \
  --levels L1 --trials 6 --num-ctx 16384 --temperature 0.8 --think off
```

4 models x 5 tasks x n=6 = **120 cells**. Screen tier per
`GOLD_STANDARD.md` §2a — hypothesis-generating only. **No pass-rate claim
from this run is reportable**, however clean it looks. That rule exists
because of `gemma26-csv-n100-baseline`, where three separate clean n=6
samples masked a true rate of 75%.

## `qwen3.6:35b` is deliberately excluded

It reproduces the cross-GPU auto-split CUDA illegal-memory-access crash on
the shared systemd daemon (root-caused 2026-08-28; recurred 2026-08-31 in
`ledger-strict-screen`, where it produced a 0/1 that was **not** a
capability result). Running it here would knowingly generate invalid zeros.

It needs a separate run against an isolated single-GPU daemon
(`CUDA_VISIBLE_DEVICES=0` **and** `GGML_VK_VISIBLE_DEVICES=` — Vulkan
enumerates the second card independently and `CUDA_VISIBLE_DEVICES` alone
does not stop it). **Follow-up, not done in this pass.**

## How to read the result

**If L1 shows real spread** — the instrument is recoverable without new task
design. Next step is n=30 on the cells that spread, which is the Reportable
tier and yields an honest CI. L1 pass rate then serves as a continuous 0-100
score, which is what the composite-index standards use and what pass/fail at
a single level cannot give you.

**If L1 saturates too** — the existing ladder is exhausted for this roster.
L0 is already a floor (both models under 12% in `q38-shape`), L2 is a
ceiling, and L1 joining the ceiling leaves no usable rung. Harder task
design becomes the only path, and `ledger-strict-reconciliation` (screened,
not validated) is the existing candidate. This outcome also **retires
`q38-shape`** as an opr-era artifact — it is currently cited as live
evidence that qwen3.8:27b needs plan-shaped input, and that claim would not
survive.

**Either way**, `e9-full-battery-saturation/FINDING.md` needs amending: its
saturation claim is L2-specific and is not currently labelled as such.

## What NOT to conclude

- Do not compare these numbers to `q38-shape`'s directly. Different harness.
  The whole point of this run is that such a comparison is invalid.
- Do not read a clean 6/6 as evidence of a high true rate (see §2a).
- Do not treat any `qwen3.6:35b` number as capability until it has been
  re-run against the isolated daemon.
- A 0-token or empty-output cell is `INVALID`, not a score of 0. Check
  `trajectory.completion_tokens` and `stderr` before scoring any zero.

## Outputs

- `RESULTS.md` — pass rates per model x task
- `state.json`, `run.log`, `traces/` — 120 trace JSONs
- Trace gotcha: `passed` and `wall_clock_s` are top-level;
  `completion_tokens` and `n_calls` are nested under `trajectory.*`
