#!/usr/bin/env bash
# q36-35b-e9-z13 — E9 ceiling battery on z13 for qwen3.6:35b.
# Same fixtures/settings as desktop q36-35b-e9. Placement logged. G2 is not a veto.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

X=evals/local_lane_ladder/fixtures/q36-35b-e9-z13
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# q36-35b-e9-z13 pre-run — E9 battery on unified memory"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "hostname: $(hostname)"
  echo "question: where does qwen3.6:35b sit on the E9 battery on z13 vs gemma4:26b"
  echo "design: 5 fixtures x 2 models x n=6 = 60 cells"
  echo "fixtures: csv-summarize-repair booking-off-by-one constant-and-callers ambiguous-anchor strict-log-format"
  echo "controls: num_ctx 16384, temperature 0.8, think off"
  echo "same-run control: gemma4:26b (desktop seat)"
  echo "note: 35b reports 100% GPU on this host at 32k (same blob 07d35212591f)"
  echo "power: AC0=$(cat /sys/class/power_supply/AC0/online) BAT0=$(cat /sys/class/power_supply/BAT0/status)"
  echo "governor=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor)"
  echo "powerprofile=$(powerprofilesctl get 2>/dev/null || echo unknown)"
  echo "could_not_set_performance: power-profiles-daemon AccessDenied without sudo"
} | tee "$X/evidence/prerun.txt"

( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 30; done ) \
  > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

OPERATOR_MACHINE=z13 PYTHONUNBUFFERED=1 \
  python3 -u evals/local_lane_ladder/runner.py \
  --models qwen3.6:35b gemma4:26b \
  --tasks csv-summarize-repair booking-off-by-one constant-and-callers \
          ambiguous-anchor strict-log-format \
  --levels L2 --trials 6 \
  --num-ctx 16384 --temperature 0.8 --think off --no-ledger \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "Q36_35B_E9_Z13_DONE $(date -u +%H:%M:%SZ)"
