#!/usr/bin/env bash
set -e
W=~/operator-control-plane/evals/operator_describe_20260921
cd "$W"; rm -f judge/A.md judge/B.md judge/C.md KEY.txt
mapfile -t order < <(printf '%s\n' luna astra terra | shuf)
letters=(A B C)
for i in 0 1 2; do
  src="runs/${order[$i]}/ANSWER.md"; [ -f "$src" ] || { echo "MISSING $src"; exit 1; }
  cp "$src" "judge/${letters[$i]}.md"; echo "${letters[$i]} = ${order[$i]}" >> KEY.txt
done
ln -sfn ../inputs judge/inputs
echo anonymized
