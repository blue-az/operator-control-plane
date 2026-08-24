"""Race two *local* OpenCode implementers.

Winner is arm A or arm B only. Frontier (Luna, Claude, …) is not a racer
and must not be recorded as winner. A later optional frontier race is out
of scope for this command.
"""

from __future__ import annotations

import subprocess
import json
import time
import os
import tempfile
from urllib.request import Request, urlopen
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
    ollama_host: str = ""


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
    winner: str | None  # "A", "B", or None — never a frontier harness
    rounds: list[list[RoundResult]]


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


def _ollama_url(host: str, path: str) -> str:
    if host.startswith("http://") or host.startswith("https://"):
        return f"{host.rstrip('/')}{path}"
    return f"http://{host}{path}"


def _ollama_model(model: str) -> str:
    return model.removeprefix("ollama/")


def _http_request(method: str, url: str, payload=None, timeout: int = 15):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    with urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body) if body else None


def _config_for_arm(arm: Arm) -> tempfile.NamedTemporaryFile:
    config = {
        "provider": {
            "ollama": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Ollama race",
                "options": {"baseURL": _ollama_url(arm.ollama_host, "/v1")},
            }
        }
    }
    file = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(config, file)
    file.close()
    return file


def _arm_host(arm: Arm) -> str:
    if arm.ollama_host:
        return arm.ollama_host
    return "127.0.0.1:11435" if arm.name == "A" else "127.0.0.1:11436"


def _invoke_arm(invoke, arm: Arm, prompt: str, timeout: int):
    started = time.monotonic()
    arm = Arm(arm.name, arm.model, arm.device, arm.workspace, _arm_host(arm))
    config_file = _config_for_arm(arm)
    try:
        result = invoke(
            harness_id="opencode",
            role=harness_adapter.Role.IMPLEMENTER,
            model=arm.model,
            prompt=prompt,
            workspace=arm.workspace,
            timeout_seconds=timeout,
            extra_env={
                "CUDA_VISIBLE_DEVICES": arm.device,
                "OLLAMA_HOST": arm.ollama_host,
                "OPENCODE_CONFIG": config_file.name,
            },
        )
    finally:
        os.unlink(config_file.name)
    return result, time.monotonic() - started


def _listener_env(arm: Arm, num_ctx: int, models_dir: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "CUDA_VISIBLE_DEVICES": arm.device,
            "OLLAMA_HOST": arm.ollama_host,
            "OLLAMA_CONTEXT_LENGTH": str(num_ctx),
            "OLLAMA_KEEP_ALIVE": "60m",
            "OLLAMA_MAX_LOADED_MODELS": "1",
            "OLLAMA_MODELS": models_dir,
        }
    )
    return env


def _prepare_listeners(
    arms: tuple[Arm, Arm], *, num_ctx: int, models_dir: str | None,
    spawn_fn, http_fn,
) -> list[object]:
    selected_models_dir = models_dir or os.environ.get("OLLAMA_MODELS")
    if not selected_models_dir:
        selected_models_dir = str(Path.home() / ".ollama" / "models")
    model_path = Path(selected_models_dir).expanduser()
    if not model_path.is_dir() or not os.access(model_path, os.R_OK | os.X_OK):
        raise ValueError(
            f"models directory {model_path} is missing or unreadable; "
            "the systemd store is not readable"
        )

    spawned = []
    try:
        for arm in arms:
            tags_url = _ollama_url(arm.ollama_host, "/api/tags")
            try:
                http_fn("GET", tags_url)
            except Exception:
                process = spawn_fn(
                    ["ollama", "serve"], _listener_env(arm, num_ctx, str(model_path))
                )
                spawned.append(process)
                deadline = time.monotonic() + 15
                while True:
                    try:
                        http_fn("GET", tags_url)
                        break
                    except Exception:
                        if time.monotonic() >= deadline:
                            raise ValueError(f"ollama listener {arm.ollama_host} did not start")
                        time.sleep(0.1)

            model = _ollama_model(arm.model)
            http_fn(
                "POST",
                _ollama_url(_arm_host(arm), "/api/generate"),
                {"model": model, "prompt": "ping", "keep_alive": "60m", "options": {"num_ctx": num_ctx}},
            )
            ps = http_fn("GET", _ollama_url(arm.ollama_host, "/api/ps"))
            loaded = ps.get("models", []) if isinstance(ps, dict) else []
            names = [entry.get("name") for entry in loaded if isinstance(entry, dict)]
            if model not in names:
                raise ValueError(f"ollama listener {arm.ollama_host} did not preload {model}")
    except Exception:
        _cleanup_spawned(spawned)
        raise
    return spawned


def _default_spawn(command, env):
    return subprocess.Popen(command, env=env)


def _cleanup_spawned(processes):
    for process in processes:
        process.kill()
    for process in processes:
        process.wait()


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
    invoke_fn=None,
    run_gate_fn=None,
    spawn_listeners: bool = False,
    num_ctx: int = 8192,
    models_dir: str | None = None,
    spawn_fn=None,
    http_fn=None,
) -> RaceResult:
    if arm_a.model == arm_b.model:
        raise ValueError(f"ab-local requires two different models; got {arm_a.model!r} twice")
    invoke = invoke_fn or _default_invoke
    gate = run_gate_fn or _default_gate
    arm_a = Arm(arm_a.name, arm_a.model, arm_a.device, arm_a.workspace, _arm_host(arm_a))
    arm_b = Arm(arm_b.name, arm_b.model, arm_b.device, arm_b.workspace, _arm_host(arm_b))
    arms = (arm_a, arm_b)
    spawned = []
    if spawn_listeners:
        spawned = _prepare_listeners(
            arms,
            num_ctx=num_ctx,
            models_dir=models_dir,
            spawn_fn=spawn_fn or _default_spawn,
            http_fn=http_fn or _http_request,
        )
    previous = {arm.name: None for arm in arms}
    all_rounds: list[list[RoundResult]] = []
    try:
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
                return RaceResult(winner, all_rounds)
            previous = {result.arm: result for result in results}

        return RaceResult(None, all_rounds)
    finally:
        if spawned:
            _cleanup_spawned(spawned)
