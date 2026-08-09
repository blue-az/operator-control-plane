#!/usr/bin/env python3
"""
Pass 2: add the missing arm that makes the confound pilot a real factorial.

Pass 1 (pilot_confound.py) varied --continue-steps only. Both of its arms inherited
the CURRENT local.request_timeout default of 600s from d5eea34, so neither reproduced
the harness that actually produced the historical negatives -- that harness had TWO
defaults: run_command as a terminal tool AND a hardcoded 120s read timeout. A cell
whose historical failure was timeout-driven therefore passed in pass 1's "old behavior"
arm, surfacing as pass->pass and leaving its cause unattributed.

This pass runs the missing arm:

  A1  steps 0, timeout 120   <- faithful pre-890d595/pre-d5eea34 harness   (THIS PASS)
  A2  steps 0, timeout 600   <- timeout fix only                           (pass 1)
  B   steps 4, timeout 600   <- both fixes                                 (pass 1)

Which decomposes each historical negative by mechanism:

  A1 fail, A2 pass          timeout-attributable
  A2 fail, B  pass          truncation-attributable
  A1 fail, B  fail          survives both fixes -> genuine-limit candidate
  A1 pass                   did not reproduce even under the faithful old harness
                            -> the historical record is unreliable for this cell

MUST run on the same machine as pass 1. The measured quantity is decode-rate dependent
(gemma4:31b is 21GB and runs partly on CPU here), so timeout results do not transfer
across hardware. Machine is recorded on every row for exactly this reason.
"""
import json
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import yaml  # noqa: E402
from fixtures import build_fixture  # noqa: E402
from grading import grade  # noqa: E402

TASKS_DIR = Path(__file__).parent / "tasks"
REPO_ROOT = Path(__file__).resolve().parents[2]
OPR_BIN = REPO_ROOT / "opr"
PASS1 = Path("/home/blueaz/Documents/local/routing/pilot_confound/results.json")
OUTDIR = Path("/home/blueaz/Documents/local/routing/pilot_confound_pass2")
OLD_TIMEOUT = 120
MAX_WALL = 300  # steps 0 with a 120s read timeout cannot legitimately exceed this


def load_tasks_raw():
    return [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted(TASKS_DIR.glob("*.yaml"))
    ]


def run_a1(task, level, model, config_path, tag):
    prompt = task["prompts"][level]
    fixture_root = build_fixture(
        task.get("files", {}),
        prefix=f"pilot2-{task['task_id']}-{level}",
        remove=task.get("remove"),
    )
    # No --continue-steps: pass 1 omitted the flag entirely for its steps-0 arm, and
    # this arm must differ from it in the timeout only.
    cmd = [
        str(OPR_BIN), prompt,
        "--model", model,
        "--workspace", str(fixture_root),
        "--allow-write", "--allow-run",
        "--no-govern", "--no-bn",
        "--dangerous",
        "--config", str(config_path),
    ]

    start = time.monotonic()
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=MAX_WALL)
        out, rc, err = completed.stdout, completed.returncode, completed.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err, rc = "TIMEOUT", None
    wall = time.monotonic() - start

    g = grade(task["postcondition"], fixture_root, out)
    (OUTDIR / f"{tag}.raw.txt").write_text(
        f"# cmd: {' '.join(cmd)}\n# rc={rc} wall={wall:.1f}s passed={g.passed}\n"
        f"# detail: {g.detail}\n\n--- STDOUT ---\n{out}\n--- STDERR ---\n{err}\n",
        encoding="utf-8",
    )
    return {
        "passed": g.passed,
        "detail": g.detail,
        "wall_s": round(wall, 1),
        "returncode": rc,
        "tool_calls": out.count("Model requests tool call"),
        "read_timeout": "Read timed out" in out,
        "repeat_halt": "repeated an already-handled tool call" in out
        or "repeated identical tool call" in out,
        "task_complete": "Task complete after" in out,
    }


def attribute(a1, a2, b):
    """Assign each historical negative to a mechanism. Order matters: the earliest
    fix that rescues the cell owns it."""
    if a1["passed"]:
        return "did_not_reproduce"
    if a2["passed"]:
        return "timeout"
    if b["passed"]:
        return "truncation"
    return "survives_both"


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    config_path = OUTDIR / "old_harness_timeout.yaml"
    config_path.write_text(f"local:\n  request_timeout: {OLD_TIMEOUT}\n", encoding="utf-8")

    sample = json.loads(Path(sys.argv[1]).read_text())
    pass1 = {(r["task_id"], r["level"], r["model"]): r for r in json.loads(PASS1.read_text())}
    tasks = {t["task_id"]: t for t in load_tasks_raw()}
    machine = platform.node()

    results = []
    for i, cell in enumerate(sample, 1):
        key = (cell["task_id"], cell["level"], cell["model"])
        if key not in pass1:
            print(f"[{i}/{len(sample)}] SKIP (no pass-1 row): {key}", flush=True)
            continue
        t = tasks[cell["task_id"]]
        tag = f"{cell['model'].replace(':', '-')}-{cell['task_id']}-{cell['level']}-A1-steps0-t120"
        a1 = run_a1(t, cell["level"], cell["model"], config_path, tag)
        a2, b = pass1[key]["A_steps0"], pass1[key]["B_steps4"]
        row = {
            **cell,
            "machine": machine,
            "A1_steps0_t120": a1,
            "A2_steps0_t600": a2,
            "B_steps4_t600": b,
            "attribution": attribute(a1, a2, b),
            "pass1_transition": pass1[key]["transition"],
        }
        results.append(row)
        print(
            f"[{i}/{len(sample)}] {cell['model']:<14} {cell['task_id']:<28} {cell['level']} "
            f"A1={'pass' if a1['passed'] else 'fail'} "
            f"({a1['wall_s']:.0f}s,to={a1['read_timeout']}) -> {row['attribution']}",
            flush=True,
        )
        (OUTDIR / "results_pass2.json").write_text(json.dumps(results, indent=2))

    c = Counter(r["attribution"] for r in results)
    print(f"\n--- attribution (machine={machine}, n={len(results)}) ---")
    for k, v in c.most_common():
        print(f"  {k:<20} {v}")
    harness = c["timeout"] + c["truncation"]
    reproduced = len(results) - c["did_not_reproduce"]
    if reproduced:
        print(
            f"\nharness-attributable among reproduced negatives: {harness}/{reproduced} "
            f"({100 * harness / reproduced:.0f}%)"
        )
    print(f"genuine-limit candidates: {c['survives_both']}")
    if c["did_not_reproduce"]:
        print(f"historical record unreliable for {c['did_not_reproduce']} cell(s)")


if __name__ == "__main__":
    main()
