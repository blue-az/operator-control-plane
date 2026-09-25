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
import pathlib
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


def ollama_base_url() -> str:
    return os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

# pi has no --num-ctx/--temperature CLI flags (checked --help and the
# coding-agent/ai package sources directly, 2026-08-28) -- num_ctx and
# temperature are pinned by creating a derived Ollama model via a temp
# Modelfile instead, and pi is pointed at that tag. Cached per (base model,
# ctx, temperature, num_gpu) so a multi-cell run creates each derived model once.
_PINNED_MODEL_CACHE: dict[tuple[str, int | None, float | None, int | None, int | None], str] = {}


def ensure_pinned_model(
    base_model: str, num_ctx: int | None, temperature: float | None, num_gpu: int | None = None,
    max_output: int | None = None,
) -> str:
    # num_gpu added 2026-08-30 for the VRAM-envelope accuracy ablation --
    # same rationale as num_ctx/temperature: pi has no CLI flag for it, so
    # forcing a layer-count cap (the mechanism gemma4-26b-16gb-cap/FINDING.md
    # validated as actually effective, unlike OLLAMA_GPU_OVERHEAD) requires
    # baking it into a derived Modelfile.
    if os.environ.get('LOCAL_LANE_SKIP_PIN') == '1':
        return base_model
    if num_ctx is None and temperature is None and num_gpu is None and max_output is None:
        return base_model
    key = (base_model, num_ctx, temperature, num_gpu, max_output)
    if key in _PINNED_MODEL_CACHE:
        return _PINNED_MODEL_CACHE[key]
    suffix_parts = []
    if num_ctx is not None:
        suffix_parts.append(f"ctx{num_ctx}")
    if temperature is not None:
        suffix_parts.append(f"t{str(temperature).replace('.', 'p')}")
    if num_gpu is not None:
        suffix_parts.append(f"gpu{num_gpu}")
    if max_output is not None:
        suffix_parts.append(f"out{max_output}")
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
    if num_gpu is not None:
        lines.append(f"PARAMETER num_gpu {num_gpu}")
    if max_output is not None:
        lines.append(f"PARAMETER num_predict {max_output}")
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
# Resolved relative to $HOME, not hardcoded to one user. The desktop runs as
# `blueaz` and the testbench as `ef-tb`; the absolute path silently made
# measure_tok_s return None on the bench, so a whole run's decode column came
# back empty with no error (testbench-2080-e9-batch1, 2026-09-05).
_CONTRACT_PROMPT_PATH = Path.home() / (
    "Python/project-phoenix/docs/domain_runs/"
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
                ["curl", "-s", f"{ollama_base_url()}/api/generate", "-d", payload],
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

_PRIV_SHIM_DIR = None


def _privilege_shim_dir() -> str:
    """A PATH-prepended directory whose `sudo` (and friends) refuse to run.

    Added 2026-09-07 after an L0 battery raised repeated sudo password prompts
    on the operator's desktop: `strict-log-format` at L0 says "a summary of how
    many errors happened each hour from my logs" and never names the artifact,
    so models read "my logs" as the host's real system logs and ran
    `sudo grep /var/log/messages`. See
    fixtures/l0-tiebreak-2026-09-06/FINDING.md.

    A fixture task never legitimately needs root, so refusing is free. This is
    NOT filesystem confinement -- trials still run as the invoking user and can
    read anything that user can, including ~/.pi/agent/auth.json. Real
    confinement needs a sandbox; a naive bubblewrap config was tried and broke
    the harness (the model could no longer edit files), so it is deferred rather
    than shipped half-working.
    """
    global _PRIV_SHIM_DIR
    if _PRIV_SHIM_DIR is not None:
        return _PRIV_SHIM_DIR
    d = tempfile.mkdtemp(prefix="local-lane-noroot-")
    for name in ("sudo", "pkexec", "doas", "su"):
        f = pathlib.Path(d) / name
        f.write_text(
            "#!/bin/sh\n"
            "echo \"local-lane-eval: '$0' is blocked inside a trial.\" >&2\n"
            "echo \"Fixture tasks never require root. Work inside the fixture "
            "directory.\" >&2\n"
            "exit 1\n"
        )
        f.chmod(0o755)
    _PRIV_SHIM_DIR = d
    return d

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
            rev = result.stdout.strip() if result.returncode == 0 else "unknown"
            # A sha alone is a false stamp when the tree is dirty: it names code
            # that is not what ran. runner.py itself was uncommitted through the
            # September corpus, so every "git_rev" recorded then describes a
            # revision the run did not use. Say so in the value.
            dirty = subprocess.run(
                ["git", "status", "--porcelain", "--", "evals/local_lane_ladder"],
                cwd=REPO_ROOT, capture_output=True, text=True, timeout=10, check=False,
            )
            if dirty.returncode == 0 and dirty.stdout.strip():
                changed = sorted(
                    line[3:].strip() for line in dirty.stdout.strip().splitlines()
                    if not line.startswith("??")
                )
                rev = f"{rev}-dirty({len(changed)} tracked file(s) modified)" if changed else rev
            _GIT_REV = rev
        except Exception:  # noqa: BLE001 -- provenance is recorded, never fatal
            _GIT_REV = "unknown"
        if _GIT_REV == "unknown" or _GIT_REV.startswith("unknown"):
            # The staged host packages are loose copies, not checkouts, so git
            # has nothing to say about them and "unknown" is the whole stamp.
            # Hash the file that actually ran instead: it is the only identity
            # available there, and it is enough to tell two runners apart.
            try:
                import hashlib
                digest = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()[:16]
                _GIT_REV = f"no-git:runner.py sha256:{digest}"
            except OSError:
                pass
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
    stopped_length = '"stopReason":"length"' in stdout or '"rawStopReason":"length"' in stdout
    return {
        "tool_calls": calls,
        "n_calls": len(calls),
        "n_failed_calls": sum(1 for c in calls if not c["ok"]),
        "distinct_tools": sorted({c["tool"] for c in calls if c["tool"]}),
        "stopped_repeat": False,
        # The turn ended because the model hit its context/output ceiling, not
        # because it answered. Under a pinned 16k window this is a distinct
        # outcome from a wrong answer: the task never got a final answer at all.
        "stopped_length": stopped_length,
        "no_dispatch": not saw_tool_call,
        "completion_tokens": completion_tokens,
        "think_chars": think_chars,
    }


# --- Cell outcomes -----------------------------------------------------------
#
# A failing cell is not evidence about the model until the instrument has proved
# it was measuring one. The program's own record is lopsided: the published
# Instrument Log is seventeen faults, none of them a model behaving badly; the
# 0155Z attempt returned 18 cells with returncode 0 and no timeouts that were all
# carrier violations; the 0638Z native run dispatched nothing at all; and Fusion
# L3 v2's 17 apparent failures were all deterministic-grader false negatives.
#
# So a cell has three outcomes, not two. `unproven` is not a soft fail: it says
# this cell is evidence about the harness, and is not poolable as a model result.
#
# Asymmetry is deliberate. Only a non-passing cell can be demoted to unproven.
# Demoting passes on a missing proof would invalidate the corpus wholesale every
# time a gate is added, which is the re-run treadmill this is meant to end. A
# pass still records its proof flags, so the question stays askable.
RUNTIME_POLLUTION_NAMES = (".pi-agent", ".pi-sessions", ".tmp", ".pi-auth", "node-cache")

# Shared triage. The `grader` proof was a declaration -- a task said whether its
# grader had been boundary-tested and we believed it. Fusion L3 v2 showed why
# that is not enough: 17 apparent failures were all grader false negatives.
# empty_evidence catches the shape where a check fails having observed nothing.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from failure_triage import empty_evidence
except ImportError:  # keep the runner usable if the module is not staged
    empty_evidence = None


def carrier_scope_violations(fixture_root: Path) -> list[str]:
    """Carrier runtime files inside the graded fixture. See incident 0155Z."""
    found = []
    for name in RUNTIME_POLLUTION_NAMES:
        for hit in Path(fixture_root).rglob(name):
            found.append(str(hit.relative_to(fixture_root)))
    return sorted(found)


def evaluate_proofs(
    *, returncode: int | None, stdout: str, trajectory: dict, fixture_root: Path,
    placement_verified: bool, timed_out: bool, grader_boundary_tested: bool,
    grade_checks: list | None = None,
) -> dict:
    """The five proofs a cell must satisfy before a failure means anything."""
    scope_hits = carrier_scope_violations(fixture_root)
    # A graded check that failed while reporting nothing it objected to did not
    # observe a violation; its pass condition decided the outcome. Treat that as
    # an untrusted grader rather than a model failure.
    grader_trusted = bool(grader_boundary_tested)
    hollow_checks = []
    if empty_evidence is not None:
        for check in (grade_checks or []):
            if isinstance(check, dict) and not check.get("passed", True):
                if empty_evidence(
                    {"pass": False, **{k: v for k, v in check.items()
                                       if isinstance(v, (list, tuple, set))}}
                ):
                    hollow_checks.append(check.get("name"))
        if hollow_checks:
            grader_trusted = False

    proofs = {
        "dispatch": (
            returncode == 0
            and bool(stdout.strip())
            and not trajectory.get("no_dispatch", True)
        ),
        "scope": not scope_hits,
        "placement": bool(placement_verified),
        "grader": grader_trusted,
        "timing": not timed_out,
    }
    detail = {"missing": sorted(k for k, ok in proofs.items() if not ok),
              "trajectory": trajectory}
    if hollow_checks:
        detail["hollow_checks"] = hollow_checks
    if scope_hits:
        detail["scope_violations"] = scope_hits
    return {"proofs": proofs, **detail}


def classify_failure(detail: str | None, trajectory: dict | None = None) -> str | None:
    """Separate what the model could not do from what it was not allowed to do,
    and from what it never finished.

    Gemma's L2 misses are a mix: some are the implementation failing its own
    battery, others are the model creating scratch test files (test_tmp.py,
    test_solution.py, repro.py) outside its edit scope while the implementation
    itself may be fine. A third kind is neither: the turn hit the pinned 16k
    context ceiling and stopped mid-task, so the battery grades an absent answer.
    qwen3.8's single L2 miss on 2026-09-22 was this -- it spent its window
    debugging a regex and was cut off at 16,383 of 16,384 tokens.

    Summing all three into one pass count makes a housekeeping habit and a
    truncated turn both read as capability gaps.
    """
    if (trajectory or {}).get("stopped_length"):
        return "truncated"
    if not detail:
        return None
    if "created out of scope" in detail:
        return "out_of_scope"
    if "postcondition command exited" in detail:
        return "capability"
    return "other_check"


def classify_outcome(graded_pass: bool, proof_report: dict) -> str:
    if graded_pass:
        return "pass"
    return "fail" if not proof_report["missing"] else "unproven"



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
        # The three-outcome verdict and its proofs belong in the trace too: the
        # trace is what a forensic reads, and "passed: false" alone is the
        # ambiguity this whole mechanism exists to remove.
        "outcome": record.get("outcome"),
        "proofs": record.get("proofs"),
        "unproven_reasons": record.get("unproven_reasons"),
        "scope_violations": record.get("scope_violations"),
        "placement_evidence": record.get("placement_evidence"),
        "grade_detail": record.get("detail"),
        "tok_s": record.get("tok_s"),
        "tok_s_probe": record.get("tok_s_probe"),
        "prompt": prompt,
        "argv": argv,
        "carrier_outer_argv": record.get("carrier_outer_argv"),
        "pi_inner_argv": record.get("pi_inner_argv"),
        "carrier_env_policy": record.get("carrier_env_policy"),
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


class GPUResidencyError(RuntimeError):
    """The requested GPU-resident benchmark model did not fit as configured."""


class HostStateError(RuntimeError):
    """The inference host failed its declared precondition."""


def run_host_gate(command: str | None) -> None:
    if not command:
        return
    result = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=30)
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()[:300]
        raise HostStateError(f"host gate failed ({result.returncode}): {detail}")


