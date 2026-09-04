"""One-off ablation: does telling gemma4:26b to be terse close the wall-clock
gap with qwen3.8:27b on csv-summarize-repair, without losing correctness?

Reuses the harness's own fixture builder, model pinning, trajectory parser,
and grader so this is directly comparable to the e9-pi-rerun trial-1 baseline
(6 turns, 3659 completion tokens, PASS).
"""
import sys
import time
import subprocess
import yaml
from pathlib import Path

sys.path.insert(0, "/home/blueaz/operator-control-plane/evals/local_lane_ladder")
from fixtures import build_fixture, hash_tree, cleanup_fixture  # noqa: E402
from grading import grade  # noqa: E402
from runner import (  # noqa: E402
    ensure_pinned_model, parse_trajectory, PI_BIN, MAX_WALL_CLOCK_SECONDS,
)

TASK_PATH = Path("/home/blueaz/operator-control-plane/evals/local_lane_ladder/tasks/csv_summarize_repair.yaml")
task = yaml.safe_load(TASK_PATH.read_text())

BREVITY_ADDENDUM = (
    "\n\nBe terse. Do not narrate what you are about to do or restate the task "
    "back. Do not explain your reasoning in prose. Make the edit, run the "
    "verification command once, and stop as soon as it passes. No summary at "
    "the end."
)

base_prompt = task["prompts"]["L2"]
prompt = base_prompt + BREVITY_ADDENDUM

model = "gemma4:26b"
sampling = {"num_ctx": 16384, "temperature": 0.8, "think": "off"}

fixture_root = build_fixture(task.get("files", {}), prefix=f"{task['task_id']}-brevity", remove=task.get("remove"))
manifest = hash_tree(fixture_root)

dispatch_model = ensure_pinned_model(model, sampling["num_ctx"], sampling["temperature"])
print(f"dispatch_model: {dispatch_model}")
print(f"fixture_root: {fixture_root}")

argv = [PI_BIN, "--provider", "ollama", "--model", dispatch_model, "--mode", "json", "--print",
        "--thinking", "off", "--", prompt]

start = time.monotonic()
completed = subprocess.run(
    argv, capture_output=True, text=True, timeout=MAX_WALL_CLOCK_SECONDS,
    cwd=str(fixture_root),
)
wall_clock = time.monotonic() - start

grade_result = grade(task["postcondition"], fixture_root, completed.stdout, manifest)
traj = parse_trajectory(completed.stdout)

print()
print("=== RESULT (brevity-instructed gemma4:26b) ===")
print(f"passed: {grade_result.passed}  detail: {getattr(grade_result, 'detail', '')}")
print(f"wall_clock_s: {wall_clock:.1f}")
print(f"n_calls: {traj.get('n_calls')}")
print(f"completion_tokens: {traj.get('completion_tokens')}")
print(f"think_chars: {traj.get('think_chars')}")

print()
print("=== BASELINE (e9-pi-rerun trial 1, default prompt) ===")
print("passed: True  wall_clock_s: 21.6")
print("n_calls (turns): 6  completion_tokens: 3659")

cleanup_fixture(fixture_root)
