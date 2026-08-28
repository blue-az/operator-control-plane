# qwenflash-e9 finding — the harness change is the headline, not qwen3-next

**Run:** desktop, 2026-08-28, 05:38:53Z–07:09:29Z (1h30m36s), rev `33edfe9` (pi
migration landed mid-investigation, see below). 60/60 cells, zero timeouts, `pi`
as local implementer (opr carved out of this codebase; opencode deprecated
before it). `num_ctx 16384 · temperature 0.8 · think off`, pinned via a derived
Ollama model per model (`ensure_pinned_model`, since pi's CLI has no
`--temperature`/context flag at all). Same-run control: `gemma4:26b` (seat).

## Result — both models near-ceiling

| Model | Total | ambiguous-anchor | booking-off-by-one | constant-and-callers | csv-summarize-repair | strict-log-format |
|---|---:|---:|---:|---:|---:|---:|
| `gemma4:26b` | **28/30** | 6/6 | 6/6 | 4/6 | 6/6 | 6/6 |
| `qwen3-next:latest` | **29/30** | 6/6 | 6/6 | 6/6 | 5/6 | 6/6 |

## The actual finding: this is not comparable to any prior E9 number

Every fixture jumped relative to its `opr`-era figure, for **both** models:

| Fixture | `qwen3-next` (opr, `qnext-80b-e9-ceiling`) | `qwen3-next` (pi, this run) | `gemma4:26b` (opr, `e9-ceiling-continued`) | `gemma4:26b` (pi, this run) |
|---|---:|---:|---:|---:|
| ambiguous-anchor | 3/6 | **6/6** | (24/30 aggregate) | 6/6 |
| booking-off-by-one | 2/6 | **6/6** | | 6/6 |
| constant-and-callers | 5/6 | **6/6** | | 4/6 |
| csv-summarize-repair | 0/6 | **5/6** | 0/6 (of 42 roster-wide) | **6/6** |
| strict-log-format | 0/6 | **6/6** | 18/42 (roster-wide) | **6/6** |
| **Total** | **10/30** | **29/30** | 24/30 | 28/30 |

`csv-summarize-repair` is the one to sit with: the existing `GOLD_STANDARD.md`
findings describe it as "brackets the top... near-floor rather than
discriminating," with only 3 of 42 trials passing across the *entire seven-model
roster* under `opr`. Under `pi`, both models tested here clear it almost
perfectly (11/12 combined). Same for `strict-log-format` (previously a "good
discriminator" at 18/42 roster-wide; now 12/12 here).

**This is best read as evidence that a meaningful fraction of the existing
E9/ladder ranking history measured `opr`-cooperation, not pure model capability.**
Two models tested here, both jumping dramatically and on the *hardest* fixtures
specifically, is not consistent with "these two models happen to be much better
than the rest of the roster" — it's consistent with the harness itself having
been the binding constraint on some fixtures.

## Corroborating signal: the run also finished 2.3x faster

The `opr`-era `qnext-80b-e9-ceiling` run (same 60-cell design, same fixtures,
same sampling contract) took **3h25m** (2026-08-19, 09:35:20Z–13:00:21Z). This
run took **1h30m36s**. Faster *and* far higher pass rates on the same hardware,
same model, same task set is the pattern you'd expect if the old harness was
frequently stalling, retrying, or failing to complete turns cleanly rather than
the model needing more attempts to succeed.

## Why this run happened on a broken harness first, and what that revealed

The first attempt at this run (same day, same script) produced a false **0/30,
0/30** result in under 5 seconds — `opr` now just prints a deprecation notice
and exits 2; neither model was ever actually invoked. That failure is *why*
`runner.py` got migrated to `pi` mid-session (see `runner.py`'s module
docstring and commit `ed22df8`) rather than this run using the old, broken
path. The corrected, validated run above is what actually executed.

Anecdotal harness-quality ordering that emerged along the way, small sample,
not itself measured here: `opr` → `opencode` → `pi`, each a real step up in
getting local models through actual multi-turn agentic tool use, on the model/
task pairs touched in this session.

## What this does NOT show

- That `qwen3-next` is now "the best" model on this battery — `gemma4:26b`,
  historically the strongest model on E9, is right behind it (28 vs 29) and
  actually the *only* one of the two with a real capability miss this run
  (`constant-and-callers` 4/6, a genuine multi-file consistency failure, not a
  harness artifact — see its trace).
- The magnitude of the `opr` vs `pi` effect for the other five models in the
  historical roster (`qwen3.6:27b`, `qwen3-vl:30b`, `qwen2.5-coder:14b`,
  `qwen3:32b`, `gemma3:27b`) — none of them have been re-run under `pi` yet.
- A clean decode-tok/s comparison for `qwen3-next`'s CPU-spill cost. Wall-clock
  per trial conflates tool-execution time with generation time under `pi`'s
  `--mode json` output (no per-turn generation-only timestamps are available,
  checked directly), and the two models produced very different output-token
  volumes per trial, so token-count/wall-clock is not a clean decode-rate
  proxy here. Use the purpose-built `docs/domain_runs/` throughput packets
  (e.g. `MODEL-RANKING-001`) for that question instead.

## Not superseded, but now suspect

Per this repo's own supersession convention (`LOCAL_INFERENCE_BENCH_HARNESS.md`:
"a run that supersedes another strikes through the old figure and names the
supersession"), this finding does **not** itself strike through
`e9-ceiling-continued` or `qnext-80b-e9-ceiling` — those numbers are real
records of what happened under `opr`, and remain valid as *that* measurement.
What changes is how much weight either should carry as evidence about model
capability going forward, versus evidence about `opr`'s limitations.

**Open, not yet resourced:** a full re-run of the `e9-ceiling-continued` seven-
model roster under `pi` is the only way to settle how much of the existing
ranking spread (12/30 to 24/30) was real and how much was harness-cooperation
variance. `run_map_probe.py`, `run_repo_turns.py`, `pilot_confound.py`,
`pilot_pass2_oldharness.py`, and `pilot_pass3_replicated.py` still invoke `opr`
directly (not through `runner.py`) and are not yet migrated — any of them would
currently fail the same way `runner.py` did before this session's fix.

## Evidence

- `RESULTS.md`, `state.json`, `traces/` (60 trace files) — this run
- `evidence/prerun.txt`, `evidence/ollama_ps_samples.log` — placement/config
- Comparators: `../qnext-80b-e9-ceiling/` (opr, qwen3-next), `../e9-ceiling-continued/` (opr, 7-model roster)
