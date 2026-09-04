# One-off run drivers

Scripts written for specific ablations that `runner.py` could not express at the
time. Preserved 2026-09-03 out of a session scratchpad that was going to be
deleted — several of these produced findings that are now cited in committed
write-ups, and the finding was reproducible only if the driver survived.

**These are not part of the harness.** `runner.py` is. Each of these hardcodes a
model, a task set, and a sweep; read the docstring before reusing one.

| script | produced | notes |
|---|---|---|
| `gemma31_boundary_sweep2.py` | `gemma31-vramcap-e9` addendum (40/45 boundary) | Adds explicit `keep_alive:0` eviction between `num_gpu` levels and a live free-RAM floor. **v1 is deliberately absent** — it had no eviction step and killed the machine with a kernel OOM. |
| `gemma31_boundary_sweep3.py` | same addendum, `num_gpu=40` re-verification | Re-verifies a single level with the safe methodology. Aborts a trial rather than proceed below the RAM floor — that abort fired in practice and worked. |
| `run_brevity_doe.py` | `gemma26-brevity-ablation-001` | 2x2 brevity-instruction DOE. |
| `run_brevity_generalization.py` | same | Cross-model control cell. |
| `run_qnext_brevity.py` | `qwen3next-brevity-001` (negative result) | The brevity instruction made qwen3-next *worse*, 6/6 → 3/6. |
| `ablation_gemma26_brevity.py` | early brevity pilot | Superseded by `run_brevity_doe.py`; kept because the n=1 pilot's ambiguity is part of that finding's story. |
| `r1_screen_pinned.py` | `deepseek-r1-70b-screen` | Pinned-context screen; the model was characterized and parked. |
| `smoke_mixed_gpu.sh` | (pre-existing) | Not from this session. |

## Two things these encode that `runner.py` does not

**Explicit model eviction between pinned-tag levels.** Loading a second derived
tag before the first is unloaded can transiently double system-RAM residency. A
dense model's CPU-resident footprint *grows* as `num_gpu` shrinks, so the risk is
worst at exactly the settings a VRAM sweep cares about most. `sweep2` does:

```
curl -X POST http://127.0.0.1:11434/api/generate -d '{"model": <tag>, "keep_alive": 0}'
```

before loading the next level. Without it, a sweep OOM-killed `llama-server`
mid-run and silently contaminated a cell — the result was read as a "danger
zone" until the re-run showed it clean.

**A free-RAM floor that aborts rather than risks.** `free -b`, "available"
column, 10–12 GB floor, checked before each trial. Better to lose a trial than a
run.

Both belong in `runner.py` eventually. They are here because they were written
under a deadline and the findings shipped first.
