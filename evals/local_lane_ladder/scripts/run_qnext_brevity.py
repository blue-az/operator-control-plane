import sys, time, subprocess, yaml
from pathlib import Path
sys.path.insert(0, '/home/blueaz/operator-control-plane/evals/local_lane_ladder')
from fixtures import build_fixture, hash_tree, cleanup_fixture
from grading import grade
from runner import parse_trajectory, ensure_pinned_model, measure_tok_s, write_trace, PI_BIN

task = yaml.safe_load(Path('/home/blueaz/operator-control-plane/evals/local_lane_ladder/tasks/strict_log_format.yaml').read_text())

BREVITY_ADDENDUM = (
    "\n\nBe terse. Do not narrate what you are about to do or restate the task "
    "back. Do not explain your reasoning in prose. Make the edit, run the "
    "verification command once, and stop as soon as it passes. No summary at "
    "the end."
)

TRACE_DIR = Path('/home/blueaz/operator-control-plane/evals/local_lane_ladder/fixtures/qwen3next-brevity-001/traces')
model = 'qwen3-next:latest'

for trial_idx in range(1, 7):
    label = f"brevity__qwen3-next__t{trial_idx}"
    print(f"=== {label} ===", flush=True)
    prompt = task['prompts']['L2'] + BREVITY_ADDENDUM
    fixture_root = build_fixture(task.get('files', {}), prefix='strict-log-format-qnext-brevity')
    manifest = hash_tree(fixture_root)
    dispatch_model = ensure_pinned_model(model, 16384, 0.8)
    argv = [PI_BIN, '--provider', 'ollama', '--model', dispatch_model, '--mode', 'json', '--print',
            '--thinking', 'off', '--', prompt]
    start = time.monotonic()
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=600, cwd=str(fixture_root))
        wall_clock = time.monotonic() - start
        grade_result = grade(task['postcondition'], fixture_root, completed.stdout, manifest)
        traj = parse_trajectory(completed.stdout)
        tok_s_probe = measure_tok_s(dispatch_model)
        record = {
            "task_id": task['task_id'], "level": "L2-brevity", "model": model, "trial": trial_idx,
            "machine": "desktop", "passed": grade_result.passed, "detail": grade_result.detail,
            "check_score": round(grade_result.score, 3),
            "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in grade_result.checks],
            "wall_clock_s": round(wall_clock, 1), "returncode": completed.returncode,
            "tok_s": tok_s_probe.get("tok_s") if tok_s_probe else None, "tok_s_probe": tok_s_probe,
            "n_calls": traj.get("n_calls"), "completion_tokens": traj.get("completion_tokens"),
        }
        write_trace(
            TRACE_DIR, task['task_id'] + "-brevity", "L2", model, trial_idx,
            argv=argv, prompt=prompt, stdout=completed.stdout, stderr=completed.stderr,
            record=record, timed_out=False,
        )
        print(f"  passed={record['passed']} wall_clock_s={record['wall_clock_s']} "
              f"n_calls={record['n_calls']} completion_tokens={record['completion_tokens']}", flush=True)
    finally:
        cleanup_fixture(fixture_root)

print("QNEXT_BREVITY_DONE", flush=True)
