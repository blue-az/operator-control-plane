#!/usr/bin/env bash
# Preflight gates for adding a model to the local-lane ladder.
#
# Every gate here exists because skipping it already cost this programme a run:
#   G0  another sweep is live        -> GPU contention silently distorts timings
#   G1  weights fit                  -> nemotron-3.5-lightning is 25GB of weights
#                                       on a 24GB card; no context tuning fixes it
#   G2  100% GPU at ctx 16384        -> qwen3:32b spilled at its 32768 default;
#                                       spill is a measurement confound, not a result
#   G3  think support + obedience    -> qwen3-vl:30b IGNORES think=false, emitting
#                                       11,407 chars of reasoning and 52x the tokens
#   G4  one graded cell              -> proves the harness can actually drive it
#
# Refuses to proceed on a failed gate rather than producing a number that looks
# fine. Usage:  ./new_model_gate.sh qwen3.8:27b
set -uo pipefail

MODEL="${1:?usage: new_model_gate.sh <ollama-model-tag>}"
CTX=16384
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRATCH="$(mktemp -d -t newmodel-gate-XXXX)"
trap 'rm -rf "$SCRATCH"' EXIT
fail() { echo "  GATE FAILED: $*"; echo; echo "STOP. Do not run the battery."; exit 1; }

echo "== Gate 0: no other sweep running =="
if pgrep -f "local_lane_ladder/runner.py" >/dev/null; then
  fail "a ladder sweep is already running; GPU contention would distort every timing"
fi
echo "  ok"

echo "== Gate 1: pull and weight size =="
ollama pull "$MODEL" || fail "pull failed -- is the tag published yet?"
SIZE=$(ollama list | awk -v m="$MODEL" '$1==m{print $3" "$4}')
echo "  on disk: $SIZE"
VRAM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1)
echo "  card: ${VRAM} MiB"

echo "== Gate 2: 100% GPU residency at num_ctx $CTX =="
curl -s http://127.0.0.1:11434/api/generate \
  -d "{\"model\":\"$MODEL\",\"prompt\":\"ok\",\"stream\":false,\"options\":{\"num_ctx\":$CTX}}" >/dev/null
PS=$(ollama ps | awk -v m="$MODEL" '$1==m{print}')
echo "  $PS"
echo "$PS" | grep -q "100% GPU" || fail "not fully GPU-resident at ctx $CTX (spill is a confound, not a result)"

echo "== Gate 3: think support and obedience =="
python3 - "$MODEL" <<'PY'
import json, sys, urllib.request
model = sys.argv[1]
def ask(think):
    p = {"model": model, "prompt": 'Reply with JSON: {"tool":"read_file","path":"a.txt"}',
         "stream": False, "options": {"num_ctx": 16384, "temperature": 0.8}}
    if think is not None:
        p["think"] = think
    r = urllib.request.Request("http://127.0.0.1:11434/api/generate",
                               data=json.dumps(p).encode(),
                               headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=600) as resp:
            d = json.loads(resp.read())
        return d.get("eval_count") or 0, len(d.get("thinking") or "")
    except Exception as exc:
        return None, str(exc)[:60]

on_tok, on_think = ask(True)
off_tok, off_think = ask(False)
print(f"  think=on : tokens={on_tok} thinking_chars={on_think}")
print(f"  think=off: tokens={off_tok} thinking_chars={off_think}")
if on_tok is None:
    print("  VERDICT: no thinking mode (errors on think=true). Fine -- nothing to suppress.")
elif isinstance(off_think, int) and off_think > 0:
    print("  VERDICT: LEAKY -- ignores think=false, like qwen3-vl:30b.")
    print("  Not disqualifying, but its 'off' row measures nothing and cost is")
    print("  uncontrollable via the think parameter. Record it in the pack.")
else:
    print("  VERDICT: clean suppression. Use --think off, as every pack since e6 does.")
PY

echo "== Gate 4: one graded cell =="
cd "$ROOT"
OPERATOR_MACHINE=desktop timeout 900 python3 evals/local_lane_ladder/runner.py \
  --models "$MODEL" --tasks ambiguous-anchor --levels L2 --trials 1 --no-ledger \
  --num-ctx $CTX --temperature 0.8 --think off \
  --output "$SCRATCH/R.md" --state "$SCRATCH/s.json" --trace-dir "$SCRATCH/t" \
  2>&1 | grep -E "PASS|FAIL" || fail "no graded cell produced"

python3 - "$SCRATCH/t" <<'PY'
import glob, json, sys
fs = glob.glob(sys.argv[1] + "/*.json")
if not fs:
    print("  GATE FAILED: no trace retained"); sys.exit(1)
d = json.load(open(fs[0]))
t = d["trajectory"]
print(f"  trace ok: {t['n_calls']} tool call(s), tools={t['distinct_tools']}, "
      f"ctok={t['completion_tokens']}, think_chars={t['think_chars']}")
if t["n_calls"] == 0:
    print("  WARNING: model produced no dispatched tool call. Check the trace before")
    print("  reading any score -- this is the emission-format failure class.")
PY

cat <<EOF

== ALL GATES PASSED ==

Run the ceiling battery against the E9 reference epoch:

  OPERATOR_MACHINE=desktop python3 evals/local_lane_ladder/runner.py \\
    --models $MODEL qwen3.6:27b \\
    --tasks csv-summarize-repair booking-off-by-one constant-and-callers \\
            ambiguous-anchor strict-log-format \\
    --levels L2 --trials 6 \\
    --num-ctx $CTX --temperature 0.8 --think off \\
    --output  <pack>/RESULTS.md --state <pack>/state.json --trace-dir <pack>/traces

qwen3.6:27b is included as a same-run control: it is the direct predecessor and
scored 19/30 in E9, so a fresh side-by-side avoids comparing across invocations
(cross-invocation drift already produced one false regression in this programme).

Do NOT pool with e10-repeat-ab -- that pack varies --on-repeat and this uses the
default. Compare against e9-ceiling-continued.
EOF
