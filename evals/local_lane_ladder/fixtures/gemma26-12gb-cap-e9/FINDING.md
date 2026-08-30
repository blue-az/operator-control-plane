# gemma4:26b at a 12GB VRAM cap — does speed constraint also constrain accuracy?

**Run:** desktop, 2026-08-30, same meter as `e9-pi-rerun` (`num_ctx` 16384,
`temperature` 0.8, `think` off, dispatched via `pi`). Full 5-fixture x n=6 =
30-cell E9 battery. `num_gpu=20` -- the exact layer-count cap calibrated as
the "12GB envelope" in `gemma4-26b-16gb-cap/FINDING.md` (34.4 tok/s measured
there via a direct decode probe).

**Question:** this session repeatedly found that speed and correctness are
separate axes -- gpt-oss:120b decoded slower than expected (32.7 tok/s,
65% CPU-offloaded) yet swept E9 30/30, and the brevity-ablation work showed
verbosity (not decode speed) drives wall-clock. But all of that evidence was
observational, across different models. This is the direct, controlled
version: take one model, force it out of full VRAM residency via a real
layer-count cap (not the advisory `OLLAMA_GPU_OVERHEAD` knob), and measure
whether *accuracy* moves, holding the model itself constant.

## Result: no accuracy cost. If anything, better.

| condition | E9 pass | decode tok/s | wall_clock_s (mean) |
|---|---|---:|---:|
| full VRAM (`e9-pi-rerun`) | 28/30 | 137.3 | 37.1 |
| **12GB cap (`num_gpu=20`)** | **30/30** | **35.3** | **125.0** |

Decode collapsed to ~26% of the full-VRAM rate (137.3 -> 35.3 tok/s,
matching the earlier calibration's 34.4 tok/s almost exactly) and wall-clock
correspondingly grew ~3.4x (37.1s -> 125.0s). **Pass rate did not drop --
it went from 28/30 to a clean 30/30.** The two cells that failed at full
VRAM (a quoted-CSV-comma parsing miss on `csv-summarize-repair`, a
scope-creep miss on `strict-log-format`) both passed under the cap.

## Per-task token/turn counts: no verbosity tax either

| task | tokens (mean, range) | turns (mean) | wall_clock_s (mean) |
|---|---|---:|---:|
| csv-summarize-repair | 5751 (3522-7492) | 6.0 | 210.9 |
| strict-log-format | 6649 (4682-8731) | 4.8 | 242.3 |
| ambiguous-anchor | 1842 (1520-2521) | 7.2 | 72.4 |
| booking-off-by-one | 1618 (959-1996) | 4.7 | 63.7 |
| constant-and-callers | 705 (637-809) | 8.2 | 35.5 |

Compare against the full-VRAM baseline's own token counts (e.g.
`csv-summarize-repair` mean 4730, `strict-log-format` mean 8065): the capped
run's numbers sit inside or below the baseline's own established
trial-to-trial noise band (2.6x range documented in `e9-pi-rerun`). The VRAM
cap did not make the model noticeably more verbose to compensate, and it did
not make it terser either -- token counts here look like ordinary run-to-run
variance, not a constraint-induced behavior change.

## Interpretation

Mechanistically this is exactly what should be expected: `num_gpu` capping
moves *where* layers compute (GPU vs CPU), not *what* they compute -- same
weights, same quantization, same forward-pass arithmetic. There is no
principled reason it should touch correctness, and this result confirms
that directly, on the one axis this session had not yet controlled for
(same model, only compute placement varied). Combined with `gpt-oss:120b`'s
own clean 30/30 under 65% CPU offload, there are now two independent,
controlled data points against a general "resource constraint degrades
accuracy" hypothesis: capping GPU residency degrades throughput, and only
throughput.

This does not mean *no* mechanism can link constraint to accuracy --
quantization choice and forced context-length truncation both remain live,
separate mechanisms (see the same session's discussion) that could
independently cost real accuracy. This result specifically rules out
*compute placement itself* (GPU vs CPU, at fixed quantization and context)
as such a mechanism.

## Limits

- Single model (gemma4:26b), single envelope (12GB / `num_gpu=20`), n=6 per
  cell -- not yet checked at 8GB (`num_gpu=12`, the more extreme envelope
  originally proposed and set aside as "a stretch" in favor of this more
  moderate starting point) or on a different model.
- gemma4:26b is MoE (128 experts, 8 active) -- this result should not be
  assumed to transfer to a dense model forced into the same VRAM envelope;
  `deepseek-r1:70b`'s much worse unpinned-context collapse (2.12 tok/s) in
  this same session shows dense models can behave very differently under
  memory pressure. Not retested here at a controlled `num_gpu` cap.
- The 30/30 vs 28/30 improvement is consistent with "no accuracy cost," not
  proof of an accuracy *gain* -- n=6 per cell and known temperature-0.8
  trial-to-trial noise (documented elsewhere this session) mean a 2-cell
  swing either direction is within the noise floor already established for
  this exact model and task set.
