"""Locate the dense-model VRAM-cap timeout boundary for gemma4:31b -- v2.

v1 died from a genuine kernel OOM kill mid-sweep (confirmed via dmesg/journalctl,
not a compute timeout) with no explicit eviction between num_gpu levels. This
version explicitly unloads the previous derived model (keep_alive:0) before
loading the next, and checks free system RAM before each trial, aborting with
a clear message rather than risking another OOM if headroom looks thin.

Retests num_gpu=50 cleanly first (v1's trial 2 "timeout" there is now suspect
-- it may have been the OOM killing the model mid-generation, not genuine
compute-bound slowness), then proceeds to num_gpu=45 if warranted.
"""
import sys, time, subprocess, yaml, json, shutil
sys.path.insert(0, '/home/blueaz/operator-control-plane/evals/local_lane_ladder')
from fixtures import build_fixture, hash_tree, cleanup_fixture
from grading import grade
from runner import parse_trajectory, ensure_pinned_model, measure_tok_s, PI_BIN

task = yaml.safe_load(open('/home/blueaz/operator-control-plane/evals/local_lane_ladder/tasks/csv_summarize_repair.yaml'))
prompt = task['prompts']['L2']

MIN_AVAILABLE_GB = 12.0  # abort a level rather than risk OOM below this

def free_ram_gb():
    out = subprocess.run(["free", "-b"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            return int(parts[6]) / 1e9  # "available" column
    return None

def unload_model(tag):
    subprocess.run(
        ["curl", "-s", "-X", "POST", "http://127.0.0.1:11434/api/generate",
         "-d", json.dumps({"model": tag, "keep_alive": 0})],
        capture_output=True, text=True,
    )

NUM_GPU_LEVELS = [50, 45]  # re-test 50 cleanly, then proceed to 45
results = []
prev_tag = None

for num_gpu in NUM_GPU_LEVELS:
    print(f"\n=== num_gpu={num_gpu} ===", flush=True)

    if prev_tag is not None:
        print(f"  unloading previous model {prev_tag}...", flush=True)
        unload_model(prev_tag)
        time.sleep(5)

    avail = free_ram_gb()
    print(f"  free RAM available: {avail:.1f} GB", flush=True)
    if avail < MIN_AVAILABLE_GB:
        print(f"  ABORTING this level: available RAM ({avail:.1f} GB) below safety floor ({MIN_AVAILABLE_GB} GB)", flush=True)
        break

    dispatch_model = ensure_pinned_model('gemma4:31b', 16384, 0.8, num_gpu=num_gpu)
    prev_tag = dispatch_model
    print("dispatch_model:", dispatch_model, flush=True)

    tok_s_probe = measure_tok_s(dispatch_model)
    print("tok_s_probe:", tok_s_probe, flush=True)

    ps = json.loads(subprocess.run(["curl", "-s", "http://127.0.0.1:11434/api/ps"], capture_output=True, text=True).stdout)
    size_vram = ps["models"][0]["size_vram"] if ps.get("models") else None
    print("size_vram_GiB:", round(size_vram / 1e9, 2) if size_vram else None, flush=True)

    for trial in range(1, 3):
        avail = free_ram_gb()
        if avail < MIN_AVAILABLE_GB:
            print(f"  ABORTING trial {trial}: available RAM ({avail:.1f} GB) below safety floor", flush=True)
            break
        fixture_root = build_fixture(task.get('files', {}), prefix=f'gemma31-boundary2-gpu{num_gpu}')
        manifest = hash_tree(fixture_root)
        argv = [PI_BIN, '--provider', 'ollama', '--model', dispatch_model, '--mode', 'json', '--print',
                '--thinking', 'off', '--', prompt]
        start = time.monotonic()
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, timeout=650, cwd=str(fixture_root))
            wall_clock = time.monotonic() - start
            grade_result = grade(task['postcondition'], fixture_root, completed.stdout, manifest)
            traj = parse_trajectory(completed.stdout)
            row = {
                "num_gpu": num_gpu, "trial": trial, "passed": grade_result.passed,
                "wall_clock_s": round(wall_clock, 1), "timed_out": False,
                "completion_tokens": traj.get("completion_tokens"), "n_calls": traj.get("n_calls"),
                "tok_s_probe": tok_s_probe.get("tok_s") if tok_s_probe else None,
                "size_vram_GiB": round(size_vram / 1e9, 2) if size_vram else None,
                "free_ram_gb_before": round(avail, 1),
            }
        except subprocess.TimeoutExpired:
            wall_clock = time.monotonic() - start
            row = {
                "num_gpu": num_gpu, "trial": trial, "passed": False,
                "wall_clock_s": round(wall_clock, 1), "timed_out": True,
                "completion_tokens": None, "n_calls": None,
                "tok_s_probe": tok_s_probe.get("tok_s") if tok_s_probe else None,
                "size_vram_GiB": round(size_vram / 1e9, 2) if size_vram else None,
                "free_ram_gb_before": round(avail, 1),
            }
        finally:
            cleanup_fixture(fixture_root)
        print(f"  trial {trial}: passed={row['passed']} timed_out={row['timed_out']} "
              f"wall_clock_s={row['wall_clock_s']} tokens={row['completion_tokens']} calls={row['n_calls']} "
              f"(free RAM before: {row['free_ram_gb_before']} GB)", flush=True)
        results.append(row)

with open('/tmp/gemma31_boundary_sweep2_results.json', 'w') as f:
    json.dump(results, f, indent=2)

if prev_tag is not None:
    unload_model(prev_tag)

print("\nSWEEP2_DONE", flush=True)
