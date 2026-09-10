#!/usr/bin/env bash
# Two pinned seats: one card, one model, one daemon each.
#   ./dual_seats.sh start [--ctx N]   bring both up and report fit
#   ./dual_seats.sh check             re-report without restarting
#   ./dual_seats.sh stop              tear down, restore the system daemon
set -uo pipefail

CARD0_UUID=GPU-22b9dafe-e97d-dbb2-50ba-2f1f1dea61f9   # PCI 01:00.0, no display
CARD1_UUID=GPU-102e9c9e-f883-58fa-6119-8c72f81fd88e   # PCI 03:00.0, display
# per-seat context: the 35b holds 42/42 at 131072; the 27b spills 3 of 66 there
# and pays ~28% decode for it, so it runs one notch down at 66/66.
MODEL0=qwen3.6:35b ; PORT0=11435 ; LOG0=/tmp/ol-c0.log ; CTX0=131072
MODEL1=qwen3.8:27b ; PORT1=11436 ; LOG1=/tmp/ol-c1.log ; CTX1=98304
KV=q8_0

CMD=${1:-start}; shift || true
while [ $# -gt 0 ]; do case $1 in --ctx) CTX0=$2; CTX1=$2; shift 2;; --ctx0) CTX0=$2; shift 2;;
  --ctx1) CTX1=$2; shift 2;; --model0) MODEL0=$2; shift 2;; --model1) MODEL1=$2; shift 2;;
  --kv) KV=$2; shift 2;; *) shift;; esac; done

say() { printf '%s\n' "$*"; }

verify_uuids() {
  for u in $CARD0_UUID $CARD1_UUID; do
    nvidia-smi --query-gpu=uuid --format=csv,noheader | grep -qx "$u" || {
      say "ABORT: $u is not present. Cards moved? Re-read:"
      nvidia-smi --query-gpu=index,pci.bus_id,uuid --format=csv,noheader | sed 's/^/  /'
      exit 1; }
  done
}

launch() { # uuid port log ctx
  nohup sudo -u ollama env \
    CUDA_VISIBLE_DEVICES="$1" \
    OLLAMA_LLM_LIBRARY=cuda_v13 \
    OLLAMA_KV_CACHE_TYPE="$KV" \
    OLLAMA_FLASH_ATTENTION=1 \
    OLLAMA_CONTEXT_LENGTH="$4" \
    OLLAMA_KEEP_ALIVE=-1 \
    OLLAMA_MAX_LOADED_MODELS=1 \
    OLLAMA_HOST=127.0.0.1:"$2" \
    ollama serve > "$3" 2>&1 &
}

wait_up() { # port
  for _ in $(seq 1 40); do
    curl -sf --max-time 2 "http://127.0.0.1:$1/api/tags" >/dev/null && return 0
    sleep 1
  done
  return 1
}

load() { # port model
  curl -sf --max-time 900 "http://127.0.0.1:$1/api/generate" \
    -d "{\"model\":\"$2\",\"prompt\":\"say ok\",\"stream\":false,\"options\":{\"num_predict\":8}}" \
    -o /tmp/ol-load-$1.json
}

report() {
  say ""
  say "card  model          VRAM used / 24576   layers on GPU   verdict"
  local i=0
  for spec in "$PORT0 $MODEL0 $LOG0" "$PORT1 $MODEL1 $LOG1"; do
    set -- $spec; local port=$1 model=$2 log=$3
    local mem lay
    mem=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits | sed -n "$((i+1))p")
    lay=$(grep -o "offloaded [0-9]*/[0-9]*" "$log" 2>/dev/null | tail -1 | awk '{print $2}')
    local n=${lay%%/*} m=${lay##*/} v="?"
    if [ -n "$lay" ]; then
      if [ "$n" = "$m" ]; then v="FITS"; else v="SPILLED ($((m-n)) layers on CPU)"; fi
    else
      v="no placement line - check $log"
    fi
    printf "  %d   %-14s %6s               %-8s        %s\n" "$i" "$model" "$mem" "${lay:-?}" "$v"
    i=$((i+1))
  done
  say ""
  say "flash-attn actually passed to llama-server:"
  grep -ho '\-\-flash-attn [a-z0-9]*' "$LOG0" "$LOG1" 2>/dev/null | sort -u | sed 's/^/  /' || say "  (not found)"
  say ""
  say "if either says SPILLED:  lower that seat -- --ctx0 N (35b) or --ctx1 N (27b)"
  say "if both say FITS:        point sessions at them --"
  say "  OLLAMA_HOST=127.0.0.1:$PORT0 pi      # $MODEL0"
  say "  OLLAMA_HOST=127.0.0.1:$PORT1 pi      # $MODEL1"
}

case "$CMD" in
  start)
    verify_uuids
    say "caching sudo credentials (one prompt)..."
    sudo -v || exit 1
    say "stopping the shared daemon so it cannot hold VRAM"
    sudo systemctl stop ollama
    sleep 2
    say "starting card0=$MODEL0 :$PORT0 ctx=$CTX0   card1=$MODEL1 :$PORT1 ctx=$CTX1   kv=$KV"
    launch "$CARD0_UUID" "$PORT0" "$LOG0" "$CTX0"
    launch "$CARD1_UUID" "$PORT1" "$LOG1" "$CTX1"
    wait_up "$PORT0" || { say "ABORT: :$PORT0 never came up. tail $LOG0"; tail -5 "$LOG0"; exit 1; }
    wait_up "$PORT1" || { say "ABORT: :$PORT1 never came up. tail $LOG1"; tail -5 "$LOG1"; exit 1; }
    say "both daemons up; loading models (this is the slow part)"
    load "$PORT0" "$MODEL0" || say "  WARNING: $MODEL0 load/generate failed - see below"
    load "$PORT1" "$MODEL1" || say "  WARNING: $MODEL1 load/generate failed - see below"
    for p in $PORT0 $PORT1; do
      if grep -q '"error"' /tmp/ol-load-$p.json 2>/dev/null; then
        say "  :$p returned an error:"; head -c 300 /tmp/ol-load-$p.json | sed 's/^/    /'; say ""
      fi
    done
    report
    ;;
  check) report ;;
  stop)
    sudo -v || exit 1
    sudo pkill -f "OLLAMA_HOST=127.0.0.1:$PORT0" 2>/dev/null
    sudo pkill -f "OLLAMA_HOST=127.0.0.1:$PORT1" 2>/dev/null
    sudo pkill -u ollama -f "ollama serve" 2>/dev/null
    sleep 2
    sudo systemctl start ollama
    say "torn down; system daemon restarted"
    ;;
  *) say "usage: $0 {start|check|stop} [--ctx N] [--kv f16|q8_0]"; exit 2;;
esac
