#!/usr/bin/python3
"""Typed, resumable privileged dogfood runner (Issue #8, slice 1).

Operational tooling that replaces the manual sudo relay used during Issue #7
dogfood with a reviewed, digest-bound plan and a checkpointed, idempotent
executor. This module sits next to the P3 authority boundary
(authority_broker.py / authority_admin.py) and reuses its atomic-write,
path-safety, and digest primitives directly -- it does not weaken, extend, or
reimplement that boundary. See docs/DOGFOOD_RUNNER_OPERATIONS.md for the
review/execution/interruption/recovery workflow and the current list of
implemented vs. open phase types.
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import authority_admin
import authority_broker as broker

AdminError = authority_admin.AdminError
InstallLayout = authority_admin.InstallLayout
DeploymentIdentity = authority_admin.DeploymentIdentity

PLAN_SCHEMA_VERSION = 1
RUN_STATE_SCHEMA_VERSION = 1

PLAN_FIELDS = frozenset(
    {
        "plan_schema_version",
        "created_at",
        "created_by_uid",
        "ledger_id",
        "policy_binding",
        "expected_release_digest",
        "host_paths",
        "phases",
    }
)
POLICY_BINDING_FIELDS = frozenset({"policy_id", "generation", "sha256"})
HOST_PATH_FIELDS = frozenset({"install_root", "config_root", "state_root", "runtime_root"})
PHASE_FIELDS = frozenset({"phase_id", "operation", "args", "mutating"})

RUN_ID_RE = re.compile(r"^[0-9a-f]{32}$")


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DogfoodLayout:
    anchor: Path
    admin_root: Path
    plans_root: Path
    runs_root: Path

    @classmethod
    def production(cls) -> DogfoodLayout:
        admin_root = Path("/var/lib/operator-control-plane-admin")
        return cls(
            anchor=Path("/"),
            admin_root=admin_root,
            plans_root=admin_root / "dogfood-plans",
            runs_root=admin_root / "dogfood-runs",
        )

    @classmethod
    def under(cls, root: Path) -> DogfoodLayout:
        root = root.resolve()
        admin_root = root / "var/lib/operator-control-plane-admin"
        return cls(
            anchor=root,
            admin_root=admin_root,
            plans_root=admin_root / "dogfood-plans",
            runs_root=admin_root / "dogfood-runs",
        )


def dogfood_identity(admin_uid: int, admin_gid: int) -> DeploymentIdentity:
    # broker_user/broker_uid/broker_gid/socket_group/socket_gid are unused: DogfoodLayout
    # paths are, by construction, never within any InstallLayout's state_root/runtime_root
    # (they live under a sibling admin_root), so authority_admin's
    # expected_directory_owner/expected_directory_gid always resolve through
    # admin_uid/admin_gid regardless of these placeholder values.
    return DeploymentIdentity(admin_uid, admin_gid, "dogfood-admin", 0, 0, "dogfood-admin", 0)


def ensure_dogfood_layout(
    dogfood_layout: DogfoodLayout, install_layout: InstallLayout, identity: DeploymentIdentity
) -> None:
    for path in (dogfood_layout.admin_root, dogfood_layout.plans_root, dogfood_layout.runs_root):
        authority_admin.ensure_directory(
            path, 0o700, identity.admin_uid, identity.admin_gid, install_layout, identity
        )


# ---------------------------------------------------------------------------
# Plan schema, digest, bindings
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PhaseSpec:
    mutating: bool
    args_schema: frozenset[str]
    handler: Callable[[InstallLayout, int, int, dict], dict]


def phase_installation_verification(
    layout: InstallLayout, admin_uid: int, admin_gid: int, args: dict
) -> dict:
    return authority_admin.audit_deployment(layout, admin_uid, admin_gid)


def phase_privilege_evidence(
    layout: InstallLayout, admin_uid: int, admin_gid: int, args: dict
) -> dict:
    return authority_admin.collect_evidence_deployment(layout, admin_uid, admin_gid)


def phase_final_audit(layout: InstallLayout, admin_uid: int, admin_gid: int, args: dict) -> dict:
    return authority_admin.audit_deployment(layout, admin_uid, admin_gid)


# Slice 1 covers only the two read-only phase types with an existing clean
# primitive to wrap plus the one mutating phase type with an existing clean
# primitive to wrap. Remaining phase types (service lifecycle, enrollment,
# reconciliation, rotation, outage/recovery, revocation checks) are deferred
# to later slices and are added here as additional catalog entries against
# this same engine -- not architectural changes. See
# docs/DOGFOOD_RUNNER_OPERATIONS.md.
PHASE_CATALOG: dict[str, PhaseSpec] = {
    "installation_verification": PhaseSpec(
        mutating=False, args_schema=frozenset(), handler=phase_installation_verification
    ),
    "privilege_evidence": PhaseSpec(
        mutating=True, args_schema=frozenset(), handler=phase_privilege_evidence
    ),
    "final_audit": PhaseSpec(
        mutating=False, args_schema=frozenset(), handler=phase_final_audit
    ),
}


@dataclass(frozen=True)
class DogfoodPlan:
    plan_schema_version: int
    created_at: str
    created_by_uid: int
    ledger_id: str
    policy_binding: dict
    expected_release_digest: str
    host_paths: dict
    phases: tuple[dict, ...]
    canonical_json: str
    plan_digest: str


def parse_plan_object(raw: object) -> DogfoodPlan:
    if not isinstance(raw, dict):
        raise AdminError("invalid_plan", "plan must be a JSON object")
    authority_admin.require_exact_keys(raw, PLAN_FIELDS, "plan")
    if raw["plan_schema_version"] != PLAN_SCHEMA_VERSION:
        raise AdminError("unsupported_plan_schema", "unsupported plan schema")

    created_at = raw["created_at"]
    if not isinstance(created_at, str) or not created_at:
        raise AdminError("invalid_plan", "created_at must be a non-empty string")

    created_by_uid = raw["created_by_uid"]
    if (
        not isinstance(created_by_uid, int)
        or isinstance(created_by_uid, bool)
        or created_by_uid != 0
    ):
        raise AdminError("invalid_plan", "created_by_uid must be 0")

    ledger_id = authority_admin.require_token(raw["ledger_id"], "ledger_id")

    policy_binding = raw["policy_binding"]
    if not isinstance(policy_binding, dict):
        raise AdminError("invalid_plan", "policy_binding must be an object")
    authority_admin.require_exact_keys(policy_binding, POLICY_BINDING_FIELDS, "policy_binding")
    policy_id = authority_admin.require_token(
        policy_binding["policy_id"], "policy_binding.policy_id"
    )
    generation = policy_binding["generation"]
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise AdminError("invalid_plan", "policy_binding.generation must be a positive integer")
    policy_sha256 = authority_admin.require_sha256(
        policy_binding["sha256"], "policy_binding.sha256"
    )

    expected_release_digest = authority_admin.require_sha256(
        raw["expected_release_digest"], "expected_release_digest"
    )

    host_paths = raw["host_paths"]
    if not isinstance(host_paths, dict):
        raise AdminError("invalid_plan", "host_paths must be an object")
    authority_admin.require_exact_keys(host_paths, HOST_PATH_FIELDS, "host_paths")
    for field in HOST_PATH_FIELDS:
        if not isinstance(host_paths[field], str) or not host_paths[field]:
            raise AdminError("invalid_plan", f"host_paths.{field} must be a non-empty string")

    raw_phases = raw["phases"]
    if not isinstance(raw_phases, list) or not raw_phases:
        raise AdminError("invalid_plan", "phases must be a non-empty list")
    phases: list[dict] = []
    for index, phase in enumerate(raw_phases, start=1):
        if not isinstance(phase, dict):
            raise AdminError("invalid_plan", f"phase {index} must be an object")
        authority_admin.require_exact_keys(phase, PHASE_FIELDS, f"phase {index}")
        if phase["phase_id"] != index:
            raise AdminError(
                "invalid_phase_sequence",
                f"phase {index} has phase_id {phase['phase_id']!r}; "
                "phase_id must be sequential starting at 1",
            )
        operation = phase["operation"]
        if not isinstance(operation, str) or operation not in PHASE_CATALOG:
            raise AdminError(
                "unknown_operation", f"phase {index} names unknown operation: {operation!r}"
            )
        spec = PHASE_CATALOG[operation]
        args = phase["args"]
        if not isinstance(args, dict):
            raise AdminError("invalid_plan", f"phase {index} args must be an object")
        authority_admin.require_exact_keys(args, spec.args_schema, f"phase {index} args")
        mutating = phase["mutating"]
        if not isinstance(mutating, bool):
            raise AdminError("invalid_plan", f"phase {index} mutating must be a boolean")
        if mutating != spec.mutating:
            raise AdminError(
                "mutating_flag_mismatch",
                f"phase {index} claims mutating={mutating!r} but "
                f"{operation!r} is mutating={spec.mutating!r}",
            )
        phases.append(
            {"phase_id": index, "operation": operation, "args": args, "mutating": spec.mutating}
        )

    normalized = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "created_at": created_at,
        "created_by_uid": 0,
        "ledger_id": ledger_id,
        "policy_binding": {
            "policy_id": policy_id,
            "generation": generation,
            "sha256": policy_sha256,
        },
        "expected_release_digest": expected_release_digest,
        "host_paths": {field: host_paths[field] for field in HOST_PATH_FIELDS},
        "phases": phases,
    }
    canonical = broker.canonical_json(normalized)
    digest = authority_admin.sha256_bytes(canonical.encode("ascii"))
    return DogfoodPlan(
        PLAN_SCHEMA_VERSION,
        created_at,
        0,
        ledger_id,
        normalized["policy_binding"],
        expected_release_digest,
        normalized["host_paths"],
        tuple(phases),
        canonical,
        digest,
    )


def read_plan_file(path: Path, owner_uid: int) -> DogfoodPlan:
    data = authority_admin.read_input_file(
        path, owner_uid, "dogfood plan", authority_admin.MAX_ADMIN_FILE_BYTES
    )
    try:
        return parse_plan_object(broker.decode_json(data))
    except broker.BrokerError as exc:
        raise AdminError("invalid_plan", exc.message) from exc


def compute_installed_release_digest(
    install_layout: InstallLayout, identity: DeploymentIdentity
) -> str:
    # Reuses read_source_assets against the currently installed install_root rather than
    # a staged release directory -- read_release_assets already documents that a release
    # directory and an install --source-dir are the same shape, and install_root is that
    # same shape post-install. This recomputes the digest from live bytes; it never trusts
    # any digest recorded in the install manifest.
    assets = authority_admin.read_source_assets(install_layout.install_root, install_layout, identity)
    return authority_admin.compute_release_digest(authority_admin.hash_source_assets(assets))


def validate_plan_bindings(
    plan: DogfoodPlan, install_layout: InstallLayout, identity: DeploymentIdentity
) -> dict:
    expected_host_paths = {
        "install_root": str(install_layout.install_root),
        "config_root": str(install_layout.config_root),
        "state_root": str(install_layout.state_root),
        "runtime_root": str(install_layout.runtime_root),
    }
    if plan.host_paths != expected_host_paths:
        raise AdminError(
            "host_paths_mismatch",
            "plan host_paths do not match the fixed installation layout",
        )

    installed_digest = compute_installed_release_digest(install_layout, identity)
    if plan.expected_release_digest != installed_digest:
        raise AdminError(
            "release_digest_mismatch",
            "plan expected_release_digest does not match the currently installed release",
        )

    # validate_binding=False here is deliberate, not a weakening: this call exists to bind
    # the plan's *content* (ledger/policy/release/paths) to live state before execution
    # starts. The full broker-identity binding check (validate_identity_binding, including
    # validate_privileged_runtime) still runs at its normal default (validate_binding=True)
    # inside the installation_verification phase handler, which every slice-1 plan runs
    # first -- so the security property is preserved, just performed once, at execution
    # time, instead of redundantly here as well.
    deployment = authority_admin.audit_deployment(
        install_layout, identity.admin_uid, identity.admin_gid, validate_binding=False
    )
    if deployment["ledger_id"] != plan.ledger_id:
        raise AdminError("ledger_mismatch", "plan ledger_id does not match the installed deployment")
    current = deployment["current"]
    if (
        current["policy_id"] != plan.policy_binding["policy_id"]
        or current["policy_generation"] != plan.policy_binding["generation"]
        or current["policy_sha256"] != plan.policy_binding["sha256"]
    ):
        raise AdminError(
            "policy_binding_mismatch", "plan policy_binding does not match the installed policy"
        )
    if current["state"] != "active":
        raise AdminError("policy_revoked", "cannot run a dogfood plan under a revoked policy")
    return deployment


# ---------------------------------------------------------------------------
# Plan store (digest-named, self-describing, like a staged release)
# ---------------------------------------------------------------------------


def plan_store_path(dogfood_layout: DogfoodLayout, plan_digest: str) -> Path:
    return dogfood_layout.plans_root / f"{plan_digest}.json"


def store_plan(
    plan: DogfoodPlan,
    dogfood_layout: DogfoodLayout,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
) -> None:
    authority_admin.write_protected_file(
        plan_store_path(dogfood_layout, plan.plan_digest),
        (plan.canonical_json + "\n").encode("ascii"),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        install_layout,
        identity,
        replace=False,
    )


def load_stored_plan(
    plan_digest: str,
    dogfood_layout: DogfoodLayout,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
) -> DogfoodPlan:
    data = authority_admin.read_protected_file(
        plan_store_path(dogfood_layout, plan_digest),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        install_layout,
        identity,
    )
    raw = authority_admin.decode_canonical(data, "dogfood plan")
    plan = parse_plan_object(raw)
    if plan.plan_digest != plan_digest:
        raise AdminError("plan_digest_mismatch", "stored plan does not hash to its own file name")
    return plan


# ---------------------------------------------------------------------------
# Run state, checkpoints, history
# ---------------------------------------------------------------------------


def validate_run_id(run_id: str) -> str:
    if not RUN_ID_RE.fullmatch(run_id):
        raise AdminError("invalid_run_id", "run_id must be 32 lowercase hex characters")
    return run_id


def new_run_id(plan_digest: str) -> str:
    return authority_admin.sha256_bytes(f"{plan_digest}:{os.urandom(16).hex()}".encode("ascii"))[:32]


def run_dir(dogfood_layout: DogfoodLayout, run_id: str) -> Path:
    return dogfood_layout.runs_root / run_id


def checkpoints_dir(dogfood_layout: DogfoodLayout, run_id: str) -> Path:
    return run_dir(dogfood_layout, run_id) / "checkpoints"


def checkpoint_path(
    dogfood_layout: DogfoodLayout, run_id: str, phase_id: int, operation: str, state: str
) -> Path:
    return checkpoints_dir(dogfood_layout, run_id) / f"{phase_id:04d}-{operation}.{state}.json"


def write_run_state(
    dogfood_layout: DogfoodLayout,
    run_id: str,
    plan: DogfoodPlan,
    current_phase: int,
    status: str,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
) -> None:
    state = {
        "run_state_schema_version": RUN_STATE_SCHEMA_VERSION,
        "run_id": run_id,
        "plan_digest": plan.plan_digest,
        "phase_count": len(plan.phases),
        "current_phase": current_phase,
        "status": status,
    }
    authority_admin.write_protected_file(
        run_dir(dogfood_layout, run_id) / "run-state.json",
        authority_admin.json_bytes(state),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        install_layout,
        identity,
        replace=True,
    )


def create_run(
    plan: DogfoodPlan,
    dogfood_layout: DogfoodLayout,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
) -> str:
    run_id = new_run_id(plan.plan_digest)
    target = run_dir(dogfood_layout, run_id)
    authority_admin.ensure_directory(
        target, 0o700, identity.admin_uid, identity.admin_gid, install_layout, identity
    )
    authority_admin.ensure_directory(
        target / "checkpoints", 0o700, identity.admin_uid, identity.admin_gid, install_layout, identity
    )
    authority_admin.write_protected_file(
        target / "plan.json",
        (plan.canonical_json + "\n").encode("ascii"),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        install_layout,
        identity,
        replace=False,
    )
    write_run_state(dogfood_layout, run_id, plan, 1, "running", install_layout, identity)
    append_run_history(
        dogfood_layout, run_id, {"event": "run_created", "plan_digest": plan.plan_digest},
        install_layout, identity,
    )
    return run_id


def load_run_plan(
    dogfood_layout: DogfoodLayout,
    run_id: str,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
) -> DogfoodPlan:
    data = authority_admin.read_protected_file(
        run_dir(dogfood_layout, run_id) / "plan.json",
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        install_layout,
        identity,
    )
    raw = authority_admin.decode_canonical(data, "run plan")
    return parse_plan_object(raw)


def append_run_history(
    dogfood_layout: DogfoodLayout,
    run_id: str,
    entry: dict,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
) -> None:
    # Mirrors append_upgrade_history's append-only pattern: no reused primitive covers
    # append (write_protected_file always replaces or creates the whole file), so this
    # is the one small piece of new atomic-write code in this module.
    path = run_dir(dogfood_layout, run_id) / "run-history.jsonl"
    line = (broker.canonical_json(entry) + "\n").encode("ascii")
    with authority_admin.open_layout_directory(path.parent, install_layout, identity) as parent_fd:
        flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path.name, flags, 0o600, dir_fd=parent_fd)
        try:
            metadata = os.fstat(fd)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != identity.admin_uid
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise AdminError("unsafe_path_metadata", f"run history file is unsafe: {path}")
            authority_admin.write_all(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(parent_fd)


def phase_checkpoint_state(
    dogfood_layout: DogfoodLayout,
    run_id: str,
    phase: dict,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
) -> tuple[str, dict | None]:
    for state in ("completed", "failed", "pending"):
        path = checkpoint_path(dogfood_layout, run_id, phase["phase_id"], phase["operation"], state)
        metadata = authority_admin.entry_metadata_if_present(path, install_layout, identity)
        if metadata is not None:
            data = authority_admin.read_protected_file(
                path, 0o600, identity.admin_uid, identity.admin_gid, install_layout, identity
            )
            return state, authority_admin.decode_canonical(data, f"checkpoint {path.name}")
    return "not_started", None


def write_checkpoint(
    dogfood_layout: DogfoodLayout,
    run_id: str,
    phase: dict,
    state: str,
    payload: dict,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
    *,
    replace: bool = False,
    fault: Callable[[str, Path], None] | None = None,
) -> None:
    path = checkpoint_path(dogfood_layout, run_id, phase["phase_id"], phase["operation"], state)
    authority_admin.write_protected_file(
        path,
        authority_admin.json_bytes(payload),
        0o600,
        identity.admin_uid,
        identity.admin_gid,
        install_layout,
        identity,
        replace=replace,
        fault=fault,
    )


def compute_operation_key(run_id: str, phase_id: int, operation: str) -> str:
    return authority_admin.sha256_bytes(f"{run_id}:{phase_id}:{operation}".encode("ascii"))


def compute_request_digest(plan_digest: str, phase_id: int, operation: str, args: dict) -> str:
    payload = {
        "plan_digest": plan_digest,
        "phase_id": phase_id,
        "operation": operation,
        "args": args,
    }
    return authority_admin.sha256_bytes(broker.canonical_json(payload).encode("ascii"))


# ---------------------------------------------------------------------------
# Phase / run execution
# ---------------------------------------------------------------------------


def execute_phase(
    plan: DogfoodPlan,
    dogfood_layout: DogfoodLayout,
    run_id: str,
    phase: dict,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
    admin_uid: int,
    admin_gid: int,
    *,
    acknowledge_recovered: bool,
    fault: Callable[[str, Path], None] | None = None,
) -> dict:
    operation_key = compute_operation_key(run_id, phase["phase_id"], phase["operation"])
    request_digest = compute_request_digest(
        plan.plan_digest, phase["phase_id"], phase["operation"], phase["args"]
    )

    state, existing = phase_checkpoint_state(dogfood_layout, run_id, phase, install_layout, identity)
    if state == "completed":
        if existing["operation_key"] != operation_key or existing["request_digest"] != request_digest:
            raise AdminError(
                "plan_replaced",
                f"phase {phase['phase_id']} checkpoint no longer matches this run/plan",
            )
        return {**existing, "idempotent_replay": True}
    if state == "failed" and not acknowledge_recovered:
        raise AdminError(
            "failed_phase_requires_acknowledgement",
            f"phase {phase['phase_id']} ({phase['operation']}) previously failed; "
            "use dogfood-resume --acknowledge-recovered to retry it",
        )

    write_checkpoint(
        dogfood_layout,
        run_id,
        phase,
        "pending",
        {
            "operation_key": operation_key,
            "request_digest": request_digest,
            "phase_id": phase["phase_id"],
            "operation": phase["operation"],
        },
        install_layout,
        identity,
        fault=fault,
    )

    spec = PHASE_CATALOG[phase["operation"]]
    try:
        handler_result = spec.handler(install_layout, admin_uid, admin_gid, phase["args"])
    except (AdminError, broker.BrokerError, OSError) as exc:
        error = (
            exc.as_dict()
            if isinstance(exc, AdminError)
            else {"code": "phase_execution_error", "message": str(exc)}
        )
        write_checkpoint(
            dogfood_layout,
            run_id,
            phase,
            "failed",
            {
                "operation_key": operation_key,
                "request_digest": request_digest,
                "phase_id": phase["phase_id"],
                "operation": phase["operation"],
                "error": error,
            },
            install_layout,
            identity,
            replace=True,
        )
        append_run_history(
            dogfood_layout,
            run_id,
            {"event": "phase_failed", "phase_id": phase["phase_id"], "operation": phase["operation"]},
            install_layout,
            identity,
        )
        raise

    result_digest = authority_admin.sha256_bytes(broker.canonical_json(handler_result).encode("ascii"))
    completed = {
        "operation_key": operation_key,
        "request_digest": request_digest,
        "phase_id": phase["phase_id"],
        "operation": phase["operation"],
        "result_digest": result_digest,
    }
    write_checkpoint(
        dogfood_layout, run_id, phase, "completed", completed, install_layout, identity, fault=fault
    )
    append_run_history(
        dogfood_layout,
        run_id,
        {"event": "phase_completed", "phase_id": phase["phase_id"], "operation": phase["operation"]},
        install_layout,
        identity,
    )
    return {**completed, "idempotent_replay": False}


def execute_run(
    plan: DogfoodPlan,
    run_id: str,
    approve_phase: int | None,
    dogfood_layout: DogfoodLayout,
    install_layout: InstallLayout,
    identity: DeploymentIdentity,
    admin_uid: int,
    admin_gid: int,
    *,
    acknowledge_recovered: bool,
    fault: Callable[[str, Path], None] | None = None,
) -> dict:
    executed = []
    for phase in plan.phases:
        # Always route through execute_phase, even for an already-completed phase: it is
        # the one place that re-verifies a completed checkpoint's operation_key/
        # request_digest against the currently bound plan before treating it as a valid
        # idempotent replay. A shortcut here that skipped straight past completed phases
        # would let a tampered completed checkpoint go unverified on every later resume.
        state, _existing = phase_checkpoint_state(
            dogfood_layout, run_id, phase, install_layout, identity
        )
        if state != "completed" and phase["mutating"] and approve_phase != phase["phase_id"]:
            write_run_state(
                dogfood_layout, run_id, plan, phase["phase_id"], "awaiting_approval",
                install_layout, identity,
            )
            return {
                "ok": True,
                "action": "dogfood-run",
                "run_id": run_id,
                "plan_digest": plan.plan_digest,
                "status": "awaiting_approval",
                "next_phase": phase["phase_id"],
                "next_operation": phase["operation"],
                "message": (
                    f"phase {phase['phase_id']} ({phase['operation']}) mutates state and "
                    f"requires explicit approval; re-run with --run-id {run_id} "
                    f"--approve-phase {phase['phase_id']}"
                ),
                "executed": executed,
            }
        result = execute_phase(
            plan, dogfood_layout, run_id, phase, install_layout, identity, admin_uid, admin_gid,
            acknowledge_recovered=acknowledge_recovered, fault=fault,
        )
        executed.append(
            {
                "phase_id": phase["phase_id"],
                "operation": phase["operation"],
                "idempotent_replay": result["idempotent_replay"],
            }
        )
        # acknowledge_recovered authorizes at most one retry of one previously-failed
        # phase per resume invocation; later phases in the same pass never inherit it.
        acknowledge_recovered = False
        write_run_state(
            dogfood_layout, run_id, plan, phase["phase_id"] + 1, "running", install_layout, identity
        )

    write_run_state(
        dogfood_layout, run_id, plan, len(plan.phases) + 1, "completed", install_layout, identity
    )
    return {
        "ok": True,
        "action": "dogfood-run",
        "run_id": run_id,
        "plan_digest": plan.plan_digest,
        "status": "completed",
        "executed": executed,
    }


# ---------------------------------------------------------------------------
# Command entry points (mirrors authority_admin.py's *_deployment functions)
# ---------------------------------------------------------------------------


def dogfood_plan_command(
    install_layout: InstallLayout,
    dogfood_layout: DogfoodLayout,
    plan_path: Path,
    admin_uid: int,
    admin_gid: int,
) -> dict:
    identity = dogfood_identity(admin_uid, admin_gid)
    ensure_dogfood_layout(dogfood_layout, install_layout, identity)
    plan = read_plan_file(plan_path, admin_uid)
    validate_plan_bindings(plan, install_layout, identity)
    store_plan(plan, dogfood_layout, install_layout, identity)
    return {
        "ok": True,
        "action": "dogfood-plan",
        "plan_digest": plan.plan_digest,
        "ledger_id": plan.ledger_id,
        "phase_count": len(plan.phases),
        "mutating_phases": [p["phase_id"] for p in plan.phases if p["mutating"]],
    }


def dogfood_run_command(
    install_layout: InstallLayout,
    dogfood_layout: DogfoodLayout,
    plan_digest: str,
    run_id: str | None,
    approve_phase: int | None,
    admin_uid: int,
    admin_gid: int,
) -> dict:
    plan_digest = authority_admin.require_sha256(plan_digest, "plan_digest")
    identity = dogfood_identity(admin_uid, admin_gid)
    plan = load_stored_plan(plan_digest, dogfood_layout, install_layout, identity)
    validate_plan_bindings(plan, install_layout, identity)

    if run_id is None:
        run_id = create_run(plan, dogfood_layout, install_layout, identity)
    else:
        run_id = validate_run_id(run_id)
        bound_plan = load_run_plan(dogfood_layout, run_id, install_layout, identity)
        if bound_plan.plan_digest != plan_digest:
            raise AdminError("plan_replaced", f"run {run_id} is bound to a different plan digest")

    return execute_run(
        plan, run_id, approve_phase, dogfood_layout, install_layout, identity, admin_uid, admin_gid,
        acknowledge_recovered=False,
    )


def dogfood_status_command(
    install_layout: InstallLayout,
    dogfood_layout: DogfoodLayout,
    run_id: str,
    admin_uid: int,
    admin_gid: int,
) -> dict:
    identity = dogfood_identity(admin_uid, admin_gid)
    run_id = validate_run_id(run_id)
    plan = load_run_plan(dogfood_layout, run_id, install_layout, identity)
    phases_status = []
    for phase in plan.phases:
        state, existing = phase_checkpoint_state(
            dogfood_layout, run_id, phase, install_layout, identity
        )
        entry = {
            "phase_id": phase["phase_id"],
            "operation": phase["operation"],
            "mutating": phase["mutating"],
            "state": state,
        }
        if existing is not None:
            if "result_digest" in existing:
                entry["result_digest"] = existing["result_digest"]
            if "error" in existing:
                entry["error"] = existing["error"]
        phases_status.append(entry)
    if all(p["state"] == "completed" for p in phases_status):
        overall = "completed"
    elif any(p["state"] == "failed" for p in phases_status):
        overall = "failed"
    else:
        overall = "in_progress"
    return {
        "ok": True,
        "action": "dogfood-status",
        "run_id": run_id,
        "plan_digest": plan.plan_digest,
        "ledger_id": plan.ledger_id,
        "status": overall,
        "phases": phases_status,
    }


def dogfood_resume_command(
    install_layout: InstallLayout,
    dogfood_layout: DogfoodLayout,
    run_id: str,
    approve_phase: int | None,
    acknowledge_recovered: bool,
    admin_uid: int,
    admin_gid: int,
) -> dict:
    identity = dogfood_identity(admin_uid, admin_gid)
    run_id = validate_run_id(run_id)
    plan = load_run_plan(dogfood_layout, run_id, install_layout, identity)
    validate_plan_bindings(plan, install_layout, identity)
    return execute_run(
        plan, run_id, approve_phase, dogfood_layout, install_layout, identity, admin_uid, admin_gid,
        acknowledge_recovered=acknowledge_recovered,
    )
