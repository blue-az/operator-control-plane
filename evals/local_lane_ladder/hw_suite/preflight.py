#!/usr/bin/env python3
"""Admissibility gate for local-inference measurement.

A measurement is admissible only when every axis below is explicitly set and
recorded. This gate REFUSES (non-zero exit) rather than warning, because the
failure mode it exists to prevent is a plausible-looking number taken under an
unrecorded configuration.

The eleven axes:
   1 num_ctx                7 harness / transport
   2 temperature            8 concurrent GPU load
   3 KV cache type          9 host RAM + mmap state
   4 flash attention       10 tag lineage (bare | pinned | derived)
   5 placement (num_gpu)   11 host identity (CPU, RAM, driver, ollama build)
   6 daemon + LLM library

Two rules learned the hard way and enforced here:

* Machine quiet is verified by CONTINUOUS sampling for the whole trial, not once
  beforehand. A concurrent session on a keep-alive timer reappears mid-run and a
  pre-flight-only check will not see it.
* Foreign processes are detected with `nvidia-smi --query-compute-apps`, never
  `pgrep -f`, which matches the harness's own command line and reports itself.

Usage:
    python3 preflight.py --daemon 127.0.0.1:11434 --model qwen3.8:27b
    python3 preflight.py ... --json           # config block only, for embedding
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from typing import Any


class Refusal(Exception):
    """Raised when an axis is unset, ambiguous, or the machine is not quiet."""


def _run(cmd: list[str], timeout: int = 30) -> str:
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Refusal(f"could not run {cmd[0]}: {exc}") from exc
    if p.returncode != 0:
        raise Refusal(f"{' '.join(cmd[:3])} exited {p.returncode}: {p.stderr.strip()[:160]}")
    return p.stdout


# ---------------------------------------------------------------- axis 11
def host_identity() -> dict[str, Any]:
    cpu = ""
    threads = cores = 0
    for line in _run(["lscpu"]).splitlines():
        if line.startswith("Model name:"):
            cpu = line.split(":", 1)[1].strip()
        elif line.startswith("CPU(s):") and not threads:
            threads = int(line.split(":", 1)[1].strip())
        elif line.startswith("Core(s) per socket:"):
            cores = int(line.split(":", 1)[1].strip())
    mem_kb = 0
    with open("/proc/meminfo") as fh:
        for line in fh:
            if line.startswith("MemTotal:"):
                mem_kb = int(line.split()[1])
                break
    gpus = []
    for row in _run(["nvidia-smi",
                     "--query-gpu=index,name,uuid,memory.total,driver_version,display_active",
                     "--format=csv,noheader"]).strip().splitlines():
        idx, name, uuid, total, driver, display = [c.strip() for c in row.split(",")]
        gpus.append({"index": int(idx), "name": name, "uuid": uuid,
                     "vram_mib": int(total.split()[0]), "driver": driver,
                     "display_active": display.lower() == "enabled"})
    return {
        "hostname": os.uname().nodename,
        "kernel": os.uname().release,
        "cpu": cpu, "cores": cores, "threads": threads,
        "ram_mib": mem_kb // 1024,
        "ollama_version": _run(["ollama", "--version"]).strip(),
        "gpus": gpus,
        # CUDA_DEVICE_ORDER unset means CUDA ordinals are NOT nvidia-smi indices.
        "cuda_device_order": os.environ.get("CUDA_DEVICE_ORDER", "<unset>"),
    }


# ------------------------------------------------------------ axes 3,4,6
def daemon_config(daemon: str) -> dict[str, Any]:
    """Read the target daemon's effective settings. Refuses if unreachable."""
    try:
        with urllib.request.urlopen(f"http://{daemon}/api/tags", timeout=10) as r:
            r.read()
    except (urllib.error.URLError, OSError) as exc:
        raise Refusal(f"daemon {daemon} unreachable: {exc}")

    env: dict[str, str] = {}
    unit = _systemd_unit_for(daemon)
    if unit:
        raw = subprocess.run(["systemctl", "show", unit, "-p", "Environment", "--no-pager"],
                             text=True, capture_output=True).stdout
        for tok in raw.replace("Environment=", "").split():
            if "=" in tok:
                k, v = tok.split("=", 1)
                env[k] = v
    for k in ("OLLAMA_KV_CACHE_TYPE", "OLLAMA_FLASH_ATTENTION", "OLLAMA_LLM_LIBRARY",
              "OLLAMA_CONTEXT_LENGTH", "OLLAMA_NUM_PARALLEL", "OLLAMA_MAX_LOADED_MODELS",
              "OLLAMA_KEEP_ALIVE", "OLLAMA_SCHED_SPREAD", "CUDA_VISIBLE_DEVICES"):
        env.setdefault(k, os.environ.get(k, ""))

    kv = env.get("OLLAMA_KV_CACHE_TYPE") or "f16 (default)"
    fa = env.get("OLLAMA_FLASH_ATTENTION") or "<unset>"
    lib = env.get("OLLAMA_LLM_LIBRARY") or "<unset>"
    if lib == "<unset>":
        raise Refusal(
            "OLLAMA_LLM_LIBRARY is unset on the target daemon. It is required, not "
            "optional (hw_standard.py:26): unset, the daemon also enumerates Vulkan "
            "and the backend actually used is not determined by the record.")
    return {"endpoint": daemon, "systemd_unit": unit, "kv_cache_type": kv,
            "flash_attention": fa, "llm_library": lib,
            "context_length_env": env.get("OLLAMA_CONTEXT_LENGTH") or "0 (model default)",
            "num_parallel": env.get("OLLAMA_NUM_PARALLEL") or "<unset>",
            "max_loaded_models": env.get("OLLAMA_MAX_LOADED_MODELS") or "<unset>",
            "keep_alive": env.get("OLLAMA_KEEP_ALIVE") or "<unset>",
            "visible_devices": env.get("CUDA_VISIBLE_DEVICES") or "<all>"}


