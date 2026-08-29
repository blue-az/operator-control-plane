import subprocess
import tempfile
import time
from pathlib import Path

import gated_runner

MODELS = ["gemma4:31b", "gemma4:26b"]
TASKS = {
    "text_edit": {
        "content": "The quick brown fox jumps over the lazy dog.",
        "anchor": "the lazy dog",
        "replacement": "the active dog",
        "gate_cmd": "grep -q 'the active dog' {file} && echo 'OK'",
    },
    "py_fix": {
        "content": "def hello()\n    print('hi')",
        "anchor": "def hello()",
        "replacement": "def hello():",
        "gate_cmd": "python3 -c \"with open('{file}', 'r') as f: exec(f.read())\" && echo 'OK'",
    }
}

def get_gpu_temps():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, encoding="utf-8"
        )
        return [int(t.strip()) for t in result.stdout.strip().split("\n") if t.strip()]
    except Exception:
        return []

def call_llm(model, prompt):
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e!s}"

def run_validation():
    print("--- GPU Cable Swap Validation Run ---")
    
    pre_temps = get_gpu_temps()
    print(f"Initial GPU Temps: {pre_temps}")
    
    results = []

    for model in MODELS:
        for task_id, task_info in TASKS.items():
            with tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                file_path = root / "target.txt"
                file_path.write_text(task_info["content"])
                
                prompt = f"Change '{task_info['anchor']}' to '{task_info['replacement']}' in this content:\n{task_info['content']}\nReturn only the new content."
                
                def action_callback():
                    resp = call_llm(model, prompt)
                    file_path.write_text(resp)
                    return 1, "success"

                gate_cmd = task_info["gate_cmd"].format(file=str(file_path))
                cell = gated_runner.Cell(
                    cell_id=f"val-{model}-{task_id}",
                    objective="Validation",
                    brief="Cable swap check",
                    workspace=str(root),
                    gate=gated_runner.Gate(command=["sh", "-c", gate_cmd], expect="OK")
                )

                start = time.time()
                record = gated_runner.run_invocation(
                    cell=cell, harness="val", model=model,
                    action_callback=action_callback, artifact_path=file_path
                )
                duration = time.time() - start
                results.append((model, task_id, record.gate_verdict, duration))
                print(f"{model:<12} | {task_id:<12} | {record.gate_verdict:<10} | {duration:.2f}s")

    post_temps = get_gpu_temps()
    print(f"Final GPU Temps:   {post_temps}")
    print(f"Delta: { [post - pre for post, pre in zip(post_temps, pre_temps)] if len(post_temps)==len(pre_temps) else 'N/A'}")

if __name__ == "__main__":
    run_validation()
