# The headless bench reproduces desktop correctness at 3.8x the wall clock

**Run:** testbench (System 2), 2026-09-05. `gemma4:26b`, five E9 tasks, L2, n=3,
`num_ctx` 16384, `temperature` 0.8, `think` off. RTX 2080 (8 GB), i3-9100F,
15 GB RAM, Debian 12, ollama 0.32.12, `pi` 0.85.0 — both version-matched to the
desktop. `OPERATOR_MACHINE=testbench`.

**Question:** the campaign plan puts most functional benchmarking on the headless
bench and keeps hardware-scaling experiments on the dual-3090 desktop. That only
works if the bench produces *the same correctness answers*. Does it?

## Result: yes — same answers, roughly four times slower

| | desktop (3090, committed) | bench (2080, this run) |
|---|---|---|
| E9 L2, gemma4:26b | **28/30** (93%) | **15/15** (100%) |
| wall-clock mean | **37.1 s** | **141.1 s** |

**15/15 is entirely consistent with the desktop's 93% rate** — P(15/15 | p=0.93)
= 0.34. This is not evidence the bench is *better*; it is evidence the two do not
disagree. At n=3 per cell nothing stronger is available, and none is needed: the
question was whether the bench produces valid results, not whether it ranks
above the desktop.

The cost is **3.8x wall clock**, and it is concentrated rather than uniform:

| task | bench wall-clock |
|---|---|
| constant-and-callers | 34.2 / 41.7 / 40.9 s |
| booking-off-by-one | 59.3 / 80.4 / 90.9 s |
| ambiguous-anchor | 118.6 / 87.3 / 87.0 s |
| csv-summarize-repair | 124.5 / 218.6 / **330.8** s |
| strict-log-format | 238.3 / 243.2 / **320.6** s |

Nearly a 10x spread across tasks on the same machine. Tasks requiring more
generation pay the offload penalty repeatedly; short tool-heavy tasks barely
notice. **Budget bench campaigns by task, not by a single multiplier** — and note
that `csv-summarize-repair` at 330 s is over half the harness's 600 s timeout, so
a slower model on that task could time out on the bench while passing on the
desktop. That would look like a capability difference and would not be one.

## A portability bug this run exposed

The `decode tok/s` column came back **empty** for every cell, with no error.

`runner.py` hardcoded the contract-v1 prompt to
`/home/blueaz/Python/project-phoenix/...`. The desktop runs as `blueaz`, the
bench as `ef-tb`. On the bench that path does not exist, `measure_tok_s` hit its
`if not _CONTRACT_PROMPT_PATH.is_file(): return None` guard, and returned None
for all 15 cells — exactly as designed, since that probe "must never be able to
fail a cell."

**The guard is right; the silence is not.** A whole run's throughput data was
lost and nothing said so. Fixed by resolving from `Path.home()`; verified to
resolve on both machines.

This is the third instrument-silence failure in this program in a week, after
ollama's CUDA-to-Vulkan fallback logging at INFO and `/api/ps` misreporting VRAM.
The pattern is consistent: **the harness degrades quietly rather than loudly**,
and the degradation is only visible if you check the output for what should be
there rather than for errors.

## What it took to make the bench benchmark-capable

None of this was documented; all of it is user-local, no root:

| blocker | resolution |
|---|---|
| `pi` absent | npm `@earendil-works/pi-coding-agent@0.85.0` into `~/.local`, version-matched |
| `pi` crashed on Node 18 | requires Node **>= 22.19** (`node:fs` `globSync`); Debian 12 ships 18.20.4. Node 22.23.2 installed to `~/.local` |
| `runner.py`: `No module named yaml` | Debian ships no `pip` and no `ensurepip`. PyYAML installed from its wheel into `~/.local/lib/python3.11/site-packages` |
| `Unknown provider "ollama"` | `pi` needs `~/.pi/agent/models.json` |
| — | **`~/.pi/agent/auth.json` deliberately NOT copied.** It holds `openai-codex` credentials. Only `models.json` was transferred, after verifying its sole provider is `ollama` with the dummy key `"ollama"`. `scp -r ~/.pi` would have put real credentials on a second machine for no reason. |

## Consequence

**The bench is validated as a correctness host.** The campaign split holds:
functional benchmarking, checker tests, rescoring and evidence generation can run
here; throughput reproduction, single-vs-dual comparisons and
memory-exceeding configurations stay on the desktop.

Results are labelled `OPERATOR_MACHINE=testbench` so the two machines' data stay
separable, which matters more now that their wall-clock scales differ by ~4x.

## Limits

- One model. `gemma4:26b` is the only roster member that fits the 2080
  comfortably; larger models need separate fit checks before their lanes move.
- n=3, Screen tier. Sufficient for "does the bench agree", not for a rate.
- Decode tok/s unmeasured for this run because of the path bug; the next bench
  run will have it.
- The Alignerr lane cannot run here yet: it needs `sources.local.json`, which is
  gitignored and points at artifacts that exist only on the desktop.
