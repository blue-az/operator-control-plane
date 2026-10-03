#!/usr/bin/env python3
"""C1 repair cohort: seat weights on a dedicated, launcher-owned Ollama daemon.

Own only the study daemon (testbench 18669), tunnel (18670) and request gate
(18672). Never touch the shared seat daemons, evict workloads or restart services.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time

P = Path(__file__).resolve().parent
L = P.parents[1]
sys.path.insert(0, str(L))
from run_standard_packet import call, ollama_reset  # noqa: E402

CONTRACT = P / "contract-c1-3090.json"
C = json.loads(CONTRACT.read_text())
MODELS = ("c1-qwen3.6-35b:latest", "c1-gemma4-26b:latest")
ENV = {**os.environ, "PI_CODING_AGENT_DIR": str(P / "pi-config"),
       "LOCAL_LANE_SKIP_PIN": "1", "LOCAL_LANE_MAX_WALL_CLOCK": "600",
       "OPERATOR_MACHINE": "desktop", "OLLAMA_HOST": C["endpoint"]}
BLOBS = "/home/ef-tb/c1-study-20261001/models/blobs/sha256-"


def run(argv, **kwargs):
    return subprocess.run(argv, check=True, env=ENV, **kwargs)


def body_path(model):
    return P / "requests" / (model.replace(":", "_") + ".json")


def gate(model, capture):
    run([sys.executable, str(L / "preflight_comparison.py"), "--contract", str(CONTRACT),
         "--model", model, "--request-body", str(body_path(model)), "--capture", str(capture)],
        stdout=subprocess.DEVNULL)


def blob_identity(model, target):
    """Byte hash of weight + projector blobs, once per model block (start and end)."""
    info = C["models"][model]
    digests = [info["weight_sha256"], *info["extra_blob_sha256s"]]
    script = ("import hashlib,os,sys,json\nout={}\nfor d in sys.argv[1:]:\n p='" + BLOBS + "'+d\n"
              " h=hashlib.sha256()\n with open(p,'rb') as f:\n  [h.update(b) for b in iter(lambda:f.read(8<<20),b'')]\n"
              " s=os.stat(p); out[d]={'sha256':h.hexdigest(),'bytes':s.st_size,'inode':s.st_ino,'mtime':s.st_mtime}\n"
              "print(json.dumps(out))\n")
    result = run(["ssh", "testbench", "python3", "-", *digests], input=script, text=True,
                 capture_output=True, timeout=900)
    observed = json.loads(result.stdout)
    target.write_text(json.dumps(observed, indent=2) + "\n")
    for d in digests:
        if observed[d]["sha256"] != d:
            raise RuntimeError(f"blob {d} bytes do not match its digest")
    return observed


def packet(model, output, canary=False):
    args = [sys.executable, "-u", str(L / "run_standard_packet.py"),
            "--contract", str(CONTRACT), "--model", model, "--provider", "standard-packet",
            "--request-log", str(P / "request-gate.jsonl"),
            "--request-body", str(body_path(model)), "--output", str(output)]
    if canary:
        args += ["--tasks", "booking-off-by-one", "--trials", "1"]
    run(args)


def decode(model):
    """Loaded decode: one discarded warmup + three measured 128-token calls.

    Ollama has no ignore_eos; a call that stops before 128 tokens fails the
    contract and is recorded, not shortened. Each call starts from an unloaded
    and prompt-free-reloaded model, so the 12.8K+ prompt is never cached.
    """
    out = P / (model.split(":")[0] + "-decode")
    out.mkdir()
    corpus = (P / "decode-corpus.txt").read_text()
    results = []
    for trial in range(4):
        prompt = f"[standard loaded-decode trial {trial}]\n" + corpus
        options = {"num_predict": 128, "temperature": 0, "seed": 1234, "num_ctx": 16384}
        reset = ollama_reset(C["endpoint"], model)
        gate(model, out / f"before-{trial}.json")
        response = call(C["endpoint"], "/api/generate", {"model": model, "prompt": prompt, "raw": True,
                        "stream": False, "keep_alive": -1, "options": options}, timeout=600)
        (out / f"response-{trial}.json").write_text(json.dumps(response, indent=2) + "\n")
        gate(model, out / f"after-{trial}.json")
        n = response.get("prompt_eval_count")
        if not (type(n) is int and 12800 <= n <= 16384 - 128) or response.get("eval_count") != 128:
            raise RuntimeError(f"decode depth/output contract not met: prompt {n}, "
                               f"eval {response.get('eval_count')}, {response.get('done_reason')}")
        results.append({"trial": trial, "discarded_warmup": trial == 0,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "options": options, "cache_reset": reset,
                        "prompt_eval_count": n, "eval_count": response["eval_count"],
                        "prompt_eval_duration_ns": response["prompt_eval_duration"],
                        "eval_duration_ns": response["eval_duration"],
                        "decode_tok_s": response["eval_count"] / (response["eval_duration"] / 1e9)})
        (out / "results.json").write_text(json.dumps(results, indent=2) + "\n")


def remote_check():
    check = '''import csv,subprocess,socket
s=socket.socket();s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);s.bind(('127.0.0.1',18669));s.close()
r=subprocess.check_output(['nvidia-smi','--query-compute-apps=pid,used_gpu_memory','--format=csv,noheader,nounits'],text=True)
assert all(float(row[1])<=64 for row in csv.reader(r.splitlines())), 'GPU compute workload present'
'''
    run(["ssh", "testbench", "python3", "-"], input=check, text=True, timeout=20)


def stop_server(log):
    match = re.search(r"C1_SERVER_PID=(\d+)", log.read_text()) if log.exists() else None
    if not match:
        return
    script = '''import os,signal,sys
from pathlib import Path
pid=int(sys.argv[1])
p=Path(f'/proc/{pid}')
if p.exists():
 args=(p/'cmdline').read_bytes().decode().split('\\0')
 env=(p/'environ').read_bytes().decode().split('\\0')
 if 'serve' not in args or 'OLLAMA_HOST=127.0.0.1:18669' not in env or not any(e.startswith('OLLAMA_MODELS=/home/ef-tb/c1-study-20261001/') for e in env):
  raise SystemExit('refusing to stop process that does not match the study daemon')
 os.kill(pid,signal.SIGTERM)
'''
    run(["ssh", "-o", "ConnectTimeout=5", "testbench", "python3", "-", match[1]],
        input=script, text=True, timeout=15)


def main():
    if (P / "STARTED").exists():
        raise SystemExit("packet already started; no silent resume")
    (P / "STARTED").write_text(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()) + "\n")
    for port in (18670, 18672):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
    remote_check()
    tunnel = proxy = server = None
    log = P / "server.log"
    try:
        server = subprocess.Popen(["ssh", "testbench", "bash", C["daemon"]["script"]],
                                  stdin=subprocess.DEVNULL, stdout=log.open("w"), stderr=subprocess.STDOUT)
        tunnel = subprocess.Popen(["ssh", "-N", "-o", "ExitOnForwardFailure=yes",
            "-o", "ConnectTimeout=5", "-L", "127.0.0.1:18670:127.0.0.1:18669", "testbench"],
            stdout=(P / "tunnel.log").open("w"), stderr=subprocess.STDOUT)
        proxy = subprocess.Popen([sys.executable, "-u", str(L / "request_gate_proxy.py"),
            "--contract", str(CONTRACT), "--upstream", C["endpoint"], "--listen-port", "18672",
            "--log", str(P / "request-gate.jsonl"), "--capture-dir", str(P / "requests")],
            stdout=(P / "proxy.log").open("w"), stderr=subprocess.STDOUT)
        for _ in range(60):
            if server.poll() is not None or proxy.poll() is not None or tunnel.poll() is not None:
                raise RuntimeError("study service exited during startup")
            try:
                if call(C["endpoint"], "/api/version").get("version") == C["ollama_version"]:
                    break
            except OSError:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("daemon did not become reachable")
        (P / "daemon-tags.json").write_text(json.dumps(call(C["endpoint"], "/api/tags"), indent=2) + "\n")
        for model in MODELS:
            stem = model.split(":")[0]
            blob_identity(model, P / f"blobs-start-{stem}.json")
            ollama_reset(C["endpoint"], model)
            # Instrument probe, not a scored cell. All outgoing options gated.
            with (P / f"wire-probe-{stem}.jsonl").open("w") as output:
                run(["pi", "--provider", "standard-packet", "--model", model,
                     "--mode", "json", "--print", "--thinking", "off", "--",
                     "Reply with exactly: ready"], cwd="/tmp", stdout=output,
                    stderr=subprocess.STDOUT, timeout=180)
            gate(model, P / f"launch-preflight-{stem}.json")
            packet(model, P / f"canary-{stem}", canary=True)
            canary = json.loads((P / f"canary-{stem}" / "results.json").read_text())
            if any(r["outcome"] == "unproven" for r in canary):
                raise RuntimeError("canary has unproven cells; full packet not dispatched")
            try:
                decode(model)
            except RuntimeError as exc:
                # A separate column: record the bounded failure, keep the quality packet.
                (P / f"{stem}-decode" / "DECODE_FAILED.json").write_text(
                    json.dumps({"error": str(exc)}, indent=2) + "\n")
                print(f"{model} decode failed contract: {exc}", flush=True)
            packet(model, P / f"quality-{stem}")
            blob_identity(model, P / f"blobs-end-{stem}.json")
            call(C["endpoint"], "/api/generate", {"model": model, "keep_alive": 0}, timeout=120)
        (P / "DONE").write_text("C1 3090 repair cohort finished (both models). Native Fusion is a separate packet.\n")
    finally:
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
