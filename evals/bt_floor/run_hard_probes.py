#!/usr/bin/env python3
"""
Run the hard (cross-document) BT probes across a field of models.

    ./build_funnel.sh current > funnel.txt
    ./run_hard_probes.py funnel.txt gemma4:26b gemma4:31b ...

EPOCH CONSTRAINT -- read before choosing a funnel.

These probes require the `current` epoch. They CANNOT run on `capped`:
that epoch applies `sed '/^## Self-Blocked/,$d'` to BOTTLENECKS.md, which
removes line 106 (magic_bridge/report.html, Hansen-lite -> h1) and line 131
(Front H, the two-ledger divergence -> h3). build_funnel.sh's own comment
says the entries below that heading "carry none of the answers" -- true for
p1..p5, false for these. The runner verifies the required source strings are
present and refuses to run if any is missing, rather than silently scoring
models on an unanswerable question.

think is forced off. gemma4:12b previously returned zero-character responses
on this battery with thinking left at model default.
"""

import json
import sys
import time
from pathlib import Path

import requests

from hard_probes import HARD_PROBES, grade

# Funnel measures 40,510 real tokens -- a chars/4 estimate understates it by
# ~9%. Sized so generation cannot compete with the prompt for the window.
NUM_CTX = 49152
TIMEOUT = 3600

# A source string per probe that must survive into the funnel, so a truncated
# or wrong-epoch funnel fails loudly instead of producing scoreable garbage.
REQUIRED_SOURCES = {
    "h1_hyperlambda_impl": ["Hansen-lite"],
    "h2_crystal_status_today": ["draft proposal", "never trusted status"],
    "h3_cross_machine_verify": ["Front H", "uid_isolated"],
}

INSTRUCTION = (
    "You are a cold-start agent. The project documentation is provided above. "
    "Answer the question strictly from that documentation. If the documentation "
    "does not answer it, say so.\n\nQuestion: "
)


def preflight(funnel):
    missing = []
    for pid, needles in REQUIRED_SOURCES.items():
        for n in needles:
            if n not in funnel:
                missing.append(f"{pid}: {n!r}")
    if missing:
        print("FUNNEL PREFLIGHT FAILED -- required sources absent:")
        for m in missing:
            print(f"  {m}")
        print("\nUse `./build_funnel.sh current`. The capped epoch truncates "
              "BOTTLENECKS.md and removes these.")
        return False
    return True


def ask(model, funnel, question):
    r = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": model,
            "prompt": funnel + "\n\n" + INSTRUCTION + question,
            "stream": False,
            "think": False,
            "options": {"num_ctx": NUM_CTX, "temperature": 0},
            "keep_alive": "10m",
        },
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 2

    funnel = Path(sys.argv[1]).read_text()
    models = sys.argv[2:]

    if not preflight(funnel):
        return 1
    print(f"funnel ok: {len(funnel)} chars, num_ctx={NUM_CTX}\n")

    out = {}
    for model in models:
        rec = {"model": model, "num_ctx": NUM_CTX, "funnel_chars": len(funnel),
               "epoch": "current", "probes": {}}
        for p in HARD_PROBES:
            t0 = time.time()
            try:
                resp = ask(model, funnel, p["question"])
            except Exception as e:
                print(f"[{model}|{p['id']}] ERROR {type(e).__name__}: {e}", flush=True)
                rec["probes"][p["id"]] = {"output": "", "error": str(e)}
                continue
            dt = time.time() - t0
            pec = resp.get("prompt_eval_count", -1)
            done_reason = resp.get("done_reason", "")
            ans = resp.get("response", "")
            rec["probes"][p["id"]] = {
                "question": p["question"],
                "prompt_eval_count": pec,
                "eval_count": resp.get("eval_count"),
                "seconds": round(dt, 1),
                "done_reason": done_reason,
                "output": ans,
            }
            g = grade(p, ans)
            flag = ""
            if pec >= NUM_CTX - 64:
                flag = "  !! CONTEXT CAP -- funnel truncated, cell INVALID"
            # Generation stopped because it ran out of window, not because the
            # model finished: the answer is cut mid-thought and any FAIL on it
            # is the harness's, not the model's.
            if done_reason == "length":
                flag += "  !! GENERATION TRUNCATED (done_reason=length)"
            if g["citations"]["ungrounded"]:
                flag += f"  !! ungrounded: {','.join(g['citations']['ungrounded'])}"
            if g["empty_output"]:
                flag += "  !! EMPTY OUTPUT"
            print(f"[{model}|{p['id']}] {g['verdict']:16s} "
                  f"{dt:6.1f}s  ptok={pec}  bonus={len(g['bonus_hit'])}"
                  f"  missing={g['required_missing'] or '-'}{flag}", flush=True)
        out[model] = rec
        # Free VRAM between models so the next load starts clean.
        try:
            requests.post("http://localhost:11434/api/generate",
                          json={"model": model, "keep_alive": 0}, timeout=60)
        except Exception:
            pass

    stamp = time.strftime("%Y%m%d_%H%M%S")
    dest = Path(f"/home/blueaz/handoffs/bt_hard_{stamp}.json")
    dest.write_text(json.dumps(out, indent=2))
    print(f"\nraw -> {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
