#!/usr/bin/env python3
"""Repeatable local-inference measurement suite.

Every trial is gated by preflight.py and carries its full config block, so rows
from different sessions and different hosts are comparable or provably not.

Two cell families:

  budget   full GPU residency; vary num_ctx x kv_cache_type.
           Answers: VRAM footprint vs context, and where a model spills.
           GPU-bound, so these rows should be HOST-INVARIANT -- they are the
           cross-host control. If they move between machines, the setup is
           wrong, not the hardware.

  offload  fixed num_ctx; vary num_gpu downward to force layers onto the CPU.
           Answers: cost per CPU-resident layer. HOST-SENSITIVE by design --
           this is the arm that measures a CPU/RAM change.
           The only such curve on disk was measured on an MoE model and does
           not transfer to dense ones; this produces the missing counterpart.

Phases are read from ollama's own timings rather than wall clock alone, so
load / prefill / decode never get conflated:

    load_duration | prompt_eval_count,prompt_eval_duration | eval_count,eval_duration

Placement is captured from the daemon's own log during each residency
('offloaded N/M layers'). A trial whose placement could not be read is recorded
as INVALID rather than silently accepted -- estimating layers from a VRAM ratio
is what left the previous sweep unable to support a causal claim.

Usage:
  python3 suite.py budget  --model qwen3.8:27b --ctx 16384,32768,65536 --kv f16,q8_0
  python3 suite.py offload --model qwen3.8:27b --ctx 16384 --num-gpu 66,65,44,22
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight  # noqa: E402

OUT_BASE = Path(__file__).resolve().parent / "runs"
NS = 1_000_000_000

PARAGRAPH = (
    "The registry records device family, model number and registered implants "
    "for each year. Analysts reconcile these against the published subset "
    "before drawing any conclusion about market concentration. "
)


def make_prompt(target_tokens: int) -> tuple[str, str]:
    """Fixed, reproducible prompt. Its hash and actual token count are recorded."""
    reps = max(1, target_tokens // 30)
    text = ("Read the following and reply with exactly the word ACK.\n\n"
            + PARAGRAPH * reps + "\nReply with exactly: ACK")
    return text, hashlib.sha256(text.encode()).hexdigest()[:16]


def generate(daemon: str, model: str, prompt: str, options: dict) -> dict:
    body = json.dumps({"model": model, "prompt": prompt, "stream": False,
                       "options": options}).encode()
    req = urllib.request.Request(f"http://{daemon}/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            d = json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return {"ok": False, "wall_s": round(time.time() - t0, 3),
                "error": exc.read().decode(errors="replace")[:300]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "wall_s": round(time.time() - t0, 3), "error": repr(exc)[:300]}
    pe_n = d.get("prompt_eval_count") or 0
    pe_d = d.get("prompt_eval_duration") or 0
    ev_n = d.get("eval_count") or 0
    ev_d = d.get("eval_duration") or 0
    return {
        "ok": True, "wall_s": round(time.time() - t0, 3),
        "load_s": round((d.get("load_duration") or 0) / NS, 3),
        "prompt_tokens": pe_n, "prefill_s": round(pe_d / NS, 3),
        "prefill_ms_per_token": round(pe_d / NS * 1000 / pe_n, 4) if pe_n else None,
        "output_tokens": ev_n, "decode_s": round(ev_d / NS, 3),
        "decode_tok_s": round(ev_n / (ev_d / NS), 2) if ev_d else None,
        "total_s": round((d.get("total_duration") or 0) / NS, 3),
    }


def vram() -> list[int]:
    out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used",
                          "--format=csv,noheader,nounits"], text=True, capture_output=True).stdout
    return [int(x) for x in out.split()]


def read_placement(unit: str | None, log_path: str | None, since: str) -> dict:
    """'offloaded N/M layers' from the daemon's OWN log. INVALID if unreadable."""
    if unit:
        raw = subprocess.run(["journalctl", "-u", unit, "--no-pager", "--since", since],
                             text=True, capture_output=True).stdout
    elif log_path and Path(log_path).is_file():
        raw = Path(log_path).read_text(errors="replace")
    else:
        return {"valid": False, "reason": "no daemon log available for this endpoint"}
    hits = [l for l in raw.splitlines() if "offloaded" in l and "layers to GPU" in l]
    if not hits:
        return {"valid": False, "reason": "no 'offloaded N/M layers' line in window"}
    tail = hits[-1].split("offloaded", 1)[1]
    n, m = tail.split("layers")[0].strip().split("/")
    return {"valid": True, "gpu_layers": int(n), "total_layers": int(m.strip()),
            "cpu_layers": int(m.strip()) - int(n)}


