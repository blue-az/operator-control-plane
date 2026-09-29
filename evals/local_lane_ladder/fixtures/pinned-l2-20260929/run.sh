#!/usr/bin/env bash
# pinned-l2-20260929: the first comparison under a full sampler pin.
# All 14 Ollama option fields identical within each cohort (contract_A/B.json);
# tags, pi's actual outbound request and remote placement passed
# preflight_comparison.py (evidence/preflight_*.json) before launch; every
# request in the run goes through request_gate_proxy.py (evidence/request_gate.jsonl),
# which rejects any body that does not match the contract. Booking fixture
# repaired; initial-state gate active. Same 5 L2 tasks x n=6.
set -uo pipefail
cd /home/blueaz/operator-control-plane
X=evals/local_lane_ladder/fixtures/pinned-l2-20260929
mkdir -p "$X/traces"
export OPERATOR_MACHINE=desktop OLLAMA_HOST=http://127.0.0.1:11444 LOCAL_LANE_SKIP_PIN=1
TASKS="csv-summarize-repair booking-off-by-one constant-and-callers ambiguous-anchor strict-log-format"
curl -sf 127.0.0.1:11454/v1/models >/dev/null || { echo "ABORT: request gate proxy not running"; exit 1; }
python3 -u evals/local_lane_ladder/runner.py --provider testbench-pinned \
  --models pinA-nemotron-lightning:latest pinA-qwen3-next-instruct:latest pinA-qwen3.6-35b:latest \
  --tasks $TASKS --levels L2 --trials 6 --num-ctx 16384 --temperature 0.8 --think off \
  --output "$X/RESULTS_A.md" --state "$X/state_A.json" --trace-dir "$X/traces"
echo "GROUP_A_DONE $(date -u +%H:%M:%SZ)"
LOCAL_LANE_MAX_WALL_CLOCK=1200 python3 -u evals/local_lane_ladder/runner.py --provider testbench-pinned \
  --models pinB-qwen3-next-thinking:latest \
  --tasks $TASKS --levels L2 --trials 6 --num-ctx 32768 --temperature 0.6 --think medium \
  --output "$X/RESULTS_B.md" --state "$X/state_B.json" --trace-dir "$X/traces"
echo "GROUP_B_DONE $(date -u +%H:%M:%SZ)"