def _systemd_unit_for(daemon: str) -> str | None:
    """Only the stock unit serves :11434; a solo daemon logs elsewhere."""
    if daemon.endswith(":11434"):
        r = subprocess.run(["systemctl", "is-active", "ollama"], text=True, capture_output=True)
        if r.stdout.strip() == "active":
            return "ollama"
    return None


# ------------------------------------------------------------ axes 1,2,5,10
def model_config(model: str) -> dict[str, Any]:
    out = _run(["ollama", "show", model])
    params: dict[str, str] = {}
    for line in out.splitlines():
        f = line.split()
        if len(f) == 2 and f[0] in ("num_ctx", "temperature", "num_gpu", "num_predict"):
            params[f[0]] = f[1]
    lineage = "derived" if "hwstd" in model or "tmp-" in model else (
        "pinned" if "e9pin" in model or "ctx" in model else "bare")
    if lineage == "bare":
        # Not fatal: the caller may pin per-request. Recorded, and the runner
        # refuses if neither the tag nor the request supplies num_ctx.
        params.setdefault("num_ctx", "<model default>")
    return {"tag": model, "tag_lineage": lineage, "tag_params": params}


# ---------------------------------------------------------------- axis 8
class QuietWatch:
    """Continuous foreign-GPU-process sampler. Detection via nvidia-smi only."""

    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self.seen: dict[str, int] = {}
        self._stop = threading.Event()
        self._t: threading.Thread | None = None
        self.samples = 0

    @staticmethod
    def _snapshot() -> set[str]:
        out = subprocess.run(
            ["nvidia-smi", "--query-compute-apps=pid,process_name", "--format=csv,noheader"],
            text=True, capture_output=True).stdout
        return {l.split(",")[0].strip() for l in out.splitlines() if "ollama" in l.lower()}

    def assert_quiet_now(self) -> None:
        held = self._snapshot()
        if held:
            raise Refusal(f"machine is not quiet: ollama already holds a GPU (pids {sorted(held)})")

    def _loop(self) -> None:
        while not self._stop.is_set():
            for pid in self._snapshot():
                self.seen[pid] = self.seen.get(pid, 0) + 1
            self.samples += 1
            self._stop.wait(self.interval)

    def start(self) -> None:
        self.assert_quiet_now()
        self._t = threading.Thread(target=self._loop, daemon=True)
        self._t.start()

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._t:
            self._t.join(timeout=3)
        return {"samples": self.samples, "ollama_gpu_pids": sorted(self.seen)}

    def verdict(self, own_pids: set[str]) -> tuple[bool, str]:
        foreign = sorted(set(self.seen) - own_pids)
        if foreign:
            return False, f"foreign ollama GPU processes appeared mid-trial: {foreign}"
        return True, "quiet throughout"


# ---------------------------------------------------------------- axis 9
def memory_state() -> dict[str, Any]:
    info: dict[str, int] = {}
    with open("/proc/meminfo") as fh:
        for line in fh:
            k, v = line.split(":", 1)
            info[k] = int(v.split()[0])
    avail = info.get("MemAvailable", 0) // 1024
    swap_used = (info.get("SwapTotal", 0) - info.get("SwapFree", 0)) // 1024
    return {"mem_available_mib": avail, "swap_used_mib": swap_used,
            "note": "ollama disables mmap when model_size + headroom exceeds available"}


def build(daemon: str, model: str) -> dict[str, Any]:
    return {"schema": "hw_suite/preflight-1",
            "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "host": host_identity(), "daemon": daemon_config(daemon),
            "model": model_config(model), "memory": memory_state()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--daemon", default="127.0.0.1:11434")
    ap.add_argument("--model", required=True)
    ap.add_argument("--json", action="store_true", help="emit the config block only")
    args = ap.parse_args()

    if not shutil.which("nvidia-smi") or not shutil.which("ollama"):
        print("REFUSED: nvidia-smi and ollama must both be on PATH", file=sys.stderr)
        return 2
    try:
        block = build(args.daemon, args.model)
        QuietWatch().assert_quiet_now()
    except Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(block, indent=2))
        return 0
    h, d, m = block["host"], block["daemon"], block["model"]
    print(f"host        {h['hostname']}  {h['cpu']} ({h['cores']}c/{h['threads']}t)  "
          f"{h['ram_mib']} MiB RAM  {h['ollama_version']}")
    for g in h["gpus"]:
        print(f"  gpu{g['index']}      {g['name']}  {g['vram_mib']} MiB  "
              f"display={'on' if g['display_active'] else 'off'}  {g['uuid']}")
    print(f"  CUDA_DEVICE_ORDER {h['cuda_device_order']}"
          + ("  <-- ordinals are NOT nvidia-smi indices; pin by UUID"
             if h["cuda_device_order"] == "<unset>" else ""))
    print(f"daemon      {d['endpoint']}  lib={d['llm_library']}  kv={d['kv_cache_type']}  "
          f"flash_attn={d['flash_attention']}  devices={d['visible_devices']}")
    print(f"model       {m['tag']}  lineage={m['tag_lineage']}  {m['tag_params']}")
    print(f"memory      {block['memory']['mem_available_mib']} MiB available, "
          f"{block['memory']['swap_used_mib']} MiB swap in use")
    print("ADMISSIBLE — all axes recorded, machine quiet at this instant")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
