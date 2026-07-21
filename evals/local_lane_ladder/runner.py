#!/usr/bin/env python3
"""Local-lane eval ladder runner. LOCAL_LANE_CONTRACT_SPEC.md Deliverable 3.

Drives opr's own tool loop (via --eval-auto-confirm against a disposable
fixture) across a grid of task x specificity-level x model x trial, grades
deterministically (grading.py, no LLM judging), records each trial into the
operator ledger, and writes a results matrix.

Usage:
    python3 runner.py --models gemma4:26b gemma4:31b qwen2.5-coder:32b llama3.1:8b \
        [--trials 3] [--tasks alias-add config-value-change ...] [--levels L0 L1 L2] \
        [--output RESULTS.md] [--state state.json] [--no-ledger] [--dry-run]

Safety: never runs against a real repo -- every trial gets its own disposable
temp fixture (fixtures.build_fixture, always under tempfile.gettempdir()),
and opr is invoked with --eval-auto-confirm, which itself independently
refuses to run outside tempfile.gettempdir() (see opr's main(), the check
right after workspace_root is resolved). This runner does not weaken or
duplicate that check -- it relies on opr's own refusal as the actual gate.

Resumability: a local state.json (not the operator ledger itself) tracks
which (task, level, model, trial) cells are already done, per the spec's
hardware-constraints note that sweeps are slow at 200W and must be
resumable. Ledger recording (session-start/session-end with lane=local,
task_class=bounded) is a separate, best-effort concern -- a ledger failure
logs a warning and does not abort the sweep or lose grading data.

Known gap: tool-call count is not currently captured (opr's own stdout
format was not validated against a real run while writing this). Wall-clock
and pass/fail are exact; tool-call count is a TODO for after the first real
smoke run confirms what opr's subprocess output actually looks like.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
import task_lint  # noqa: E402

from fixtures import build_fixture, cleanup_fixture  # noqa: E402
from grading import grade  # noqa: E402

TASKS_DIR = Path(__file__).resolve().parent / "tasks"
OPR_BIN = REPO_ROOT / "opr"
OPERATOR_BIN = REPO_ROOT / "operator"
DEFAULT_LEVELS = ("L0", "L1", "L2")
HARNESS_ID = "local-lane-eval"
MAX_WALL_CLOCK_SECONDS = 600  # 10 minutes per trial, per spec


def load_tasks(task_ids: list[str] | None) -> list[dict]:
    tasks = []
    for path in sorted(TASKS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if task_ids and data["task_id"] not in task_ids:
            continue
        tasks.append(data)
    return tasks


def validate_task_prompts(tasks: list[dict]) -> list[str]:
    """Per the spec: 'the linter validates the eval's own inputs.' L2 prompts
    must lint plan-shaped, L0 prompts must lint goal-shaped, before any
    trial runs -- a task whose own prompts don't clear this bar would be
    measuring something other than what the spec intends."""
    problems = []
    for task in tasks:
        l0_verdict = task_lint.lint(task["prompts"]["L0"]).overall
        if l0_verdict != "goal-shaped":
            problems.append(
                f"{task['task_id']}: L0 prompt lints {l0_verdict!r}, expected 'goal-shaped'"
            )
        l2_verdict = task_lint.lint(task["prompts"]["L2"]).overall
        if l2_verdict != "plan-shaped":
            problems.append(
                f"{task['task_id']}: L2 prompt lints {l2_verdict!r}, expected 'plan-shaped'"
            )
    return problems


def load_state(state_path: Path) -> dict:
    if state_path.exists():
        return json.loads(state_path.read_text(encoding="utf-8"))
    return {}


def save_state(state_path: Path, state: dict) -> None:
    state_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def cell_key(task_id: str, level: str, model: str, trial: int) -> str:
    return f"{task_id}|{level}|{model}|{trial}"


def ensure_eval_harness_registered(op_dir: Path) -> None:
    harness_path = op_dir / "harnesses" / f"{HARNESS_ID}.yaml"
    if harness_path.exists():
        return
    harness_path.parent.mkdir(parents=True, exist_ok=True)
    harness_data = {
        "harness_id": HARNESS_ID,
        "display_name": "Local Lane Eval Ladder",
        "kind": "local-lane-eval",
        "command": None,
        "working_directory": None,
        "model": None,
        "permission_profile": "local",
        "usage_source": "local",
        "transcript_source": "local",
        "strengths": ["deterministic local-model eval grid"],
        "known_failure_modes": ["degrees-of-freedom failures at low specificity levels"],
    }
    harness_path.write_text(yaml.safe_dump(harness_data, sort_keys=False), encoding="utf-8")


def _ledger_session_start(ledger_dir: Path, task_slug: str, objective: str) -> str | None:
    try:
        subprocess.run(
            [str(OPERATOR_BIN), "task-create", "--id", task_slug, "--objective", objective[:200]],
            cwd=ledger_dir, capture_output=True, text=True, timeout=15, check=False,
        )
        result = subprocess.run(
            [
                str(OPERATOR_BIN), "session-start",
                "--task", task_slug,
                "--harness", HARNESS_ID,
                "--lane", "local",
                "--class", "bounded",
            ],
            cwd=ledger_dir, capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode != 0:
            print(
                f"  [ledger] session-start failed (non-fatal): {result.stderr.strip()[:200]}",
                file=sys.stderr,
            )
            return None
        match = re.search(r"usage-\d+", result.stdout)
        return match.group(0) if match else None
    except Exception as exc:  # noqa: BLE001 -- ledger recording is best-effort by design
        print(f"  [ledger] session-start error (non-fatal): {exc}", file=sys.stderr)
        return None


# session-end's --outcome is a fixed vocabulary evaluating the session's
# work, not a bare pass/fail -- there is no exact match, so a trial that
# cleared its postcondition is tagged "useful" and one that didn't is
# "no_go". --cost is required=True by operator's own argparse (a local
# model has no API cost, but the flag must still be supplied or the command
# fails closed with an argparse error).
_LEDGER_OUTCOME = {"pass": "useful", "fail": "no_go"}


def _ledger_session_end(ledger_dir: Path, usage_id: str, outcome: str) -> None:
    try:
        result = subprocess.run(
            [
                str(OPERATOR_BIN), "session-end", usage_id,
                "--outcome", _LEDGER_OUTCOME[outcome],
                "--cost", "0.0",
            ],
            cwd=ledger_dir, capture_output=True, text=True, timeout=15, check=False,
        )
        if result.returncode != 0:
            print(
                f"  [ledger] session-end failed (non-fatal): {result.stderr.strip()[:200]}",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001 -- ledger recording is best-effort by design
        print(f"  [ledger] session-end error (non-fatal): {exc}", file=sys.stderr)


def run_trial(
    task: dict, level: str, model: str, trial_idx: int, ledger_dir: Path, use_ledger: bool
) -> dict:
    prompt = task["prompts"][level]
    fixture_root = build_fixture(
        task.get("files", {}), prefix=f"{task['task_id']}-{level}", remove=task.get("remove")
    )
    task_slug = f"eval-{task['task_id']}-{level}-{model.replace(':', '-')}-t{trial_idx}"
    usage_id = None
    start = time.monotonic()
    try:
        if use_ledger:
            usage_id = _ledger_session_start(ledger_dir, task_slug, prompt)
        completed = subprocess.run(
            [
                str(OPR_BIN), prompt,
                "--model", model,
                "--workspace", str(fixture_root),
                "--eval-auto-confirm",
                "--allow-write", "--allow-run",
                "--no-govern",  # runner does its own explicit ledger tagging above
                "--no-bn",
            ],
            capture_output=True, text=True, timeout=MAX_WALL_CLOCK_SECONDS,
        )
        wall_clock = time.monotonic() - start
        grade_result = grade(task["postcondition"], fixture_root, completed.stdout)
        outcome = "pass" if grade_result.passed else "fail"
        if use_ledger and usage_id:
            _ledger_session_end(ledger_dir, usage_id, outcome)
        return {
            "task_id": task["task_id"],
            "level": level,
            "model": model,
            "trial": trial_idx,
            "passed": grade_result.passed,
            "detail": grade_result.detail,
            "wall_clock_s": round(wall_clock, 1),
            "returncode": completed.returncode,
        }
    except subprocess.TimeoutExpired:
        wall_clock = time.monotonic() - start
        if use_ledger and usage_id:
            _ledger_session_end(ledger_dir, usage_id, "fail")
        return {
            "task_id": task["task_id"],
            "level": level,
            "model": model,
            "trial": trial_idx,
            "passed": False,
            "detail": f"timed out after {MAX_WALL_CLOCK_SECONDS}s",
            "wall_clock_s": round(wall_clock, 1),
            "returncode": None,
        }
    finally:
        cleanup_fixture(fixture_root)


def write_results_md(results: list[dict], output_path: Path) -> None:
    models = sorted({r["model"] for r in results})
    tasks = sorted({r["task_id"] for r in results})
    lines = ["# Local Lane Ladder — Results", ""]
    lines.append(f"Generated from {len(results)} trial records.")
    lines.append("")
    lines.append("## Pass rate per model x level (all tasks combined)")
    lines.append("")
    lines.append("| Model | L0 | L1 | L2 |")
    lines.append("|---|---|---|---|")
    for model in models:
        row = [model]
        for level in DEFAULT_LEVELS:
            cell = [r for r in results if r["model"] == model and r["level"] == level]
            row.append("—" if not cell else f"{sum(1 for r in cell if r['passed'])}/{len(cell)}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Per-task breakdown")
    lines.append("")
    for task_id in tasks:
        lines.append(f"### {task_id}")
        lines.append("")
        lines.append("| Model | L0 | L1 | L2 |")
        lines.append("|---|---|---|---|")
        for model in models:
            row = [model]
            for level in DEFAULT_LEVELS:
                cell = [
                    r for r in results
                    if r["model"] == model and r["level"] == level and r["task_id"] == task_id
                ]
                row.append(
                    "—" if not cell else f"{sum(1 for r in cell if r['passed'])}/{len(cell)}"
                )
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local lane eval ladder runner")
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model tags, e.g. gemma4:26b")
    parser.add_argument("--tasks", nargs="+", default=None, help="Task ids to run (default: all)")
    parser.add_argument(
        "--levels", nargs="+", default=list(DEFAULT_LEVELS), choices=list(DEFAULT_LEVELS)
    )
    parser.add_argument("--trials", type=int, default=3, help="Trials per cell (spec minimum: 3)")
    parser.add_argument(
        "--output", default=str(Path(__file__).resolve().parent / "RESULTS.md")
    )
    parser.add_argument(
        "--state", default=str(Path(__file__).resolve().parent / "state.json")
    )
    parser.add_argument("--ledger-dir", default=str(REPO_ROOT))
    parser.add_argument(
        "--no-ledger", action="store_true", help="Skip operator session-start/end recording"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Validate task prompts and print the planned grid; run no trials.",
    )
    args = parser.parse_args()

    tasks = load_tasks(args.tasks)
    if not tasks:
        print("No tasks matched.", file=sys.stderr)
        return 1

    problems = validate_task_prompts(tasks)
    if problems:
        print("Task prompt validation failed (fix before running):", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    grid = [
        (task, level, model, trial)
        for task in tasks
        for level in args.levels
        for model in args.models
        for trial in range(1, args.trials + 1)
    ]
    print(
        f"Grid: {len(tasks)} tasks x {len(args.levels)} levels x {len(args.models)} models "
        f"x {args.trials} trials = {len(grid)} cells"
    )

    if args.dry_run:
        print("Dry run: task prompts validated, no trials executed.")
        return 0

    ledger_dir = Path(args.ledger_dir).resolve()
    use_ledger = not args.no_ledger
    if use_ledger:
        ensure_eval_harness_registered(ledger_dir / ".operator")

    state_path = Path(args.state)
    state = load_state(state_path)
    results = list(state.get("results", []))
    done = state.get("done", {})

    for task, level, model, trial in grid:
        key = cell_key(task["task_id"], level, model, trial)
        if key in done:
            continue
        print(f"[{key}] running...")
        result = run_trial(task, level, model, trial, ledger_dir, use_ledger)
        results.append(result)
        done[key] = True
        state["done"] = done
        state["results"] = results
        save_state(state_path, state)
        verdict = "PASS" if result["passed"] else "FAIL"
        print(f"[{key}] {verdict} ({result['wall_clock_s']}s) -- {result['detail']}")

    write_results_md(results, Path(args.output))
    print(f"\nWrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
