import subprocess
from pathlib import Path
import tempfile
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

# --- R3 Primitive ---
def anchored_replace(content: str, anchor: str, replacement: str) -> str:
    """Strict anchored replacement logic (Harness-side)."""
    if anchor not in content:
        raise ValueError("anchor not found")
    if content.count(anchor) > 1:
        raise ValueError("anchor not unique")
    return content.replace(anchor, replacement)


class ModelTimeout(Exception):
    """Raised when the seat does not answer within the trial timeout."""

def get_model_response(model, prompt):
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=20
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired as exc:
        raise ModelTimeout from exc

def apply_raw_edit(response):
    if "```" in response:
        parts = response.split("```")
        for i in range(1, len(parts), 2):
            block = parts[i]
            lines = block.splitlines()
            if lines:
                if lines[0].strip() in ["python", "yaml", "text", "json", "markdown"]:
                    return "\n".join(lines[1:])
                return "\n".join(lines)
    return response

def run_measurement_grid(mode="raw", trials=3):
    if mode not in {"raw", "harness-r3"}:
        raise ValueError(f"unsupported measurement mode: {mode}")
    storage_dir = Path(f"./measurement_results_{mode}")
    storage_dir.mkdir(exist_ok=True)
    results = []

    print(f"Starting {mode.upper()} grid: {len(MODELS)} models x {len(TASKS)} tasks x {trials} trials")
    print("-" * 80)

    for model in MODELS:
        for task_id, task_info in TASKS.items():
            for trial in range(1, trials + 1):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    file_path = root / "target.txt"
                    file_path.write_text(task_info["content"])
                    
                    if mode == "raw":
                        prompt = (
                            f"You are a precise text editor. Return ONLY the updated file content.\n"
                            f"Content:\n{task_info['content']}\n"
                            f"Change '{task_info['anchor']}' to '{task_info['replacement']}'."
                        )
                        def action_callback():
                            try:
                                resp = get_model_response(model, prompt)
                            except ModelTimeout:
                                return 0, "timeout"
                            file_path.write_text(apply_raw_edit(resp))
                            return 1, "success"
                    else:  # harness-r3: the model is completely off the write path
                        def action_callback():
                            try:
                                current_text = file_path.read_text()
                                updated_text = anchored_replace(
                                    current_text,
                                    task_info["anchor"],
                                    task_info["replacement"],
                                )
                                file_path.write_text(updated_text)
                                return 1, "harness-r3: applied REPLACE"
                            except ValueError as exc:
                                return 1, f"harness-r3: rejected REPLACE ({exc})"

                    gate_cmd = task_info["gate_cmd"].format(file=str(file_path))
                    cell = gated_runner.Cell(
                        cell_id=f"{model}-{task_id}-t{trial}-{mode}",
                        objective=task_info["desc"],
                        brief="R3 Contrast trial",
                        workspace=str(root),
                        gate=gated_runner.Gate(command=["sh", "-c", gate_cmd], expect="OK")
                    )

                    record = gated_runner.run_invocation(
                        cell=cell, harness=f"r3-grid-{mode}", model=model,
                        action_callback=action_callback, artifact_path=file_path,
                        storage_dir=storage_dir
                    )
                    
                    results.append({
                        "model": model, "task": task_id, "trial": trial,
                        "verdict": record.gate_verdict, "drift": record.artifact_hash_changed
                    })
                    print(f"{model[:12]:<12} | {task_id:<12} | {mode:<8} | {record.gate_verdict:<10} | {str(record.artifact_hash_changed):<6}")

    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", help="Run a specific model to avoid timeouts")
    parser.add_argument("--mode", choices=["raw", "harness-r3"], help="Run a specific mode")
    parser.add_argument("--trials", type=int, default=3, help="Trials per model/task cell")
    args = parser.parse_args()

    if args.model:
        m = args.model
        # Override global MODELS list
        MODELS[:] = [m]
        
        modes = [args.mode] if args.mode else ["raw", "harness-r3"]
        run_results = {}
        for mode in modes:
            run_results[mode] = run_measurement_grid(mode=mode, trials=args.trials)
    else:
        run_results = {
            "raw": run_measurement_grid(mode="raw", trials=args.trials),
            "harness-r3": run_measurement_grid(mode="harness-r3", trials=args.trials),
        }
        
    print("\n--- Final Contrast Summary ---")
    denominator = len(TASKS) * args.trials
    for model in MODELS:
        fields = []
        for mode, label in (("raw", "Raw"), ("harness-r3", "Harness-R3")):
            if mode in run_results:
                passed = sum(
                    1
                    for result in run_results[mode]
                    if result["model"] == model and result["verdict"] == "pass"
                )
                fields.append(f"{label} Pass: {passed}/{denominator}")
        print(f"{model:<15} | " + " | ".join(fields))
