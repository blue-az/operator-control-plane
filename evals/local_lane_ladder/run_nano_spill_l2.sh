#!/usr/bin/env bash
# nano-spill-l2 — host-conditioned L2 characterization.
#
# nemotron-3-nano:latest spills ~7% at num_ctx 16384 but decodes at ~121 tok/s
# (26b-class, not 31b). This pack measures L2 merit with placement sampled.
# Same-run controls: gemma4:26b (seat), qwen3.6:27b (family/ceiling marker).
# Not Elo. Not a seat change. Not pooled with E9/E11 or q36-35b-spill-l2.
#
# 3 fixtures x 3 models x n=6 = 54 cells.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

export PHOENIX_REPO_ROOT=/home/blueaz/Python/project-phoenix
source /home/blueaz/Python/project-phoenix/scripts/with_tracking.sh
setup_tracking nano_spill_l2
start_gpu_telemetry

X=evals/local_lane_ladder/fixtures/nano-spill-l2
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# nano-spill-l2 pre-run — host-conditioned characterization"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: does nemotron-3-nano (7% CPU spill, ~121 tok/s) win L2 merit vs gemma4:26b and qwen3.6:27b"
  echo "design: 3 fixtures x 3 models x n=6 = 54 cells"
  echo "fixtures: csv-summarize-repair strict-log-format ambiguous-anchor (E11 set)"
  echo "levels: L2"
  echo "controls: num_ctx 16384, temperature 0.8, think off, --on-repeat default (stop)"
  echo "same-run controls: gemma4:26b (seat), qwen3.6:27b"
  echo "prior decode: fixtures/nano-spill-tps (warm 121.2 vs 26b 127.4 vs 31b 34.4)"
  echo "framing: desktop-spill host row. Placement sampled every 30s. Not Elo."
  echo "not pooled with: e9 / e11 / q38-ladder / q36-35b-spill-l2"
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
  --models nemotron-3-nano:latest gemma4:26b qwen3.6:27b \
  --tasks csv-summarize-repair strict-log-format ambiguous-anchor \
  --levels L2 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off --no-ledger \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "NANO_SPILL_L2_DONE $(date -u +%H:%M:%SZ)"
