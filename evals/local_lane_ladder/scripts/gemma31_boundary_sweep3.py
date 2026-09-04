"""Re-verify num_gpu=40 cleanly -- this is the point that anchors last
night's committed gemma31-vramcap-e9/FINDING.md (3/3 timeout, pre-eviction-fix).
v2 already showed 45 and 50 are BOTH clean once eviction is done properly,
directly against last night's expectation. This retests 40 with the same
safe methodology (explicit eviction, RAM floor check) before trusting
whether last night's finding still holds.
"""
import sys, time, subprocess, yaml, json
sys.path.insert(0, '/home/blueaz/operator-control-plane/evals/local_lane_ladder')
from fixtures import build_fixture, hash_tree, cleanup_fixture
from grading import grade
from runner import parse_trajectory, ensure_pinned_model, measure_tok_s, PI_BIN

task = yaml.safe_load(open('/home/blueaz/operator-control-plane/evals/local_lane_ladder/tasks/csv_summarize_repair.yaml'))
prompt = task['prompts']['L2']

MIN_AVAILABLE_GB = 10.0

def free_ram_gb():
    out = subprocess.run(["free", "-b"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("Mem:"):
            return int(line.split()[6]) / 1e9
    return None

def unload_model(tag):
    subprocess.run(["curl", "-s", "-X", "POST", "http://127.0.0.1:11434/api/generate",
                    "-d", json.dumps({"model": tag, "keep_alive": 0})], capture_output=True, text=True)

num_gpu = 40
print(f"\n=== num_gpu={num_gpu} (re-verify) ===", flush=True)
avail = free_ram_gb()
print(f"  free RAM available: {avail:.1f} GB", flush=True)

dispatch_model = ensure_pinned_model('gemma4:31b', 16384, 0.8, num_gpu=num_gpu)
print("dispatch_model:", dispatch_model, flush=True)

tok_s_probe = measure_tok_s(dispatch_model)
print("tok_s_probe:", tok_s_probe, flush=True)

ps = json.loads(subprocess.run(["curl", "-s", "http://127.0.0.1:11434/api/ps"], capture_output=True, text=True).stdout)
size_vram = ps["models"][0]["size_vram"] if ps.get("models") else None
print("size_vram_GiB:", round(size_vram / 1e9, 2) if size_vram else None, flush=True)

results = []
for trial in range(1, 4):
    avail = free_ram_gb()
    print(f"  free RAM before trial {trial}: {avail:.1f} GB", flush=True)
    if avail < MIN_AVAILABLE_GB:
        print(f"  ABORTING trial {trial}: available RAM below safety floor", flush=True)
        break
    fixture_root = build_fixture(task.get('files', {}), prefix=f'gemma31-boundary3-gpu{num_gpu}')
    manifest = hash_tree(fixture_root)
    argv = [PI_BIN, '--provider', 'ollama', '--model', dispatch_model, '--mode', 'json', '--print',
            '--thinking', 'off', '--', prompt]
    start = time.monotonic()
    try:
        completed = subprocess.run(argv, capture_output=True, text=True, timeout=650, cwd=str(fixture_root))
        wall_clock = time.monotonic() - start
        grade_result = grade(task['postcondition'], fixture_root, completed.stdout, manifest)
        traj = parse_trajectory(completed.stdout)
        row = {"trial": trial, "passed": grade_result.passed, "wall_clock_s": round(wall_clock, 1),
               "timed_out": False, "completion_tokens": traj.get("completion_tokens"), "n_calls": traj.get("n_calls")}
    except subprocess.TimeoutExpired:
        wall_clock = time.monotonic() - start
        row = {"trial": trial, "passed": False, "wall_clock_s": round(wall_clock, 1),
               "timed_out": True, "completion_tokens": None, "n_calls": None}
    finally:
        cleanup_fixture(fixture_root)
    print(f"  trial {trial}: passed={row['passed']} timed_out={row['timed_out']} "
          f"wall_clock_s={row['wall_clock_s']} tokens={row['completion_tokens']} calls={row['n_calls']}", flush=True)
    results.append(row)

with open('/tmp/gemma31_boundary_sweep3_results.json', 'w') as f:
    json.dump(results, f, indent=2)

unload_model(dispatch_model)
print("\nSWEEP3_DONE", flush=True)
