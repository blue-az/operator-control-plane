#!/usr/bin/env bash
# qnext-80b-e9-ceiling — L2 ceiling battery for qwen3-next:80b-a3b.
#
# First model measured on this box that does not fit VRAM: 51 GB on a 24 GB
# card, ~55% CPU. Gate 2 warned (host-conditioned spill, not a veto) — so this
# is a host-conditioned row: placement must print next to every score.
#
# qwen3.6:27b is the same-run control (E9: 19/30). Do NOT pool with e9/e11.
# Compare against e9-ceiling-continued. 5 tasks x 6 trials x 2 models = 60 cells.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

source /home/blueaz/Python/project-phoenix/scripts/with_tracking.sh
setup_tracking qnext_l2
start_gpu_telemetry

X=evals/local_lane_ladder/fixtures/qnext-80b-e9-ceiling
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# qnext-80b-e9-ceiling pre-run — L2 ceiling, host-conditioned"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: does qwen3-next:80b-a3b clear the 36/54 L2 ceiling"
  echo "design: 5 fixtures x L2 x 2 models x n=6 = 60 cells"
  echo "controls: num_ctx 16384, temperature 0.8, think off, --on-repeat default"
  echo "same-run control: qwen3.6:27b (E9 19/30). Not pooled with e9/e11."
  echo "HOST-CONDITIONED: qwen3-next is 51 GB on a 24 GB card, ~55% CPU."
  echo "  Gate 2 warned, did not veto. Print placement beside every score."
  echo "hardware: single RTX 3090 @ 320 W. Second card still unpowered."
  echo "measured speed this config: peak 18.4 t/s, @15k 28.1 t/s"
  nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader
} | tee "$X/evidence/prerun.txt"

( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 30; done ) \
  > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null; stop_gpu_telemetry' EXIT

OPERATOR_MACHINE=desktop python3 -u evals/local_lane_ladder/runner.py \
  --models qwen3-next:latest qwen3.6:27b \
  --tasks csv-summarize-repair booking-off-by-one constant-and-callers \
          ambiguous-anchor strict-log-format \
  --levels L2 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "QNEXT_L2_DONE $(date -u +%H:%M:%SZ)"
