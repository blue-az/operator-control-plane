#!/usr/bin/env python3
"""P2 repair cohort on the Z13 (Strix Halo 8050S, unified memory).

One model at a time on z13:18669, each served by a process this launcher starts
and stops: a dedicated Ollama daemon (C1, Z13's own seat weights) or Prism Vulkan
llama-server (F1). Desktop owns the tunnel (18690) and request gate (18692).
Never touches the Z13 system Ollama service, evicts workloads or changes power state.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import time

P = Path(__file__).resolve().parent
L = P.parents[1]
sys.path.insert(0, str(L))
from run_standard_packet import call, ollama_reset  # noqa: E402

CONTRACTS = {"ollama": P / "contract-z13-ollama.json", "llama": P / "contract-z13-prism.json"}
C = {k: json.loads(v.read_text()) for k, v in CONTRACTS.items()}
ORDER = [("c1z-qwen3.6-35b:latest", "ollama"), ("qwen3.8-27b-q4km", "llama"),
         ("bonsai-27b-pq2", "llama"), ("c1z-gemma4-26b:latest", "ollama")]
ENDPOINT = "http://127.0.0.1:18690"
ENV = {**os.environ, "PI_CODING_AGENT_DIR": str(P / "pi-config"),
       "LOCAL_LANE_SKIP_PIN": "1", "LOCAL_LANE_MAX_WALL_CLOCK": "600",
       "OPERATOR_MACHINE": "desktop", "OLLAMA_HOST": ENDPOINT}
ENGINE = "/home/blueaz/bonsai/bin/llama-prism-b10743-adfffbe"


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, env=ENV, **kwargs)


def stem(model):
    return model.split(":")[0]


def body_path(model):
    return P / "requests" / (model.replace(":", "_") + ".json")


def gate(model, runtime, capture):
    run([sys.executable, str(L / "preflight_uma.py"), "--contract", str(CONTRACTS[runtime]),
         "--model", model, "--request-body", str(body_path(model)), "--capture", str(capture)],
        stdout=subprocess.DEVNULL)


def packet(model, runtime, output, canary=False):
    args = [sys.executable, "-u", str(L / "run_standard_packet.py"),
            "--contract", str(CONTRACTS[runtime]), "--model", model, "--provider", "z13-packet",
            "--request-log", str(P / "request-gate.jsonl"),
            "--request-body", str(body_path(model)), "--output", str(output)]
    if canary:
        args += ["--tasks", "booking-off-by-one", "--trials", "1"]
    run(args)


def blob_identity(model, runtime, target):
    """Byte hash of the served weights, once at the start and end of each model block."""
    info = C[runtime]["models"][model]
    path = info["gguf_path"] if runtime == "llama" else \
        "/home/blueaz/c1-study-z13-20261001/models/blobs/sha256-" + info["weight_sha256"]
    want = info["gguf_sha256"] if runtime == "llama" else info["weight_sha256"]
    script = ("import hashlib,os,sys,json\np=sys.argv[1];h=hashlib.sha256()\n"
              "with open(p,'rb') as f:\n [h.update(b) for b in iter(lambda:f.read(8<<20),b'')]\n"
              "s=os.stat(p);print(json.dumps({'path':p,'sha256':h.hexdigest(),'bytes':s.st_size,'inode':s.st_ino,'mtime':s.st_mtime}))\n")
    observed = json.loads(run(["ssh", "z13", "python3", "-", path], input=script, text=True,
                              capture_output=True, timeout=900).stdout)
    target.write_text(json.dumps(observed, indent=2) + "\n")
    if observed["sha256"] != want:
        raise RuntimeError(f"{model}: served weight bytes do not match the contract")


def decode(model, runtime):
    """One discarded warmup + three measured 128-token calls from an empty cache."""
    out = P / (stem(model) + "-decode")
    out.mkdir()
    corpus = (P / "decode-corpus.txt").read_text()
    results = []
    for trial in range(4):
        prompt = f"[standard loaded-decode trial {trial}]\n" + corpus
        if runtime == "ollama":
            reset = ollama_reset(ENDPOINT, model)
            gate(model, runtime, out / f"before-{trial}.json")
            options = {"num_predict": 128, "temperature": 0, "seed": 1234, "num_ctx": 16384}
            r = call(ENDPOINT, "/api/generate", {"model": model, "prompt": prompt, "raw": True,
                     "stream": False, "keep_alive": -1, "options": options}, timeout=900)
            n, generated = r.get("prompt_eval_count"), r.get("eval_count")
            rate = generated / (r["eval_duration"] / 1e9) if r.get("eval_duration") else None
            cached = 0
        else:
            gate(model, runtime, out / f"before-{trial}.json")
            reset = call(ENDPOINT, "/slots/0?action=erase", {})
            if type(reset.get("n_erased")) is not int:
                raise RuntimeError("decode cache reset not confirmed")
            options = {"n_predict": 128, "temperature": 0, "seed": 1234, "cache_prompt": False,
                       "ignore_eos": True, "stream": False}
            r = call(ENDPOINT, "/completion", {"prompt": prompt, **options}, timeout=900)
            t = r["timings"]
            n, generated, rate, cached = t["prompt_n"], t["predicted_n"], t["predicted_per_second"], t.get("cache_n", 0)
        (out / f"response-{trial}.json").write_text(json.dumps(r, indent=2) + "\n")
        gate(model, runtime, out / f"after-{trial}.json")
        if not (type(n) is int and 12800 <= n <= 16384 - 128) or generated != 128 or cached:
            raise RuntimeError(f"decode depth/output contract not met: prompt {n}, generated {generated}, cached {cached}")
        results.append({"trial": trial, "discarded_warmup": trial == 0, "runtime": runtime,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "options": options,
                        "cache_reset": reset, "prompt_tokens": n, "generated": generated, "decode_tok_s": rate})
        (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")


START_LLAMA = '''set -eu
cd {engine}
slotdir=$(mktemp -d /tmp/z13-l012-slots.XXXXXX)
echo Z13_SERVER_PID=$$
exec env LD_LIBRARY_PATH=. ./llama-server -m {path} --alias {model} --host 127.0.0.1 --port 18669 \\
-ngl 99 -fa on -c 16384 -np 1 -n 4096 --keep 4 --seed 1234 \\
--temp 0.7 --top-k 20 --top-p 0.8 --min-p 0 --typical 1 \\
--repeat-last-n 64 --repeat-penalty 1 --presence-penalty 0 --frequency-penalty 0 \\
--jinja --chat-template-kwargs '{{"enable_thinking":false}}' --reasoning-budget 0 \\
--no-context-shift --no-webui --slots --slot-save-path "$slotdir"
'''
START_OLLAMA = '''set -eu
exec bash -c 'echo Z13_SERVER_PID=$$; exec bash /home/blueaz/c1-study-z13-20261001/serve.sh'
'''

STOP = '''import os,signal,sys
from pathlib import Path
pid=int(sys.argv[1]); p=Path(f'/proc/{pid}')
if p.exists():
 args=(p/'cmdline').read_bytes().decode().split('\\0')
 env=(p/'environ').read_bytes().decode().split('\\0')
 ok_llama='18669' in args and '--alias' in args
 ok_ollama='serve' in args and 'OLLAMA_HOST=127.0.0.1:18669' in env and any(e.startswith('OLLAMA_MODELS=/home/blueaz/c1-study-z13-') for e in env)
 if not (ok_llama or ok_ollama): raise SystemExit('refusing to stop process that does not match a study server')
 os.kill(pid,signal.SIGTERM)
'''


def stop_server(log):
    match = re.search(r"Z13_SERVER_PID=(\d+)|C1_SERVER_PID=(\d+)", log.read_text()) if log.exists() else None
    if match:
        run(["ssh", "-o", "ConnectTimeout=5", "z13", "python3", "-", match[1] or match[2]],
            input=STOP, text=True, timeout=15)
        time.sleep(3)


def remote_check():
    check = '''import socket
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',18669));s.close()
'''
    run(["ssh", "z13", "python3", "-"], input=check, text=True, timeout=20)


def main():
    if (P / "STARTED").exists():
        raise SystemExit("packet already started; no silent resume")
    (P / "STARTED").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
    for port in (18690, 18692):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
    tunnel = proxy = server = None
    log = None
    try:
        tunnel = subprocess.Popen(["ssh", "-N", "-o", "ExitOnForwardFailure=yes", "-o", "ConnectTimeout=5",
            "-L", "127.0.0.1:18690:127.0.0.1:18669", "z13"],
            stdout=(P / "tunnel.log").open("w"), stderr=subprocess.STDOUT)
        proxy = subprocess.Popen([sys.executable, "-u", str(L / "request_gate_proxy.py"),
            "--contract", str(CONTRACTS["ollama"]), "--contract", str(CONTRACTS["llama"]),
            "--upstream", ENDPOINT, "--listen-port", "18692",
            "--log", str(P / "request-gate.jsonl"), "--capture-dir", str(P / "requests")],
            stdout=(P / "proxy.log").open("w"), stderr=subprocess.STDOUT)
        for model, runtime in ORDER:
            remote_check()
            log = P / f"server-{stem(model)}.log"
            script = START_OLLAMA if runtime == "ollama" else START_LLAMA.format(
                engine=ENGINE, path=shlex.quote(C["llama"]["models"][model]["gguf_path"]), model=shlex.quote(model))
            server = subprocess.Popen(["ssh", "z13", "bash", "-s"], stdin=subprocess.PIPE,
                                      stdout=log.open("w"), stderr=subprocess.STDOUT, text=True)
            server.stdin.write(script); server.stdin.close()
            ready = "/api/version" if runtime == "ollama" else "/health"
            for _ in range(120):
                if server.poll() is not None or proxy.poll() is not None or tunnel.poll() is not None:
                    raise RuntimeError("study service exited during startup")
                try:
                    reply = call(ENDPOINT, ready)
                    if reply.get("status") == "ok" or reply.get("version") == "0.32.12":
                        break
                except OSError:
                    pass
                time.sleep(2)
            else:
                raise RuntimeError("server did not become ready")
            blob_identity(model, runtime, P / f"blobs-start-{stem(model)}.json")
            if runtime == "ollama":
                ollama_reset(ENDPOINT, model)
            with (P / f"wire-probe-{stem(model)}.jsonl").open("w") as output:
                run(["pi", "--provider", "z13-packet", "--model", model, "--mode", "json", "--print",
                     "--thinking", "off", "--", "Reply with exactly: ready"], cwd="/tmp",
                    stdout=output, stderr=subprocess.STDOUT, timeout=300)
            gate(model, runtime, P / f"launch-preflight-{stem(model)}.json")
            packet(model, runtime, P / f"canary-{stem(model)}", canary=True)
            canary = json.loads((P / f"canary-{stem(model)}" / "results.json").read_text())
            if any(r["outcome"] == "unproven" for r in canary):
                raise RuntimeError(f"{model}: canary has unproven cells; full packet not dispatched")
            try:
                decode(model, runtime)
            except RuntimeError as exc:
                (P / f"{stem(model)}-decode" / "DECODE_FAILED.json").write_text(json.dumps({"error": str(exc)}, indent=2) + "\n")
                print(f"{model} decode failed contract: {exc}", flush=True)
            packet(model, runtime, P / f"quality-{stem(model)}")
            blob_identity(model, runtime, P / f"blobs-end-{stem(model)}.json")
            stop_server(log)
            server.wait(timeout=30)
            server = log = None
        (P / "DONE").write_text("Z13 P2 repair cohort finished (four configurations). Native Fusion is separate.\n")
    finally:
        if log is not None:
            stop_server(log)
        for process in (server, proxy, tunnel):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait()


if __name__ == "__main__":
    main()
