#!/usr/bin/env bash
# q36-35b-e9 — E9 ceiling battery for qwen3.6:35b.
#
# G2 is not a veto. Placement is logged, not used to drop the model.
# Same-run control: gemma4:26b (seat). Five E9 fixtures, n=6, 60 cells.
# Do not pool with q36-35b-spill-l2 (3 fixtures). Compare to e9-ceiling-continued.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

source /home/blueaz/Python/project-phoenix/scripts/with_tracking.sh
setup_tracking q36_35b_e9
start_gpu_telemetry

X=evals/local_lane_ladder/fixtures/q36-35b-e9
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# q36-35b-e9 pre-run — E9 battery, host-conditioned 35b"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: where does qwen3.6:35b sit on the E9 ceiling battery vs gemma4:26b"
  echo "design: 5 fixtures x 2 models x n=6 = 60 cells"
  echo "fixtures: csv-summarize-repair booking-off-by-one constant-and-callers ambiguous-anchor strict-log-format"
  echo "levels: L2"
  echo "controls: num_ctx 16384, temperature 0.8, think off, --on-repeat default (stop)"
  echo "same-run control: gemma4:26b (seat)"
  echo "framing: host-conditioned. Placement sampled every 30s. G2 is not a veto."
  echo "not pooled with: q36-35b-spill-l2 (3-fixture subset)"
  echo "compare against: e9-ceiling-continued (26b 24/30)"
  echo "hardware: single RTX 3090, 320W. Second card still unpowered."
  nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader
  nvidia-smi -q -d POWER | sed -n '1,25p'
} | tee "$X/evidence/prerun.txt"

( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 30; done ) \
  > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null; stop_gpu_telemetry' EXIT

OPERATOR_MACHINE=desktop PATH="/home/blueaz/Python/project-phoenix/.venv/bin:$PATH" \
  python3 -u evals/local_lane_ladder/runner.py \
  --models qwen3.6:35b gemma4:26b \
  --tasks csv-summarize-repair booking-off-by-one constant-and-callers \
          ambiguous-anchor strict-log-format \
  --levels L2 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off --no-ledger \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "Q36_35B_E9_DONE $(date -u +%H:%M:%SZ)"
