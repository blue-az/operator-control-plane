"""Race two local OpenCode implementers, with a gated Codex fallback."""

from __future__ import annotations

import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path

import harness_adapter


@dataclass(frozen=True)
class Arm:
    name: str
    model: str
    device: str
    workspace: Path


@dataclass
class RoundResult:
    arm: str
    exit_state: str
    gate_returncode: int | None
    gate_stdout: str
    gate_stderr: str
    duration_s: float
    passed: bool


@dataclass
class RaceResult:
    winner: str | None
    rounds: list[list[RoundResult]]
    fallback_used: bool


def _default_invoke(**kwargs):
    return harness_adapter.invoke(**kwargs)


def _default_gate(workspace: Path, gate_cmd: list[str]):
    result = subprocess.run(
        gate_cmd, cwd=workspace, capture_output=True, text=True
    )
    return result.returncode, result.stdout, result.stderr


def _state(result) -> str:
    value = getattr(result, "exit_state", result)
    return getattr(value, "value", str(value))


def _prompt_for_arm(original: str, previous: RoundResult | None) -> str:
    if previous is None:
        return original
    return (
        f"{original}\n\n"
        "Continuation: the previous attempt did not pass the gate.\n"
        "Here is the gate output from your arm's previous attempt; fix the issue and try again.\n"
        f"Gate stdout:\n{previous.gate_stdout}\n"
        f"Gate stderr:\n{previous.gate_stderr}\n"
    )


def _invoke_arm(invoke, arm: Arm, prompt: str, timeout: int):
    started = time.monotonic()
    result = invoke(
        harness_id="opencode",
        role=harness_adapter.Role.IMPLEMENTER,
        model=arm.model,
        prompt=prompt,
        workspace=arm.workspace,
        timeout_seconds=timeout,
        extra_env={"CUDA_VISIBLE_DEVICES": arm.device},
    )
    return result, time.monotonic() - started


def _round(
    *, invoke, gate, gate_cmd: list[str], prompt_by_arm: dict[str, str],
    arms: tuple[Arm, Arm], timeout: int,
) -> list[RoundResult]:
    executor = ThreadPoolExecutor(max_workers=2)
    futures = {
        arm.name: executor.submit(_invoke_arm, invoke, arm, prompt_by_arm[arm.name], timeout)
        for arm in arms
    }
    deadline = time.monotonic() + timeout
    completed: dict[str, tuple[object, float]] = {}
    for arm in arms:
        remaining = max(0.0, deadline - time.monotonic())
        try:
            completed[arm.name] = futures[arm.name].result(timeout=remaining)
        except TimeoutError:
            completed[arm.name] = (None, timeout)
    executor.shutdown(wait=False, cancel_futures=True)

    results = []
    for arm in arms:
        invocation, duration = completed[arm.name]
        if invocation is None:
            exit_state = "timeout"
        else:
            exit_state = _state(invocation)
        returncode, stdout, stderr = gate(arm.workspace, gate_cmd)
        results.append(
            RoundResult(
                arm=arm.name,
                exit_state=exit_state,
                gate_returncode=returncode,
                gate_stdout=stdout,
                gate_stderr=stderr,
                duration_s=duration,
                passed=returncode == 0,
            )
        )
    return results


def run_race(
    *,
    prompt: str,
    gate_cmd: list[str],
    arm_a: Arm,
    arm_b: Arm,
    round_timeout_s: int = 600,
    max_rounds: int = 2,
    fallback_harness: str = "codex",
    fallback_model: str = "gpt-5.6-luna",
    invoke_fn=None,
    run_gate_fn=None,
) -> RaceResult:
    invoke = invoke_fn or _default_invoke
    gate = run_gate_fn or _default_gate
    arms = (arm_a, arm_b)
    previous = {arm.name: None for arm in arms}
    all_rounds: list[list[RoundResult]] = []

    for _ in range(max_rounds):
        prompts = {
            arm.name: _prompt_for_arm(prompt, previous[arm.name]) for arm in arms
        }
        results = _round(
            invoke=invoke,
            gate=gate,
            gate_cmd=gate_cmd,
            prompt_by_arm=prompts,
            arms=arms,
            timeout=round_timeout_s,
        )
        all_rounds.append(results)
        winners = [result for result in results if result.passed]
        if winners:
            winner = min(winners, key=lambda result: result.duration_s).arm
            return RaceResult(winner, all_rounds, False)
        previous = {result.arm: result for result in results}

    last = {result.arm: result for result in all_rounds[-1]} if all_rounds else {}
    fallback_prompt = (
        f"{prompt}\n\nContinuation after both local arms failed their gate:\n"
        f"Arm A gate stderr:\n{last.get('A').gate_stderr if last.get('A') else ''}\n"
        f"Arm B gate stderr:\n{last.get('B').gate_stderr if last.get('B') else ''}\n"
    )
    invoke(
        harness_id=fallback_harness,
        role=harness_adapter.Role.IMPLEMENTER,
        model=fallback_model,
        prompt=fallback_prompt,
        workspace=arm_a.workspace,
        timeout_seconds=round_timeout_s,
        extra_env=None,
    )
    returncode, _, _ = gate(arm_a.workspace, gate_cmd)
    return RaceResult("fallback" if returncode == 0 else None, all_rounds, True)
