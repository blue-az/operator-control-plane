#!/usr/bin/env bash
# qwenflash-e9 — E9 ceiling battery for qwen3-next (colloquially "qwen-flash").
#
# Prepared 2026-08-28, NOT yet run (GPUs were in use for other work at prep time).
# Mirrors run_q36_35b_e9.sh exactly -- that is the precedent for adding a new
# model to this battery. Dry-run validated: 5 fixtures x 2 models x 6 trials =
# 60 cells, task prompts all valid (`runner.py ... --dry-run`).
#
# Tag confirmed against `ollama list` 2026-08-28: qwen3-next:latest (b2ebb986e4e9,
# 50 GB). Note qwen3-next is NOT new to this machine or to Front I -- it already
# has extensive throughput/capacity evidence (28.1 tok/s at 15k ctx, 55% CPU
# offload, docs/LOCAL_INFERENCE_BOTTLENECKS.md). What's new here is capability:
# it is not in e9-ceiling-continued's existing roster (gemma4:31b/26b,
# qwen3.6:27b, qwen3-vl:30b, qwen2.5-coder:14b, qwen3:32b, gemma3:27b).
#
# G2 is not a veto. Placement is logged, not used to drop the model. At 50 GB on
# a 24 GB card, expect real CPU offload here -- record it, do not treat it as a
# disqualifier per the framing above.
# Same-run control: gemma4:26b (seat). Five E9 fixtures, n=6, 60 cells.
# Compare to e9-ceiling-continued (26b 24/30, 31b 24/30, qwen3.6:27b 19/30).
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

MODEL="qwen3-next:latest"

source /home/blueaz/Python/project-phoenix/scripts/with_tracking.sh
setup_tracking qwenflash_e9
start_gpu_telemetry

X=evals/local_lane_ladder/fixtures/qwenflash-e9
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# qwenflash-e9 pre-run — E9 battery, qwen-flash"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: where does $MODEL sit on the E9 ceiling battery vs gemma4:26b"
  echo "design: 5 fixtures x 2 models x n=6 = 60 cells"
  echo "fixtures: csv-summarize-repair booking-off-by-one constant-and-callers ambiguous-anchor strict-log-format"
  echo "levels: L2"
  echo "controls: num_ctx 16384, temperature 0.8, think off, --on-repeat default (stop)"
  echo "same-run control: gemma4:26b (seat)"
  echo "framing: host-conditioned. Placement sampled every 30s. G2 is not a veto."
  echo "compare against: e9-ceiling-continued (26b 24/30, 31b 24/30, qwen3.6:27b 19/30, qwen3-vl:30b 16/30, qwen2.5-coder:14b 14/30, qwen3:32b 13/30, gemma3:27b 12/30)"
  nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader
  nvidia-smi -q -d POWER | sed -n '1,25p'
} | tee "$X/evidence/prerun.txt"

( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 30; done ) \
  > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null; stop_gpu_telemetry' EXIT

OPERATOR_MACHINE=desktop PATH="/home/blueaz/Python/project-phoenix/.venv/bin:$PATH" \
  python3 -u evals/local_lane_ladder/runner.py \
  --models "$MODEL" gemma4:26b \
  --tasks csv-summarize-repair booking-off-by-one constant-and-callers \
          ambiguous-anchor strict-log-format \
  --levels L2 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off --no-ledger \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "QWENFLASH_E9_DONE $(date -u +%H:%M:%SZ)"
