"""Regression coverage for issue 14's field contract."""

from __future__ import annotations

import authority_broker
import subprocess
from pathlib import Path

import pytest


def test_claim_create_keeps_gate_artifact_and_verify_command_distinct() -> None:
    operation = authority_broker.normalize_operation(
        {
            "kind": "claim.create",
            "task_id": "task-0001",
            "claim_id": "claim-0001",
            "claim_type": "test_passes",
            "text": "the gate passes",
            "required_gate": "tests/test_operator.py",
            "verify_cmd": "python3 -m unittest tests.test_operator",
        }
    )

    assert operation["required_gate"] == "tests/test_operator.py"
    assert operation["verify_cmd"] == "python3 -m unittest tests.test_operator"


def test_claim_create_allows_legacy_optional_gate_without_command() -> None:
    operation = authority_broker.normalize_operation(
        {
            "kind": "claim.create",
            "task_id": "task-0001",
            "claim_id": "claim-0001",
            "claim_type": "real_data",
            "text": "the observation is real",
            "required_gate": "evidence/observation.yaml",
        }
    )

    assert operation["required_gate"] == "evidence/observation.yaml"
    assert "verify_cmd" not in operation


def test_create_route_delegate_and_doctor_use_distinct_fields(tmp_path: Path) -> None:
    operator = Path(__file__).resolve().parents[1] / "operator"

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(operator), *args], cwd=tmp_path, text=True, capture_output=True, check=False
        )

    assert run("init").returncode == 0
    (tmp_path / ".operator" / "harnesses" / "claude.yaml").write_text("name: claude\n")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_operator.py").write_text("# gate artifact\n")
    assert run("task-create", "--id", "field-test", "--objective", "field test", "--review", "claude").returncode == 0
    claim_result = run(
        "claim-add",
        "--task",
        "field-test",
        "--type",
        "test_passes",
        "--text",
        "gate claim",
        "--gate",
        "tests/test_operator.py",
        "--verify-cmd",
        "python3 -m unittest tests.test_operator",
    )
    if "authority registry ancestor is writable by an agent" in claim_result.stderr:
        pytest.skip("host authority registry is unavailable in the restricted test sandbox")
    assert claim_result.returncode == 0, claim_result.stderr
    # Negative case while review_harness is still SET: the routing field must not
    # supply verifier identity. Pre-fix this succeeded and emitted a bundle naming
    # "claude"; post-fix it must refuse.
    stale_before = set((tmp_path / ".operator" / "review_delegations").glob("*.yaml"))
    stale = run("review-delegate", "claim-0001", "--mode", "advisory-agent")
    assert stale.returncode != 0, stale.stdout
    assert "routing metadata" in stale.stderr, stale.stderr
    assert set((tmp_path / ".operator" / "review_delegations").glob("*.yaml")) == stale_before

    routed = run(
        "task-route",
        "--task",
        "field-test",
        "--clear-review",
        "--rationale",
        "reviewer route was stale",
    )
    assert routed.returncode == 0, routed.stderr
    delegated = run(
        "review-delegate",
        "claim-0001",
        "--reviewer",
        "claude",
        "--mode",
        "advisory-agent",
    )
    assert delegated.returncode == 0, delegated.stderr
    before_negative = set((tmp_path / ".operator" / "review_delegations").glob("*.yaml"))
    negative = run("review-delegate", "claim-0001", "--mode", "advisory-agent")
    assert negative.returncode != 0
    assert "--reviewer is required" in negative.stderr
    assert set((tmp_path / ".operator" / "review_delegations").glob("*.yaml")) == before_negative
    checked = run("doctor")
    assert checked.returncode == 0, checked.stdout
