#!/usr/bin/env bash
# qnext-nemotron-dual-l2-20260928: L2 retest after QWEN3NEXT-VARIANT-001.
# Same 5 L2 tasks x n=6 as qnext-80b-e9-ceiling, dispatched through pi to the
# testbench dual-card endpoint (provider testbench-dual, tunnel 127.0.0.1:11444).
# Group A (as the originals: ctx 16384, t 0.8, think off):
#   nemotron-3.5-lightning (new), qwen3-next INSTRUCT (the variant the originals
#   should have been), qwen3.6:35b (same-run control; prior E9 scores exist).
# Group B (the thinking model as designed): qwen3-next thinking, think ON,
#   ctx 32768, temp 0.6 / top_p 0.95 / top_k 20.
# Tags pre-pinned on the testbench (LOCAL_LANE_SKIP_PIN=1); pins recorded in prerun.txt.
set -uo pipefail
cd /home/blueaz/operator-control-plane
X=evals/local_lane_ladder/fixtures/qnext-nemotron-dual-l2-20260928
mkdir -p "$X/traces" "$X/evidence"
{ echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "git_rev: $(git rev-parse HEAD)"
  for m in nemotron-lightning-e9pin-ctx16384-t0p8 qwen3-next-instruct-e9pin-ctx16384-t0p8 qwen3.6-35b-e9pin-ctx16384-t0p8 qwen3-next-thinking-ctx32768-t0p6; do
    echo "== $m"; curl -s 127.0.0.1:11444/api/show -d "{\"model\":\"$m\"}" | python3 -c "import json,sys;d=json.load(sys.stdin);print(d.get('parameters','').strip());print('capabilities',d.get('capabilities'))"; done
} > "$X/evidence/prerun.txt" 2>&1
export OPERATOR_MACHINE=desktop OLLAMA_HOST=http://127.0.0.1:11444 LOCAL_LANE_SKIP_PIN=1
TASKS="csv-summarize-repair booking-off-by-one constant-and-callers ambiguous-anchor strict-log-format"
python3 -u evals/local_lane_ladder/runner.py --provider testbench-dual \
  --models nemotron-lightning-e9pin-ctx16384-t0p8:latest qwen3-next-instruct-e9pin-ctx16384-t0p8:latest qwen3.6-35b-e9pin-ctx16384-t0p8:latest \
  --tasks $TASKS --levels L2 --trials 6 --num-ctx 16384 --temperature 0.8 --think off \
  --output "$X/RESULTS_A.md" --state "$X/state_A.json" --trace-dir "$X/traces"
echo "GROUP_A_DONE $(date -u +%H:%M:%SZ)"
python3 -u evals/local_lane_ladder/runner.py --provider testbench-dual \
  --models qwen3-next-thinking-ctx32768-t0p6:latest \
  --tasks $TASKS --levels L2 --trials 6 --num-ctx 32768 --temperature 0.6 --think on \
  --output "$X/RESULTS_B.md" --state "$X/state_B.json" --trace-dir "$X/traces"
echo "GROUP_B_DONE $(date -u +%H:%M:%SZ)"
