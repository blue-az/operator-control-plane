#!/usr/bin/env bash
# q36-35b-spill-l2 — host-conditioned L2 characterization.
#
# 100% GPU is not the goal. Performance is. qwen3.6:35b spills ~4% on this
# 3090 at num_ctx 16384; this pack measures L2 merit anyway, with placement
# sampled. Same-run controls: gemma4:26b (seat) and qwen3.6:27b (family).
# Speed row is on the desktop ranking. This 3-fixture pack is not E9 Elo.
#
# 3 fixtures x 3 models x n=6 = 54 cells.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

source /home/blueaz/Python/project-phoenix/scripts/with_tracking.sh
setup_tracking q36_35b_spill_l2
start_gpu_telemetry

X=evals/local_lane_ladder/fixtures/q36-35b-spill-l2
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# q36-35b-spill-l2 pre-run — host-conditioned characterization"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: does qwen3.6:35b (4% CPU spill at 16k) win L2 merit vs gemma4:26b and qwen3.6:27b"
  echo "design: 3 fixtures x 3 models x n=6 = 54 cells"
  echo "fixtures: csv-summarize-repair strict-log-format ambiguous-anchor (E11 set)"
  echo "levels: L2"
  echo "controls: num_ctx 16384, temperature 0.8, think off, --on-repeat default (stop)"
  echo "same-run controls: gemma4:26b (seat), qwen3.6:27b (family predecessor)"
  echo "framing: desktop-spill host row. Placement sampled every 30s."
  echo "not pooled with e9 (wrong fixture set). G2 is not a veto."
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
  --models qwen3.6:35b gemma4:26b qwen3.6:27b \
  --tasks csv-summarize-repair strict-log-format ambiguous-anchor \
  --levels L2 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off --no-ledger \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "Q36_35B_SPILL_L2_DONE $(date -u +%H:%M:%SZ)"
