#!/usr/bin/env bash
# E11 — depth sweep on the discriminating fixtures.
#
# The Rasch fit over e9 put 95% CIs 200-400 Elo points wide, so only the top
# two models separate from the field; the middle order is not real. n=6 is the
# cause. This adds n=12 on the three fixtures that carry signal.
#
# Dropped deliberately:
#   booking-off-by-one    42/42, difficulty ~615 Elo, far below the whole field
#   constant-and-callers  36/42, mild, and the cheapest to re-add later
#
# Last clean single-3090 baseline: a second card arrives 2026-08-14, after which
# timings and residency limits are not comparable to anything measured here.
set -uo pipefail
cd "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

X=evals/local_lane_ladder/fixtures/e11-depth
mkdir -p "$X/traces" "$X/evidence"
{
  echo "# E11 pre-run provenance — depth on the discriminating fixtures"
  echo "captured_utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "git_rev: $(git rev-parse HEAD)"
  echo "question: resolve the middle of the ranking, which n=6 could not"
  echo "design: 3 fixtures x 7 models x n=12 = 252 cells"
  echo "fixtures: csv-summarize-repair strict-log-format ambiguous-anchor"
  echo "dropped: booking-off-by-one (42/42, ~615 Elo difficulty), constant-and-callers (36/42)"
  echo "controls: num_ctx 16384, temperature 0.8, think off, --on-repeat default (stop)"
  echo "pools with: e9-ceiling-continued (identical settings) -> n=18 on these three"
  echo "            pooling is validated empirically, not assumed: compare this run's"
  echo "            rates against e9's on the same cells before combining"
  echo "hardware: single RTX 3090, 24GB. LAST CLEAN BASELINE -- second card 2026-08-14."
  nvidia-smi --query-gpu=name,memory.total,power.limit --format=csv,noheader
} | tee "$X/evidence/prerun.txt"

( while true; do echo "--- $(date -u +%H:%M:%SZ)"; ollama ps; sleep 30; done ) \
  > "$X/evidence/ollama_ps_samples.log" 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER 2>/dev/null' EXIT

OPERATOR_MACHINE=desktop python3 -u evals/local_lane_ladder/runner.py \
  --models gemma4:26b gemma4:31b gemma3:27b qwen2.5-coder:14b qwen3.6:27b qwen3-vl:30b qwen3:32b \
  --tasks csv-summarize-repair strict-log-format ambiguous-anchor \
  --levels L2 --trials 12 \
  --num-ctx 16384 --temperature 0.8 --think off \
  --output "$X/RESULTS.md" --state "$X/state.json" --trace-dir "$X/traces"

echo "E11_DONE $(date -u +%H:%M:%SZ)"
