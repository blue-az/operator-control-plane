import glob
import json
from collections import defaultdict
from pathlib import Path


def analyze_results():
    results_dir = Path("./measurement_results")
    if not results_dir.exists():
        print("No results directory found.")
        return

    # Group results by (model, task)
    grid = defaultdict(list)
    
    files = list(results_dir.glob("outcome-*.json"))
    if not files:
        print("No outcome records found.")
        return

    for f in files:
        with open(f, "r") as reader:
            data = json.load(reader)
            model = data["model"]
            # task_id is formatted as model-task_id-tN
            task_id = data["task_id"].replace(f"{model}-", "").split("-t")[0]
            grid[(model, task_id)].append(data["gate_verdict"])

    # Print Grid
    models = sorted(list(set(m for m, t in grid.keys())))
    tasks = sorted(list(set(t for m, t in grid.keys())))

    print(f"{'Model':<15} | {'Task':<15} | {'Pass Rate':<12} | {'Sample'}")
    print("-" * 60)

    for model in models:
        for task in tasks:
            verdicts = grid.get((model, task), [])
            if not verdicts:
                print(f"{model:<15} | {task:<15} | {'N/A':<12} | -")
                continue
            
            pass_rate = sum(1 for v in verdicts if v == "pass") / len(verdicts)
            v_str = ",".join([v[0].upper() for v in verdicts]) # P, F, E
            print(f"{model:<15} | {task:<15} | {pass_rate:>10.2%} | {v_str}")

if __name__ == "__main__":
    analyze_results()
