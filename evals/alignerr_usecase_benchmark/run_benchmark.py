#!/usr/bin/env python3
"""Run the Alignerr-derived internal use-case benchmark locally.

No network or external Alignerr access is required by this script beyond whatever
model provider the caller explicitly selects for `pi`. The default provider is
local Ollama.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "runs" / time.strftime("%Y%m%d-%H%M%S")

MODELS = [
    ("qwen38", "qwen3.8:27b"),
    ("qwen36-35b", "qwen3.6:35b"),
    ("gemma31", "gemma4:31b"),
    ("gemma26", "gemma4:26b"),
]

TASKS = {
    "aub1_code_preference": {
        "sources": [
            "/home/blueaz/Documents/Career/Applications/Alignerr/ALIGNERR_EVAL_RESULT_2026-04-24.md",
            "/home/blueaz/Alignerr/Test_Instructions.md",
        ],
        "prompt": """You are doing an internal benchmark derived from a saved local evaluator task.\nDo not use network or external systems.\n\nTask: Given the local notes about a Koalas code-preference eval, identify the correct preference and explain why in reviewer form.\n\nReturn exactly these sections:\nPREFERENCE: <A or B>\nRATIONALE: <5-8 sentences>\nRISKS: <bullets>\nVERIFICATION_GAPS: <bullets>\n\nScoring rewards: preferring the narrower localized patch, identifying reset-index/rebuild-index workaround risk, noticing TODOs in final code, and not overclaiming correctness without verification.\n""",
    },
    "aub2_dispute_rederivation": {
        "sources": ["/home/blueaz/Alignerr/batch4_failure_catalog.md"],
        "prompt": """You are doing an internal benchmark derived from saved local dispute-handling work.\nDo not use network or external systems.\n\nTask: Extract the operating rule for handling reviewer disputes. Explain how to decide which disputed additions/removals/arithmetic changes to accept, reject, or hold for clarification.\n\nReturn exactly these sections:\nCORE_RULE: <one sentence>\nPROCEDURE: <numbered steps>\nFAILURE_MODES: <bullets>\nWHEN_TO_HOLD: <bullets>\n\nScoring rewards: treating disputes as claims not verdicts, independently re-deriving file sets and arithmetic, decomposing subclaims, literal-rule adherence, and routing corrections through claim/evidence/review.\n""",
    },
    "aub3_mujoco_verification": {
        "sources": [
            "/home/blueaz/Alignerr/mujoco-prep/PREP_BRIEF.md",
            "/home/blueaz/Alignerr/mujoco-prep/GPU_CPU_BENCH_SECTION.md",
            "/home/blueaz/Alignerr/mujoco-prep/INTERVIEW_CRIB.md",
            "/home/blueaz/Alignerr/mujoco_spike/MUJOCO_LESSONS_LEARNED.md",
        ],
        "prompt": """You are doing an internal benchmark derived from saved local MuJoCo/RL work.\nDo not use network or external systems.\n\nTask: Extract benchmarkable claims and propose rerunnable verification gates. Separate throughput from convergence, Gym-MuJoCo learner-device tests from MJX/GPU physics, and contact/model invariants from subjective visual assessment.\n\nReturn exactly these sections:\nMEASURED_CLAIMS: <bullets with numbers>\nRERUNNABLE_GATES: <bullets with commands or test types>\nPHYSICS_API_RULES: <bullets>\nSCOPE_LIMITS: <bullets>\n\nScoring rewards: closed-form geometry checks, mj_forward not mj_step for set-pose/read-sensor tests, support-force-equals-weight after self-contact filtering, CPU/GPU crossover correctness, and honest limits.\n""",
    },
}


def read_sources(paths: list[str], max_chars: int = 26000) -> str:
    chunks = []
    remaining = max_chars
    for raw in paths:
        path = Path(raw)
        text = path.read_text(errors="replace")
        if len(text) > remaining:
            text = text[:remaining] + "\n[TRUNCATED]\n"
        chunks.append(f"\n===== SOURCE: {path} =====\n{text}")
        remaining -= len(text)
        if remaining <= 0:
            break
    return "\n".join(chunks)


def run_openai_compatible(model: str, prompt: str, timeout: int, base_url: str) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 2048,
        "thinking": {"type": "disabled"},
        "reasoning_effort": "none",
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    started = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode()
        data = json.loads(raw)
        message = data.get("choices", [{}])[0].get("message", {})
        return {
            "returncode": 0,
            "elapsed_s": round(time.time() - started, 3),
            "stdout": message.get("content", ""),
            "stderr": "",
            "raw_response": data,
            "cmd": ["POST", url],
            "model": model,
        }
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        return {"returncode": exc.code, "elapsed_s": round(time.time() - started, 3), "stdout": "", "stderr": raw, "cmd": ["POST", url], "model": model}


def run_one(provider: str, model: str, task_name: str, prompt: str, timeout: int, ollama_host: str, base_url: str) -> dict:
    if provider in {"openai-compatible", "freetoken"}:
        result = run_openai_compatible(model, prompt, timeout, base_url)
        result["task"] = task_name
        return result
    env = os.environ.copy()
    env["OLLAMA_HOST"] = ollama_host
    cmd = [
        "pi",
        "--provider",
        provider,
        "--model",
        model,
        "--thinking",
        "off",
        "--no-context-files",
        "--no-session",
        "--print",
        "--",
        prompt,
    ]
    started = time.time()
    proc = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout, env=env)
    elapsed = time.time() - started
    return {
        "returncode": proc.returncode,
        "elapsed_s": round(elapsed, 3),
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        # The assembled prompt embeds verbatim source artifacts (see SOURCES).
        # Never persist it: storing cmd wholesale put those artifacts into a
        # public repo once already. The prompt is reproducible from the task
        # yaml plus the local source files, so it does not need to be on disk.
        "cmd": cmd[:-1] + ["<prompt omitted: embeds source artifacts>"],
        "task": task_name,
        "model": model,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--ollama-host", default="127.0.0.1:11435")
    parser.add_argument("--base-url", default="http://127.0.0.1:1934/v1")
    parser.add_argument("--served-model", default=None, help="Override model id sent to an OpenAI-compatible server, e.g. a FreeToken served-model-name.")
    parser.add_argument("--timeout", type=int, default=420)
    parser.add_argument("--models", default=",".join(label for label, _ in MODELS))
    args = parser.parse_args()

    selected = {x.strip() for x in args.models.split(",") if x.strip()}
    models = [(label, model) for label, model in MODELS if label in selected]
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {"out_dir": str(OUT), "provider": args.provider, "ollama_host": args.ollama_host, "base_url": args.base_url, "results": []}

    for task_name, spec in TASKS.items():
        prompt = spec["prompt"] + "\n" + read_sources(spec["sources"])
        # The assembled prompt inlines verbatim source artifacts, some of them
        # confidential (client eval instructions, personal career notes). It is
        # written only under runs/, which is gitignored, and is reproducible on
        # demand from the task spec plus the local sources.
        (OUT / f"{task_name}.prompt.txt").write_text(prompt)
        for label, model in models:
            print(f"RUN {task_name} {label} {model}", flush=True)
            request_model = args.served_model or model
            result = run_one(args.provider, request_model, task_name, prompt, args.timeout, args.ollama_host, args.base_url)
            result["label"] = label
            result["model"] = model
            result["request_model"] = request_model
            stem = f"{task_name}__{label}"
            (OUT / f"{stem}.json").write_text(json.dumps(result, indent=2))
            (OUT / f"{stem}.out.md").write_text(result["stdout"])
            manifest["results"].append({
                "task": task_name,
                "label": label,
                "model": model,
                "request_model": request_model,
                "returncode": result["returncode"],
                "elapsed_s": result["elapsed_s"],
                "stdout_path": f"{stem}.out.md",
            })
            print(f"DONE {task_name} {label} rc={result['returncode']} elapsed={result['elapsed_s']}", flush=True)
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