def require_gpu_residency(model: str, minimum_ratio: float = 0.9) -> dict:
    """Load *model* briefly and fail closed unless it is resident in VRAM."""
    payload = json.dumps({
        "model": model,
        "prompt": "Reply with exactly: placement gate ready",
        "stream": False,
        "keep_alive": "10m",
        "options": {"num_predict": 8, "temperature": 0},
    })
    try:
        subprocess.run(
            ["curl", "-sS", "--max-time", "120", f"{ollama_base_url()}/api/generate", "-d", payload],
            capture_output=True, text=True, timeout=125, check=True,
        )
        ps = subprocess.run(
            ["curl", "-sS", "--max-time", "5", f"{ollama_base_url()}/api/ps"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        models = json.loads(ps.stdout).get("models", [])
        row = next((item for item in models if item.get("name") == model), None)
        if row is None:
            # Ollama may retain a same-digest alias when a derived Modelfile
            # differs only in sampling parameters. Match the requested tag's
            # digest rather than falsely declaring placement failure.
            tags = subprocess.run(
                ["curl", "-sS", "--max-time", "5", f"{ollama_base_url()}/api/tags"],
                capture_output=True, text=True, timeout=10, check=True,
            )
            requested = next(
                (item for item in json.loads(tags.stdout).get("models", [])
                 if item.get("name") == model), None
            )
            if requested:
                row = next(
                    (item for item in models if item.get("digest") == requested.get("digest")),
                    None,
                )
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        raise GPUResidencyError(f"placement gate could not inspect {model}: {exc}") from exc
    if row is None:
        raise GPUResidencyError(f"placement gate found no loaded model: {model}")
    size = int(row.get("size") or 0)
    vram = int(row.get("size_vram") or 0)
    ratio = vram / size if size else 0.0
    result = {"model": model, "size": size, "size_vram": vram, "ratio": round(ratio, 4)}
    if ratio < minimum_ratio:
        raise GPUResidencyError(
            f"placement gate failed for {model}: {vram} / {size} bytes in VRAM "
            f"({ratio:.1%}, required {minimum_ratio:.0%})"
        )
    print(f"Placement gate passed: {model} ({vram}/{size} VRAM, {ratio:.1%})")
    return result


# --- Placement, per host class -----------------------------------------------
#
# `ollama ps` cannot carry this proof by itself. The Instrument Log records it
# reporting 29 GB against 34,728 MiB actually allocated, and "100% GPU" for a
# runner with a layer explicitly held back on CPU. A ratio from that source is
# corroboration, never evidence.
#
# The right proof also differs by host class, so it is selected explicitly:
#
#   cuda-single-device  two discrete cards, so residency AND card count both
#                       matter. nvidia-smi per device is primary; a model with
#                       allocation on more than one card fails closed, because a
#                       split model is a different measurement, not a slower one.
#   unified-memory      the Z13 APU. VRAM residency is not the same question
#                       when memory is unified, so it is recorded not-applicable
#                       and endpoint identity is proved instead: a misrouted run
#                       over a tunnel is the failure that actually occurs there.
MIN_DEVICE_ALLOCATION_MIB = 512


def _gpu_index_by_uuid(run=subprocess.run) -> dict[str, int]:
    out = run(["nvidia-smi", "--query-gpu=index,uuid", "--format=csv,noheader"],
              capture_output=True, text=True, timeout=15, check=True).stdout
    mapping = {}
    for line in out.strip().splitlines():
        index, uuid = (part.strip() for part in line.split(",", 1))
        mapping[uuid] = int(index)
    return mapping


def _compute_apps(run=subprocess.run) -> list[tuple[str, int, int]]:
    """(gpu_uuid, pid, used MiB) for every process holding GPU memory."""
    out = run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_gpu_memory",
               "--format=csv,noheader,nounits"],
              capture_output=True, text=True, timeout=15, check=True).stdout
    apps = []
    for line in out.strip().splitlines():
        if not line.strip():
            continue
        uuid, pid, mib = (part.strip() for part in line.split(","))
        apps.append((uuid, int(pid), int(mib)))
    return apps


