#!/usr/bin/env python3
"""Local-lane eval ladder runner. LOCAL_LANE_CONTRACT_SPEC.md Deliverable 3.

Drives `pi` (the local implementer as of 2026-08-28 -- opr is carved out of
this codebase, opencode is deprecated) in non-interactive JSON mode across a
grid of task x specificity-level x model x trial, grades deterministically
(grading.py, no LLM judging), records each trial into the operator ledger,
and writes a results matrix.

Migration note (2026-08-28, opr -> pi): this runner previously drove `opr`.
That code path, its trajectory parser, and the opr-specific safety/sampling
mechanics it depended on are gone, replaced below. If you find a reference to
opr anywhere else in this file's comments, it is describing history, not
current behavior. Historical restore path, kept for archaeology only: `git
checkout fe4211b09bc164c3dc0b7b48bad929e39ab68356 -- opr`.

Usage:
    python3 runner.py --models gemma4:26b gemma4:31b qwen2.5-coder:32b llama3.1:8b \
        [--trials 3] [--tasks alias-add config-value-change ...] [--levels L0 L1 L2] \
        [--output RESULTS.md] [--state state.json] [--no-ledger] [--dry-run] \
        [--trace-dir DIR]

Safety: never runs against a real repo -- every trial gets its own disposable
temp fixture (fixtures.build_fixture, always under tempfile.gettempdir()). pi
has no --workspace flag and no opr-style internal refusal-to-run-outside-tempdir
check, so the sandbox boundary is entirely this runner's responsibility: pi is
always invoked with `cwd` pinned to that fixture directory (see run_trial).
There is no independent second gate the way opr's own check was; do not change
run_trial's cwd handling without preserving this property.

Sampling: pi's CLI has no --temperature or context-window flag at all (checked
--help and the coding-agent/ai package sources directly). --num-ctx and
--temperature are pinned by creating a derived Ollama model via a temp
Modelfile and pointing pi at that tag (see ensure_pinned_model) rather than by
a request-level option. --seed and --on-repeat have no pi equivalent and are
dropped with a warning, not silently ignored -- see main().

Resumability: a local state.json (not the operator ledger itself) tracks
which (task, level, model, trial) cells are already done, per the spec's
hardware-constraints note that sweeps are slow at 200W and must be
resumable. Ledger recording (session-start/session-end with lane=local,
task_class=bounded) is a separate, best-effort concern -- a ledger failure
logs a warning and does not abort the sweep or lose grading data.

Trace retention: --trace-dir writes one JSON per cell holding pi's raw
`--mode json` stdout and stderr (which carry the tool-call log), the exact
argv and prompt, the git revision, and the grade outcome. It is off by
default, so runs that omit it behave exactly as before. GOLD_STANDARD.md rule
4 requires retained traces for a scoreable cell, so a matrix run without
--trace-dir is not Front E evidence. Traces are written for passes, fails,
AND timeouts: a failure with no retained output is precisely the confound
that invalidated the 88 pre-890d595 negatives (opr-era; the general principle
still applies), so the write fails closed -- if it raises, the caller must
not mark the cell done.

Trajectory: every trace now carries a parsed `trajectory` object -- the ordered
tool calls with their paths and errors, call counts, the two harness-visible
terminations (repeat-guard, non-dispatch), and token/thinking accounting.
`stopped_repeat` is always False under the pi backend (no repeat-guard
concept). It is descriptive only: the deterministic postcondition remains the
sole gate, and the parse is deliberately tolerant so it can never fail a cell
the grader already decided.

Scope: run_trial hashes the fixture before pi runs and passes that manifest to
the grader, which is what makes a `files_unchanged` postcondition able to enforce
LOCAL_LANE_CONTRACT R6. Tasks without such a postcondition are unaffected.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
from fixtures import build_fixture, cleanup_fixture, hash_tree
from grading import grade

import task_lint

TASKS_DIR = Path(__file__).resolve().parent / "tasks"
PI_BIN = shutil.which("pi") or "pi"
OPERATOR_BIN = REPO_ROOT / "operator"

# pi has no --num-ctx/--temperature CLI flags (checked --help and the
# coding-agent/ai package sources directly, 2026-08-28) -- num_ctx and
# temperature are pinned by creating a derived Ollama model via a temp
# Modelfile instead, and pi is pointed at that tag. Cached per (base model,
# ctx, temperature) so a multi-cell run creates each derived model once.
_PINNED_MODEL_CACHE: dict[tuple[str, int | None, float | None], str] = {}


def ensure_pinned_model(base_model: str, num_ctx: int | None, temperature: float | None) -> str:
    if num_ctx is None and temperature is None:
        return base_model
    key = (base_model, num_ctx, temperature)
    if key in _PINNED_MODEL_CACHE:
        return _PINNED_MODEL_CACHE[key]
    suffix_parts = []
    if num_ctx is not None:
        suffix_parts.append(f"ctx{num_ctx}")
    if temperature is not None:
        suffix_parts.append(f"t{str(temperature).replace('.', 'p')}")
    # Bug fix 2026-08-28: this used to be base_model.split(":")[0], which
    # collapses e.g. gemma4:26b and gemma4:31b to the identical "gemma4"
    # prefix -- both derived to the SAME tag, so whichever model's
    # ensure_pinned_model call ran second silently overwrote the first's
    # weights under that tag. Any trial dispatched to the shared tag *after*
    # the overwrite ran against the wrong model while still being labeled
    # with its own model name in the results. Sanitizing the full tag instead
    # of just its prefix makes every base model's derived tag unique.
    base_name = re.sub(r"[^A-Za-z0-9._-]", "-", base_model)
    tag = f"{base_name}-e9pin-{'-'.join(suffix_parts)}:latest"
    lines = [f"FROM {base_model}"]
    if num_ctx is not None:
        lines.append(f"PARAMETER num_ctx {num_ctx}")
    if temperature is not None:
        lines.append(f"PARAMETER temperature {temperature}")
    fd, modelfile_path = tempfile.mkstemp(suffix=".Modelfile")
    try:
        with os.fdopen(fd, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Pinning {base_model} -> {tag} ({', '.join(lines[1:]) or 'no overrides'})")
        subprocess.run(
            ["ollama", "create", tag, "-f", modelfile_path],
            check=True, capture_output=True, text=True,
        )
    finally:
        os.unlink(modelfile_path)
    _PINNED_MODEL_CACHE[key] = tag
    return tag


# LOCAL_INFERENCE_BENCH_HARNESS.md contract v1's own prompt (436 bytes, 121
# tokens) -- reused here, not a bespoke one, so this probe's tok/s is directly
# comparable to existing Front I throughput data (e.g. MODEL-RANKING-001),
# not just an internal-only number.
_CONTRACT_PROMPT_PATH = Path(
    "/home/blueaz/Python/project-phoenix/docs/domain_runs/"
    "GEMMA4-CTX8192-3090-VS-Z13-001/prompt.txt"
)


def measure_tok_s(model: str) -> dict | None:
    """Direct Ollama /api/generate probe for a genuine decode tok/s alongside
    each trial's wall-clock completion time.

    Added 2026-08-28 because pi's `--mode json` cannot supply this: checked
    directly, message_start and message_end share the identical millisecond
    even for a pure-text (non-tool-call) response, so there is no way to
    derive per-turn generation duration from pi's own event stream. This
    probe is a supplementary measurement, run against the same pinned model
    tag (so num_ctx matches the trial), contract-v1 prompt/num_predict, and
    temperature 0 (greedy decode-rate measurement, independent of whatever
    temperature is pinned for the capability trial itself). Two calls per the
    contract's "run 2 is the warm figure" rule -- the model may have been
    evicted by tool-call activity during the pi turn.

    Returns None on any failure. This must never be able to fail a cell; it
    is not part of the grade.
    """
    if not _CONTRACT_PROMPT_PATH.is_file():
        return None
    try:
        prompt = _CONTRACT_PROMPT_PATH.read_text()
        payload = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "keep_alive": "5m",
                "options": {"num_predict": 128, "temperature": 0},
            }
        )
        data = None
        for _ in range(2):
            result = subprocess.run(
                ["curl", "-s", "http://localhost:11434/api/generate", "-d", payload],
                capture_output=True, text=True, timeout=120,
            )
            data = json.loads(result.stdout)
        eval_count = data.get("eval_count") if data else None
        eval_duration = data.get("eval_duration") if data else None  # nanoseconds
        if not eval_count or not eval_duration:
            return None
        return {
            "tok_s": round(eval_count / (eval_duration / 1e9), 1),
            "eval_count": eval_count,
            "eval_duration_s": round(eval_duration / 1e9, 2),
        }
    except Exception:  # noqa: BLE001 -- supplementary measurement, never fails a cell
        return None
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


def parse_trajectory(stdout: str) -> dict:
    """Turn pi's `--mode json` line-delimited event stream into a structured
    trajectory.

    Replaces the previous opr-stdout-marker parser (2026-08-28 migration off
    opr, which is carved out of this codebase -- pi is the local implementer
    now; see AGENTS.md/CLAUDE.md local-implementer-dispatch notes). pi's JSON
    events are structurally parseable -- no marker-scraping needed, which is
    strictly easier than what this replaced.

    Fields are kept the same shape as the opr-era parser where a pi equivalent
    exists. `stopped_repeat` is always False under this backend: pi has no
    repeat-guard concept, so a model re-issuing an identical tool call is not
    distinguished from any other tool call here.

    Parsing is deliberately tolerant: a malformed or unrecognised line is
    skipped rather than raising, because a trajectory parse must never be able
    to fail a cell that the deterministic postcondition already graded.
    """
    calls: list[dict] = []
    completion_tokens = 0
    think_chars = 0
    saw_tool_call = False
    pending_args: dict[str, dict] = {}  # toolCallId -> args, from tool_execution_start
    for line in stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        etype = event.get("type")
        if etype == "tool_execution_start":
            call_id = event.get("toolCallId")
            if call_id:
                pending_args[call_id] = event.get("args") or {}
        elif etype == "tool_execution_end":
            saw_tool_call = True
            call_id = event.get("toolCallId")
            args = pending_args.pop(call_id, {}) if call_id else {}
            result = event.get("result") or {}
            is_error = bool(result.get("isError"))
            content = result.get("content") or []
            text = ""
            if content and isinstance(content[0], dict):
                text = content[0].get("text", "") or ""
            calls.append(
                {
                    "tool": event.get("toolName"),
                    "path": args.get("path"),
                    "ok": not is_error,
                    "error": text.splitlines()[0][:200] if is_error and text else None,
                }
            )
        elif etype == "message_end":
            msg = event.get("message") or {}
            usage = msg.get("usage") or {}
            try:
                completion_tokens += int(usage.get("output") or 0)
            except (TypeError, ValueError):
                pass
            for block in msg.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    think_chars += len(block.get("text") or "")
    return {
        "tool_calls": calls,
        "n_calls": len(calls),
        "n_failed_calls": sum(1 for c in calls if not c["ok"]),
        "distinct_tools": sorted({c["tool"] for c in calls if c["tool"]}),
        "stopped_repeat": False,
        "no_dispatch": not saw_tool_call,
        "completion_tokens": completion_tokens,
        "think_chars": think_chars,
    }


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
        "recorded_utc": datetime.now(UTC).isoformat(),
        "timed_out": timed_out,
        "timeout_limit_s": MAX_WALL_CLOCK_SECONDS,
        "returncode": record.get("returncode"),
        "wall_clock_s": record.get("wall_clock_s"),
        "passed": record.get("passed"),
        "grade_detail": record.get("detail"),
        "tok_s": record.get("tok_s"),
        "tok_s_probe": record.get("tok_s_probe"),
        "prompt": prompt,
        "argv": argv,
        "trajectory": parse_trajectory(stdout),
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


# ONE LEDGER TASK PER PACK, NOT PER CELL.
#
# Every cell used to create its own `eval-<task>-<level>-<model>-t<n>` task,
# purely so `session-start` had something to attach to. Nothing ever read those
# tasks -- the real record of a cell is its retained trace plus the pack's
# RESULTS.md -- but they accumulated: 939 of 951 tasks on the desktop ledger
# (98.7%) were this scaffolding, and the 12 tasks representing actual work were
# unfindable inside them.
#
# They cannot be deleted after the fact. The YAML files are projections of a
# durable append-only ledger, and removing them orphans the durable records
# (verified 2026-08-15: moving them aside took `doctor` from 19 issues to 2774).
# So the fix is to stop minting them. Cell identity is NOT lost: it already
# lives in each retained trace (`cell_key`) and in the pack's RESULTS.md, which
# are the artifacts anything actually reads. It does not survive into the ledger
# -- `session-start` takes only --task/--harness/--lane/--class, with no field
# for a per-cell label -- and that is the same as before, since nothing ever
# read the per-cell task either.
LEDGER_PACK_TASK = (
    os.environ.get("EVAL_LEDGER_TASK")
    or f"eval-pack-{time.strftime('%Y%m%d')}"
)
_pack_task_created = False


def _ledger_session_start(ledger_dir: Path, objective: str) -> str | None:
    global _pack_task_created
    try:
        if not _pack_task_created:
            subprocess.run(
                [
                    str(OPERATOR_BIN), "task-create", "--id", LEDGER_PACK_TASK,
                    "--objective",
                    f"Local lane ladder eval pack {LEDGER_PACK_TASK}; "
                    f"per-cell detail in session records and pack RESULTS.md",
                ],
                cwd=ledger_dir, capture_output=True, text=True, timeout=15, check=False,
            )
            _pack_task_created = True
        result = subprocess.run(
            [
                str(OPERATOR_BIN), "session-start",
                "--task", LEDGER_PACK_TASK,
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
    trace_dir: Path | None = None, sampling: dict | None = None,
) -> dict:
    prompt = task["prompts"][level]
    fixture_root = build_fixture(
        task.get("files", {}), prefix=f"{task['task_id']}-{level}", remove=task.get("remove")
    )
    # Pre-run state, so a scope postcondition can tell "edited the declared file"
    # from "edited the declared file and three others". Taken before pi runs.
    manifest = hash_tree(fixture_root)
    usage_id = None
    sampling = sampling or {}

    # num_ctx/temperature are pinned by model, not CLI flag -- see
    # ensure_pinned_model. --seed has no pi equivalent (dropped, not silently
    # ignored -- see the warning main() prints once if --seed is passed).
    dispatch_model = ensure_pinned_model(
        model, sampling.get("num_ctx"), sampling.get("temperature")
    )
    argv = [
        PI_BIN,
        "--provider", "ollama",
        "--model", dispatch_model,
        "--mode", "json",
        "--print",
    ]
    think = sampling.get("think")
    if think is not None:
        # runner.py's own --think choices include "on", which pi's --thinking
        # does not accept (its levels are off/minimal/low/medium/high/xhigh/max).
        # Every call to date in this repo has used "off"; "on" is mapped to
        # "medium" (pi's own documented default) rather than erroring.
        argv += ["--thinking", "medium" if think == "on" else think]
    # No --continue-steps equivalent, and none is needed: that flag existed to
    # work around OPR-RUL-008 (opr exiting after the first successful
    # state-changing tool call). pi does not impose that cap -- it continues
    # its own tool loop until it decides it's done or MAX_WALL_CLOCK_SECONDS
    # kills it, same as the multi-call sequence in the pi migration smoke test
    # (bash -> edit -> bash -> stop). task.get("state_changes") is therefore
    # unused under this backend; left in task defs for opr-era provenance.
    argv += ["--", prompt]
    start = time.monotonic()
    try:
        if use_ledger:
            usage_id = _ledger_session_start(ledger_dir, prompt)
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=MAX_WALL_CLOCK_SECONDS,
                cwd=str(fixture_root),  # pi has no --workspace flag; this is the sandbox boundary
                # PYTHONUNBUFFERED is load-bearing for diagnosis, not a tidy-up.
                # On timeout the runner SIGKILLs the process and an unflushed
                # buffer dies with it -- unbuffered, partial output survives the
                # kill and shows how far the turn got. (Originally documented
                # against opr; pi's own buffering behavior under a pipe hasn't
                # been separately characterized, so this is left set.)
                env={**os.environ, "PYTHONUNBUFFERED": "1"},
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
        grade_result = grade(
            task["postcondition"], fixture_root, completed.stdout, manifest
        )
        outcome = "pass" if grade_result.passed else "fail"
        if use_ledger and usage_id:
            _ledger_session_end(ledger_dir, usage_id, outcome)
        tok_s_probe = measure_tok_s(dispatch_model)
        record = {
            "task_id": task["task_id"],
            "level": level,
            "model": model,
            "trial": trial_idx,
            "machine": MACHINE,
            "passed": grade_result.passed,
            "detail": grade_result.detail,
            "check_score": round(grade_result.score, 3),
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in grade_result.checks
            ],
            "wall_clock_s": round(wall_clock, 1),
            "returncode": completed.returncode,
            "tok_s": tok_s_probe.get("tok_s") if tok_s_probe else None,
            "tok_s_probe": tok_s_probe,
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
    lines.append(
        "| Model | L0 | L1 | L2 | decode tok/s (mean, contract-v1 probe) | "
        "wall_clock_s (mean, per trial) |"
    )
    lines.append("|---|---|---|---|---|---|")
    for model in models:
        row = [model]
        for level in DEFAULT_LEVELS:
            cell = [r for r in results if r["model"] == model and r["level"] == level]
            row.append("—" if not cell else f"{sum(1 for r in cell if r['passed'])}/{len(cell)}")
        model_results = [r for r in results if r["model"] == model]
        tok_s_values = [r["tok_s"] for r in model_results if r.get("tok_s") is not None]
        row.append(f"{sum(tok_s_values) / len(tok_s_values):.1f}" if tok_s_values else "—")
        wall_values = [r["wall_clock_s"] for r in model_results if r.get("wall_clock_s") is not None]
        row.append(f"{sum(wall_values) / len(wall_values):.1f}" if wall_values else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append(
        "> decode tok/s is a supplementary direct-Ollama probe "
        "(`LOCAL_INFERENCE_BENCH_HARNESS.md` contract-v1 prompt, `num_predict 128`, "
        "`temperature 0`, run against the same pinned model config as the trial), "
        "not derived from the implementer's own turn timing -- see runner.py's "
        "`measure_tok_s` docstring for why. wall_clock_s is task-completion time "
        "(includes tool-execution, not decode-only) and is what the capability "
        "pass/fail cells above were actually measured under."
    )
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
        "--num-ctx", type=int, default=None,
        help=(
            "Pin the local-model context window for every cell. Unset means each "
            "model uses its own default, which differs across models and can force "
            "CPU spill on large ones -- both of which confound a comparison."
        ),
    )
    parser.add_argument(
        "--temperature", type=float, default=None,
        help=(
            "Pin sampling temperature for every cell. Unset means model defaults "
            "(non-zero), so each cell is a fresh stochastic draw and n=3 cannot "
            "separate a reliable model from a mostly-reliable one. Use 0 to measure."
        ),
    )
    parser.add_argument(
        "--seed", type=int, default=None,
        help="Pin the sampling seed for every cell. Pair with --temperature 0.",
    )
    parser.add_argument(
        "--on-repeat", choices=["stop", "feedback"], default=None,
        help=(
            "OPR-ERA, NO LONGER FUNCTIONAL: was pass-through to opr for what to do "
            "when a model re-issues an identical tool call. pi has no equivalent; "
            "setting this now only prints a warning and is otherwise ignored."
        ),
    )
    parser.add_argument(
        "--think", choices=["on", "off", "low", "medium", "high"], default=None,
        help=(
            "Pin reasoning mode for every cell. Unset leaves each model at its own "
            "default (ON for thinking-capable models), which is both a large cost "
            "difference and an uncontrolled variable across a comparison."
        ),
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

    sampling = {
        "num_ctx": args.num_ctx,
        "temperature": args.temperature,
        "think": args.think,
    }
    if args.seed is not None:
        print(
            "WARNING: --seed has no pi equivalent and is IGNORED under this "
            "backend (dropped 2026-08-28 opr->pi migration). Trials are "
            "independently sampled, not seed-reproducible.",
            file=sys.stderr,
        )
    if args.on_repeat is not None:
        print(
            "WARNING: --on-repeat has no pi equivalent and is IGNORED -- pi has "
            "no repeat-guard concept. A model re-issuing an identical tool call "
            "is not distinguished from any other tool call.",
            file=sys.stderr,
        )
    if any(v is not None for v in sampling.values()):
        pinned = {k: v for k, v in sampling.items() if v is not None}
        print(f"Sampling pinned: {pinned}")
    else:
        print(
            "Sampling NOT pinned -- model defaults for temperature/context. Cells are "
            "stochastic draws and context varies by model; fine for a smoke, not for "
            "a comparison.",
            file=sys.stderr,
        )

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
            result = run_trial(
                task, level, model, trial, ledger_dir, use_ledger, trace_dir, sampling
            )
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
