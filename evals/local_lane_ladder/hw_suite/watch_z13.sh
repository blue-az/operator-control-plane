#!/usr/bin/env bash
# Live z13 GPU busy + ollama (no nvidia-smi on Flow Z13).
# From desktop: ./watch_z13.sh
set -euo pipefail
exec watch -n1 'ssh -o ConnectTimeout=3 z13 "
  echo -n gpu_busy%; cat /sys/class/drm/card1/device/gpu_busy_percent 2>/dev/null
  echo
  curl -sf --max-time 1 http://127.0.0.1:11434/api/ps | python3 -c \"
import sys,json
d=json.load(sys.stdin)
for m in d.get('\''models'\'',[]):
    print(m.get('\''name'\''), '\''ctx'\'', m.get('\''context_length'\''))
\" 2>/dev/null || echo ollama_down
"'
