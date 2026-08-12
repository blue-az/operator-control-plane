#!/usr/bin/env python3
"""Local-lane eval ladder runner. LOCAL_LANE_CONTRACT_SPEC.md Deliverable 3.

Drives opr's own tool loop (via --eval-auto-confirm against a disposable
fixture) across a grid of task x specificity-level x model x trial, grades
deterministically (grading.py, no LLM judging), records each trial into the
operator ledger, and writes a results matrix.

Usage:
    python3 runner.py --models gemma4:26b gemma4:31b qwen2.5-coder:32b llama3.1:8b \
        [--trials 3] [--tasks alias-add config-value-change ...] [--levels L0 L1 L2] \
        [--output RESULTS.md] [--state state.json] [--no-ledger] [--dry-run] \
        [--trace-dir DIR]

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

Trace retention: --trace-dir writes one JSON per cell holding opr's raw
stdout and stderr (which carry the tool-call log), the exact argv and prompt,
the git revision, and the grade outcome. It is off by default, so runs that
omit it behave exactly as before. GOLD_STANDARD.md rule 4 requires retained
traces for a scoreable cell, so a matrix run without --trace-dir is not
Front E evidence. Traces are written for passes, fails, AND timeouts: a
failure with no retained output is precisely the confound that invalidated
the 88 pre-890d595 negatives, so the write fails closed -- if it raises, the
caller must not mark the cell done.

Known gap: tool-call count is not parsed into a structured field (opr's own
stdout format was not validated against a real run while writing this).
Wall-clock and pass/fail are exact; with --trace-dir the raw output needed to
derive tool-call counts is now retained, so that parse can be added later
without re-running the matrix.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
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


def resolve_machine() -> str:
    """Producer machine for a trial record, per MACHINE_PROVENANCE_SPEC.md:
    OPERATOR_MACHINE override -> short hostname -> "unknown".

    Trials are not comparable across machines. Pass/fail on a deterministic
    postcondition mostly transfers, but wall_clock_s and any timeout-mediated
    outcome are decode-rate dependent, and decode rate depends on how much of a
    model fits in VRAM on that host. Records written before this field existed
    read as "unknown" and must not be pooled with tagged ones.
    """
    return os.environ.get("OPERATOR_MACHINE") or platform.node().split(".")[0] or "unknown"


MACHINE = resolve_machine()


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


_GIT_REV: str | None = None


def _git_rev() -> str:
    """Exact revision under test, stamped into every trace for provenance.

    Cached so --help and dry-runs never pay for it, and a 27-cell sweep
    resolves it once rather than per cell.
    """
    global _GIT_REV
    if _GIT_REV is None:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                capture_output=True, text=True, timeout=10, check=False,
            )
            _GIT_REV = result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:  # noqa: BLE001 -- provenance is recorded, never fatal
            _GIT_REV = "unknown"
    return _GIT_REV


def _as_text(blob: str | bytes | None) -> str:
    """TimeoutExpired carries whatever was captured before the kill, and it is
    bytes rather than str on some paths even when the call passed text=True.
    Partial output from a timed-out cell is the most diagnostic trace there is,
    so normalise instead of dropping it."""
    if blob is None:
        return ""
    if isinstance(blob, bytes):
        return blob.decode("utf-8", errors="replace")
    return blob


def trace_path_for(trace_dir: Path, task_id: str, level: str, model: str, trial: int) -> Path:
    safe_model = re.sub(r"[^A-Za-z0-9._-]", "-", model)
    return trace_dir / f"{task_id}__{level}__{safe_model}__t{trial}.json"


def write_trace(
    trace_dir: Path, task_id: str, level: str, model: str, trial: int, *,
    argv: list[str], prompt: str, stdout: str, stderr: str, record: dict, timed_out: bool,
) -> Path:
    """Persist the per-cell trace GOLD_STANDARD rule 4 requires.

    Deliberately fails closed: this raises rather than warning, and main()
    aborts without marking the cell done. A silently untraced cell would look
    identical to a traced one in state.json, which is the failure mode the
    E0 consultant review flagged.
    """
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_path_for(trace_dir, task_id, level, model, trial)
    payload = {
        "cell_key": cell_key(task_id, level, model, trial),
        "task_id": task_id,
        "level": level,
        "model": model,
        "trial": trial,
        "machine": MACHINE,
        "git_rev": _git_rev(),
        "harness": HARNESS_ID,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "timed_out": timed_out,
        "timeout_limit_s": MAX_WALL_CLOCK_SECONDS,
        "returncode": record.get("returncode"),
        "wall_clock_s": record.get("wall_clock_s"),
        "passed": record.get("passed"),
        "grade_detail": record.get("detail"),
        "prompt": prompt,
        "argv": argv,
        "stdout": stdout,
        "stderr": stderr,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


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
        # Phrased as an observed correlation, not a settled cause. The
        # supporting negative records predate opr 890d595, when run_command
        # was a terminal tool that ended the loop on first success, so they
        # cannot distinguish model failure from harness truncation. See
        # .operator/evidence/opr-continuation-loop-audit/evidence-0008.md
        "known_failure_modes": [
            "observed (pre-890d595 harness): lower pass rates at low specificity levels; "
            "cause not established"
        ],
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
    task: dict, level: str, model: str, trial_idx: int, ledger_dir: Path, use_ledger: bool,
    trace_dir: Path | None = None,
) -> dict:
    prompt = task["prompts"][level]
    fixture_root = build_fixture(
        task.get("files", {}), prefix=f"{task['task_id']}-{level}", remove=task.get("remove")
    )
    task_slug = f"eval-{task['task_id']}-{level}-{model.replace(':', '-')}-t{trial_idx}"
    usage_id = None
    argv = [
        str(OPR_BIN), prompt,
        "--model", model,
        "--workspace", str(fixture_root),
        "--eval-auto-confirm",
        "--allow-write", "--allow-run",
        "--no-govern",  # runner does its own explicit ledger tagging above
        "--no-bn",
    ]
    start = time.monotonic()
    try:
        if use_ledger:
            usage_id = _ledger_session_start(ledger_dir, task_slug, prompt)
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=MAX_WALL_CLOCK_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            wall_clock = time.monotonic() - start
            if use_ledger and usage_id:
                _ledger_session_end(ledger_dir, usage_id, "fail")
            record = {
                "task_id": task["task_id"],
                "level": level,
                "model": model,
                "trial": trial_idx,
                "machine": MACHINE,
                "passed": False,
                "detail": f"timed out after {MAX_WALL_CLOCK_SECONDS}s",
                "wall_clock_s": round(wall_clock, 1),
                "returncode": None,
            }
            if trace_dir is not None:
                record["trace"] = str(write_trace(
                    trace_dir, task["task_id"], level, model, trial_idx,
                    argv=argv, prompt=prompt,
                    stdout=_as_text(exc.stdout), stderr=_as_text(exc.stderr),
                    record=record, timed_out=True,
                ))
            return record
        wall_clock = time.monotonic() - start
        grade_result = grade(task["postcondition"], fixture_root, completed.stdout)
        outcome = "pass" if grade_result.passed else "fail"
        if use_ledger and usage_id:
            _ledger_session_end(ledger_dir, usage_id, outcome)
        record = {
            "task_id": task["task_id"],
            "level": level,
            "model": model,
            "trial": trial_idx,
            "machine": MACHINE,
            "passed": grade_result.passed,
            "detail": grade_result.detail,
            "wall_clock_s": round(wall_clock, 1),
            "returncode": completed.returncode,
        }
        if trace_dir is not None:
            record["trace"] = str(write_trace(
                trace_dir, task["task_id"], level, model, trial_idx,
                argv=argv, prompt=prompt,
                stdout=completed.stdout, stderr=completed.stderr,
                record=record, timed_out=False,
            ))
        return record
    finally:
        cleanup_fixture(fixture_root)


def write_results_md(results: list[dict], output_path: Path) -> None:
    models = sorted({r["model"] for r in results})
    tasks = sorted({r["task_id"] for r in results})
    lines = ["# Local Lane Ladder — Results", ""]
    lines.append(f"Generated from {len(results)} trial records.")
    machines = sorted({r.get("machine", "unknown") for r in results})
    lines.append(f"Producer machine(s): {', '.join(machines)}.")
    if len(machines) > 1:
        counts = ", ".join(
            f"{m}: {sum(1 for r in results if r.get('machine', 'unknown') == m)}"
            for m in machines
        )
        lines.append("")
        lines.append(
            f"> **Mixed-machine dataset ({counts}).** Wall-clock and any timeout-mediated "
            "outcome are decode-rate dependent and do not transfer between hosts; the "
            "aggregates below pool them anyway. Split by machine before drawing timing "
            "conclusions. See MACHINE_PROVENANCE_SPEC.md."
        )
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
    parser.add_argument(
        "--trace-dir", default=None,
        help=(
            "Retain one JSON trace per cell (raw opr stdout/stderr, argv, prompt, "
            "git rev, grade outcome) for passes, fails and timeouts. Off by "
            "default; required for a scoreable run under GOLD_STANDARD rule 4."
        ),
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

    trace_dir = Path(args.trace_dir).resolve() if args.trace_dir else None
    if trace_dir is not None:
        print(f"Trace retention: ON -> {trace_dir}")
    else:
        print(
            "Trace retention: OFF -- results are NOT scoreable under "
            "GOLD_STANDARD rule 4 (pass --trace-dir DIR).",
            file=sys.stderr,
        )

    state_path = Path(args.state)
    state = load_state(state_path)
    results = list(state.get("results", []))
    done = state.get("done", {})

    for task, level, model, trial in grid:
        key = cell_key(task["task_id"], level, model, trial)
        if key in done:
            continue
        print(f"[{key}] running...")
        try:
            result = run_trial(task, level, model, trial, ledger_dir, use_ledger, trace_dir)
        except OSError as exc:
            # Trace write failed. Abort rather than record an untraced cell --
            # state.json cannot distinguish the two after the fact.
            print(
                f"[{key}] ABORT: trace write failed ({exc}). Cell not recorded; "
                "fix the trace destination and re-run to resume.",
                file=sys.stderr,
            )
            save_state(state_path, state)
            return 1
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
