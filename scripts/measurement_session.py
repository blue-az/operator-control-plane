import hashlib
import json
import os
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import gated_runner

# --- Models to Test ---
MODELS = ["gemma4:31b", "gemma4:26b", "qwen3.8:27b", "qwen3.6:27b"]

# --- Tasks (Multi-Task Grid) ---
TASKS = {
    "text_edit": {
        "content": "The quick brown fox jumps over the lazy dog.",
        "anchor": "the lazy dog",
        "replacement": "the active dog",
        "gate_cmd": "grep -q 'the active dog' {file} && echo 'OK'",
        "desc": "Simple text replacement"
    },
    "py_fix": {
        "content": "def hello()\n    print('hi')",
        "anchor": "def hello()",
        "replacement": "def hello():",
        "gate_cmd": "python3 -c \"with open('{file}', 'r') as f: exec(f.read())\" && echo 'OK'",
        "desc": "Python syntax fix"
    },
    "yaml_val": {
        "content": "setting: false\nmode: auto",
        "anchor": "setting: false",
        "replacement": "setting: true",
        "gate_cmd": "grep -q 'setting: true' {file} && echo 'OK'",
        "desc": "YAML value toggle"
    },
    "log_clean": {
        "content": "2026-01-01 INFO UserLogin\n2026-01-01 DEBUG Trace-123\n2026-01-01 INFO UserLogout",
        "anchor": "DEBUG Trace-123",
        "replacement": "[REDACTED]",
        "gate_cmd": "grep -v 'DEBUG' {file} | grep -q 'REDACTED' && echo 'OK'",
        "desc": "Log PII redaction"
    },
    "json_upd": {
        "content": "{\"version\": \"1.0\", \"status\": \"beta\"}",
        "anchor": "\"status\": \"beta\"",
        "replacement": "\"status\": \"stable\"",
        "gate_cmd": "python3 -c \"import json; f=open('{file}'); d=json.load(f); exit(0 if d['status']=='stable' else 1)\" && echo 'OK'",
        "desc": "JSON status update"
    }
}

def get_model_response(model, prompt):
    """Interaction with Ollama."""
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e!s}"

def apply_edit(response):
    """Robust extraction of content from model response."""
    # 1. Try to find content in Markdown code blocks
    if "```" in response:
        parts = response.split("```")
        # The content will be in the 2nd, 4th, etc. parts (odds)
        for i in range(1, len(parts), 2):
            block = parts[i]
            # Strip language tag (e.g., 'python' or 'yaml') from the first line
            lines = block.splitlines()
            if lines:
                first_line = lines[0].strip()
                if first_line in ["python", "yaml", "text", "json", "markdown"]:
                    return "\n".join(lines[1:])
                return "\n".join(lines)
    
    # 2. Fallback: If no code blocks, but response is short and looks like the goal, return as is
    # (Avoid returning long conversations)
    if len(response) < 500:
        return response
    
    return "ERROR: Could not extract clean content"

def get_gpu_temps():
    """Capture current temperatures of all GPUs."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8"
        )
        return [int(t.strip()) for t in result.stdout.strip().split("\n") if t.strip()]
    except Exception:
        return []

import argparse


def run_measurement(model_filter=None, trials_per_cell=3):
    storage_dir = Path("./measurement_results")
    storage_dir.mkdir(exist_ok=True)
    results = []

    models_to_run = [model_filter] if model_filter else MODELS

    print(f"Starting measurement session: {len(models_to_run)} models x {len(TASKS)} tasks x {trials_per_cell} trials")
    print("-" * 80)

    for model in models_to_run:
        # Capture pre-model temps
        pre_temps = get_gpu_temps()
        
        for task_id, task_info in TASKS.items():
            for trial in range(1, trials_per_cell + 1):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    file_path = root / "target.txt"
                    file_path.write_text(task_info["content"])
                    
                    prompt = (
                        f"You are a precise text editor. Return ONLY the updated file content.\n"
                        f"Content:\n{task_info['content']}\n"
                        f"Change '{task_info['anchor']}' to '{task_info['replacement']}'.\n"
                        f"Do not include any explanations or Markdown unless using a code block."
                    )
                    
                    def action_callback():
                        resp = get_model_response(model, prompt)
                        file_path.write_text(apply_edit(resp))
                        return 1, "success"

                    gate_cmd = task_info["gate_cmd"].format(file=str(file_path))
                    cell_id = f"{model}-{task_id}-t{trial}"
                    cell = gated_runner.Cell(
                        cell_id=cell_id,
                        objective=task_info["desc"],
                        brief="Measurement trial",
                        workspace=str(root),
                        gate=gated_runner.Gate(command=["sh", "-c", gate_cmd], expect="OK")
                    )

                    record = gated_runner.run_invocation(
                        cell=cell, harness="measurement-harness", model=model,
                        action_callback=action_callback, artifact_path=file_path,
                        storage_dir=storage_dir
                    )
                    
                    results.append({
                        "model": model, 
                        "task": task_id, 
                        "trial": trial,
                        "verdict": record.gate_verdict, 
                        "drift": record.artifact_hash_changed,
                        "pre_temps": pre_temps
                    })
                    print(f"{model[:12]:<12} | {task_id:<12} | T{trial} | {record.gate_verdict:<10} | {record.artifact_hash_changed!s:<6}")
        
        post_temps = get_gpu_temps()
        print(f"Model {model} finished. GPU Temps: Pre {pre_temps} -> Post {post_temps}")

    print("\n--- Grid session complete ---")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Run a specific model only")
    args = parser.parse_args()
    run_measurement(model_filter=args.model)