def run_cell(args, ctx: int, kv: str, num_gpu: int | None, prompt: str, phash: str) -> dict:
    cfg = preflight.build(args.daemon, args.model)
    if kv and kv != (cfg["daemon"]["kv_cache_type"].split()[0]):
        return {"status": "SKIPPED", "reason":
                f"daemon KV type is {cfg['daemon']['kv_cache_type']}, cell wants {kv}; "
                f"restart the daemon with OLLAMA_KV_CACHE_TYPE={kv}",
                "num_ctx": ctx, "kv_cache_type": kv, "num_gpu": num_gpu}

    watch = preflight.QuietWatch()
    watch.start()                       # refuses if not quiet at t0
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    subprocess.run(["ollama", "stop", args.model], capture_output=True)
    time.sleep(2)

    options = {"num_ctx": ctx, "num_predict": 16, "temperature": 0}
    if num_gpu is not None:
        options["num_gpu"] = num_gpu

    warm = generate(args.daemon, args.model, "Reply with exactly: ACK", options)
    peak = vram()
    trials = []
    for _ in range(args.repeats):
        r = generate(args.daemon, args.model, prompt, options)
        peak = [max(a, b) for a, b in zip(peak, vram())]
        trials.append(r)

    placement = read_placement(cfg["daemon"]["systemd_unit"], args.daemon_log, since)
    sampled = watch.stop()
    quiet, why = watch.verdict(set(sampled["ollama_gpu_pids"]))

    ok = [t for t in trials if t["ok"]]
    status = "OK"
    if not ok:
        status = "FAILED"
    elif not placement["valid"]:
        status = "INVALID"          # placement unknown -> cannot support a causal claim
    elif not quiet:
        status = "INVALID"

    row = {"status": status, "config": cfg, "num_ctx": ctx, "kv_cache_type": kv,
           "num_gpu": num_gpu, "prompt_sha16": phash, "repeats": args.repeats,
           "placement": placement, "quiet": {"ok": quiet, "detail": why, **sampled},
           "vram_peak_mib": peak, "warm_load_s": warm.get("load_s"), "trials": trials}
    if ok:
        row["summary"] = {
            "prompt_tokens": ok[0]["prompt_tokens"],
            "decode_tok_s_median": statistics.median(
                [t["decode_tok_s"] for t in ok if t["decode_tok_s"]] or [0]),
            "prefill_ms_per_token_median": statistics.median(
                [t["prefill_ms_per_token"] for t in ok if t["prefill_ms_per_token"]] or [0]),
            "output_tokens_median": statistics.median([t["output_tokens"] for t in ok]),
            "wall_s_median": statistics.median([t["wall_s"] for t in ok]),
        }
    else:
        row["summary"] = {"error": trials[0].get("error", "")[:200]}
    return row


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("family", choices=["budget", "offload"])
    ap.add_argument("--model", required=True)
    ap.add_argument("--daemon", default="127.0.0.1:11434")
    ap.add_argument("--daemon-log", default=None,
                    help="log file for a non-systemd daemon; required off :11434")
    ap.add_argument("--ctx", default="16384")
    ap.add_argument("--kv", default="f16", help="cells to attempt; must match the daemon")
    ap.add_argument("--num-gpu", default=None, help="offload family: layer counts")
    ap.add_argument("--prompt-tokens", type=int, default=12800)
    ap.add_argument("--repeats", type=int, default=6)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    prompt, phash = make_prompt(args.prompt_tokens)
    ctxs = [int(x) for x in args.ctx.split(",")]
    kvs = [x.strip() for x in args.kv.split(",")]
    gpus = [int(x) for x in args.num_gpu.split(",")] if args.num_gpu else [None]
    if args.family == "offload" and gpus == [None]:
        print("REFUSED: offload family requires --num-gpu", file=sys.stderr)
        return 2
    if args.family == "budget" and gpus != [None]:
        print("REFUSED: budget family is full-residency; do not pass --num-gpu", file=sys.stderr)
        return 2

    out = Path(args.out) if args.out else OUT_BASE / time.strftime(f"{args.family}-%Y%m%d-%H%M%S")
    if out.exists():
        print(f"REFUSED: run dir exists: {out}", file=sys.stderr)
        return 2
    out.mkdir(parents=True)

    rows = []
    try:
        for kv in kvs:
            for ctx in ctxs:
                for g in gpus:
                    label = f"{args.model} ctx={ctx} kv={kv}" + (f" num_gpu={g}" if g else "")
                    print(f"RUN  {label}", flush=True)
                    row = run_cell(args, ctx, kv, g, prompt, phash)
                    s = row.get("summary", {})
                    print(f"DONE {row['status']:8} vram={row['vram_peak_mib']} "
                          f"layers={row['placement'].get('gpu_layers')}/"
                          f"{row['placement'].get('total_layers')} "
                          f"decode={s.get('decode_tok_s_median')} "
                          f"out_tok={s.get('output_tokens_median')}", flush=True)
                    rows.append(row)
                    (out / "rows.json").write_text(json.dumps(rows, indent=2))
    except preflight.Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        (out / "rows.json").write_text(json.dumps(rows, indent=2))
        return 2

    (out / "rows.json").write_text(json.dumps(rows, indent=2))
    bad = [r for r in rows if r["status"] != "OK"]
    print(f"\n{out}\n{len(rows)} cells, {len(bad)} not OK")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
