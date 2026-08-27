#!/usr/bin/env bash
# smoke_mixed_gpu.sh — mixed dual-GPU smoke (prefer this BEFORE matched dual-3090 capacity claims)
#
# "Mixed" here means either:
#   (A) two different cards (e.g. 3090+4090), or same SKU with asymmetric PCIe/power
#   (B) two Ollama instances pinned to separate GPUs (true dual-resident seats)
#
# Does NOT run the E9 210-cell matrix. Capacity + residency + concurrency only.
#
# Usage:
#   ./smoke_mixed_gpu.sh              # full smoke if 2+ GPUs and GPU free
#   ./smoke_mixed_gpu.sh --check      # inventory + gate only
#   ./smoke_mixed_gpu.sh --force      # allow when a runner is detected (dangerous)
#
# Env:
#   MIXED_MODEL_A   default gemma4:26b   (GPU0 instance)
#   MIXED_MODEL_B   default qwen2.5-coder:14b  (GPU1 instance)
#   MIXED_NUM_CTX   default 8192         (keep small for smoke)
#   OUT_DIR         default fixtures/e11-mixed-smoke under ladder

set -euo pipefail

CHECK_ONLY=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --force) FORCE=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
  esac
done

LADDER_DIR="$(cd "$(dirname "$0")/.." && pwd)"
REPO_ROOT="$(cd "$LADDER_DIR/../.." && pwd)"
OUT_DIR="${OUT_DIR:-$LADDER_DIR/fixtures/e11-mixed-smoke}"
MODEL_A="${MIXED_MODEL_A:-gemma4:26b}"
MODEL_B="${MIXED_MODEL_B:-qwen2.5-coder:14b}"
NUM_CTX="${MIXED_NUM_CTX:-8192}"
HOST_A="${MIXED_HOST_A:-127.0.0.1:11434}"
HOST_B="${MIXED_HOST_B:-127.0.0.1:11435}"

mkdir -p "$OUT_DIR/evidence" "$OUT_DIR/logs"
LOG="$OUT_DIR/evidence/smoke_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

echo "=== mixed GPU smoke ==="
echo "utc: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "host: $(hostname -s)"
echo "git: $(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)"
echo "out: $OUT_DIR"
echo "models: A=$MODEL_A  B=$MODEL_B  num_ctx=$NUM_CTX"

if ! command -v nvidia-smi >/dev/null; then
  echo "FAIL: nvidia-smi missing"
  exit 2
fi

mapfile -t GPU_LINES < <(nvidia-smi --query-gpu=index,name,memory.total --format=csv,noheader)
NGPU=${#GPU_LINES[@]}
echo "--- nvidia-smi -L ---"
nvidia-smi -L
echo "--- GPU table ---"
nvidia-smi --query-gpu=index,name,memory.total,memory.used,pcie.link.gen.current,pcie.link.width.current --format=csv
echo "gpu_count=$NGPU"

if (( NGPU < 2 )); then
  echo "FAIL_CLOSED: need ≥2 GPUs for mixed smoke (saw $NGPU). Seat the second card first."
  exit 3
fi

# Heterogeneous?
NAMES=$(nvidia-smi --query-gpu=name --format=csv,noheader | sort -u | wc -l)
MEMS=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | sort -u | wc -l)
if (( NAMES > 1 || MEMS > 1 )); then
  echo "config_class=heterogeneous_cards"
else
  echo "config_class=matched_cards_mixed_runtime  # same SKU; still run dual-resident smoke"
fi

# Busy gate — do not steal E10 / ladder runner
if (( FORCE == 0 )); then
  if pgrep -af 'evals/local_lane_ladder/runner.py' | grep -v grep >/dev/null; then
    echo "FAIL_CLOSED: ladder runner.py is live. Wait for E10 (or pass --force)."
    pgrep -af 'evals/local_lane_ladder/runner.py' | head -5
    exit 4
  fi
fi

if (( CHECK_ONLY == 1 )); then
  echo "CHECK_ONLY: gates OK for mixed smoke when GPU free."
  exit 0
fi

if ! command -v ollama >/dev/null; then
  echo "FAIL: ollama not on PATH"
  exit 2
fi