def daemon_process_tree(endpoint: str, run=subprocess.run) -> set[int]:
    """PIDs of the daemon serving *endpoint* and its children.

    Device totals cannot carry this proof on a host that runs more than one
    daemon: testbench's gpu1 service pins a model with OLLAMA_KEEP_ALIVE=8760h,
    so device 1 always shows ~22 GB allocated by a process that has nothing to
    do with this run. Allocation must be attributed to our own process tree.
    """
    port = endpoint.rsplit(":", 1)[-1].split("/")[0]
    listeners = run(["ss", "-lptnH", f"sport = :{port}"],
                    capture_output=True, text=True, timeout=15, check=False).stdout
    pids = {int(m) for m in re.findall(r"pid=(\d+)", listeners)}
    for pid in list(pids):
        children = run(["pgrep", "-P", str(pid)], capture_output=True, text=True,
                       timeout=15, check=False).stdout
        pids.update(int(line) for line in children.split() if line.strip().isdigit())
    return pids


def model_blob_mib(model: str, endpoint: str, run=subprocess.run) -> int | None:
    """The model's own file size, from /api/tags.

    /api/ps cannot answer how much of a model is resident. On 2026-09-22 it
    reported size 748 MiB and size_vram 748 MiB -- a ratio of 1.0 -- for a
    17,742 MiB blob with 4,468 MiB actually on the card. Its own numbers are
    self-consistent and wrong together, so a ratio computed from them proves
    nothing. /api/tags reports the blob, which is independent of placement.
    """
    try:
        out = run(["curl", "-sS", "--max-time", "5", f"{endpoint}/api/tags"],
                  capture_output=True, text=True, timeout=10, check=True).stdout
        for item in json.loads(out).get("models", []):
            if item.get("name") == model:
                return int(item.get("size") or 0) // 2 ** 20
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        return None
    return None


