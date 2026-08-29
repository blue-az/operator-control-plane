#!/usr/bin/env python3
"""26b vs 31b on real Evaluation repos with agent files stripped.

Copies each repo into tempfile (opr --eval-auto-confirm will not touch a
live tree), unlinks AGENTS.md / CLAUDE.md and kin, then drives the same
opr loop as runner.py. Primary metric is trajectory.n_calls on passing
cells, not wall-clock.

Not Elo. Not a seat. Not UID-verified.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from collections import defaultdict
from datetime import UTC, datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from fixtures import cleanup_fixture, hash_tree
from grading import grade
from runner import (
    MACHINE,
    OPR_BIN,
    REPO_ROOT,
    _as_text,
    cell_key,
    load_state,
    parse_trajectory,
    save_state,
    write_trace,
)

EVAL_ROOT = Path("/home/blueaz/Python/Evaluation")
PACK = HERE / "fixtures" / "repo-turns"
TASKS_DIR = PACK / "tasks"
AGENT_NAMES = {
    "AGENTS.md",
    "AGENT.md",
    "agents.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CODEX.md",
    "GROK.md",
    ".cursorrules",
    ".clinerules",
}
COPY_IGNORE = {
    ".git",
    "node_modules",
    "dist",
    "target",
    "__pycache__",
    ".venv",
    "venv",
    ".mypy_cache",
    ".pytest_cache",
    ".turbo",
    "coverage",
}
MAX_WALL = 600


def load_tasks(task_ids: list[str] | None) -> list[dict]:
    tasks = []
    for path in sorted(TASKS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if task_ids and data["task_id"] not in task_ids:
            continue
        tasks.append(data)
    return tasks


def strip_agent_files(root: Path) -> list[str]:
    removed: list[str] = []
    for p in root.rglob("*"):
        if p.is_file() and p.name in AGENT_NAMES:
            removed.append(str(p.relative_to(root)))
            p.unlink()
    return removed


def copy_repo(repo: str, prefix: str) -> Path:
    src = (EVAL_ROOT / repo).resolve()
    if not src.is_dir():
        raise FileNotFoundError(f"repo not found: {src}")
    dest = Path(tempfile.mkdtemp(prefix=f"local-lane-eval-{prefix}-")).resolve()
    shutil.copytree(
        src,
        dest,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(*COPY_IGNORE),
        symlinks=True,
    )
    return dest


def run_trial(
    task: dict,
    model: str,
    trial: int,
    *,
    sampling: list[str],
    trace_dir: Path,
) -> dict:
    prompt = task["prompts"]["L1"]
    root = copy_repo(task["repo"], prefix=f"{task['task_id']}-{model.replace(':', '-')}-t{trial}")
    stripped = strip_agent_files(root)
    leftover = [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and p.name in AGENT_NAMES
    ]
    if leftover:
        cleanup_fixture(root)
        raise RuntimeError(f"agent files survived strip: {leftover}")
    manifest = hash_tree(root)
    argv = [
        str(OPR_BIN),
        prompt,
        "--model",
        model,
        "--workspace",
        str(root),
        "--eval-auto-confirm",
        "--allow-write",
        "--allow-run",
        "--no-govern",
        "--no-bn",
        "--continue-steps",
        str(task.get("state_changes") or 2),
    ]
    for i, token in enumerate(sampling):
        if token == "--seed":
            argv.extend(["--seed", str(int(sampling[i + 1]) + trial)])
        elif i and sampling[i - 1] == "--seed":
            continue
        else:
            argv.append(token)

    import subprocess

    start = time.monotonic()
    timed_out = False
    try:
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=MAX_WALL,
                env={**__import__("os").environ, "PYTHONUNBUFFERED": "1"},
            )
            stdout, stderr, rc = completed.stdout, completed.stderr, completed.returncode
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout, stderr, rc = _as_text(exc.stdout), _as_text(exc.stderr), None
        wall = time.monotonic() - start
        traj = parse_trajectory(stdout)
        if timed_out:
            passed, detail = False, f"timed out after {MAX_WALL}s"
            checks: list = []
            score = 0.0
        else:
            g = grade(task["postcondition"], root, stdout, manifest)
            passed, detail, score = g.passed, g.detail, round(g.score, 3)
            checks = [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in g.checks]
        record = {
            "task_id": task["task_id"],
            "repo": task["repo"],
            "level": "L1",
            "model": model,
            "trial": trial,
            "machine": MACHINE,
            "passed": passed,
            "detail": detail,
            "check_score": score,
            "checks": checks,
            "n_calls": traj["n_calls"],
            "n_failed_calls": traj["n_failed_calls"],
            "stopped_repeat": traj["stopped_repeat"],
            "no_dispatch": traj["no_dispatch"],
            "stripped_agent_files": stripped,
            "wall_clock_s": round(wall, 1),
            "returncode": rc,
        }
        record["trace"] = str(
            write_trace(
                trace_dir,
                task["task_id"],
                "L1",
                model,
                trial,
                argv=argv,
                prompt=prompt,
                stdout=stdout,
                stderr=stderr,
                record=record,
                timed_out=timed_out,
            )
        )
        return record
    finally:
        cleanup_fixture(root)


def write_results(rows: list[dict], path: Path) -> None:
    lines = [
        "# repo-turns — 26b vs 31b",
        "",
        "Primary metric is tool calls on **passing** cells. Wall-clock is 26b's",
        "speed advantage; do not rank on it. Not Elo. Not a seat.",
        "",
        f"Generated from {len(rows)} trial records. Machine: {MACHINE}.",
        "",
        "| model | task | t | pass | n_calls | failed_calls | repeat | wall s |",
        "|---|---|---:|:---:|---:|---:|:---:|---:|",
    ]
    for r in rows:
        lines.append(
            f"| `{r['model']}` | `{r['task_id']}` | {r['trial']} | "
            f"{int(r['passed'])} | {r['n_calls']} | {r['n_failed_calls']} | "
            f"{int(r['stopped_repeat'])} | {r['wall_clock_s']} |"
        )

    bag: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        bag[(r["model"], r["task_id"])].append(r)
    lines += [
        "",
        "## Per cell (n trials)",
        "",
        "| model | task | pass | mean n_calls (pass only) | mean n_calls (all) |",
        "|---|---|---|---:|---:|",
    ]
    for key in sorted(bag):
        model, task = key
        cell = bag[key]
        wins = [r["n_calls"] for r in cell if r["passed"]]
        allc = [r["n_calls"] for r in cell]
        mean_w = f"{sum(wins) / len(wins):.1f}" if wins else "—"
        mean_a = f"{sum(allc) / len(allc):.1f}" if allc else "—"
        lines.append(
            f"| `{model}` | `{task}` | {sum(1 for r in cell if r['passed'])}/{len(cell)} "
            f"| {mean_w} | {mean_a} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Real-repo 26b vs 31b turn count")
    ap.add_argument("--models", nargs="+", default=["gemma4:26b", "gemma4:31b"])
    ap.add_argument("--tasks", nargs="+", default=None)
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--num-ctx", type=int, default=16384)
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--think", default="off")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-ledger", action="store_true", default=True)
    ap.add_argument("--trace-dir", default=str(PACK / "traces"))
    ap.add_argument("--output", default=str(PACK / "RESULTS.md"))
    ap.add_argument("--state", default=str(PACK / "state.json"))
    args = ap.parse_args()

    tasks = load_tasks(args.tasks)
    if not tasks:
        print("No tasks matched.", file=sys.stderr)
        return 1
    for t in tasks:
        src = EVAL_ROOT / t["repo"]
        if not src.is_dir():
            print(f"missing repo: {src}", file=sys.stderr)
            return 1

    grid = [
        (task, model, trial)
        for task in tasks
        for model in args.models
        for trial in range(1, args.trials + 1)
    ]
    print(
        f"Grid: {len(tasks)} repos x {len(args.models)} models x {args.trials} "
        f"= {len(grid)} cells. eval_root={EVAL_ROOT}"
    )
    if args.dry_run:
        for task, model, trial in grid:
            print(f"  {task['task_id']}  {model}  t{trial}  repo={task['repo']}")
        print("Dry run. No trials.")
        return 0

    sampling: list[str] = []
    for flag, value in (
        ("--num-ctx", args.num_ctx),
        ("--temperature", args.temperature),
        ("--seed", args.seed),
        ("--think", args.think),
    ):
        if value is not None:
            sampling.extend([flag, str(value)])
    print(f"Sampling pinned: {' '.join(sampling)}")

    trace_dir = Path(args.trace_dir)
    state_path = Path(args.state)
    state = load_state(state_path)
    done = set(state.get("done", []))
    rows = list(state.get("results", []))

    for task, model, trial in grid:
        key = cell_key(task["task_id"], "L1", model, trial)
        if key in done:
            print(f"[skip] {key}", flush=True)
            continue
        print(f"[{key}] running...", flush=True)
        rec = run_trial(task, model, trial, sampling=sampling, trace_dir=trace_dir)
        rec["recorded_utc"] = datetime.now(UTC).isoformat()
        rows.append(rec)
        done.add(key)
        save_state(state_path, {"done": sorted(done), "results": rows})
        print(
            f"[{key}] pass={int(rec['passed'])} n_calls={rec['n_calls']} "
            f"wall={rec['wall_clock_s']}s  {rec['detail'][:80]}",
            flush=True,
        )

    write_results(rows, Path(args.output))
    print(f"Wrote {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
