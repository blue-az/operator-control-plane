import hashlib
import json
import subprocess
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import gated_runner

# --- Models to Test ---
MODELS = ["gemma4:31b", "gemma4:26b"]

# --- R3 Primitive ---
def anchored_replace(content: str, anchor: str, replacement: str) -> str:
    """The R3 Primitive: Strict anchored replacement."""
    if anchor not in content:
        raise ValueError("Anchor not found")
    if content.count(anchor) > 1:
        raise ValueError("Anchor not unique")
    return content.replace(anchor, replacement)

# --- Tasks ---
# Tasks specifically designed to be "hard" for raw writes (longer files, mid-file edits)
TASKS = [
    {
        "id": "mid_file_edit",
        "content": "Line 1\nLine 2\nTarget: Change me\nLine 4\nLine 5",
        "anchor": "Target: Change me",
        "replacement": "Target: I am changed",
        "gate_cmd": "grep -q 'Target: I am changed' {file} && echo 'OK'"
    },
    {
        "id": "syntax_fix",
        "content": "def fix_me()\n    print('hi')",
        "anchor": "def fix_me()",
        "replacement": "def fix_me():",
        "gate_cmd": "python3 -c \"with open('{file}', 'r') as f: exec(f.read())\" && echo 'OK'"
    }
]

def call_llm(model, prompt):
    try:
        result = subprocess.run(
            ["ollama", "run", model, prompt],
            capture_output=True, text=True, encoding="utf-8", timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"Error: {e!s}"

def run_trial(model, task, mode):
    """
    mode 'raw': Model is asked to rewrite the file.
    mode 'anchored': Model is asked to use the REPLACE(anchor, replacement) tool.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        file_path = root / "target.txt"
        file_path.write_text(task["content"])
        
        if mode == 'raw':
            prompt = (
                f"Rewrite the following file. Change '{task['anchor']}' to '{task['replacement']}'.\n"
                f"Return ONLY the new file content.\n\nFile:\n{task['content']}"
            )
        else:
            prompt = (
                f"You have a tool: REPLACE(anchor, replacement).\n"
                f"File content:\n{task['content']}\n"
                f"Goal: Change '{task['anchor']}' to '{task['replacement']}'.\n"
                f"Return ONLY the tool call, e.g., REPLACE('the anchor', 'the replacement')"
            )

        def action_callback():
            response = call_llm(model, prompt)
            
            if mode == 'raw':
                # In raw mode, the response is the new content
                file_path.write_text(response)
                return 1, "success"
            else:
                # in anchored mode, we parse the tool call
                if "REPLACE" in response:
                    try:
                        # Naive parse: REPLACE('...', '...')
                        parts = response.split("REPLACE(")[1].split(")")[0].split(",", 1)
                        anchor = parts[0].strip().strip("'\"")
                        repl = parts[1].strip().strip("'\"")
                        
                        current_text = file_path.read_text()
                        new_text = anchored_replace(current_text, anchor, repl)
                        file_path.write_text(new_text)
                        return 1, "success"
                    except Exception as e:
                        return 1, f"tool_error: {e!s}"
                else:
                    return 1, "no_tool_call"

        gate_cmd = task["gate_cmd"].format(file=str(file_path))
        cell = gated_runner.Cell(
            cell_id=f"{model}-{task['id']}-{mode}",
            objective="R3 Test",
            brief="...",
            workspace=str(root),
            gate=gated_runner.Gate(command=["sh", "-c", gate_cmd], expect="OK")
        )

        return gated_runner.run_invocation(
            cell=cell, harness="r3-exp", model=model,
            action_callback=action_callback, artifact_path=file_path
        )

if __name__ == "__main__":
    print(f"{'Model':<12} | {'Task':<15} | {'Mode':<10} | {'Verdict':<10} | {'Hash':<6}")
    print("-" * 60)
    
    for model in MODELS:
        for task in TASKS:
            for mode in ['raw', 'anchored']:
                res = run_trial(model, task, mode)
                print(f"{model:<12} | {task['id']:<15} | {mode:<10} | {res.gate_verdict:<10} | {res.artifact_hash_changed!s:<6}")