def verify_placement(
    model: str, *, profile: str, expected_device: int = 0, minimum_ratio: float = 0.9,
    run=subprocess.run, ps_row: dict | None = None, endpoint: str | None = None,
) -> dict:
    """Prove where the model ran, by the rules of this host class.

    Returns an evidence dict; raises GPUResidencyError when the proof fails.
    """
    endpoint = endpoint or ollama_base_url()
    if profile == "unified-memory":
        if not str(endpoint).startswith(("http://127.0.0.1", "http://localhost")):
            raise GPUResidencyError(
                f"placement: unified-memory host must serve its own daemon, got {endpoint}"
            )
        if ps_row is None:
            raise GPUResidencyError("placement: no loaded model reported by the local daemon")
        return {
            "profile": profile, "proved": True, "endpoint": endpoint,
            "vram_residency": "not_applicable_unified_memory",
            "model": model, "size": int(ps_row.get("size") or 0),
        }

    if profile != "cuda-single-device":
        raise GPUResidencyError(f"placement: unknown profile {profile!r}")

    pids = daemon_process_tree(endpoint, run=run)
    if not pids:
        raise GPUResidencyError(
            f"placement: found no daemon process listening on {endpoint}; "
            "placement cannot be attributed"
        )
    index_by_uuid = _gpu_index_by_uuid(run=run)
    ours: dict[int, int] = {}
    for uuid, pid, mib in _compute_apps(run=run):
        if pid in pids and mib >= MIN_DEVICE_ALLOCATION_MIB:
            device = index_by_uuid.get(uuid)
            if device is None:
                raise GPUResidencyError(f"placement: unknown GPU uuid {uuid}")
            ours[device] = ours.get(device, 0) + mib
    devices = sorted(ours)
    if len(devices) > 1:
        raise GPUResidencyError(
            f"placement: this daemon is spread over devices {devices} "
            f"(MiB by device {ours}); pin it to one card"
        )
    if devices != [expected_device]:
        raise GPUResidencyError(
            f"placement: expected allocation on device {expected_device}, "
            f"found {devices or 'none'} for pids {sorted(pids)}"
        )
    evidence = {
        "profile": profile, "proved": True, "device": expected_device,
        "attributed_mib_by_device": ours, "daemon_pids": sorted(pids),
        "endpoint": endpoint, "model": model,
    }
    # Which card is not the whole question. A model can sit on the right device
    # and still be mostly in host RAM, because ollama's fitting pass decides
    # placement at load time against whatever VRAM was free THEN and never
    # revisits it. Check the attributed memory against the model's own blob.
    blob = model_blob_mib(model, endpoint, run=run)
    evidence["blob_mib"] = blob
    if blob:
        resident = ours.get(expected_device, 0)
        share = resident / blob
        evidence["resident_mib"] = resident
        evidence["resident_share"] = round(share, 4)
        if share < minimum_ratio:
            raise GPUResidencyError(
                f"placement: {model} is {resident} MiB on device {expected_device} of a "
                f"{blob} MiB model ({share:.1%}, required {minimum_ratio:.0%}). "
                "Placement is fixed at load time, so free VRAM now does not undo it -- "
                "unload and reload with the card clear."
            )
    if ps_row:
        size, vram = int(ps_row.get("size") or 0), int(ps_row.get("size_vram") or 0)
        ratio = vram / size if size else 0.0
        evidence["reported_ratio"] = round(ratio, 4)
        evidence["reported_ratio_is_corroboration_only"] = True
        # Deliberately not a gate. This is the number that passed a 25%-resident
        # model on 2026-09-22; it is recorded so the two can be compared, never
        # so it can decide anything.
    return evidence