# Stop any leftover secondary server we might have started earlier
cleanup() {
  if [[ -n "${OLLAMA_B_PID:-}" ]] && kill -0 "$OLLAMA_B_PID" 2>/dev/null; then
    echo "stopping secondary ollama pid=$OLLAMA_B_PID"
    kill "$OLLAMA_B_PID" 2>/dev/null || true
    wait "$OLLAMA_B_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "--- S1: layer-split probe (single ollama, both GPUs visible) ---"
# Use default ollama on HOST_A; both devices visible
export CUDA_VISIBLE_DEVICES=0,1
# Warm model A (may sit on one or both cards depending on size)
if ! curl -sf "http://${HOST_A}/api/tags" >/dev/null; then
  echo "FAIL: primary ollama not reachable at $HOST_A (start: systemctl --user start ollama / ollama serve)"
  exit 5
fi

echo "loading $MODEL_A on primary (both GPUs visible)..."
T0=$(date +%s)
ollama run "$MODEL_A" "Reply with exactly: OK" --verbose 2>"$OUT_DIR/logs/s1_${MODEL_A//[:\/]/_}.err" \
  | tee "$OUT_DIR/logs/s1_${MODEL_A//[:\/]/_}.out" | tail -5
T1=$(date +%s)
echo "s1_wall_s=$((T1 - T0))"
echo "--- ollama ps after S1 ---"
ollama ps | tee "$OUT_DIR/evidence/ollama_ps_s1.txt"
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv | tee "$OUT_DIR/evidence/nvidia_s1.csv"

echo "--- S2: dual-resident (separate ollama per GPU) ---"
# Secondary server on GPU1 only
export OLLAMA_HOST="$HOST_B"
export CUDA_VISIBLE_DEVICES=1
export OLLAMA_MODELS="${OLLAMA_MODELS:-$HOME/.ollama/models}"
# Avoid clobbering primary; use same model store read-only OK
if curl -sf "http://${HOST_B}/api/tags" >/dev/null 2>&1; then
  echo "secondary already up at $HOST_B"
else
  echo "starting secondary ollama on $HOST_B CUDA_VISIBLE_DEVICES=1"
  nohup ollama serve >"$OUT_DIR/logs/ollama_b.log" 2>&1 &
  OLLAMA_B_PID=$!
  for i in $(seq 1 30); do
    curl -sf "http://${HOST_B}/api/tags" >/dev/null 2>&1 && break
    sleep 0.5
  done
  if ! curl -sf "http://${HOST_B}/api/tags" >/dev/null 2>&1; then
    echo "FAIL: secondary ollama did not come up (see $OUT_DIR/logs/ollama_b.log)"
    exit 6
  fi
  echo "secondary pid=$OLLAMA_B_PID"
fi

# Load A on GPU0-only primary, B on GPU1 secondary
echo "loading A=$MODEL_A on GPU0 ($HOST_A) and B=$MODEL_B on GPU1 ($HOST_B) ..."
(
  export OLLAMA_HOST="$HOST_A"
  export CUDA_VISIBLE_DEVICES=0
  ollama run "$MODEL_A" "Reply with exactly: A_OK" 2>"$OUT_DIR/logs/s2a.err" | tee "$OUT_DIR/logs/s2a.out" | tail -3
) &
PID_A=$!
(
  export OLLAMA_HOST="$HOST_B"
  export CUDA_VISIBLE_DEVICES=1
  ollama run "$MODEL_B" "Reply with exactly: B_OK" 2>"$OUT_DIR/logs/s2b.err" | tee "$OUT_DIR/logs/s2b.out" | tail -3
) &
PID_B=$!
wait $PID_A
RC_A=$?
wait $PID_B
RC_B=$?
echo "s2_rc_A=$RC_A s2_rc_B=$RC_B"

echo "--- concurrent residency ---"
export OLLAMA_HOST="$HOST_A"
CUDA_VISIBLE_DEVICES=0 ollama ps | tee "$OUT_DIR/evidence/ollama_ps_s2a.txt" || true
export OLLAMA_HOST="$HOST_B"
CUDA_VISIBLE_DEVICES=1 ollama ps | tee "$OUT_DIR/evidence/ollama_ps_s2b.txt" || true
nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv | tee "$OUT_DIR/evidence/nvidia_s2.csv"

echo "--- S3: concurrent prompt latency (3 turns each, parallel) ---"
run_turns() {
  local host=$1 model=$2 tag=$3
  export OLLAMA_HOST="$host"
  local t0 t1
  t0=$(date +%s%3N)
  for i in 1 2 3; do
    ollama run "$model" "Say the number $i and nothing else." >/dev/null 2>>"$OUT_DIR/logs/s3_${tag}.err" || return 1
  done
  t1=$(date +%s%3N)
  echo "s3_${tag}_ms=$((t1 - t0))"
}
(
  export CUDA_VISIBLE_DEVICES=0
  run_turns "$HOST_A" "$MODEL_A" a
) &
PA=$!
(
  export CUDA_VISIBLE_DEVICES=1
  run_turns "$HOST_B" "$MODEL_B" b
) &
PB=$!
wait $PA; RA=$?
wait $PB; RB=$?
echo "s3_rc_A=$RA s3_rc_B=$RB"

# Write short FINDING skeleton
cat >"$OUT_DIR/FINDING_DRAFT.md" <<EOF
# E11 mixed GPU smoke (draft)

**UTC:** $(date -u +%Y-%m-%dT%H:%M:%SZ)
**Host:** $(hostname -s)
**GPU count:** $NGPU
**Models:** A=\`$MODEL_A\` (GPU0) · B=\`$MODEL_B\` (GPU1)
**Log:** \`$LOG\`

## Gates

- Hardware ≥2 GPUs: PASS
- S1 layer-split probe: see evidence/ollama_ps_s1.txt
- S2 dual-resident: rc A=$RC_A B=$RC_B
- S3 concurrent turns: rc A=$RA B=$RB

## Claim shape (fill after reading samples)

- Mixed dual-resident seats: [yes/no]
- CPU spill observed: [yes/no]
- Heterogeneous bottleneck notes: [PCIe / weaker card / none]

**Not a ranking pack.** E9 remains the single-card ranking instrument.
EOF

echo "=== DONE mixed smoke ==="
echo "draft: $OUT_DIR/FINDING_DRAFT.md"
echo "log: $LOG"
exit 0
