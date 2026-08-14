#!/usr/bin/env bash
# E12 — conclusive repeat-guard test, targeted and interleaved.
#
# E10 measured +11.1 pts on engaged cells but at p=0.32 -- ~4x underpowered
# against an 11.3% noise floor. Detecting a 14-pt effect at 80% power needs
# ~200 cells per arm; this gives 216 (9 classes x 24 trials).
#
# Two design changes from E10:
#  * Only the 9 cell classes where the repeat path actually engaged. The other
#    26 of 35 contribute noise and cost, not signal.
#  * Arms INTERLEAVED per class (stop then feedback, back to back) rather than
#    run as two blocks. E10 ran feedback-then-stop and had to justify the gap
#    with a drift probe; pairing removes the exposure instead of measuring it.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
X=evals/local_lane_ladder/fixtures/e12-repeat-conclusive
mkdir -p "$X"/{stop,feedback}/traces "$X/evidence"
{
  echo "# E12 pre-run provenance — conclusive repeat-guard test"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "design: 9 engaged cell classes x n=24 x 2 arms = 432 cells (216/arm)"
  echo "powered for: ~14 pt effect at 80% power against an 11.3% noise floor"
  echo "arms interleaved per class, not blocked -- removes E10's drift exposure"
  echo "controls: num_ctx 16384, temperature 0.8, think off"
} | tee "$X/evidence/prerun.txt"
( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 60; done ) > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

run() { # task model arm
  OPERATOR_MACHINE=desktop python3 -u evals/local_lane_ladder/runner.py \
    --models "$2" --tasks "$1" --levels L2 --trials 24 --no-ledger \
    --num-ctx 16384 --temperature 0.8 --think off --on-repeat "$3" \
    --output "$X/$3/RESULTS.md" --state "$X/$3/state_$1_${2//[:.]/-}.json" \
    --trace-dir "$X/$3/traces" 2>&1 | tail -1
}
while read -r TASK MODEL; do
  [ -z "$TASK" ] && continue
  echo "### $TASK x $MODEL"
  for ARM in stop feedback; do printf "   %-9s " "$ARM"; run "$TASK" "$MODEL" "$ARM"; done
done <<'CLASSES'
booking-off-by-one qwen2.5-coder:14b
booking-off-by-one qwen3.6:27b
booking-off-by-one qwen3:32b
constant-and-callers gemma3:27b
constant-and-callers qwen3.6:27b
csv-summarize-repair gemma4:26b
csv-summarize-repair gemma4:31b
csv-summarize-repair qwen2.5-coder:14b
strict-log-format gemma4:31b
CLASSES
echo "E12_DONE $(date -u +%H:%M:%SZ)"