def build_process_env(carrier_env: dict[str, str]) -> dict[str, str]:
    return {
        **os.environ,
        "PYTHONUNBUFFERED": "1",
        "PATH": _privilege_shim_dir() + os.pathsep + os.environ.get("PATH", ""),
        **carrier_env,
    }


def provision_carrier_fixture(fixture_root: Path, carrier_pi_config: Path) -> None:
    """Add only non-secret provider config; never copy Pi auth/runtime state."""
    pi_config = fixture_root / "pi-config"
    pi_config.mkdir(parents=True, exist_ok=True)
    (fixture_root / "home").mkdir(exist_ok=True)
    shutil.copyfile(carrier_pi_config, pi_config / "models.json")


def build_carrier_command(
    pi_argv: list[str], fixture_root: Path, carrier_script: Path | None = None,
    provider: str = "local",
) -> tuple[list[str], dict[str, str]]:
    """Build an explicit sandbox command; default preserves historical dispatch."""
    if carrier_script is None:
        return pi_argv, {}
    env = {
        "HOME": "/work/home",
        "PI_CODING_AGENT_DIR": "/work/pi-config",
        "PATH": "/usr/local/bin:/usr/bin:/bin",
    }
    if provider == "l3-testbench":
        env["BWRAP_SHARE_NET"] = "1"
    env_args = [f"{key}={value}" for key, value in env.items()]
    return [str(carrier_script), str(fixture_root), "env", *env_args, *pi_argv], env


