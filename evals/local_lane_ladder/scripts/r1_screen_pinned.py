import sys, time, subprocess, yaml
from pathlib import Path
sys.path.insert(0, '/home/blueaz/operator-control-plane/evals/local_lane_ladder')
from fixtures import build_fixture, hash_tree, cleanup_fixture
from grading import grade
from runner import parse_trajectory, ensure_pinned_model, PI_BIN

task = yaml.safe_load(Path('/home/blueaz/operator-control-plane/evals/local_lane_ladder/tasks/csv_summarize_repair.yaml').read_text())
prompt = task['prompts']['L2']
fixture_root = build_fixture(task.get('files', {}), prefix='csv-summarize-repair-r1-screen2')
manifest = hash_tree(fixture_root)
print('fixture:', fixture_root, flush=True)

dispatch_model = ensure_pinned_model('deepseek-r1:70b', 16384, 0.8)
print('dispatch_model:', dispatch_model, flush=True)

argv = [PI_BIN, '--provider', 'ollama', '--model', dispatch_model, '--mode', 'json', '--print', '--thinking', 'off', '--', prompt]
start = time.monotonic()
completed = subprocess.run(argv, capture_output=True, text=True, timeout=600, cwd=str(fixture_root))
wall_clock = time.monotonic() - start
grade_result = grade(task['postcondition'], fixture_root, completed.stdout, manifest)
traj = parse_trajectory(completed.stdout)
print(flush=True)
print('=== RESULT ===', flush=True)
print('passed:', grade_result.passed, grade_result.detail, flush=True)
print('wall_clock_s:', round(wall_clock,1), flush=True)
print('n_calls:', traj.get('n_calls'), 'completion_tokens:', traj.get('completion_tokens'), 'think_chars:', traj.get('think_chars'), flush=True)
print('returncode:', completed.returncode, flush=True)
if completed.returncode != 0:
    print('stderr tail:', completed.stderr[-1000:], flush=True)
cleanup_fixture(fixture_root)
