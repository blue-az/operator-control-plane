#!/usr/bin/env python3
"""
Pass 3: replicate each arm N times so the truncation estimate has an error bar.

Passes 1 and 2 established the design but ran n=1 per arm. Cells demonstrably
flip between runs -- three pass1<->pass2 label disagreements, and 4 of 17 cells
did not reproduce their historical failure at all -- so a single flip cannot be
distinguished from noise and neither 41% nor 31% is a defensible point estimate.
PILOT_CONFOUND_FINDINGS.md names repeating each arm ~5x as the highest-value
follow-up. This is that.

Two arms, not three:

  A1  steps 0, timeout 120   faithful pre-890d595/pre-d5eea34 harness
  B   steps 4, timeout 600   both fixes

A2 (timeout fix only) is dropped deliberately. Pass 2 attributed zero cells to
the timeout and observed no read timeout firing at all under the 120s config,
and that is structural rather than luck: runner.py never passed
--continue-steps, so the historical ladder was single-dispatch, and one
dispatch rarely reaches 120s of generation. Spending a third of the compute
re-confirming a zero is not worth it here.

Reporting per cell: pass RATE out of N under each arm, not a binary flip. The
per-cell effect is rate_B - rate_A1. That is robust to the single-flip noise
that made passes 1 and 2 disagree.

Machine-dependent: all decode-rate sensitive. z13 only.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import yaml  # noqa: E402
from fixtures import build_fixture  # noqa: E402
from grading import grade  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
OPR_BIN = REPO_ROOT / "opr"
TASKS_DIR = Path(__file__).parent / "tasks"
OUTDIR = Path("/home/blueaz/Documents/local/routing/pilot_confound_pass3")
OLD_TIMEOUT = 120
MAX_WALL = 900


def load_tasks_raw():
    return [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted(TASKS_DIR.glob("*.yaml"))]


def run_arm(task, level, model, arm, config_path, tag):
    prompt = task["prompts"][level]
    fixture_root = build_fixture(
        task.get("files", {}), prefix=f"p3-{task['task_id']}-{level}", remove=task.get("remove")
    )
    cmd = [
        str(OPR_BIN), prompt, "--model", model,
        "--workspace", str(fixture_root),
        "--allow-write", "--allow-run", "--no-govern", "--no-bn", "--dangerous",
    ]
    if arm == "A1":
        cmd += ["--config", str(config_path)]  # 120s timeout, no --continue-steps
    else:
        cmd += ["--continue-steps", "4"]

    start = time.monotonic()
    try:
        c = subprocess.run(cmd, capture_output=True, text=True, timeout=MAX_WALL)
        out, err, rc = c.stdout, c.stderr, c.returncode
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err, rc = "TIMEOUT", None
    wall = time.monotonic() - start
    g = grade(task["postcondition"], fixture_root, out)
    (OUTDIR / f"{tag}.raw.txt").write_text(
        f"# {' '.join(cmd)}\n# rc={rc} wall={wall:.1f}s passed={g.passed}\n# {g.detail}\n\n{out}\n--STDERR--\n{err}\n",
        encoding="utf-8",
    )
    return {
        "passed": g.passed, "wall_s": round(wall, 1),
        "tool_calls": out.count("Model requests tool call"),
        "read_timeout": "Read timed out" in out,
    }


def main():
    reps = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    OUTDIR.mkdir(parents=True, exist_ok=True)
    cfg = OUTDIR / "old_harness_timeout.yaml"
    cfg.write_text(f"local:\n  request_timeout: {OLD_TIMEOUT}\n", encoding="utf-8")

    sample = json.loads(Path(sys.argv[1]).read_text())
    tasks = {t["task_id"]: t for t in load_tasks_raw()}
    results = []

    for i, cell in enumerate(sample, 1):
        t = tasks[cell["task_id"]]
        base = f"{cell['model'].replace(':', '-')}-{cell['task_id']}-{cell['level']}"
        row = {**cell, "A1": [], "B": []}
        for arm in ("A1", "B"):
            for r in range(1, reps + 1):
                res = run_arm(t, cell["level"], cell["model"], arm, cfg, f"{base}-{arm}-r{r}")
                row[arm].append(res)
        a1_rate = sum(x["passed"] for x in row["A1"]) / reps
        b_rate = sum(x["passed"] for x in row["B"]) / reps
        row["A1_pass_rate"], row["B_pass_rate"] = a1_rate, b_rate
        row["effect"] = round(b_rate - a1_rate, 2)
        results.append(row)
        print(
            f"[{i}/{len(sample)}] {cell['model']:<18} {cell['task_id']:<28} {cell['level']} "
            f"A1={a1_rate:.1f} B={b_rate:.1f} effect={row['effect']:+.1f}",
            flush=True,
        )
        (OUTDIR / "results.json").write_text(json.dumps(results, indent=2))

    print(f"\n--- summary (n={reps} per arm) ---")
    tot_a1 = sum(r["A1_pass_rate"] for r in results) / len(results)
    tot_b = sum(r["B_pass_rate"] for r in results) / len(results)
    print(f"mean pass rate  A1 (old harness) = {tot_a1:.3f}")
    print(f"mean pass rate  B  (both fixes)  = {tot_b:.3f}")
    print(f"mean effect (B - A1)             = {tot_b - tot_a1:+.3f}")
    never = [r for r in results if r["A1_pass_rate"] == 0 and r["B_pass_rate"] == 0]
    always = [r for r in results if r["A1_pass_rate"] == 1.0]
    print(f"cells failing under BOTH arms every rep (genuine model failure): {len(never)}/{len(results)}")
    print(f"cells passing under the OLD harness every rep (historical record unreliable): {len(always)}/{len(results)}")


if __name__ == "__main__":
    main()
