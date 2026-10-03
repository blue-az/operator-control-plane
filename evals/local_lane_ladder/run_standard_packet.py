#!/usr/bin/env python3
"""Prospective L0/L1/L2 packet with pre/post cell gates and separate decode.

Uses the existing repair runner and preserves its raw traces. Qualification is
stored separately: missing proof never becomes a scored model failure or pass.
Only operates on an already running, dedicated, request-gated configuration.
llama-server: one slot, erased after the before-gate. Ollama (a dedicated,
launcher-owned daemon): the study model is unloaded and reloaded with no prompt
before the before-gate, so every cell starts from an empty KV cache with warm
page-cached weights; the reload is outside the task timer.
Does not start/stop services, create tags, evict workloads or change Pi settings.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import urllib.request

from comparison_preflight import LLAMA_SCHEMA, validate_contract, validate_request
import runner

TASKS = ["ambiguous-anchor", "booking-off-by-one", "constant-and-callers",
         "csv-summarize-repair", "strict-log-format"]
LEVELS = ["L0", "L1", "L2"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def call(endpoint: str, path: str, body: dict | None = None, timeout: int = 15) -> dict:
    request = urllib.request.Request(endpoint.rstrip("/") + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def ollama_reset(endpoint: str, model: str) -> dict:
    """Unload, confirm nothing is resident, reload without a prompt (no generation)."""
    call(endpoint, "/api/generate", {"model": model, "keep_alive": 0}, timeout=120)
    deadline = time.time() + 120
    while call(endpoint, "/api/ps").get("models"):
        if time.time() > deadline:
            raise RuntimeError("study model did not unload")
        time.sleep(0.5)
    started = time.time()
    loaded = call(endpoint, "/api/generate", {"model": model, "keep_alive": -1}, timeout=600)
    if loaded.get("done_reason") != "load" or loaded.get("response"):
        raise RuntimeError(f"reload was not a prompt-free load: {loaded}")
    rows = call(endpoint, "/api/ps").get("models", [])
    if len(rows) != 1 or rows[0].get("name") != model:
        raise RuntimeError(f"unexpected residency after reload: {rows}")
    return {"method": "ollama unload + prompt-free reload", "unloaded_confirmed": True,
            "reload_s": round(time.time() - started, 2), "ps": rows}


def qualified_outcome(raw: dict, before: dict, after: dict, requests: list[dict]) -> str:
    if not before.get("passed") or not after.get("passed") or not requests:
        return "unproven"
    if not all(r.get("passed") for r in requests):
        return "unproven"
    if before["remote"]["listener_pid"] != after["remote"]["listener_pid"]:
        return "unproven"
    proofs = {**raw.get("proofs", {}), "placement": True}
    if any(proofs.get(k) is not True for k in ("dispatch", "scope", "grader", "timing", "placement")):
        return "unproven"
    return "pass" if raw["passed"] else "fail"


def summarize(records: list[dict], path: Path) -> None:
    lines = ["# Standard packet: fresh results", "",
             "Counts are separate by instruction level. Unproven is not model failure.",
             "Raw fixture grades remain in the traces; qualified outcomes require pre/post placement and request evidence.",
             "Wall time excludes qualification, loading and decode probes; all recorded cells are included.", "",
             "| Level | Pass | Fail | Unproven | Recorded | Median task s | Total task min |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for level in LEVELS:
        cells = [r for r in records if r["raw"]["level"] == level]
        if not cells:
            continue
        counts = [sum(r["outcome"] == s for r in cells) for s in ("pass", "fail", "unproven")]
        times = [r["raw"]["wall_clock_s"] for r in cells]
        lines.append(f"| {level} | {counts[0]} | {counts[1]} | {counts[2]} | {len(cells)} | {statistics.median(times):.2f} | {sum(times)/60:.2f} |")
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contract", type=Path, required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--provider", required=True)
    ap.add_argument("--request-log", type=Path, required=True)
    ap.add_argument("--request-body", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--trials", type=int, default=6)
    ap.add_argument("--tasks", nargs="+", default=TASKS, choices=TASKS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.trials < 1:
        ap.error("positive trials required")
    contract = json.loads(args.contract.read_text())
    validate_contract(contract)
    if args.model not in contract["models"]:
        ap.error("model not in contract")
    tasks = runner.load_tasks(args.tasks)
    if len(tasks) != len(args.tasks):
        ap.error("missing or duplicate tasks")
    errors = runner.validate_task_prompts(tasks)
    if errors:
        raise ValueError(errors)
    for task in tasks:
        runner.validate_task_baseline(task)
    sources = [Path(__file__), Path(runner.__file__), Path(__file__).with_name("grading.py"),
               Path(__file__).with_name("fixtures.py"), Path(__file__).with_name("comparison_preflight.py"),
               Path(__file__).with_name("request_gate_proxy.py"),
               Path(__file__).with_name("preflight_comparison.py"),
               Path(__file__).with_name("preflight_llama_server.py"),
               Path(__file__).with_name("preflight_uma.py"), Path(__file__).with_name("uma_placement.py"),
               args.contract]
    sources += sorted(Path(__file__).with_name("tasks").glob("*.yaml"))
    config_dir = os.environ.get("PI_CODING_AGENT_DIR")
    if config_dir:
        sources += [Path(config_dir) / "models.json", Path(config_dir) / "settings.json"]
    hashes = {str(p.resolve()): digest(p) for p in sources}
    grid = [(task, level, trial) for trial in range(1, args.trials + 1)
            for level in LEVELS for task in tasks]
    print(f"Grid: {len(tasks)} tasks x 3 levels x {args.trials} trials = {len(grid)} cells", flush=True)
    if args.dry_run:
        print("Prompts and untouched-fixture controls passed. No inference.")
        return 0
    if os.environ.get("LOCAL_LANE_SKIP_PIN") != "1":
        ap.error("LOCAL_LANE_SKIP_PIN=1 required: never mutate comparison models")
    if not os.environ.get("PI_CODING_AGENT_DIR"):
        ap.error("isolated PI_CODING_AGENT_DIR required")
    if args.output.exists():
        ap.error("output already exists; use a new directory (no silent resume or overwrite)")
    args.output.mkdir(parents=True)
    (args.output / "manifest.json").write_text(json.dumps({
        "hashes": hashes, "model": args.model, "provider": args.provider,
        "tasks": args.tasks, "levels": LEVELS, "trials_per_task_level": args.trials,
        "cells": len(grid), "timeout_s": runner.MAX_WALL_CLOCK_SECONDS,
        "order": "trial, level, task", "placement_scope": "pre/post snapshots, not continuous",
        "decode": "separate run; never legacy per-cell probe",
        "cache_reset": "llama-server slot erase" if contract["schema"] == LLAMA_SCHEMA
                       else "ollama unload + prompt-free reload before the before-gate",
    }, indent=2) + "\n")
    records = []
    if contract.get("placement", {}).get("kind") == "uma-amdgpu":
        preflight = "preflight_uma.py"
    else:
        preflight = "preflight_llama_server.py" if contract["schema"] == LLAMA_SCHEMA else "preflight_comparison.py"

    def gate(path: Path) -> dict:
        for name, sha in hashes.items():
            if digest(Path(name)) != sha:
                raise RuntimeError(f"frozen input changed: {name}")
        command = [sys.executable, str(Path(__file__).with_name(preflight)),
                   "--contract", str(args.contract.resolve()), "--model", args.model,
                   "--request-body", str(args.request_body.resolve()), "--capture", str(path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=650)
        if result.returncode:
            raise RuntimeError(f"preflight refused: {result.stdout} {result.stderr}")
        report = json.loads(path.read_text())
        if report.get("passed") is not True:
            raise RuntimeError("preflight did not attest success")
        return report

    for task, level, trial in grid:
        cell = args.output / f"{task['task_id']}__{level}__t{trial}"
        cell.mkdir()
        # Fresh conversation KV, warm weights. Never clear another daemon/model.
        if contract["schema"] == LLAMA_SCHEMA:
            before = gate(cell / "before.json")
            erased = call(contract["endpoint"], "/slots/0?action=erase", {})
            if type(erased.get("n_erased")) is not int or erased["n_erased"] < 0:
                raise RuntimeError(f"slot erase not confirmed: {erased}")
        else:
            erased = ollama_reset(contract["endpoint"], args.model)
            before = gate(cell / "before.json")
        (cell / "cache-reset.json").write_text(json.dumps(erased, indent=2) + "\n")
        stat = args.request_log.stat()
        offset = stat.st_size
        started = time.time()
        raw = runner.run_trial(task, level, args.model, trial,
            ledger_dir=runner.REPO_ROOT, use_ledger=False, trace_dir=cell / "traces",
            provider=args.provider, sampling={"think": "off" if contract["think"] == "off" else "medium",
                                              "skip_decode_probe": True})
        finished = time.time()
        # Gate failures leave the raw trace intact and stop the campaign.
        try:
            after = gate(cell / "after.json")
        except Exception as exc:
            (cell / "GATE_FAILURE.json").write_text(json.dumps({"error": str(exc), "raw": raw}, indent=2))
            raise
        current = args.request_log.stat()
        if (current.st_dev, current.st_ino) != (stat.st_dev, stat.st_ino) or current.st_size < offset:
            raise RuntimeError("request log replaced or truncated")
        with args.request_log.open("rb") as stream:
            stream.seek(offset)
            requests = [json.loads(line) for line in stream.read().splitlines()]
        for request in requests:
            if request.get("model") != args.model or not started <= request["ts"] <= finished:
                raise RuntimeError("request log contains traffic outside this cell")
            validate_request(contract, request["fields"])
        record = {"outcome": qualified_outcome(raw, before, after, requests), "raw": raw,
                  "placement": {"before": str(cell / "before.json"), "after": str(cell / "after.json")},
                  "requests": requests, "request_log_offset": offset}
        (cell / "qualified.json").write_text(json.dumps(record, indent=2) + "\n")
        records.append(record)
        (args.output / "results.json").write_text(json.dumps(records, indent=2) + "\n")
        summarize(records, args.output / "RESULTS.md")
        print(f"{task['task_id']} {level} t{trial}: {record['outcome']} ({raw['wall_clock_s']}s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
