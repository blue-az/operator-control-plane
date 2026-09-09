# The second card is worth 5.5x at the operator's context depth and nothing at benchmark depth

**Run:** desktop, 2026-09-08. `hw_standard.py`, Standard A, loaded regime
(12,838 prompt tokens), n=3, `qwen3.8:27b` across four context depths on both
arms. Solo daemon isolation verified per `GOLD_STANDARD.md` 2b.2.

Predictions were registered in `HANDOFF_2026-09-06.md` before the run. One of five
hit.

## Result

| config | decode tok/s | prefill ms/token | VRAM total |
|---|---:|---:|---:|
| dual ctx16384 | 62.8 | 0.865 | 20,424 |
| dual ctx32768 | 60.5 | 0.872 | 21,896 |
| dual ctx65536 | 60.8 | 0.872 | 24,844 |
| dual ctx131072 | 61.4 | 0.888 | 28,644 |
| solo ctx16384 | 55.1 | 0.872 | 18,907 |
| solo ctx32768 | 57.8 | 0.872 | 20,027 |
| solo ctx65536 | 56.4 | 0.872 | 22,237 |
| **solo ctx131072** | **11.2** | **1.573** | 22,823 |

## The headline

At **ctx131072** - the depth the operator sizing work recommends for interactive
use, against a measured median turn of 72,113 tokens - dual runs **61.4 tok/s** and
solo runs **11.2**. That is **5.5x**.

At ctx16384, the depth every other battery in this program uses, the same
comparison reads **-8%**. Same daemon, same model, opposite conclusions. **Depth
is not a parameter of this experiment, it is the experiment.**

## What that does to the dual-card question

It resolves the null rather than contradicting it. Splitting does nothing for
decode while the model fits one card, and is worth 5.5x when it does not. The
second card is not a speed upgrade. It is what keeps the seat model resident at
the operator's real context depth.

Dual decode is flat across the whole range - 62.8 to 61.4 from 16k to 131k - while
VRAM grows 20,424 to 28,644 MiB. **With two cards, context costs memory and not
speed.** With one card it costs both, discontinuously.

## Spill cost does not transfer between models

Solo at 131072 holds 22,823 MiB against the 28,644 the model needs, so roughly
5,821 MiB (~20%, about 13 of 66 layers) is on CPU. Time per token goes 17.7 ms to
89.3 ms: **~5.5 ms per CPU-resident layer**, four times the 1.34 ms measured on
`gemma4:26b`. Predicted 8% per layer, actual ~31%.

Caveat: the layer count is inferred from the VRAM shortfall, not measured. The
solo arm recorded `layers: None` because `layers()` parsed the systemd journal and
the solo daemon does not run under that unit. Fixed 2026-09-08 by adding
`placement()`, which reads `/api/ps` on the daemon under test.
