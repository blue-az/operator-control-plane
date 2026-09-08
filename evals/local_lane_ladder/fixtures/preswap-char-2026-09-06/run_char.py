#!/usr/bin/env python3
"""Pre-swap characterization: 2080 / 3090x1 / 3090x2 / agy frontier.

Local pin is the e9pin path the runner uses (num_ctx 16384, temperature 0.8
baked; probe request is temperature 0 / num_predict 128). n=3 warm (one
discarded generate first). No ollama pull. No docker pull.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PROMPT_PATH = Path.home() / (
    "Python/project-phoenix/docs/domain_runs/"
    "GEMMA4-CTX8192-3090-VS-Z13-001/prompt.txt"
)
OUT = Path(__file__).resolve().parent
PIN_26B = "gemma4-26b-e9pin-ctx16384-t0p8:latest"
PIN_35B = "qwen3.6-35b-e9pin-ctx16384-t0p8:latest"
AGY_MODEL = "gemini-3.7-flash-low"
DESKTOP = "http://127.0.0.1:11434"
SOLO = "http://127.0.0.1:11435"
BENCH = "http://testbench.local:11434"


def log(msg: str) -> None:
    print(msg, flush=True)


def append_jsonl(name: str, row: dict) -> None:
    path = OUT / name
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def http_json(url: str, payload: dict | None = None, timeout: int = 180) -> dict:
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def nvidia_smi() -> list[dict]:
    try:
        raw = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,"
                "power.limit,pcie.link.gen.current,pcie.link.width.current",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=10,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    rows = []
    for line in raw.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 7:
            rows.append(
                {
                    "index": int(p[0]),
                    "name": p[1],
                    "mem_used": float(p[2]),
                    "mem_total": float(p[3]),
                    "power_limit": float(p[4]),
                    "pcie_gen": p[5],
                    "pcie_width": p[6],
                }
            )
    return rows


def unload(host: str, model: str) -> None:
    try:
        http_json(
            f"{host}/api/generate",
            {
                "model": model,
                "prompt": "x",
                "stream": False,
                "keep_alive": 0,
                "options": {"num_predict": 1},
            },
            timeout=60,
        )
    except Exception as exc:  # noqa: BLE001
        log(f"  unload {model} on {host}: {exc}")


def generate_once(host: str, model: str, prompt: str) -> dict:
    t0 = time.monotonic()
    data = http_json(
        f"{host}/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": "5m",
            "options": {"num_predict": 128, "temperature": 0},
        },
        timeout=180,
    )
    wall = time.monotonic() - t0
    eval_count = data.get("eval_count") or 0
    eval_ns = data.get("eval_duration") or 0
    tok_s = (eval_count / (eval_ns / 1e9)) if eval_ns else None
    return {
        "tok_s": round(tok_s, 2) if tok_s else None,
        "eval_count": eval_count,
        "eval_duration_s": round(eval_ns / 1e9, 3) if eval_ns else None,
        "wall_s": round(wall, 3),
        "load_duration_s": round((data.get("load_duration") or 0) / 1e9, 3),
        "prompt_eval_count": data.get("prompt_eval_count"),
        "prompt_eval_duration_s": round(
            (data.get("prompt_eval_duration") or 0) / 1e9, 3
        ),
    }


def decode_n(host: str, model: str, label: str, n: int = 3) -> dict:
    prompt = PROMPT_PATH.read_text()
    log(f"decode {label} {model} @ {host}")
    generate_once(host, model, prompt)  # warm, discarded
    reps = []
    for i in range(n):
        row = generate_once(host, model, prompt)
        row["rep"] = i + 1
        row["smi"] = nvidia_smi()
        reps.append(row)
        log(f"  rep{i+1} {row['tok_s']} tok/s wall={row['wall_s']}s")
        append_jsonl(
            "decode.jsonl",
            {"label": label, "host": host, "model": model, **row},
        )
    toks = [r["tok_s"] for r in reps if r["tok_s"] is not None]
    summary = {
        "label": label,
        "host": host,
        "model": model,
        "n": n,
        "tok_s_mean": round(sum(toks) / len(toks), 2) if toks else None,
        "tok_s_min": min(toks) if toks else None,
        "tok_s_max": max(toks) if toks else None,
        "reps": reps,
    }
    (OUT / f"decode-{label}.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def run_agy_print(prompt: str, cwd: Path, extra: list[str] | None = None) -> dict:
    argv = [
        "agy",
        "--print-timeout",
        "10m",
        "--effort",
        "low",
        "--model",
        AGY_MODEL,
        "--disable-slash-commands",
        *(extra or []),
        "-p",
        prompt,
    ]
    t0 = time.monotonic()
    proc = subprocess.run(
        argv,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=600,
    )
    wall = time.monotonic() - t0
    return {
        "argv": argv,
        "returncode": proc.returncode,
        "wall_s": round(wall, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr[-4000:],
        "stdout_chars": len(proc.stdout or ""),
    }


def agy_decode(n: int = 3) -> None:
    prompt = PROMPT_PATH.read_text()
    tmp = Path("/tmp/agy-decode-stick")
    tmp.mkdir(exist_ok=True)
    log(f"agy decode stick model={AGY_MODEL} effort=low n={n}")
    run_agy_print(prompt, tmp)  # warm
    reps = []
    for i in range(n):
        row = run_agy_print(prompt, tmp)
        row["rep"] = i + 1
        reps.append({k: row[k] for k in ("rep", "returncode", "wall_s", "stdout_chars")})
        append_jsonl("agy.jsonl", {"kind": "decode", **reps[-1], "stdout": row["stdout"][-2000:]})
        log(f"  agy decode rep{i+1} wall={row['wall_s']}s chars={row['stdout_chars']} rc={row['returncode']}")
        (OUT / f"agy-decode-rep{i+1}.txt").write_text(row["stdout"] or "")
    (OUT / "agy-decode.json").write_text(json.dumps({"model": AGY_MODEL, "reps": reps}, indent=2) + "\n")


def agy_operator(n: int = 3) -> None:
    sys.path.insert(0, str(ROOT / "evals" / "local_lane_ladder"))
    import fixtures as fx
    import yaml
    from grading import grade

    task_path = ROOT / "evals/local_lane_ladder/tasks/constant_and_callers.yaml"
    task = yaml.safe_load(task_path.read_text())
    prompt = task["prompts"]["L2"]
    log(f"agy operator stick constant-and-callers L2 n={n}")
    reps = []
    for i in range(n):
        root = fx.build_fixture(task.get("files", {}), prefix=f"agy-cac-{i+1}")
        manifest = fx.hash_tree(root)
        row = run_agy_print(
            prompt,
            root,
            extra=["--mode", "accept-edits", "--dangerously-skip-permissions"],
        )
        graded = grade(task["postcondition"], root, row["stdout"] or "", manifest)
        rec = {
            "kind": "operator",
            "task": "constant-and-callers",
            "rep": i + 1,
            "wall_s": row["wall_s"],
            "returncode": row["returncode"],
            "passed": graded.passed,
            "grade_detail": graded.detail,
            "fixture": str(root),
        }
        reps.append(rec)
        append_jsonl("agy.jsonl", rec)
        log(f"  agy op rep{i+1} wall={row['wall_s']}s passed={graded.passed} {graded.detail[:80]}")
        (OUT / f"agy-op-rep{i+1}.txt").write_text(
            (row["stdout"] or "") + "\n--- stderr ---\n" + (row["stderr"] or "")
        )
    (OUT / "agy-operator.json").write_text(json.dumps({"model": AGY_MODEL, "reps": reps}, indent=2) + "\n")


def runner_wall(models: list[str], tasks: list[str], tag: str) -> None:
    out_dir = OUT / tag
    out_dir.mkdir(exist_ok=True)
    argv = [
        sys.executable,
        "-u",
        str(ROOT / "evals/local_lane_ladder/runner.py"),
        "--models",
        *models,
        "--tasks",
        *tasks,
        "--levels",
        "L2",
        "--trials",
        "3",
        "--num-ctx",
        "16384",
        "--temperature",
        "0.8",
        "--think",
        "off",
        "--no-ledger",
        "--output",
        str(out_dir / "RESULTS.md"),
        "--state",
        str(out_dir / "state.json"),
        "--trace-dir",
        str(out_dir / "traces"),
    ]
    env = {**os.environ, "OPERATOR_MACHINE": "desktop", "PYTHONUNBUFFERED": "1"}
    log("runner " + " ".join(argv[-12:]))
    with (out_dir / "run.log").open("w") as logf:
        proc = subprocess.run(
            argv,
            cwd=str(ROOT),
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            timeout=3600,
        )
    log(f"  runner {tag} rc={proc.returncode}")


def start_solo_daemon() -> None:
    """GPU0-only ollama on :11435 using the already-local ollama/ollama image."""
    subprocess.run(["docker", "rm", "-f", "ollama-gpu0"], capture_output=True)
    argv = [
        "docker",
        "run",
        "-d",
        "--name",
        "ollama-gpu0",
        "--gpus",
        "device=0",
        "-e",
        "CUDA_VISIBLE_DEVICES=0",
        "-e",
        "OLLAMA_FLASH_ATTENTION=1",
        "-e",
        "OLLAMA_KV_CACHE_TYPE=q8_0",
        "-v",
        "/usr/share/ollama/.ollama:/root/.ollama",
        "-p",
        "127.0.0.1:11435:11434",
        "ollama/ollama:latest",
    ]
    log("starting " + " ".join(argv))
    subprocess.run(argv, check=True)
    for _ in range(30):
        try:
            http_json(f"{SOLO}/api/tags", timeout=2)
            log("  :11435 up")
            return
        except Exception:
            time.sleep(1)
    raise SystemExit(":11435 did not come up")


def stop_solo_daemon() -> None:
    subprocess.run(["docker", "rm", "-f", "ollama-gpu0"], capture_output=True)


def with_pi_ollama_url(url: str):
    path = Path.home() / ".pi/agent/models.json"
    orig = path.read_text()
    data = json.loads(orig)
    data["providers"]["ollama"]["baseUrl"] = url.rstrip("/") + "/v1"
    path.write_text(json.dumps(data, indent=2) + "\n")
    return orig, path


def restore_pi(orig: str, path: Path) -> None:
    path.write_text(orig)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("phase")
    args = p.parse_args()
    OUT.mkdir(exist_ok=True)
    if not PROMPT_PATH.is_file():
        raise SystemExit(f"missing contract prompt {PROMPT_PATH}")

    if args.phase == "decode-dual":
        decode_n(DESKTOP, PIN_26B, "desktop-dual-26b")
        decode_n(DESKTOP, PIN_35B, "desktop-dual-35b")
        unload(DESKTOP, PIN_26B)
        unload(DESKTOP, PIN_35B)
    elif args.phase == "decode-2080":
        decode_n(BENCH, PIN_26B, "bench-2080-26b")
        unload(BENCH, PIN_26B)
    elif args.phase == "agy-decode":
        agy_decode()
    elif args.phase == "agy-operator":
        agy_operator()
    elif args.phase == "wall-dual-26b":
        generate_once(DESKTOP, PIN_26B, PROMPT_PATH.read_text())
        runner_wall(["gemma4:26b"], ["constant-and-callers", "csv-summarize-repair"], "wall-dual-26b")
        unload(DESKTOP, PIN_26B)
    elif args.phase == "wall-dual-35b":
        generate_once(DESKTOP, PIN_35B, PROMPT_PATH.read_text())
        runner_wall(["qwen3.6:35b"], ["csv-summarize-repair"], "wall-dual-35b")
        unload(DESKTOP, PIN_35B)
    elif args.phase == "solo-up":
        unload(DESKTOP, PIN_26B)
        unload(DESKTOP, PIN_35B)
        start_solo_daemon()
    elif args.phase == "decode-solo":
        decode_n(SOLO, PIN_26B, "desktop-solo-26b")
        decode_n(SOLO, PIN_35B, "desktop-solo-35b")
        unload(SOLO, PIN_26B)
        unload(SOLO, PIN_35B)
    elif args.phase == "wall-solo-26b":
        orig, path = with_pi_ollama_url(SOLO)
        try:
            generate_once(SOLO, PIN_26B, PROMPT_PATH.read_text())
            runner_wall(["gemma4:26b"], ["constant-and-callers", "csv-summarize-repair"], "wall-solo-26b")
            unload(SOLO, PIN_26B)
        finally:
            restore_pi(orig, path)
    elif args.phase == "wall-solo-35b":
        orig, path = with_pi_ollama_url(SOLO)
        try:
            generate_once(SOLO, PIN_35B, PROMPT_PATH.read_text())
            runner_wall(["qwen3.6:35b"], ["csv-summarize-repair"], "wall-solo-35b")
            unload(SOLO, PIN_35B)
        finally:
            restore_pi(orig, path)
    elif args.phase == "solo-down":
        stop_solo_daemon()
        path = Path.home() / ".pi/agent/models.json"
        data = json.loads(path.read_text())
        data["providers"]["ollama"]["baseUrl"] = "http://localhost:11434/v1"
        path.write_text(json.dumps(data, indent=2) + "\n")
    else:
        raise SystemExit(f"unknown phase {args.phase}")


if __name__ == "__main__":
    main()
