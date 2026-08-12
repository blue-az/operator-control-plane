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
stdout/stderr and tool activity. The present runner has no such interface, so
this gate currently fails:

```bash
python3 evals/local_lane_ladder/runner.py --help
```

Do not treat console output, `state.json` summaries, or model prose as a
retained trace. Do not run the matrix until the runner's documented trace
option and artifact layout can be inserted into the command below.

## 4. Deferred desktop matrix

After the trace gate is fixed, Grok or Claude supervision must update this
command with the approved trace-retention option before execution:

```bash
OPERATOR_MACHINE=desktop python3 evals/local_lane_ladder/runner.py \
  --models gemma4:26b gemma4:31b qwen2.5-coder:14b \
  --tasks alias-add config-value-change function-add \
  --levels L2 \
  --trials 3 \
  --output evals/local_lane_ladder/fixtures/e1-gold-pack/RESULTS.md \
  --state evals/local_lane_ladder/fixtures/e1-gold-pack/state.json \
  <APPROVED-TRACE-RETENTION-OPTION>
```

During each model's cells, retain the output of `ollama ps`. The Qwen floor
row is eligible only if it reports 100% GPU. Keep all run artifacts and
ledger writes on desktop; do not copy them into or reconcile them with z13's
ledger. Stop after this 27-cell matrix—there is no full-ladder or optional
32b run in E1.
