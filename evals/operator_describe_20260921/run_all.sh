#!/usr/bin/env bash
cd ~/operator-control-plane
W="$PWD/evals/operator_describe_20260921"
F=()
for f in "$W/inputs"/*.txt; do F+=(--freeze "evals/operator_describe_20260921/inputs/$(basename "$f")"); done
for pair in "luna:gpt-5.6-luna" "astra:gpt-6-astra" "terra:gpt-5.6-terra"; do
  short="${pair%%:*}"; model="${pair#*:}"
  echo "=== $short / $model $(date -u +%H:%M:%SZ) ==="
  ./delegate-brief --task operator-describe-20260921 --brief "$W/ANALYST_BRIEF.md" \
    --harness codex --model "$model" \
    --cwd "$W/runs/$short" --deliver "$W/runs/$short" \
    "${F[@]}" --timeout 1200 --record
  if [ -f "$W/runs/$short/ANSWER.md" ]; then echo "--- $short OK $(wc -w < "$W/runs/$short/ANSWER.md") words";
  else echo "--- $short NO DELIVERABLE"; fi
done
echo "ROUND 4 COMPLETE $(date -u +%H:%M:%SZ)"
