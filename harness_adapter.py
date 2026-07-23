#!/usr/bin/env python3
"""Typed headless harness adapters shared by `opr` and `study_runner.py`.

Replaces ad hoc per-harness subprocess string templates (previously duplicated
inside `opr`'s `dispatch_frontier`) with typed profiles: an argv **list**
(never a shell string), an explicit prompt-transport mode, and a closed
exit-state vocabulary that distinguishes success from every way a headless CLI
call can fail short of that.

Profile argv/flags below are taken directly from each CLI's own `--help`
output (`claude --help`, `agy --help`, `codex exec --help`, `grok --help`), not
guessed. Where a role needs a permission/sandbox flag that has no real
equivalent on a given CLI, none is added -- see ROLE_ARGS.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ExitState(Enum):
    SUCCESS = "success"
    NONZERO_EXIT = "nonzero_exit"
    MALFORMED_OUTPUT = "malformed_output"
    TIMEOUT = "timeout"
    MISSING_EXECUTABLE = "missing_executable"
    QUOTA_EXHAUSTED = "quota_exhausted"


class PromptTransport(Enum):
    STDIN = "stdin"
    PROMPT_FILE = "prompt_file"
    # The prompt is the argv value of a specific flag (e.g. agy's `-p`),
    # not piped via stdin. Confirmed necessary by a real smoke call: agy's
    # `-p` takes the prompt as its own argument -- piping it over stdin
    # instead produces a real, coherent, but completely unrelated response
    # (agy answered a question about one of its own other flags), which is
    # exactly the kind of silent-wrong-answer this adapter exists to avoid.
    INLINE_ARG = "inline_arg"


class Role(Enum):
    SUPERVISOR = "supervisor"
    IMPLEMENTER = "implementer"
    JUDGE = "judge"


DEFAULT_TIMEOUT_SECONDS = 1800


@dataclass(frozen=True)
class HarnessProfile:
    harness_id: str
    executable: str
    base_args: tuple[str, ...]
    prompt_transport: PromptTransport
    # "text": stdout is the response verbatim. "json": stdout is a single JSON
    # object. "jsonl": stdout is newline-delimited JSON events; the last
    # well-formed JSON line is treated as the result.
    output_format: str
    role_args: dict[str, tuple[str, ...]]
    prompt_file_flag: Optional[str] = None
    prompt_arg_flag: Optional[str] = None
    version_args: tuple[str, ...] = ("--version",)
    # Best-effort, case-insensitive substrings checked against combined
    # stdout+stderr to recognize quota/rate-limit exhaustion. This is
    # necessarily heuristic -- no real quota-exhaustion transcript was
    # captured to ground these (doing so would require a live paid call,
    # which is exactly what this project treats as requiring separate
    # approval). Expect these to need refinement against real CLI behavior.
    quota_markers: tuple[str, ...] = (
        "rate limit",
        "rate_limit",
        "quota",
        "usage limit",
        "429",
    )


# Role flags are only added where the CLI's own --help documents a real,
# matching flag. Confirmed directly against each CLI's --help output:
#   claude --permission-mode {..., plan, acceptEdits, ...}
#   agy    --mode {accept-edits, plan}
#   codex exec -s/--sandbox {read-only, workspace-write, danger-full-access}
#   grok   --permission-mode {..., plan, acceptEdits, ...}
PROFILES: dict[str, HarnessProfile] = {
    "claude": HarnessProfile(
        harness_id="claude",
        executable="claude",
        base_args=("-p", "--output-format", "json"),
        prompt_transport=PromptTransport.STDIN,
        output_format="json",
        role_args={
            Role.SUPERVISOR.value: ("--permission-mode", "plan"),
            Role.JUDGE.value: ("--permission-mode", "plan"),
            Role.IMPLEMENTER.value: ("--permission-mode", "acceptEdits"),
        },
    ),
    "agy": HarnessProfile(
        harness_id="agy",
        executable="agy",
        base_args=("--print-timeout", "30m"),
        prompt_transport=PromptTransport.INLINE_ARG,
        prompt_arg_flag="-p",
        output_format="text",
        role_args={
            Role.SUPERVISOR.value: ("--mode", "plan"),
            Role.JUDGE.value: ("--mode", "plan"),
            Role.IMPLEMENTER.value: ("--mode", "accept-edits"),
        },
    ),
    "codex": HarnessProfile(
        harness_id="codex",
        executable="codex",
        base_args=("exec", "-", "--json", "--ephemeral"),
        prompt_transport=PromptTransport.STDIN,
        output_format="jsonl",
        role_args={
            Role.SUPERVISOR.value: ("--sandbox", "read-only"),
            Role.JUDGE.value: ("--sandbox", "read-only"),
            Role.IMPLEMENTER.value: ("--sandbox", "workspace-write"),
        },
    ),
    "grok": HarnessProfile(
        harness_id="grok",
        executable="grok",
        base_args=(
            "--output-format",
            "json",
            "--no-subagents",
            "--no-memory",
            "--disable-web-search",
        ),
        prompt_transport=PromptTransport.PROMPT_FILE,
        prompt_file_flag="--prompt-file",
        output_format="json",
        role_args={
            Role.SUPERVISOR.value: ("--permission-mode", "plan"),
            Role.JUDGE.value: ("--permission-mode", "plan"),
            Role.IMPLEMENTER.value: ("--permission-mode", "acceptEdits"),
        },
    ),
}


class AdapterError(Exception):
    pass


@dataclass(frozen=True)
class FrozenAdapter:
    """The result of `freeze()`: everything about a harness invocation that
    must be nailed down and recorded *before* a study plan is hashed, so the
    plan digest binds to what will actually run."""

    harness_id: str
    role: str
    model: str
    executable_path: str
    cli_version: str
    argv: tuple[str, ...]
    workspace: str


@dataclass(frozen=True)
class AdapterResult:
    exit_state: ExitState
    returncode: Optional[int]
    stdout: str
    stderr: str
    parsed_output: Optional[dict]
    duration_seconds: float
    argv: tuple[str, ...]
    # Caller provenance: who invoked this adapter, if they said so. See
    # resolve_initiator_identity() -- None unless the calling process
    # explicitly declares itself via environment variables. Nothing here
    # auto-detects a caller; a process shelling out to Python (e.g. a live
    # agy or claude session's own run_command-style tool) has no built-in
    # way to know who its parent is, so this is opt-in, not inferred.
    initiator: Optional[dict]


INITIATOR_HARNESS_ENV = "OPERATOR_INITIATOR_HARNESS"
INITIATOR_SESSION_ENV = "OPERATOR_INITIATOR_SESSION_ID"


def resolve_initiator_identity() -> Optional[dict]:
    """Reads the calling process's self-declared identity, if any, from
    OPERATOR_INITIATOR_HARNESS / OPERATOR_INITIATOR_SESSION_ID. Mirrors the
    same explicit, opt-in environment-variable convention `operator` itself
    uses for get_executor_identity()'s OPERATOR_TEST_UID/
    OPERATOR_TEST_SENTINEL -- provenance is declared, never inferred."""
    harness = os.environ.get(INITIATOR_HARNESS_ENV, "").strip()
    session_id = os.environ.get(INITIATOR_SESSION_ENV, "").strip()
    if not harness and not session_id:
        return None
    identity: dict = {}
    if harness:
        identity["harness"] = harness
    if session_id:
        identity["session_id"] = session_id
    return identity


def get_profile(harness_id: str) -> HarnessProfile:
    profile = PROFILES.get(harness_id)
    if profile is None:
        raise AdapterError(f"No adapter profile for harness: {harness_id!r}")
    return profile


def _run_version_check(profile: HarnessProfile) -> str:
    executable_path = shutil.which(profile.executable)
    if not executable_path:
        raise AdapterError(
            f"Cannot freeze harness {profile.harness_id!r}: executable "
            f"{profile.executable!r} not found on PATH."
        )
    try:
        res = subprocess.run(
            [executable_path, *profile.version_args],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise AdapterError(
            f"Cannot freeze harness {profile.harness_id!r}: version check failed: {exc}"
        ) from exc
    version = (res.stdout or res.stderr or "").strip()
    if res.returncode != 0 or not version:
        raise AdapterError(
            f"Cannot freeze harness {profile.harness_id!r}: version check exited "
            f"{res.returncode} with no usable output."
        )
    return version


def freeze(
    harness_id: str,
    role: Role,
    model: str,
    workspace: Path,
) -> FrozenAdapter:
    """Resolve and record the actual executable path, CLI version, adapter
    argv, and workspace for one harness/role/model combination.

    Deliberately does not attempt to resolve a model *alias* (e.g. "sonnet")
    into a canonical model ID by querying the harness live -- doing so would
    require a real, paid invocation, which this project treats as requiring
    separate approval, not something a freeze/plan-hashing step should ever
    trigger silently. Callers must pass a concrete model identifier already;
    freeze() validates it is present and non-empty and raises otherwise ("the
    selected model cannot be resolved").
    """
    if not model or not model.strip():
        raise AdapterError(
            f"Cannot freeze harness {harness_id!r}: no model identifier was provided "
            "(the selected model cannot be resolved)."
        )
    profile = get_profile(harness_id)
    executable_path = shutil.which(profile.executable)
    if not executable_path:
        raise AdapterError(
            f"Cannot freeze harness {harness_id!r}: executable {profile.executable!r} "
            "not found on PATH."
        )
    cli_version = _run_version_check(profile)
    argv = build_argv(profile, role, model, prompt_file_path=None)
    return FrozenAdapter(
        harness_id=harness_id,
        role=role.value,
        model=model,
        executable_path=executable_path,
        cli_version=cli_version,
        argv=tuple(argv),
        workspace=str(Path(workspace).resolve()),
    )


def build_argv(
    profile: HarnessProfile,
    role: Role,
    model: str,
    prompt_file_path: Optional[str] = None,
    inline_prompt: Optional[str] = None,
) -> list[str]:
    argv = [profile.executable]
    if profile.prompt_transport == PromptTransport.INLINE_ARG:
        if not profile.prompt_arg_flag:
            raise AdapterError(
                f"Harness {profile.harness_id!r} declares INLINE_ARG transport but has "
                "no prompt_arg_flag configured."
            )
        # Placeholder ("<prompt>") when the real prompt isn't known yet
        # (e.g. during freeze(), which must record argv before a study
        # plan is hashed, without the prompt content itself in that argv).
        argv.extend(
            [profile.prompt_arg_flag, inline_prompt if inline_prompt is not None else "<prompt>"]
        )
    argv.extend(profile.base_args)
    argv.extend(profile.role_args.get(role.value, ()))
    if model:
        argv.extend(["--model", model])
    if profile.prompt_transport == PromptTransport.PROMPT_FILE:
        if not profile.prompt_file_flag:
            raise AdapterError(
                f"Harness {profile.harness_id!r} declares PROMPT_FILE transport but has "
                "no prompt_file_flag configured."
            )
        argv.extend([profile.prompt_file_flag, prompt_file_path or "<prompt-file>"])
    return argv


def _classify_and_parse(
    profile: HarnessProfile, returncode: int, stdout: str, stderr: str
) -> tuple[ExitState, Optional[dict]]:
    combined_lower = (stdout + "\n" + stderr).lower()
    if any(marker in combined_lower for marker in profile.quota_markers):
        return ExitState.QUOTA_EXHAUSTED, None

    if returncode != 0:
        return ExitState.NONZERO_EXIT, None

    if profile.output_format == "text":
        return ExitState.SUCCESS, None

    if profile.output_format == "json":
        try:
            parsed = json.loads(stdout)
        except (json.JSONDecodeError, TypeError):
            return ExitState.MALFORMED_OUTPUT, None
        if not isinstance(parsed, dict):
            return ExitState.MALFORMED_OUTPUT, None
        return ExitState.SUCCESS, parsed

    if profile.output_format == "jsonl":
        last_parsed = None
        saw_any_line = False
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            saw_any_line = True
            try:
                candidate = json.loads(line)
            except json.JSONDecodeError:
                return ExitState.MALFORMED_OUTPUT, None
            if isinstance(candidate, dict):
                last_parsed = candidate
        if not saw_any_line or last_parsed is None:
            return ExitState.MALFORMED_OUTPUT, None
        return ExitState.SUCCESS, last_parsed

    raise AdapterError(
        f"Unknown output_format on profile {profile.harness_id!r}: {profile.output_format!r}"
    )


def invoke(
    harness_id: str,
    role: Role,
    model: str,
    prompt: str,
    workspace: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> AdapterResult:
    """Run one headless harness call. Never raises for a failed call -- every
    outcome short of a well-formed success is returned as a typed
    AdapterResult with raw stdout/stderr preserved, never silently treated as
    success."""
    profile = get_profile(harness_id)
    initiator = resolve_initiator_identity()
    executable_path = shutil.which(profile.executable)
    if not executable_path:
        return AdapterResult(
            exit_state=ExitState.MISSING_EXECUTABLE,
            returncode=None,
            stdout="",
            stderr=f"executable not found on PATH: {profile.executable!r}",
            parsed_output=None,
            duration_seconds=0.0,
            argv=tuple(),
            initiator=initiator,
        )

    prompt_file_path = None
    temp_prompt_file = None
    try:
        if profile.prompt_transport == PromptTransport.PROMPT_FILE:
            import tempfile

            fd, temp_prompt_file = tempfile.mkstemp(prefix="opr-adapter-prompt-", suffix=".txt")
            with open(fd, "w") as handle:
                handle.write(prompt)
            prompt_file_path = temp_prompt_file

        inline_prompt = prompt if profile.prompt_transport == PromptTransport.INLINE_ARG else None
        argv = build_argv(profile, role, model, prompt_file_path, inline_prompt)
        argv[0] = executable_path

        stdin_data = prompt if profile.prompt_transport == PromptTransport.STDIN else None

        start = time.monotonic()
        try:
            res = subprocess.run(
                argv,
                input=stdin_data,
                capture_output=True,
                text=True,
                cwd=str(workspace),
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - start
            return AdapterResult(
                exit_state=ExitState.TIMEOUT,
                returncode=None,
                stdout=(exc.stdout or "") if isinstance(exc.stdout, str) else "",
                stderr=(exc.stderr or "") if isinstance(exc.stderr, str) else "",
                parsed_output=None,
                duration_seconds=duration,
                argv=tuple(argv),
                initiator=initiator,
            )
        except OSError as exc:
            duration = time.monotonic() - start
            return AdapterResult(
                exit_state=ExitState.MISSING_EXECUTABLE,
                returncode=None,
                stdout="",
                stderr=str(exc),
                parsed_output=None,
                duration_seconds=duration,
                argv=tuple(argv),
                initiator=initiator,
            )
        duration = time.monotonic() - start

        exit_state, parsed = _classify_and_parse(profile, res.returncode, res.stdout, res.stderr)
        return AdapterResult(
            exit_state=exit_state,
            returncode=res.returncode,
            stdout=res.stdout,
            stderr=res.stderr,
            parsed_output=parsed,
            duration_seconds=duration,
            argv=tuple(argv),
            initiator=initiator,
        )
    finally:
        if temp_prompt_file:
            try:
                Path(temp_prompt_file).unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Legacy string-template config (deprecated, kept for opr.yaml compatibility)
# ---------------------------------------------------------------------------


def build_legacy_argv(cmd_template: str, prompt: str) -> tuple[list[str], bool]:
    """Deprecated path for opr.yaml's old `frontier.commands.<harness>` string
    templates. Still never shells out through shell=True -- shlex.split plus
    {prompt}/{task} substitution into individual argv tokens, exactly as
    opr's original dispatch_frontier() did. Returns (argv, has_placeholder);
    callers should pass the prompt via stdin when has_placeholder is False."""
    cmd_args = shlex.split(cmd_template)
    has_placeholder = False
    for i in range(len(cmd_args)):
        if "{prompt}" in cmd_args[i]:
            cmd_args[i] = cmd_args[i].replace("{prompt}", prompt)
            has_placeholder = True
        if "{task}" in cmd_args[i]:
            cmd_args[i] = cmd_args[i].replace("{task}", prompt)
            has_placeholder = True
    return cmd_args, has_placeholder


LEGACY_FALLBACK_COMMANDS = {
    # agy's old fallback was the bare string "antigravity", which is not a
    # real invocable command on this machine or documented anywhere -- the
    # real CLI is `agy`. claude/codex fall back to their own real executable
    # names, which were already correct.
    "claude": "claude",
    "codex": "codex",
    "agy": "agy",
}
