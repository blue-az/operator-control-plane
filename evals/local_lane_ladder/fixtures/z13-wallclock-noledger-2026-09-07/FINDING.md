# Cross-chip wall clock, corrected — decode punishes the dense model, task time does not

**Run:** z13 (Ryzen AI MAX 390), 2026-09-07. Three models × two E9 tasks × L2 ×
n=4 (trial 1 cold, 2–4 warm), `e9pin ctx16384 t0.8`, think off, **`--no-ledger`**,
`pi` 0.85.1 version-matched. Compared against
`preswap-wallclock-noledger-2026-09-07` on the dual-3090 desktop.

**Supersedes `z13-wallclock-2026-09-07`**, whose timings included ~+4.5 s/trial of
ledger bookkeeping inside `wall_clock_s` (fixed in `runner.py` 2026-09-07).

## Cross-chip speed, normalised to desktop `gemma4:26b`

| chip | model | short | long | speed |
|---|---|---:|---:|---:|
| RTX 3090 | qwen3.6:35b | 8.8 | 15.6 | **1.99** |
| RTX 3090 | gemma4:26b | 13.0 | 38.9 | 1.00 |
| RTX 3090 | qwen3.8:27b | 18.1 | 32.4 | 0.96 |
| MAX 390 | qwen3.6:35b | 27.3 | 40.6 | **0.72** |
| MAX 390 | gemma4:26b | 26.3 | 132.4 | 0.39 |
| MAX 390 | qwen3.8:27b | 35.3 | 96.8 | 0.39 |

`qwen3.6:35b` leads on **both** chips. On the MAX 390 the other two are tied
(0.394 vs 0.385).

## Correction: the dense-penalty claim was overstated

The superseded run showed `qwen3.8:27b` at 57.9 s on the short task against
`gemma4:26b`'s 20.6 s, and that was used to argue dense models are
disproportionately punished on this chip. **Clean, it is 35.3 s against 26.3 s**
— and on the long task 27b now *beats* 26b, **96.8 s vs 132.4 s**.

What survives is narrower and more interesting:

| model | arch | z13 decode | z13 speed |
|---|---|---:|---:|
| qwen3.6:35b | MoE | 54.5 | 0.72 |
| gemma4:26b | MoE | 53.7 | 0.39 |
| qwen3.8:27b | **dense** | **22.4** | **0.39** |

**Decode punishes the dense model 2.4x. Task time does not punish it at all.**
`qwen3.8:27b` decodes at 41% of `gemma4:26b`'s rate on this chip and completes
the same work at the same speed, because it emits far fewer tokens. This is the
decode-vs-wall-clock result reproducing on a second, very different accelerator —
and it is the cleanest case of it yet, since here the two effects almost exactly
cancel.

The dense-model penalty on constrained hardware is real but is a **decode**
phenomenon (and a residency one, per `testbench-2080-fit-check`'s 16/66 layers).
It does not automatically become a task-time penalty.

## Still no chip factor

| model | short | long |
|---|---:|---:|
| gemma4:26b | 2.02x | 3.40x |
| qwen3.8:27b | 1.95x | 2.99x |
| qwen3.6:35b | 3.09x | 2.61x |

Range **1.95x–3.40x**, and it still reverses between tasks (`gemma4:26b` is the
least penalised on the short task and the most on the long). Budget cross-chip
work per task, not per chip. This conclusion is unchanged from the superseded
run.

## Limits

- n=3 warm per cell. Within-cell spreads on the desktop ran 1.3x–4.2x; the same
  noise applies here, and it is why the two tied MAX 390 rows should not be
  ordered.
- **z13 runs ollama 0.32.13, the desktop 0.32.12** — a stated confound on
  cross-chip magnitudes, not on within-chip ordering. Downgrading was rejected as
  a 2.3 GB system change to remove an unmeasured one-patch risk.
- Two tasks, three models.
- Quality for this chip is in `z13-seat-2026-09-07` (n=6/fixture, `/18` scale) and
  is **not** pooled with the desktop's deeper corpus.
