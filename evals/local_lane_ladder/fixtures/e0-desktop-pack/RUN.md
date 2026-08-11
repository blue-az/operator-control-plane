# Running the E0 desktop pack

Run from `~/operator-control-plane` **on desktop** (the runner hits Ollama at
`localhost:11434`, so it must execute on the host serving the models, not remotely).
Checked 2026-08-11: desktop's checkout is merged to include `890d595`/`d5eea34` — verify
this is still true before running if time has passed:

```bash
git -C ~/operator-control-plane merge-base --is-ancestor 890d595 HEAD && \
git -C ~/operator-control-plane merge-base --is-ancestor d5eea34 HEAD && \
echo ok
```

Then, from `~/operator-control-plane`:

```bash
python3 evals/local_lane_ladder/runner.py \
  --models gemma4:26b gemma4:31b llama3.1:8b qwen2.5-coder:32b \
  --tasks alias-add config-value-change grep-and-report \
  --levels L2 \
  --trials 3 \
  --output evals/local_lane_ladder/fixtures/e0-desktop-pack/RESULTS.md \
  --state evals/local_lane_ladder/fixtures/e0-desktop-pack/state.json
```

Grid: 3 tasks x 1 level (L2 only) x 4 models x 3 trials = **36 cells**. 3 trials, not 1,
because `PILOT_CONFOUND_FINDINGS.md` demonstrated directly that n=1 per cell produces
flips indistinguishable from variance — the spec's stated minimum (3) is the floor for
a reason, and this pack shouldn't repeat a mistake this codebase already paid to learn.

`--tasks` selects by `task_id` (hyphenated, e.g. `alias-add`) from the **live**
`evals/local_lane_ladder/tasks/` directory, not from this `fixtures/e0-desktop-pack/`
copy — `runner.py`'s `TASKS_DIR` is hardcoded relative to its own location. The pinned
copies here are the audit/provenance record (see checksums in `MANIFEST.md`); before
running, diff them against the live dir to confirm nothing drifted:

```bash
diff evals/local_lane_ladder/tasks/alias_add.yaml evals/local_lane_ladder/fixtures/e0-desktop-pack/tasks/alias_add.yaml
diff evals/local_lane_ladder/tasks/config_value_change.yaml evals/local_lane_ladder/fixtures/e0-desktop-pack/tasks/config_value_change.yaml
diff evals/local_lane_ladder/tasks/grep_and_report.yaml evals/local_lane_ladder/fixtures/e0-desktop-pack/tasks/grep_and_report.yaml
```

`--state` is separate from the shared `evals/local_lane_ladder/state.json` so this pack's
resumability doesn't collide with the historical z13 sweep's records. Trials still
record to the real operator ledger (`--ledger-dir` defaults to repo root), tagged
`harness=local-lane-eval`, `lane=local`, `task_class=bounded` — this is a genuine ledger
entry, not a throwaway.

**Power cap not applied at freeze time** (desktop reads 320 W; spec wants <=200 W).
Erik explicitly accepted this risk 2026-08-11 — see `MANIFEST.md`. If you're running this
later and the cap situation has changed, recheck rather than assuming the prior decision
still applies:

```bash
nvidia-smi --query-gpu=power.limit --format=csv,noheader
```
