#!/usr/bin/env bash
# q38-shape — L0/L1 on the E11 fixtures for qwen3.8:27b vs gemma4:26b.
#
# L2 pass/fail and mean trajectory cannot separate these two. This pack
# asks whether qwen3.8 needs plan-shaped input, with 26b as same-run control
# because these three fixtures have no L0/L1 baseline for either model.
#
# 3 fixtures x 2 levels x 2 models x n=6 = 72 cells.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

source /home/blueaz/Python/project-phoenix/scripts/with_tracking.sh
setup_tracking q38_shape
start_gpu_telemetry

X=evals/local_lane_ladder/fixtures/q38-shape
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# q38-shape pre-run — L0/L1 shape dependence"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: does qwen3.8:27b need plan-shaped (L2) input, vs gemma4:26b"
  echo "design: 3 fixtures x 2 levels x 2 models x n=6 = 72 cells"
  echo "fixtures: csv-summarize-repair strict-log-format ambiguous-anchor"
  echo "levels: L0 L1 (L2 already measured: q38-ladder + e11-depth)"
  echo "controls: num_ctx 16384, temperature 0.8, think off, --on-repeat default (stop)"
  echo "same-run control: gemma4:26b (seat). Not pooled with any prior L2 pack."
  echo "hardware: single RTX 3090, 320W. Second card still unpowered."
  nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader
  nvidia-smi -q -d POWER | sed -n '1,25p'
} | tee "$X/evidence/prerun.txt"

( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 30; done ) \
  > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null; stop_gpu_telemetry' EXIT

OPERATOR_MACHINE=desktop python3 -u evals/local_lane_ladder/runner.py \
  --models qwen3.8:27b gemma4:26b \
  --tasks csv-summarize-repair strict-log-format ambiguous-anchor \
  --levels L0 L1 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "Q38_SHAPE_DONE $(date -u +%H:%M:%SZ)"
