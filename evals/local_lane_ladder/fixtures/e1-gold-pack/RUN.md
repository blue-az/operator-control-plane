# Running the E1 gold pack

Run from `~/operator-control-plane` on `desktop`, the host serving Ollama and
owning the run ledger. The scoreable matrix is currently blocked because
`runner.py` does not retain stdout/stderr/tool traces. Do not proceed past the
dry-run until an approved trace-retention change exists.

## 1. Implementation smoke and provenance

```bash
cd ~/operator-control-plane
python3 -c "import yaml; import sys; sys.path.insert(0, 'evals/local_lane_ladder'); import runner, grading"
git merge-base --is-ancestor 890d595 HEAD
hostname -s
git rev-parse HEAD
ollama list
```

Confirm the live definitions used by the current runner match the pinned pack
copies except for the documented `trajectory_hint` additions:

```bash
python3 - <<'PY'
from pathlib import Path
import yaml

root = Path("evals/local_lane_ladder")
for name in ("alias_add.yaml", "config_value_change.yaml", "function_add.yaml"):
    live = yaml.safe_load((root / "tasks" / name).read_text())
    pinned = yaml.safe_load((root / "fixtures/e1-gold-pack/tasks" / name).read_text())
    pinned.pop("trajectory_hint", None)
    assert live == pinned, name
print("pinned tasks match runner inputs")
PY
```

## 2. L2 lint and dry-run

```bash
python3 - <<'PY'
from pathlib import Path
import sys
import yaml

sys.path.insert(0, ".")
import task_lint

for path in sorted(Path("evals/local_lane_ladder/fixtures/e1-gold-pack/tasks").glob("*.yaml")):
    task = yaml.safe_load(path.read_text())
    result = task_lint.lint(task["prompts"]["L2"])
    assert result.overall == "plan-shaped", (path, result.as_dict())
    print(path.name, result.overall)
PY

OPERATOR_MACHINE=desktop python3 evals/local_lane_ladder/runner.py \
  --models gemma4:26b gemma4:31b qwen2.5-coder:14b \
  --tasks alias-add config-value-change function-add \
  --levels L2 \
  --trials 3 \
  --output evals/local_lane_ladder/fixtures/e1-gold-pack/RESULTS.md \
  --state evals/local_lane_ladder/fixtures/e1-gold-pack/state.json \
  --dry-run
```

The dry-run must report 27 planned cells and execute none. If the preferred
Qwen tag is absent, replace it in the dry-run and future command with the
chosen installed 14b-class tag and record that choice in MANIFEST.md.

## 3. Hard trace gate

Before a model trial, inspect the approved runner interface and prove that a
disposable single-cell run creates a retained per-cell trace containing model
stdout/stderr and tool activity.

```bash
python3 evals/local_lane_ladder/runner.py --help   # must list --trace-dir
```

Do not treat console output, `state.json` summaries, or model prose as a
retained trace.

**Gate status: PASSED on desktop 2026-08-12** (rev `77a31e2`, Claude-supervised).

`runner.py` gained `--trace-dir DIR`, which writes one JSON per cell holding
raw opr stdout/stderr, the exact argv and prompt, git rev, machine, and grade
outcome. It is off by default, so omitting it reproduces the previous
behaviour exactly; when omitted the runner now prints a "NOT scoreable" warning
to stderr. Trace writes **fail closed** — an unwritable destination aborts the
sweep instead of recording an untraced cell.

Evidence retained for this gate:

- Disposable single cell `alias-add | L2 | gemma4:26b | t1`, run with
  `--no-ledger` and scratch paths, PASS in 18.1s. Its trace contains the full
  tool sequence (`read_file` → args → tool output → `patch_file` → args → tool
  output), not a summary. `ollama ps` reported **100% GPU** during the cell.
- `tests/test_ladder_runner_trace.py` (5 tests, hermetic — no model required)
  asserts traces are retained for graded **fails** and for **timeouts** with
  partial output, that `--trace-dir` absent is a no-op, and that a failed trace
  write raises. Retention on failure is the property that matters: the
  pre-`890d595` confound was 88 negatives with no output kept.

Re-verify before trusting this line:

```bash
python3 -m unittest tests.test_ladder_runner_trace -v
```

## 4. Desktop matrix

The trace gate is passed and the option below is filled in. This command is
**not** self-authorising: the operator still picks the phase before it runs.

```bash
OPERATOR_MACHINE=desktop python3 evals/local_lane_ladder/runner.py \
  --models gemma4:26b gemma4:31b qwen2.5-coder:14b \
  --tasks alias-add config-value-change function-add \
  --levels L2 \
  --trials 3 \
  --output evals/local_lane_ladder/fixtures/e1-gold-pack/RESULTS.md \
  --state evals/local_lane_ladder/fixtures/e1-gold-pack/state.json \
  --trace-dir evals/local_lane_ladder/fixtures/e1-gold-pack/traces
```

The run is resumable: `state.json` skips completed cells, so an interrupted
sweep is restarted with the same command. Completeness check afterwards —
27 cells means 27 traces, and a short count means the matrix is not scoreable:

```bash
ls evals/local_lane_ladder/fixtures/e1-gold-pack/traces/*.json | wc -l   # expect 27
```

During each model's cells, retain the output of `ollama ps`. The Qwen floor
row is eligible only if it reports 100% GPU. Keep all run artifacts and
ledger writes on desktop; do not copy them into or reconcile them with z13's
ledger. Stop after this 27-cell matrix—there is no full-ladder or optional
32b run in E1.