def run_trial(
    task: dict, level: str, model: str, trial_idx: int, ledger_dir: Path, use_ledger: bool,
    trace_dir: Path | None = None, sampling: dict | None = None, provider: str = "local",
    append_system_prompt: str | None = None, carrier_script: Path | None = None,
    carrier_pi_config: Path | None = None,
) -> dict:
    prompt = task["prompts"][level]
    fixture_root = build_fixture(
        task.get("files", {}), prefix=f"{task['task_id']}-{level}", remove=task.get("remove")
    )
    if carrier_script is not None:
        if carrier_pi_config is None:
            raise ValueError("--carrier-pi-config is required with --carrier-script")
        provision_carrier_fixture(fixture_root, carrier_pi_config)
    # Pre-run state, so a scope postcondition can tell "edited the declared file"
    # from "edited the declared file and three others". Taken before pi runs.
    manifest = hash_tree(fixture_root)
    usage_id = None
    sampling = sampling or {}

    # num_ctx/temperature are pinned by model, not CLI flag -- see
    # ensure_pinned_model. --seed has no pi equivalent (dropped, not silently
    # ignored -- see the warning main() prints once if --seed is passed).
    dispatch_model = ensure_pinned_model(
        model, sampling.get("num_ctx"), sampling.get("temperature"), sampling.get("num_gpu"),
        sampling.get("max_output")
    )
    placement_verified = False
    placement_evidence = None
    profile = sampling.get("placement_profile")
    if profile:
        # require_gpu_residency loads the model and returns ollama's own ps row;
        # verify_placement decides what that row is worth on this host class.
        ps_row = None
        if profile == "cuda-single-device" or sampling.get("require_gpu_residency"):
            ps_row = require_gpu_residency(
                dispatch_model, sampling.get("minimum_gpu_ratio", 0.9)
            )
        placement_evidence = verify_placement(
            dispatch_model, profile=profile,
            expected_device=sampling.get("gpu_index", 0),
            minimum_ratio=sampling.get("minimum_gpu_ratio", 0.9),
            ps_row=ps_row,
        )
        placement_verified = bool(placement_evidence.get("proved"))
    elif sampling.get("require_gpu_residency"):
        require_gpu_residency(dispatch_model, sampling.get("minimum_gpu_ratio", 0.9))
        placement_verified = True
    argv = [
        PI_BIN,
        # 127.0.0.1, not localhost. An `ssh -L 11434:127.0.0.1:11434 testbench`
        # tunnel holds [::1]:11434 and getent resolves localhost to ::1 first,
        # so the "ollama" provider (baseUrl localhost:11434) silently reaches
        # the *headless machine's* daemon. gemma4:26b exists on both, so a
        # misrouted run loads fine and reports the wrong GPU with no error.
        # The "local" provider pins the literal IP. See fixtures/
        # desktop-2080-i9-e9-2026-09-11/VOID.md. 2026-09-11.
        "--provider", provider,
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
    if append_system_prompt:
        argv += ["--append-system-prompt", append_system_prompt]
    argv += ["--", prompt]
    inner_argv = list(argv)
    carrier_env = {}
    argv, carrier_env = build_carrier_command(argv, fixture_root, carrier_script, provider)
    # Fallback only -- overwritten below. Kept assigned so the TimeoutExpired
    # handler cannot hit an unbound `start` if the ledger call itself raises.
    start = time.monotonic()
    try:
        if use_ledger:
            usage_id = _ledger_session_start(ledger_dir, prompt)
        # Clock starts AFTER the ledger call, not before it. Fixed 2026-09-07.
        # _ledger_session_start shells out to the operator CLI (two
        # subprocess.run calls, 15 s timeout each), and until this change that
        # sat inside wall_clock_s. Measured back-to-back on the same cell:
        # 15.7 / 16.1 s with the ledger against 11.4 / 10.0 s with --no-ledger,
        # about +4.5 s per trial.
        #
        # It mattered more than a constant offset suggests: a FIXED cost on a
        # VARIABLE quantity inflates an 11 s task by 40% and a 46 s task by 10%,
        # so it does not cancel in a ratio and it systematically flattered slow
        # models. wall_clock_s is the power ranking's speed axis
        # (LOCAL_LANE_POWER_RANKING_PROTOCOL.md, amendment 2026-09-06), so this
        # was contaminating the published ranking.
        #
        # Every wall-clock figure produced before this fix is inflated unless
        # its run passed --no-ledger: roster-walltime-2026-09-05,
        # preswap-wallclock-2026-09-05, testbench-2080-e9-batch1 and
        # z13-wallclock-2026-09-07 are all affected.
        # _ledger_session_end is already outside the window (it runs after
        # wall_clock is computed) and needs no change.
        start = time.monotonic()
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=MAX_WALL_CLOCK_SECONDS,
                cwd=str(fixture_root),  # host-side cwd; carrier changes inner cwd to /work
                # PYTHONUNBUFFERED is load-bearing for diagnosis, not a tidy-up.
                # On timeout the runner SIGKILLs the process and an unflushed
                # buffer dies with it -- unbuffered, partial output survives the
                # kill and shows how far the turn got. (Originally documented
                # against opr; pi's own buffering behavior under a pipe hasn't
                # been separately characterized, so this is left set.)
                env=build_process_env(carrier_env),
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
                "outcome": "unproven",
                "proofs": {"dispatch": None, "scope": None, "placement": placement_verified,
                           "grader": None, "timing": False},
                "unproven_reasons": ["timing"],
                "detail": f"timed out after {MAX_WALL_CLOCK_SECONDS}s",
                "failure_cause": "timeout",
                "wall_clock_s": round(wall_clock, 1),
                "returncode": None,
                "carrier_outer_argv": argv,
                "pi_inner_argv": inner_argv,
                "carrier_env_policy": carrier_env,
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
        proof_report = evaluate_proofs(
            returncode=completed.returncode,
            stdout=completed.stdout,
            trajectory=parse_trajectory(completed.stdout),
            fixture_root=fixture_root,
            placement_verified=placement_verified,
            timed_out=False,
            # Absent an explicit task declaration this proof is assumed satisfied, and
            # the assumption is recorded rather than hidden. Fusion L3 v2 is why: an
            # untested deterministic grader turned 17 correct answers into failures.
            grader_boundary_tested=bool(task.get("grader_boundary_tested", True)),
            grade_checks=[{"name": c.name, "passed": c.passed, "detail": c.detail}
                          for c in grade_result.checks],
        )
        cell_outcome = classify_outcome(grade_result.passed, proof_report)
        # The ledger vocabulary is pass/fail only; an unproven cell is not a model
        # pass, so it closes as fail there while the record keeps the real outcome.
        outcome = "pass" if cell_outcome == "pass" else "fail"
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
            "outcome": cell_outcome,
            "failure_class": (
                None if grade_result.passed
                else classify_failure(grade_result.detail, proof_report.get("trajectory"))
            ),
            "proofs": proof_report["proofs"],
            "placement_evidence": placement_evidence,
            "unproven_reasons": proof_report["missing"],
            "scope_violations": proof_report.get("scope_violations", []),
            "detail": grade_result.detail,
            "failure_cause": (
                None if grade_result.passed else
                (f"unproven_{proof_report['missing'][0]}" if proof_report["missing"] else
                 "grade_failure")
            ),
            "check_score": round(grade_result.score, 3),
            "checks": [
                {"name": c.name, "passed": c.passed, "detail": c.detail}
                for c in grade_result.checks
            ],
            "wall_clock_s": round(wall_clock, 1),
            "returncode": completed.returncode,
            "tok_s": tok_s_probe.get("tok_s") if tok_s_probe else None,
            "tok_s_probe": tok_s_probe,
            "carrier_outer_argv": argv,
            "pi_inner_argv": inner_argv,
            "carrier_env_policy": carrier_env,
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


def cell_summary(cell: list[dict]) -> str:
    """`17/18`, or `16/18 (2 out-of-scope)`, or `16/18 (1 unproven)`.

    Unproven cells stay in the denominator on purpose: hiding them would make a
    contaminated battery read as a smaller clean one. Out-of-scope failures are
    named rather than folded in, because they are a different kind of miss.
    """
    if not cell:
        return "—"
    passed = sum(1 for r in cell if r["passed"])
    notes = []
    unproven = sum(1 for r in cell if r.get("outcome") == "unproven")
    if unproven:
        notes.append(f"{unproven} unproven")
    scope = sum(1 for r in cell if r.get("failure_class") == "out_of_scope")
    if scope:
        notes.append(f"{scope} out-of-scope")
    trunc = sum(1 for r in cell if r.get("failure_class") == "truncated")
    if trunc:
        notes.append(f"{trunc} truncated")
    base = f"{passed}/{len(cell)}"
    return base if not notes else f"{base} ({', '.join(notes)})"


def write_results_md(results: list[dict], output_path: Path) -> None:
    models = sorted({r["model"] for r in results})
    tasks = sorted({r["task_id"] for r in results})
    lines = ["# Local Lane Ladder — Results", ""]
    lines.append(f"Generated from {len(results)} trial records.")
    machines = sorted({r.get("machine", "unknown") for r in results})
    lines.append(f"Producer machine(s): {', '.join(machines)}.")
    unproven = [r for r in results if r.get("outcome") == "unproven"]
    if unproven:
        reasons = sorted({m for r in unproven for m in r.get("unproven_reasons") or []})
        lines.append("")
        lines.append(
            f"> **{len(unproven)} of {len(results)} cells are unproven** "
            f"({', '.join(reasons)}). An unproven cell is evidence about the harness, "
            "not about the model: it is not a failure and is not poolable as a result. "
            "Triage the instrument before reading the spread below."
        )
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
            row.append(cell_summary(cell))
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
                row.append(cell_summary(cell))
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    output_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Local lane eval ladder runner")
    parser.add_argument("--models", nargs="+", required=True, help="Ollama model tags, e.g. gemma4:26b")
    parser.add_argument("--provider", default="local", help="Pi provider name from models.json")
    parser.add_argument("--placement-profile", default=None,
                        choices=["cuda-single-device", "unified-memory"],
                        help="How placement is proved on this host class. "
                             "cuda-single-device fails closed if the model spans cards.")
    parser.add_argument("--gpu-index", type=int, default=0,
                        help="Expected CUDA device for cuda-single-device (default 0)")
    parser.add_argument("--carrier-script", default=None,
                        help="Explicit bwrap carrier script; omitted preserves historical dispatch")
    parser.add_argument("--carrier-pi-config", default=None,
                        help="Non-secret models.json copied into each carrier fixture")
    parser.add_argument("--host-gate-command", default=None,
                        help="Command to run before each cell; nonzero makes the cell invalid.")
    parser.add_argument("--append-system-prompt", default=None,
                        help="Append a behavioral instruction to the Pi system prompt.")
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
        "--require-gpu-residency", action="store_true",
        help="Load each pinned model before scoring and fail closed below 90%% VRAM residency.",
    )
    parser.add_argument(
        "--minimum-gpu-ratio", type=float, default=0.9,
        help="Minimum size_vram/size ratio for --require-gpu-residency (default: 0.9).",
    )
    parser.add_argument(
        "--max-output", type=int, default=None,
        help="Cap model completion tokens via the derived Ollama model; truncation is invalid.",
    )
    parser.add_argument(
        "--num-gpu", type=int, default=None,
        help=(
            "Cap GPU-resident layer count for every cell (VRAM-envelope "
            "ablation -- see gemma4-26b-16gb-cap/FINDING.md for calibrated "
            "envelope-to-num_gpu values on this rig). Unset means full "
            "GPU residency at whatever the model needs."
        ),
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
        "num_gpu": args.num_gpu,
        "max_output": args.max_output,
        "require_gpu_residency": args.require_gpu_residency,
        "placement_profile": args.placement_profile,
        "gpu_index": args.gpu_index,
        "minimum_gpu_ratio": args.minimum_gpu_ratio,
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
    failures = state.setdefault("failures", [])

    for task, level, model, trial in grid:
        key = cell_key(task["task_id"], level, model, trial)
        if key in done:
            continue
        print(f"[{key}] running...")
        try:
            run_host_gate(args.host_gate_command)
            result = run_trial(
                task, level, model, trial, ledger_dir, use_ledger, trace_dir, sampling,
                args.provider, args.append_system_prompt,
                Path(args.carrier_script) if args.carrier_script else None,
                Path(args.carrier_pi_config) if args.carrier_pi_config else None,
            )
        except HostStateError as exc:
            print(f"[{key}] INVALID: {exc}", file=sys.stderr)
            failures.append({"cell_key": key, "task_id": task["task_id"], "level": level,
                             "model": model, "trial": trial, "failure_cause": "host_state",
                             "detail": str(exc)})
            continue
        except GPUResidencyError as exc:
            print(f"[{key}] ABORT: {exc}", file=sys.stderr)
            failures.append({
                "cell_key": key,
                "task_id": task["task_id"],
                "level": level,
                "model": model,
                "trial": trial,
                "failure_cause": "gpu_residency_failure",
                "detail": str(exc),
            })
            save_state(state_path, state)
            return 2
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
