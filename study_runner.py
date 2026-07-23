#!/usr/bin/env python3
"""Reusable, unprivileged, resumable study runner (Section 1's `operator
study-*` commands).

Digest-bound plans and checkpointed runs live under `.operator/studies/`,
mirroring `dogfood_runner.py`'s plan-digest + checkpoint + per-phase-approval
pattern -- but this module has none of that module's root/broker machinery.
It is plain unprivileged file I/O over the same single-user `.operator/`
ledger every other `operator` subcommand already writes to, and it never
imports `operator` (avoiding an import cycle): the four ledger primitives it
needs -- session-start, session-end, evidence-attach, usage-import -- are
passed in by the caller as plain callables (see `LedgerOps`), since
`operator`'s own `study_*_cmd` wrappers already have those functions defined
in the same module and can pass them directly.

Only the mechanics that are testable with fake harnesses today are built
here: the plan/checkpoint/approval state machine, exit-state-aware harness
invocation via harness_adapter, git-based worktree-drift and out-of-scope-
write detection, and ledger integration (sessions/evidence/usage/claims).
Building and running the actual two-row live experiment (Section 3) and
blind judging (Section 4) are deliberately out of scope for this module.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import yaml

import harness_adapter

STUDY_SCHEMA_VERSION = 1
RUN_STATE_SCHEMA_VERSION = 1

PLAN_FIELDS = frozenset(
    {"plan_schema_version", "created_at", "study_id", "workspaces", "task_ids", "phases"}
)
WORKSPACE_FIELDS = frozenset({"row_a", "row_b", "shared"})
PHASE_FIELDS = frozenset(
    {"phase_id", "operation", "row", "harness_id", "model", "args", "mutating"}
)
ROW_VALUES = frozenset({"row_a", "row_b"})

STUDY_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")

# harness_adapter's short profile keys vs. the ledger's registered harness_id
# (`.operator/harnesses/<id>.yaml`) differ for one harness: the adapter calls
# it "agy" (matching the plan's exact CLI profile name); the ledger registry
# entry is "gemini-agy". claude/codex/grok are the same in both.
LEDGER_HARNESS_ID = {"claude": "claude", "codex": "codex", "agy": "gemini-agy", "grok": "grok"}

# usage_import_cmd only has log parsers for these harnesses today (no grok
# parser exists yet) -- study_runner does not add one; grok usage stays at
# whatever session-start's placeholder recorded (never estimated).
USAGE_IMPORT_SUPPORTED = frozenset({"claude", "codex", "agy"})


class StudyError(Exception):
    pass


class StudyPlanError(StudyError):
    pass


class StudyExecutionError(StudyError):
    def __init__(self, message: str, payload: Optional[dict] = None):
        super().__init__(message)
        self.payload = payload or {}


class QuotaExhaustedError(StudyError):
    def __init__(self, payload: dict):
        super().__init__("quota or rate limit exhausted")
        self.payload = payload


class IntegrityViolationError(StudyError):
    def __init__(self, message: str, payload: dict):
        super().__init__(message)
        self.payload = payload


# ---------------------------------------------------------------------------
# Small local primitives (deliberately independent of authority_admin/broker;
# this is a single-user unprivileged ledger, not the P3 boundary).
# ---------------------------------------------------------------------------


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def iso_now() -> str:
    import datetime

    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
        raise


def require_exact_keys(obj: dict, fields: frozenset, label: str) -> None:
    if set(obj.keys()) != set(fields):
        missing = fields - set(obj.keys())
        extra = set(obj.keys()) - fields
        raise StudyPlanError(
            f"{label} has the wrong key set (missing={sorted(missing)}, extra={sorted(extra)})"
        )


@contextlib.contextmanager
def _captured_stdout():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        yield buf


@contextlib.contextmanager
def _empty_stdin():
    """session_end_cmd reads sys.stdin.read() when stdin is not a TTY, which
    would otherwise block or read unrelated bytes when called in-process.
    io.StringIO("") is not a TTY and returns "" immediately."""
    import sys

    original = sys.stdin
    sys.stdin = io.StringIO("")
    try:
        yield
    finally:
        sys.stdin = original


def run_git(args: list[str], cwd: Path) -> Optional[str]:
    try:
        res = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if res.returncode != 0:
        return None
    return res.stdout


def git_worktree_dirty_snapshot(path: Path) -> Optional[list[str]]:
    """Sorted list of paths with uncommitted changes, or None if `path` isn't
    a (readable) git worktree -- callers must treat None as "cannot verify",
    never as "clean"."""
    out = run_git(["status", "--porcelain"], path)
    if out is None:
        return None
    return sorted(line[3:] for line in out.splitlines() if line.strip())


def git_head_sha(path: Path) -> Optional[str]:
    out = run_git(["rev-parse", "HEAD"], path)
    return out.strip() if out else None


# ---------------------------------------------------------------------------
# Operation catalog
# ---------------------------------------------------------------------------


def validate_no_args(args: dict) -> dict:
    return {}


def validate_prompt_args(args: dict) -> dict:
    prompt = args["prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise StudyPlanError("phase 'prompt' must be a non-empty string")
    return {"prompt": prompt}


def validate_implementation_args(args: dict) -> dict:
    prompt = args["prompt"]
    if not isinstance(prompt, str) or not prompt.strip():
        raise StudyPlanError("implementation/repair phase 'prompt' must be a non-empty string")
    allowed_paths = args["allowed_paths"]
    if (
        not isinstance(allowed_paths, list)
        or not allowed_paths
        or not all(isinstance(p, str) and p.strip() for p in allowed_paths)
    ):
        raise StudyPlanError(
            "implementation/repair phase 'allowed_paths' must be a non-empty list of "
            "non-empty strings"
        )
    normalized = sorted({p.strip().strip("/") for p in allowed_paths})
    return {"prompt": prompt, "allowed_paths": normalized}


SHELL_METACHARACTERS = frozenset(";&|`$<>")


def validate_command_args(args: dict) -> dict:
    command = args["command"]
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(c, str) and c for c in command)
    ):
        raise StudyPlanError(
            "validation phase 'command' must be a non-empty list of non-empty argv strings, "
            "not a shell string"
        )
    for token in command:
        if any(ch in token for ch in SHELL_METACHARACTERS):
            raise StudyPlanError(
                f"validation phase 'command' token looks like a shell string, not a plain "
                f"argv token: {token!r}"
            )
    return {"command": list(command)}


@dataclass(frozen=True)
class OperationSpec:
    mutating: bool
    needs_harness: bool
    row_required: bool
    args_schema: frozenset
    validate_args: Callable[[dict], dict]


OPERATIONS: dict[str, OperationSpec] = {
    "preflight": OperationSpec(False, False, False, frozenset(), validate_no_args),
    "supervisor_design": OperationSpec(
        False, True, True, frozenset({"prompt"}), validate_prompt_args
    ),
    "implementation": OperationSpec(
        True, True, True, frozenset({"prompt", "allowed_paths"}), validate_implementation_args
    ),
    "validation": OperationSpec(False, False, True, frozenset({"command"}), validate_command_args),
    "supervisor_review": OperationSpec(
        False, True, True, frozenset({"prompt"}), validate_prompt_args
    ),
    "repair": OperationSpec(
        True, True, True, frozenset({"prompt", "allowed_paths"}), validate_implementation_args
    ),
    "final_verdict": OperationSpec(False, True, True, frozenset({"prompt"}), validate_prompt_args),
    "blinding": OperationSpec(False, False, False, frozenset(), validate_no_args),
    "judge": OperationSpec(False, True, False, frozenset({"prompt"}), validate_prompt_args),
    "export": OperationSpec(False, False, False, frozenset(), validate_no_args),
}

SUPERVISION_CLAIM_LAYER = {
    "supervisor_design": "design",
    "supervisor_review": "evidence",
    "final_verdict": "release",
    "judge": "end_to_end",
}


# ---------------------------------------------------------------------------
# Plan schema, digest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StudyPlan:
    plan_schema_version: int
    created_at: str
    study_id: str
    workspaces: dict
    task_ids: dict
    phases: tuple[dict, ...]
    canonical_json: str
    plan_digest: str


def parse_plan_object(raw: object) -> StudyPlan:
    if not isinstance(raw, dict):
        raise StudyPlanError("plan must be a JSON object")
    require_exact_keys(raw, PLAN_FIELDS, "plan")

    if raw["plan_schema_version"] != STUDY_SCHEMA_VERSION:
        raise StudyPlanError("unsupported plan_schema_version")

    created_at = raw["created_at"]
    if not isinstance(created_at, str) or not created_at:
        raise StudyPlanError("created_at must be a non-empty string")

    study_id = raw["study_id"]
    if not isinstance(study_id, str) or not STUDY_ID_RE.fullmatch(study_id):
        raise StudyPlanError("study_id must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

    workspaces = raw["workspaces"]
    if not isinstance(workspaces, dict):
        raise StudyPlanError("workspaces must be an object")
    require_exact_keys(workspaces, WORKSPACE_FIELDS, "workspaces")
    for field in WORKSPACE_FIELDS:
        value = workspaces[field]
        if not isinstance(value, str) or not value or not os.path.isabs(value):
            raise StudyPlanError(f"workspaces.{field} must be a non-empty absolute path")

    task_ids = raw["task_ids"]
    if not isinstance(task_ids, dict):
        raise StudyPlanError("task_ids must be an object")
    require_exact_keys(task_ids, WORKSPACE_FIELDS, "task_ids")
    for field in WORKSPACE_FIELDS:
        value = task_ids[field]
        if not isinstance(value, str) or not value:
            raise StudyPlanError(f"task_ids.{field} must be a non-empty string")

    raw_phases = raw["phases"]
    if not isinstance(raw_phases, list) or not raw_phases:
        raise StudyPlanError("phases must be a non-empty list")

    phases: list[dict] = []
    for index, phase in enumerate(raw_phases, start=1):
        if not isinstance(phase, dict):
            raise StudyPlanError(f"phase {index} must be an object")
        require_exact_keys(phase, PHASE_FIELDS, f"phase {index}")

        if phase["phase_id"] != index:
            raise StudyPlanError(
                f"phase {index} has phase_id {phase['phase_id']!r}; phase_id must be "
                "sequential starting at 1"
            )

        operation = phase["operation"]
        if not isinstance(operation, str) or operation not in OPERATIONS:
            raise StudyPlanError(f"phase {index} names an unknown operation: {operation!r}")
        spec = OPERATIONS[operation]

        row = phase["row"]
        if spec.row_required:
            if row not in ROW_VALUES:
                raise StudyPlanError(
                    f"phase {index} ({operation}) requires row in {sorted(ROW_VALUES)}, got {row!r}"
                )
        elif row is not None:
            raise StudyPlanError(f"phase {index} ({operation}) must not set a row (got {row!r})")

        harness_id = phase["harness_id"]
        model = phase["model"]
        if spec.needs_harness:
            if not isinstance(harness_id, str) or harness_id not in harness_adapter.PROFILES:
                raise StudyPlanError(
                    f"phase {index} ({operation}) harness_id must be one of "
                    f"{sorted(harness_adapter.PROFILES)}, got {harness_id!r}"
                )
            if not isinstance(model, str) or not model.strip():
                raise StudyPlanError(
                    f"phase {index} ({operation}) requires a non-empty model identifier"
                )
        else:
            if harness_id is not None or model is not None:
                raise StudyPlanError(
                    f"phase {index} ({operation}) must not set harness_id/model "
                    "(this operation does not invoke a harness)"
                )

        args = phase["args"]
        if not isinstance(args, dict):
            raise StudyPlanError(f"phase {index} args must be an object")
        require_exact_keys(args, spec.args_schema, f"phase {index} args")
        normalized_args = spec.validate_args(args)

        mutating = phase["mutating"]
        if not isinstance(mutating, bool):
            raise StudyPlanError(f"phase {index} mutating must be a boolean")
        if mutating != spec.mutating:
            raise StudyPlanError(
                f"phase {index} claims mutating={mutating!r} but {operation!r} is "
                f"mutating={spec.mutating!r}"
            )

        phases.append(
            {
                "phase_id": index,
                "operation": operation,
                "row": row,
                "harness_id": harness_id,
                "model": model,
                "args": normalized_args,
                "mutating": spec.mutating,
            }
        )

    normalized = {
        "plan_schema_version": STUDY_SCHEMA_VERSION,
        "created_at": created_at,
        "study_id": study_id,
        "workspaces": {field: workspaces[field] for field in WORKSPACE_FIELDS},
        "task_ids": {field: task_ids[field] for field in WORKSPACE_FIELDS},
        "phases": phases,
    }
    canonical = canonical_json(normalized)
    digest = sha256_hex(canonical.encode("utf-8"))
    return StudyPlan(
        STUDY_SCHEMA_VERSION,
        created_at,
        study_id,
        normalized["workspaces"],
        normalized["task_ids"],
        tuple(phases),
        canonical,
        digest,
    )


# ---------------------------------------------------------------------------
# Storage layout
# ---------------------------------------------------------------------------


def studies_root(op_dir: str) -> Path:
    return Path(op_dir) / "studies"


def plans_root(op_dir: str) -> Path:
    return studies_root(op_dir) / "plans"


def runs_root(op_dir: str) -> Path:
    return studies_root(op_dir) / "runs"


def plan_store_path(op_dir: str, plan_digest: str) -> Path:
    return plans_root(op_dir) / f"{plan_digest}.json"


def store_plan(op_dir: str, plan: StudyPlan) -> None:
    path = plan_store_path(op_dir, plan.plan_digest)
    if path.exists():
        existing = json.loads(path.read_text())
        if canonical_json(existing) != plan.canonical_json:
            raise StudyPlanError(
                f"plan digest collision: {plan.plan_digest} is already stored with different content"
            )
        return
    atomic_write_bytes(path, (plan.canonical_json + "\n").encode("utf-8"))


def load_stored_plan(op_dir: str, plan_digest: str) -> StudyPlan:
    path = plan_store_path(op_dir, plan_digest)
    if not path.exists():
        raise StudyError(f"no stored plan with digest {plan_digest}")
    raw = json.loads(path.read_text())
    plan = parse_plan_object(raw)
    if plan.plan_digest != plan_digest:
        raise StudyError("stored plan does not hash to its own file name")
    return plan


def run_dir(op_dir: str, run_id: str) -> Path:
    return runs_root(op_dir) / run_id


def checkpoints_dir(op_dir: str, run_id: str) -> Path:
    return run_dir(op_dir, run_id) / "checkpoints"


def checkpoint_path(op_dir: str, run_id: str, phase_id: int, operation: str, state: str) -> Path:
    return checkpoints_dir(op_dir, run_id) / f"{phase_id:04d}-{operation}.{state}.json"


def new_run_id(plan_digest: str) -> str:
    return sha256_hex(f"{plan_digest}:{os.urandom(16).hex()}".encode("ascii"))[:32]


def write_run_state(
    op_dir: str, run_id: str, plan: StudyPlan, current_phase: int, status: str
) -> None:
    state = {
        "run_state_schema_version": RUN_STATE_SCHEMA_VERSION,
        "run_id": run_id,
        "plan_digest": plan.plan_digest,
        "phase_count": len(plan.phases),
        "current_phase": current_phase,
        "status": status,
    }
    atomic_write_bytes(
        run_dir(op_dir, run_id) / "run-state.json", json.dumps(state, indent=2).encode("utf-8")
    )


def create_run(op_dir: str, plan: StudyPlan) -> str:
    run_id = new_run_id(plan.plan_digest)
    target = run_dir(op_dir, run_id)
    target.mkdir(parents=True, exist_ok=True)
    (target / "checkpoints").mkdir(parents=True, exist_ok=True)
    atomic_write_bytes(target / "plan.json", (plan.canonical_json + "\n").encode("utf-8"))
    write_run_state(op_dir, run_id, plan, 1, "running")
    append_run_history(op_dir, run_id, {"event": "run_created", "plan_digest": plan.plan_digest})
    return run_id


def load_run_plan(op_dir: str, run_id: str) -> StudyPlan:
    path = run_dir(op_dir, run_id) / "plan.json"
    if not path.exists():
        raise StudyError(f"no such run: {run_id}")
    raw = json.loads(path.read_text())
    return parse_plan_object(raw)


def append_run_history(op_dir: str, run_id: str, entry: dict) -> None:
    path = run_dir(op_dir, run_id) / "run-history.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    line = canonical_json({**entry, "recorded_at": iso_now()}) + "\n"
    with open(path, "a") as handle:
        handle.write(line)


def phase_checkpoint_state(op_dir: str, run_id: str, phase: dict) -> tuple[str, Optional[dict]]:
    for state in ("completed", "failed", "waiting_quota", "pending"):
        path = checkpoint_path(op_dir, run_id, phase["phase_id"], phase["operation"], state)
        if path.exists():
            return state, json.loads(path.read_text())
    return "not_started", None


def write_checkpoint(op_dir: str, run_id: str, phase: dict, state: str, payload: dict) -> None:
    path = checkpoint_path(op_dir, run_id, phase["phase_id"], phase["operation"], state)
    atomic_write_bytes(path, json.dumps(payload, indent=2, default=str).encode("utf-8"))


def clear_checkpoint(op_dir: str, run_id: str, phase: dict, state: str) -> None:
    path = checkpoint_path(op_dir, run_id, phase["phase_id"], phase["operation"], state)
    path.unlink(missing_ok=True)


def compute_request_digest(plan_digest: str, phase: dict) -> str:
    payload = {
        "plan_digest": plan_digest,
        "phase_id": phase["phase_id"],
        "operation": phase["operation"],
        "args": phase["args"],
    }
    return sha256_hex(canonical_json(payload).encode("utf-8"))


# ---------------------------------------------------------------------------
# Ledger integration (session/evidence/usage/claims)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LedgerOps:
    """Bundles the four `operator` ledger primitives study_runner needs.
    Passed in by the caller (operator's study_*_cmd wrappers, which already
    have these functions defined in the same module) so study_runner never
    imports `operator` back -- avoiding an import cycle, and letting tests
    substitute stub callables."""

    session_start: Callable[[argparse.Namespace], int]
    session_end: Callable[[argparse.Namespace], int]
    evidence_attach: Callable[[argparse.Namespace], int]
    usage_import: Callable[[argparse.Namespace], int]
    claim_add: Callable[[argparse.Namespace], int]


# session-start's real --lane choices are local/frontier_driver/frontier_author
# (checked directly against the argparse definition) -- there is no "study"
# lane, so a role must map onto one of those three rather than inventing a
# fourth value that other lane-aware tooling (usage-summary, doctor) won't
# recognize. Mirrors opr.get_frontier_lane()'s own review-vs-author split.
LANE_FOR_ROLE = {
    harness_adapter.Role.SUPERVISOR.value: "frontier_driver",
    harness_adapter.Role.JUDGE.value: "frontier_driver",
    harness_adapter.Role.IMPLEMENTER.value: "frontier_author",
}


def _open_session(
    ledger_ops: LedgerOps, task_id: str, harness_id: str, role: harness_adapter.Role
) -> Optional[str]:
    ns = argparse.Namespace(
        task_id=task_id,
        harness_id=harness_id,
        force=True,
        lane=LANE_FOR_ROLE[role.value],
        task_class=None,
    )
    with _captured_stdout() as buf:
        ledger_ops.session_start(ns)
    match = re.search(r"usage-\d+", buf.getvalue())
    return match.group(0) if match else None


def _close_session(ledger_ops: LedgerOps, usage_id: str, outcome: str) -> None:
    ns = argparse.Namespace(
        usage_id=usage_id,
        force=True,
        status=None,
        outcome=outcome,
        cost=0.0,
        paste=False,
        attach_crystal=None,
        require_crystal=False,
        by=None,
    )
    with _empty_stdin(), _captured_stdout():
        ledger_ops.session_end(ns)


def _attach_evidence(
    ledger_ops: LedgerOps,
    task_id: str,
    path: str,
    evidence_type: str,
    by: str,
    notes: str,
    diff_base: Optional[str] = None,
) -> None:
    ns = argparse.Namespace(
        path_or_url=path,
        claim=None,
        type=evidence_type,
        diff_base=diff_base,
        task_id=task_id,
        by=by,
        hash=None,
        notes=notes,
        verify_cmd=None,
        status=None,
        verdict=None,
        verified_by=None,
    )
    with _captured_stdout():
        ledger_ops.evidence_attach(ns)


def _import_usage(
    ledger_ops: LedgerOps,
    ledger_harness_id: str,
    task_id: str,
    since: str,
    until: str,
    session_id: Optional[str],
) -> None:
    ns = argparse.Namespace(
        harness=ledger_harness_id,
        task_id=task_id,
        session_id=session_id,
        since=since,
        until=until,
        dry_run=False,
        source_dir=None,
        machine=None,
    )
    with _captured_stdout():
        ledger_ops.usage_import(ns)


def _record_supervision_claim(ledger_ops: LedgerOps, task_id: str, phase: dict) -> None:
    layer = SUPERVISION_CLAIM_LAYER.get(phase["operation"])
    if not layer:
        return
    ns = argparse.Namespace(
        type="supervision_credit",
        text=f"{phase['operation']} phase {phase['phase_id']} completed (harness={phase['harness_id']})",
        task_id=task_id,
        by=phase["harness_id"],
        gate=f"study phase {phase['phase_id']} ({phase['operation']})",
        layer=layer,
    )
    with _captured_stdout():
        ledger_ops.claim_add(ns)


def _extract_session_id(result: harness_adapter.AdapterResult) -> Optional[str]:
    if result.parsed_output is None:
        return None
    value = result.parsed_output.get("session_id")
    return value if isinstance(value, str) else None


def _write_temp_artifact(run_artifacts_dir: Path, name: str, content: str) -> Path:
    run_artifacts_dir.mkdir(parents=True, exist_ok=True)
    path = run_artifacts_dir / name
    path.write_text(content)
    return path


def _render_transcript(result: harness_adapter.AdapterResult) -> str:
    lines = [
        f"exit_state: {result.exit_state.value}",
        f"returncode: {result.returncode}",
        f"duration_seconds: {result.duration_seconds}",
        f"argv: {list(result.argv)}",
        f"initiator: {result.initiator}",
        "--- stdout ---",
        result.stdout,
        "--- stderr ---",
        result.stderr,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase handlers
# ---------------------------------------------------------------------------


class PhaseContext:
    def __init__(self, op_dir: str, run_id: str, plan: StudyPlan, ledger_ops: LedgerOps):
        self.op_dir = op_dir
        self.run_id = run_id
        self.plan = plan
        self.ledger_ops = ledger_ops

    @property
    def artifacts_dir(self) -> Path:
        return run_dir(self.op_dir, self.run_id) / "artifacts"

    def workspace_for(self, row: Optional[str]) -> Path:
        return Path(self.plan.workspaces[row if row else "shared"])

    def task_for(self, row: Optional[str]) -> str:
        return self.plan.task_ids[row if row else "shared"]


def _run_harness_phase(ctx: PhaseContext, phase: dict, role: harness_adapter.Role) -> dict:
    workspace = ctx.workspace_for(phase["row"])
    task_id = ctx.task_for(phase["row"])
    ledger_harness_id = LEDGER_HARNESS_ID.get(phase["harness_id"], phase["harness_id"])

    usage_id = _open_session(ctx.ledger_ops, task_id, ledger_harness_id, role)
    started_at = iso_now()

    result = harness_adapter.invoke(
        phase["harness_id"], role, phase["model"], phase["args"]["prompt"], workspace
    )

    ended_at = iso_now()

    transcript_path = _write_temp_artifact(
        ctx.artifacts_dir,
        f"{phase['phase_id']:04d}-{phase['operation']}-transcript.txt",
        _render_transcript(result),
    )

    if usage_id:
        # session-end's --outcome vocabulary is useful/partial/no_go/quarantined/
        # reverted/unknown -- not "success"/"failed". This bypasses argparse's
        # own choices= validation entirely (direct in-process call), so it must
        # be gotten right here rather than relying on that check.
        outcome = "useful" if result.exit_state == harness_adapter.ExitState.SUCCESS else "no_go"
        _close_session(ctx.ledger_ops, usage_id, outcome)
        note = f"study phase {phase['phase_id']} ({phase['operation']}) transcript"
        if result.initiator:
            note += f" (initiated by {result.initiator})"
        _attach_evidence(
            ctx.ledger_ops,
            task_id,
            str(transcript_path),
            "transcript",
            phase["harness_id"],
            note,
        )
        if phase["harness_id"] in USAGE_IMPORT_SUPPORTED:
            _import_usage(
                ctx.ledger_ops,
                ledger_harness_id,
                task_id,
                started_at,
                ended_at,
                _extract_session_id(result),
            )

    payload = {
        "task_id": task_id,
        "usage_id": usage_id,
        "started_at": started_at,
        "ended_at": ended_at,
        "transcript_path": str(transcript_path),
        "exit_state": result.exit_state.value,
        "returncode": result.returncode,
        "argv": list(result.argv),
        # Caller provenance -- see harness_adapter.resolve_initiator_identity().
        # None unless the calling process explicitly declared itself via
        # OPERATOR_INITIATOR_HARNESS/OPERATOR_INITIATOR_SESSION_ID.
        "initiator": result.initiator,
    }
    return payload, result


def load_task_repo(op_dir: str, task_id: str) -> Optional[str]:
    task_path = Path(op_dir) / "tasks" / f"{task_id}.yaml"
    if not task_path.exists():
        return None
    data = yaml.safe_load(task_path.read_text()) or {}
    repo = data.get("repo")
    return repo if isinstance(repo, str) and repo else None


def phase_preflight(ctx: PhaseContext, phase: dict) -> dict:
    baselines = {}
    for key in WORKSPACE_FIELDS:
        path = Path(ctx.plan.workspaces[key])
        if not path.is_dir():
            raise StudyExecutionError(f"workspace '{key}' does not exist: {path}")
        baselines[key] = {
            "path": str(path),
            "dirty_files": git_worktree_dirty_snapshot(path),
            "head": git_head_sha(path),
        }

    # implementation/repair phases' diff evidence is generated by
    # evidence_attach_cmd itself from task["repo"], not from a path this
    # module hands it -- so each row's task must already be bound to that
    # row's workspace, or diffs would silently come from the wrong repo.
    for row in ("row_a", "row_b"):
        task_id = ctx.plan.task_ids[row]
        repo = load_task_repo(ctx.op_dir, task_id)
        expected = ctx.plan.workspaces[row]
        if repo != expected:
            raise StudyExecutionError(
                f"task '{task_id}' (task_ids.{row}) has repo={repo!r}, expected "
                f"{expected!r} (workspaces.{row}); fix the task's repo field before running"
            )

    frozen = {}
    for ph in ctx.plan.phases:
        harness_id = ph["harness_id"]
        if harness_id and harness_id not in frozen:
            frozen_adapter = harness_adapter.freeze(
                harness_id, harness_adapter.Role.SUPERVISOR, ph["model"], ctx.workspace_for(None)
            )
            frozen[harness_id] = {
                "model": frozen_adapter.model,
                "executable_path": frozen_adapter.executable_path,
                "cli_version": frozen_adapter.cli_version,
                "argv": list(frozen_adapter.argv),
            }

    return {"workspaces": baselines, "frozen_harnesses": frozen}


# supervisor_design/supervisor_review/final_verdict run against their row's
# workspace under the SUPERVISOR role; judge runs against the shared
# (blinded-bundle) workspace under the JUDGE role. Both are read-only roles,
# and both get the same "did the filesystem move anyway" drift check --
# a judge changing files is exactly as much an integrity violation as a
# supervisor doing so.
READONLY_HARNESS_ROLES = {
    "supervisor_design": harness_adapter.Role.SUPERVISOR,
    "supervisor_review": harness_adapter.Role.SUPERVISOR,
    "final_verdict": harness_adapter.Role.SUPERVISOR,
    "judge": harness_adapter.Role.JUDGE,
}


def phase_readonly_harness(ctx: PhaseContext, phase: dict) -> dict:
    workspace = ctx.workspace_for(phase["row"])
    before = git_worktree_dirty_snapshot(workspace)
    role = READONLY_HARNESS_ROLES[phase["operation"]]
    payload, result = _run_harness_phase(ctx, phase, role)
    after = git_worktree_dirty_snapshot(workspace)

    if result.exit_state == harness_adapter.ExitState.QUOTA_EXHAUSTED:
        raise QuotaExhaustedError(payload)

    if before is not None and after is not None and before != after:
        payload["integrity_violation"] = (
            f"{phase['operation']} phase (read-only role) changed the workspace filesystem: "
            f"before={before}, after={after}"
        )
        payload["integrity_unverifiable"] = False
    else:
        payload["integrity_violation"] = None
        payload["integrity_unverifiable"] = before is None or after is None

    if result.exit_state != harness_adapter.ExitState.SUCCESS:
        raise StudyExecutionError(
            f"{phase['operation']} phase failed: {result.exit_state.value}", payload=payload
        )
    if payload["integrity_violation"]:
        raise IntegrityViolationError(payload["integrity_violation"], payload=payload)

    _record_supervision_claim(ctx.ledger_ops, ctx.task_for(phase["row"]), phase)
    return payload


def phase_implementer(ctx: PhaseContext, phase: dict) -> dict:
    workspace = ctx.workspace_for(phase["row"])
    task_id = ctx.task_for(phase["row"])
    before_head = git_head_sha(workspace)
    before_files = set(git_worktree_dirty_snapshot(workspace) or [])

    payload, result = _run_harness_phase(ctx, phase, harness_adapter.Role.IMPLEMENTER)

    after_files_list = git_worktree_dirty_snapshot(workspace)
    touched: list[str] = []
    violation = None
    unverifiable = False
    if after_files_list is None:
        unverifiable = True
    else:
        touched = sorted(set(after_files_list) - before_files)
        allowed = phase["args"]["allowed_paths"]
        out_of_scope = [
            f for f in touched if not any(f == a or f.startswith(a + "/") for a in allowed)
        ]
        if out_of_scope:
            violation = f"{phase['operation']} wrote outside allowed_paths: {out_of_scope}"

        if before_head:
            # evidence_attach_cmd's own --type diff path always regenerates
            # the diff itself from task["repo"] (never trusts a path_or_url
            # we hand it for this type), so phase_preflight verifies
            # task["repo"] == this row's workspace up front rather than this
            # handler duplicating diff generation here.
            _attach_evidence(
                ctx.ledger_ops,
                task_id,
                str(workspace),
                "diff",
                phase["harness_id"],
                f"study phase {phase['phase_id']} ({phase['operation']}) diff",
                diff_base=before_head,
            )

    payload["touched_paths"] = touched
    payload["integrity_violation"] = violation
    payload["integrity_unverifiable"] = unverifiable

    if result.exit_state == harness_adapter.ExitState.QUOTA_EXHAUSTED:
        raise QuotaExhaustedError(payload)
    if result.exit_state != harness_adapter.ExitState.SUCCESS:
        raise StudyExecutionError(
            f"{phase['operation']} phase failed: {result.exit_state.value}", payload=payload
        )
    if violation:
        raise IntegrityViolationError(violation, payload=payload)
    return payload


def phase_validation(ctx: PhaseContext, phase: dict) -> dict:
    workspace = ctx.workspace_for(phase["row"])
    task_id = ctx.task_for(phase["row"])
    command = phase["args"]["command"]
    try:
        res = subprocess.run(
            command, cwd=str(workspace), capture_output=True, text=True, timeout=1800
        )
    except FileNotFoundError as exc:
        raise StudyExecutionError(f"validation command executable not found: {exc}")
    except subprocess.TimeoutExpired:
        raise StudyExecutionError("validation command timed out")

    output_path = _write_temp_artifact(
        ctx.artifacts_dir,
        f"{phase['phase_id']:04d}-validation-output.txt",
        f"command: {command}\nreturncode: {res.returncode}\n--- stdout ---\n{res.stdout}\n"
        f"--- stderr ---\n{res.stderr}",
    )
    _attach_evidence(
        ctx.ledger_ops,
        task_id,
        str(output_path),
        "test_output",
        "study_runner",
        f"study phase {phase['phase_id']} (validation) output",
    )

    payload = {
        "command": command,
        "returncode": res.returncode,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "output_path": str(output_path),
    }
    if res.returncode != 0:
        raise StudyExecutionError(f"validation command exited {res.returncode}", payload=payload)
    return payload


def compute_blind_labels(plan_digest: str) -> dict:
    first_byte = int(plan_digest[:2], 16)
    if first_byte % 2 == 0:
        return {"row_a": "A", "row_b": "B"}
    return {"row_a": "B", "row_b": "A"}


def phase_blinding(ctx: PhaseContext, phase: dict) -> dict:
    labels = compute_blind_labels(ctx.plan.plan_digest)
    payload = {"labels": labels}
    _write_temp_artifact(ctx.artifacts_dir, "blinding_manifest.json", json.dumps(payload, indent=2))
    return payload


def phase_export(ctx: PhaseContext, phase: dict) -> dict:
    payload = {
        "study_id": ctx.plan.study_id,
        "plan_digest": ctx.plan.plan_digest,
        "exported_at": iso_now(),
    }
    _write_temp_artifact(ctx.artifacts_dir, "export_manifest.json", json.dumps(payload, indent=2))
    return payload


PHASE_HANDLERS: dict[str, Callable[[PhaseContext, dict], dict]] = {
    "preflight": phase_preflight,
    "supervisor_design": phase_readonly_harness,
    "implementation": phase_implementer,
    "validation": phase_validation,
    "supervisor_review": phase_readonly_harness,
    "repair": phase_implementer,
    "final_verdict": phase_readonly_harness,
    "blinding": phase_blinding,
    "judge": phase_readonly_harness,
    "export": phase_export,
}


# ---------------------------------------------------------------------------
# Run execution
# ---------------------------------------------------------------------------


def execute_phase(
    ctx: PhaseContext,
    phase: dict,
    *,
    approve_phase: Optional[int],
    acknowledge_quota_reset: bool,
) -> dict:
    request_digest = compute_request_digest(ctx.plan.plan_digest, phase)
    state, stored = phase_checkpoint_state(ctx.op_dir, ctx.run_id, phase)

    if state == "completed":
        if stored.get("request_digest") == request_digest:
            return {**stored["result"], "status": "completed", "idempotent_replay": True}
        raise StudyError(
            f"phase {phase['phase_id']} ({phase['operation']}) was completed under a "
            "different request digest -- plan_replaced"
        )

    if state == "waiting_quota":
        if not acknowledge_quota_reset:
            return {"status": "waiting_quota", "phase_id": phase["phase_id"]}
        clear_checkpoint(ctx.op_dir, ctx.run_id, phase, "waiting_quota")

    if state == "failed":
        raise StudyError(
            f"phase {phase['phase_id']} ({phase['operation']}) previously failed; resolve and "
            "resume is not yet supported for hard failures in this slice"
        )

    if phase["mutating"] and approve_phase != phase["phase_id"]:
        write_run_state(ctx.op_dir, ctx.run_id, ctx.plan, phase["phase_id"], "awaiting_approval")
        return {"status": "awaiting_approval", "phase_id": phase["phase_id"]}

    write_checkpoint(
        ctx.op_dir,
        ctx.run_id,
        phase,
        "pending",
        {"request_digest": request_digest, "started_at": iso_now()},
    )

    handler = PHASE_HANDLERS[phase["operation"]]
    try:
        result = handler(ctx, phase)
    except QuotaExhaustedError as exc:
        write_checkpoint(
            ctx.op_dir,
            ctx.run_id,
            phase,
            "waiting_quota",
            {"request_digest": request_digest, "payload": exc.payload, "recorded_at": iso_now()},
        )
        append_run_history(
            ctx.op_dir,
            ctx.run_id,
            {
                "event": "phase_waiting_quota",
                "phase_id": phase["phase_id"],
                "operation": phase["operation"],
                "note": "quota/rate-limit exhaustion; not counted as a harness failure",
            },
        )
        return {"status": "waiting_quota", "phase_id": phase["phase_id"]}
    except (StudyExecutionError, IntegrityViolationError) as exc:
        write_checkpoint(
            ctx.op_dir,
            ctx.run_id,
            phase,
            "failed",
            {
                "request_digest": request_digest,
                "error": str(exc),
                "payload": getattr(exc, "payload", {}),
                "recorded_at": iso_now(),
            },
        )
        append_run_history(
            ctx.op_dir,
            ctx.run_id,
            {
                "event": "phase_failed",
                "phase_id": phase["phase_id"],
                "operation": phase["operation"],
                "error": str(exc),
            },
        )
        raise

    write_checkpoint(
        ctx.op_dir,
        ctx.run_id,
        phase,
        "completed",
        {"request_digest": request_digest, "result": result, "recorded_at": iso_now()},
    )
    append_run_history(
        ctx.op_dir,
        ctx.run_id,
        {
            "event": "phase_completed",
            "phase_id": phase["phase_id"],
            "operation": phase["operation"],
        },
    )
    return {**result, "status": "completed", "idempotent_replay": False}


def execute_run(
    op_dir: str,
    run_id: str,
    ledger_ops: LedgerOps,
    *,
    approve_phase: Optional[int] = None,
    acknowledge_quota_reset: bool = False,
) -> dict:
    plan = load_run_plan(op_dir, run_id)
    ctx = PhaseContext(op_dir, run_id, plan, ledger_ops)

    for phase in plan.phases:
        outcome = execute_phase(
            ctx, phase, approve_phase=approve_phase, acknowledge_quota_reset=acknowledge_quota_reset
        )
        status = outcome.get("status")
        if status in ("awaiting_approval", "waiting_quota"):
            write_run_state(op_dir, run_id, plan, phase["phase_id"], status)
            return {"run_id": run_id, "status": status, "phase_id": phase["phase_id"]}

    write_run_state(op_dir, run_id, plan, len(plan.phases), "completed")
    return {"run_id": run_id, "status": "completed", "phase_id": len(plan.phases)}


def compute_run_status(op_dir: str, run_id: str) -> dict:
    plan = load_run_plan(op_dir, run_id)
    phases_status = []
    overall = "completed"
    overall_set = False
    first_incomplete_phase_id = None
    for phase in plan.phases:
        state, _ = phase_checkpoint_state(op_dir, run_id, phase)
        phases_status.append(
            {"phase_id": phase["phase_id"], "operation": phase["operation"], "state": state}
        )
        if state != "completed" and not overall_set:
            overall = state if state != "not_started" else "pending"
            first_incomplete_phase_id = phase["phase_id"]
            overall_set = True

    # "awaiting_approval" has no dedicated checkpoint state (a mutating phase
    # blocked on approval never gets a "pending" checkpoint written for
    # itself) -- it only lives in run-state.json, which write_run_state
    # otherwise treats as a convenience cache, never the source of truth.
    # Cross-check it here rather than trusting it blindly: only honor it if
    # it names the exact phase this scan independently found to be the first
    # incomplete one.
    if overall == "pending":
        state_path = run_dir(op_dir, run_id) / "run-state.json"
        if state_path.exists():
            run_state = json.loads(state_path.read_text())
            if (
                run_state.get("status") == "awaiting_approval"
                and run_state.get("current_phase") == first_incomplete_phase_id
            ):
                overall = "awaiting_approval"

    return {
        "run_id": run_id,
        "plan_digest": plan.plan_digest,
        "status": overall,
        "phases": phases_status,
    }


# ---------------------------------------------------------------------------
# Command-level entry points (called by operator's study_*_cmd wrappers)
# ---------------------------------------------------------------------------


def study_plan_command(op_dir: str, plan_path: str) -> dict:
    raw = json.loads(Path(plan_path).read_text())
    plan = parse_plan_object(raw)
    store_plan(op_dir, plan)
    return {
        "plan_digest": plan.plan_digest,
        "study_id": plan.study_id,
        "phase_count": len(plan.phases),
    }


def study_run_command(
    op_dir: str,
    plan_digest: str,
    run_id: Optional[str],
    ledger_ops: LedgerOps,
    *,
    approve_phase: Optional[int] = None,
) -> dict:
    if run_id:
        RUN_ID_RE.fullmatch(run_id) or (_ for _ in ()).throw(
            StudyError("run_id must be 32 lowercase hex characters")
        )
        if not run_dir(op_dir, run_id).exists():
            plan = load_stored_plan(op_dir, plan_digest)
            actual_run_id = create_run(op_dir, plan)
            if actual_run_id != run_id:
                raise StudyError(
                    "run_id does not match a freshly created run; use study-resume instead"
                )
    else:
        plan = load_stored_plan(op_dir, plan_digest)
        run_id = create_run(op_dir, plan)

    return execute_run(op_dir, run_id, ledger_ops, approve_phase=approve_phase)


def study_status_command(op_dir: str, run_id: str) -> dict:
    return compute_run_status(op_dir, run_id)


def study_resume_command(
    op_dir: str,
    run_id: str,
    ledger_ops: LedgerOps,
    *,
    approve_phase: Optional[int] = None,
    acknowledge_quota_reset: bool = False,
) -> dict:
    return execute_run(
        op_dir,
        run_id,
        ledger_ops,
        approve_phase=approve_phase,
        acknowledge_quota_reset=acknowledge_quota_reset,
    )
