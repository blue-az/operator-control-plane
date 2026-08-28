#!/usr/bin/env bash
# e9-pi-rerun -- E9 ceiling battery, re-run under pi, current-roster models.
#
# Direct follow-on to qwenflash-e9 (2026-08-28): that run found qwen3-next
# and gemma4:26b scoring dramatically higher under pi than their opr-era
# figures on every fixture, especially the two previously near-floor
# fixtures (csv-summarize-repair, strict-log-format). This re-runs the
# current-relevant 4-model roster (not the older 7-model e9-ceiling-continued
# set) to see how much of that gap holds across models that actually fit the
# card without CPU spill.
#
# Roster: gemma4:26b, gemma4:31b, qwen3.6:35b, qwen3.8:27b (all four pulled
# fresh 2026-08-28, confirmed via `ollama list` before this run).
# 5 fixtures x 4 models x n=6 = 120 cells -- double qwenflash-e9's 60.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

source /home/blueaz/Python/project-phoenix/scripts/with_tracking.sh
setup_tracking e9_pi_rerun
start_gpu_telemetry

X=evals/local_lane_ladder/fixtures/e9-pi-rerun
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# e9-pi-rerun pre-run"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: does the qwenflash-e9 opr-vs-pi gap hold across the current 4-model roster"
  echo "design: 5 fixtures x 4 models x n=6 = 120 cells"
  echo "fixtures: csv-summarize-repair booking-off-by-one constant-and-callers ambiguous-anchor strict-log-format"
  echo "levels: L2"
  echo "controls: num_ctx 16384, temperature 0.8, think off"
  echo "models: gemma4:26b gemma4:31b qwen3.6:35b qwen3.8:27b (freshly pulled 2026-08-28)"
  echo "compare against: e9-ceiling-continued (opr, older 7-model roster incl. gemma4:26b 24/30, gemma4:31b 24/30, qwen3.6:27b 19/30) and q36-35b-e9 (opr, qwen3.6:35b vs gemma4:26b)"
  echo "tok/s: this run includes the direct-Ollama decode probe added post-qwenflash-e9 (runner.py measure_tok_s) -- qwenflash-e9 itself does not have it"
  nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader
} | tee "$X/evidence/prerun.txt"

( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 30; done ) \
  > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null; stop_gpu_telemetry' EXIT

OPERATOR_MACHINE=desktop python3 -u evals/local_lane_ladder/runner.py \
  --models gemma4:26b gemma4:31b qwen3.6:35b qwen3.8:27b \
  --tasks csv-summarize-repair booking-off-by-one constant-and-callers \
          ambiguous-anchor strict-log-format \
  --levels L2 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "E9_PI_RERUN_DONE $(date -u +%H:%M:%SZ)"
