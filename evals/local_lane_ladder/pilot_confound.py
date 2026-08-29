#!/usr/bin/env python3
"""
Paired pilot: does the pre-890d595 terminal-tool default explain historical
ladder negatives?

Commissioned in handoff-0004 on task opr-continuation-loop-audit, as a cheaper
alternative to rerunning all 88 negative cells.

Design. Each sampled cell is a (task, level, model) triple that FAILED in the
historical sweep. It is run twice against an identical fresh fixture:

  A) --continue-steps 0  -> reproduces the old terminal-tool behavior
  B) --continue-steps 4  -> the new bounded continuation loop

Grading uses the ladder's own deterministic postcondition, unchanged. The
question is the A->B transition rate:

  fail -> pass    the historical negative was harness truncation
  fail -> fail    the historical negative survives the fix
  pass -> *       the historical record did not reproduce at all (variance)

Every raw stdout/stderr is retained, which the original sweep did not do.

Note this does NOT use --eval-auto-confirm (which the original runner used and
which is tempdir-locked); it uses --dangerous, because --eval-auto-confirm
predates and is unaffected by the continuation flag. Fixtures are still built
under tempfile.gettempdir() by build_fixture.
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import yaml
from fixtures import build_fixture
from grading import grade

TASKS_DIR = Path(__file__).parent / "tasks"


def load_tasks_raw():
    return [
        yaml.safe_load(p.read_text(encoding="utf-8"))
        for p in sorted(TASKS_DIR.glob("*.yaml"))
    ]

REPO_ROOT = Path(__file__).resolve().parents[2]
OPR_BIN = REPO_ROOT / "opr"
OUTDIR = Path("/home/blueaz/Documents/local/routing/pilot_confound")
MAX_WALL = 900


def run_one(task, level, model, continue_steps, tag):
    prompt = task["prompts"][level]
    fixture_root = build_fixture(
        task.get("files", {}),
        prefix=f"pilot-{task['task_id']}-{level}",
        remove=task.get("remove"),
    )
    cmd = [
        str(OPR_BIN), prompt,
        "--model", model,
        "--workspace", str(fixture_root),
        "--allow-write", "--allow-run",
        "--no-govern", "--no-bn",
        "--dangerous",
    ]
    if continue_steps > 0:
        cmd += ["--continue-steps", str(continue_steps)]

    start = time.monotonic()
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=MAX_WALL)
        out, rc = completed.stdout, completed.returncode
        err = completed.stderr
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = "TIMEOUT"
        rc = None
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


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    sample = json.loads(Path(sys.argv[1]).read_text())
    tasks = {t["task_id"]: t for t in load_tasks_raw()}

    results = []
    for i, cell in enumerate(sample, 1):
        t = tasks[cell["task_id"]]
        base = f"{cell['model'].replace(':', '-')}-{cell['task_id']}-{cell['level']}"
        a = run_one(t, cell["level"], cell["model"], 0, f"{base}-A-steps0")
        b = run_one(t, cell["level"], cell["model"], 4, f"{base}-B-steps4")
        transition = f"{'pass' if a['passed'] else 'fail'}->{'pass' if b['passed'] else 'fail'}"
        row = {**cell, "A_steps0": a, "B_steps4": b, "transition": transition}
        results.append(row)
        print(
            f"[{i}/{len(sample)}] {cell['model']:<20} {cell['task_id']:<28} {cell['level']} "
            f"{transition:<12} A(tc={a['tool_calls']}) B(tc={b['tool_calls']},"
            f"complete={b['task_complete']},repeat={b['repeat_halt']})",
            flush=True,
        )
        (OUTDIR / "results.json").write_text(json.dumps(results, indent=2))

    from collections import Counter
    c = Counter(r["transition"] for r in results)
    print("\n--- transitions ---")
    for k, v in c.most_common():
        print(f"  {k:<14} {v}")
    print(f"\nharness-truncation rate among reproduced historical negatives: "
          f"{c['fail->pass']}/{c['fail->pass'] + c['fail->fail']}")


if __name__ == "__main__":
    main()
