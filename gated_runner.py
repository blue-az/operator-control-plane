import json
import subprocess
import time
import hashlib
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional


class CellError(Exception):
    """Raised for any invalid cell."""

    pass


@dataclass
class Gate:
    command: list[str]
    expect: str


@dataclass
class GateProbe:
    stdout: str
    stderr: str
    returncode: int


@dataclass
class Verdict:
    status: str
    detail: str


@dataclass
class OutcomeRecord:
    task_id: str
    harness: str
    model: str
    declared_artifact: str
    wall_clock: float
    tool_call_count: int
    exit_cause: str
    gate_verdict: str
    artifact_hash_changed: bool
    timestamp: float = 0.0


@dataclass
class Cell:
    cell_id: str
    objective: str
    brief: str
    workspace: str
    gate: Gate


MUTATING_TOKENS = frozenset(
    [
        "set-default-sink",
        "set-sink-volume",
        "set-card-profile",
        "set-sink-mute",
        "rm",
        "mv",
        "cp",
        "restart",
        "stop",
        "start",
        "install",
        "write",
        "tee",
        "dd",
        "chmod",
        "chown",
        "kill",
        "reboot",
    ]
)


def load_cell(path: str) -> Cell:
    with open(path, "r") as f:
        data = json.load(f)

    if "gate" not in data:
        raise CellError("gate key is absent")

    gate_data = data["gate"]
    command = gate_data.get("command")

    if not isinstance(command, list):
        raise CellError("gate[command] is not a list")

    if len(command) == 0:
        raise CellError("gate[command] is empty")

    for token in command:
        if token in MUTATING_TOKENS:
            raise CellError(f"command contains mutating token: {token}")

    return Cell(
        cell_id=data["cell_id"],
        objective=data["objective"],
        brief=data["brief"],
        workspace=data["workspace"],
        gate=Gate(command=command, expect=gate_data["expect"]),
    )


def probe(gate: Gate) -> GateProbe:
    try:
        result = subprocess.run(
            gate.command, capture_output=True, text=True, shell=False, timeout=30
        )
        return GateProbe(stdout=result.stdout, stderr=result.stderr, returncode=result.returncode)
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return GateProbe(stdout="", stderr=str(e), returncode=127)


def evaluate(pre: GateProbe, post: GateProbe, gate: Gate) -> Verdict:
    if post.returncode != 0:
        return Verdict("error", "command failed")

    pre_ok = pre.stdout.strip() == gate.expect.strip()
    post_ok = post.stdout.strip() == gate.expect.strip()

    if pre_ok:
        return Verdict("vacuous", "pre-state already matches")
    if post_ok:
        return Verdict("pass", "gate passed")
    return Verdict("fail", "gate failed to change state")


def evidence_args(verdict: Verdict) -> list[str]:
    mapping = {
        "pass": "verified",
        "fail": "false",
        "vacuous": "quarantined",
        "error": "quarantined",
    }
    status_word = mapping.get(verdict.status, "quarantined")
    return ["--status", status_word, "--verdict", verdict.detail]


def _calculate_hash(path: Path) -> str:
    if not path.exists():
        return "missing"
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            sha256.update(chunk)
    return sha256.hexdigest()


def save_outcome_record(record: OutcomeRecord, storage_dir: Path):
    """Persistent storage for R6 records (R6b)."""
    storage_dir.mkdir(parents=True, exist_ok=True)
    # Grid trials can complete within one second.  Second-resolution names
    # silently overwrite evidence, so retain microsecond resolution and make
    # collisions impossible for synthetic/frozen timestamps too.
    stem = f"outcome-{int(record.timestamp * 1_000_000)}"
    path = storage_dir / f"{stem}.json"
    suffix = 1
    while path.exists():
        path = storage_dir / f"{stem}-{suffix}.json"
        suffix += 1
    with open(path, "w") as f:
        json.dump(asdict(record), f, indent=2)


def run_invocation(
    cell: Cell,
    harness: str,
    model: str,
    action_callback: callable,
    artifact_path: Path,
    storage_dir: Optional[Path] = None,
) -> OutcomeRecord:
    """
    The core R6 orchestration loop.
    1. Pre-state capture
    2. Action execution
    3. Post-state capture
    4. Record emission & persistence
    """
    start_time = time.time()
    
    # Pre-state
    pre_hash = _calculate_hash(artifact_path)
    pre_probe = probe(cell.gate)
    
    # Execution
    try:
        # Action callback returns (tool_call_count, exit_cause)
        tool_calls, exit_cause = action_callback()
    except Exception as e:
        tool_calls, exit_cause = 0, f"exception: {str(e)}"
    
    # Post-state
    post_hash = _calculate_hash(artifact_path)
    post_probe = probe(cell.gate)
    
    duration = time.time() - start_time
    verdict = evaluate(pre_probe, post_probe, cell.gate)
    
    record = OutcomeRecord(
        task_id=cell.cell_id,
        harness=harness,
        model=model,
        declared_artifact=str(artifact_path),
        wall_clock=duration,
        tool_call_count=tool_calls,
        exit_cause=exit_cause,
        gate_verdict=verdict.status,
        artifact_hash_changed=pre_hash != post_hash,
        timestamp=start_time,
    )
    
    if storage_dir:
        save_outcome_record(record, storage_dir)
        
    return record
