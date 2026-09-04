"""Generalization check for gemma26-brevity-ablation-001: does the brevity
instruction's effect hold on a second, more-verbose task (strict-log-format),
and does it also help gemma4:31b's smaller-but-real verbosity tax on the
original task (csv-summarize-repair)?

Three new cells, n=6 each, interleaved:
  A: gemma4:26b + brevity, strict-log-format   (task generalization)
  B: qwen3.8:27b + brevity, strict-log-format  (control for A)
  C: gemma4:31b + brevity, csv-summarize-repair (model generalization;
     control is the EXISTING qwen3.8:27b+brevity csv-summarize-repair cell
     from gemma26-brevity-ablation-001, not re-run)
"""
import sys
import time
import random
import subprocess
import yaml
from pathlib import Path

sys.path.insert(0, "/home/blueaz/operator-control-plane/evals/local_lane_ladder")
from fixtures import build_fixture, hash_tree, cleanup_fixture  # noqa: E402
from grading import grade  # noqa: E402
from runner import (  # noqa: E402
    ensure_pinned_model, parse_trajectory, measure_tok_s, write_trace,
    PI_BIN, MAX_WALL_CLOCK_SECONDS,
)

TASKS_DIR = Path("/home/blueaz/operator-control-plane/evals/local_lane_ladder/tasks")
tasks = {
    "csv-summarize-repair": yaml.safe_load((TASKS_DIR / "csv_summarize_repair.yaml").read_text()),
    "strict-log-format": yaml.safe_load((TASKS_DIR / "strict_log_format.yaml").read_text()),
}

BREVITY_ADDENDUM = (
    "\n\nBe terse. Do not narrate what you are about to do or restate the task "
    "back. Do not explain your reasoning in prose. Make the edit, run the "
    "verification command once, and stop as soon as it passes. No summary at "
    "the end."
)

SAMPLING = {"num_ctx": 16384, "temperature": 0.8, "think": "off"}
FIXTURE_DIR = Path("/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/gemma26-brevity-ablation-001")
TRACE_DIR = FIXTURE_DIR / "traces"
TRACE_DIR.mkdir(parents=True, exist_ok=True)

CELLS = (
    [("gemma4:26b", "strict-log-format", i) for i in range(1, 7)]
    + [("qwen3.8:27b", "strict-log-format", i) for i in range(1, 7)]
    + [("gemma4:31b", "csv-summarize-repair", i) for i in range(1, 7)]
)
random.seed(20260829)
random.shuffle(CELLS)
print("Run order:", CELLS, flush=True)

for model, task_id, trial_idx in CELLS:
    task = tasks[task_id]
    label = f"brevity__{model.replace(':', '-')}__{task_id}__t{trial_idx}"
    print(f"=== {label} ===", flush=True)
    prompt = task["prompts"]["L2"] + BREVITY_ADDENDUM
    fixture_root = build_fixture(task.get("files", {}), prefix=f"{task_id}-brevity", remove=task.get("remove"))
    manifest = hash_tree(fixture_root)
    dispatch_model = ensure_pinned_model(model, SAMPLING["num_ctx"], SAMPLING["temperature"])
    argv = [PI_BIN, "--provider", "ollama", "--model", dispatch_model, "--mode", "json", "--print",
            "--thinking", "off", "--", prompt]
    start = time.monotonic()
    try:
        completed = subprocess.run(
            argv, capture_output=True, text=True, timeout=MAX_WALL_CLOCK_SECONDS,
            cwd=str(fixture_root),
        )
        wall_clock = time.monotonic() - start
        grade_result = grade(task["postcondition"], fixture_root, completed.stdout, manifest)
        traj = parse_trajectory(completed.stdout)
        tok_s_probe = measure_tok_s(dispatch_model)
        record = {
            "task_id": task_id, "level": "L2-brevity", "model": model, "trial": trial_idx,
            "machine": "desktop", "passed": grade_result.passed, "detail": grade_result.detail,
            "check_score": round(grade_result.score, 3),
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in grade_result.checks],
            "wall_clock_s": round(wall_clock, 1), "returncode": completed.returncode,
            "tok_s": tok_s_probe.get("tok_s") if tok_s_probe else None, "tok_s_probe": tok_s_probe,
            "n_calls": traj.get("n_calls"), "completion_tokens": traj.get("completion_tokens"),
        }
        write_trace(
            TRACE_DIR, task_id + "-brevity", "L2", model, trial_idx,
            argv=argv, prompt=prompt, stdout=completed.stdout, stderr=completed.stderr,
            record=record, timed_out=False,
        )
        print(f"  passed={record['passed']} wall_clock_s={record['wall_clock_s']} "
              f"n_calls={record['n_calls']} completion_tokens={record['completion_tokens']}", flush=True)
    finally:
        cleanup_fixture(fixture_root)

print("GENERALIZATION_DONE", flush=True)
