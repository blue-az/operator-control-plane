#!/usr/bin/env python3
"""Disposable trusted-consumer Pi smoke for POE-FUT-012/010/011.

Creates a temp consumer project and a temp Operator ledger, installs the
extension with an explicit contract, and exercises read-only /op:next-steps
and /op:project under isolated Pi config/trust/session paths.

Uses ``pi --approve`` for that disposable project only. Does not copy
auth/credentials, does not write host ``~/.pi/agent/trust.json``, does not
publish, and does not mutate the control-plane runtime ledger.

Existing mocked pi-server loader coverage is not equivalent. If the live
session cannot start, this script records the exact blocker and exits 2
rather than fabricating a pass.
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install-operator-extension.py"
OPERATOR_SRC = ROOT / "operator"
SMOKE_PREFIX = "poe-route-c-pi-smoke-"


def _run(
    argv: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def write_operator_shim(dest: Path) -> None:
    dest.write_text(
        "#!/usr/bin/env python3\n"
        "import os\n"
        "import sys\n"
        f"REPO = {str(OPERATOR_SRC.parent)!r}\n"
        "os.execv(sys.executable, [sys.executable, os.path.join(REPO, 'operator'), *sys.argv[1:]])\n",
        encoding="utf-8",
    )
    dest.chmod(dest.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def isolated_env(pi_home: Path, session_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["PI_CODING_AGENT_DIR"] = str(pi_home)
    env["PI_CODING_AGENT_SESSION_DIR"] = str(session_dir)
    env["PI_OFFLINE"] = "1"
    env["PI_SKIP_VERSION_CHECK"] = "1"
    env["PI_TELEMETRY"] = "0"
    env["NO_COLOR"] = "1"
    # Host FORCE_COLOR makes pi warn and can confuse empty-output checks.
    env.pop("FORCE_COLOR", None)
    env.pop("PI_PACKAGE_DIR", None)
    return env


def setup_temp_ledger(ledger_root: Path) -> None:
    write_operator_shim(ledger_root / "operator")
    init = _run([str(ledger_root / "operator"), "init"], cwd=ledger_root, timeout=30)
    if init.returncode != 0:
        raise RuntimeError(f"operator init failed: {init.stdout}\n{init.stderr}")
    # Orientation commands read this PBC from ledger.root. Copy the file into
    # the disposable control plane; do not copy .operator/ runtime records.
    pbc_src = ROOT / "owners-manual" / "pbc" / "appendix-pi-operator-extension.pbc.md"
    pbc_dest = ledger_root / "owners-manual" / "pbc" / "appendix-pi-operator-extension.pbc.md"
    pbc_dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pbc_src, pbc_dest)
    created = _run(
        [
            str(ledger_root / "operator"),
            "task-create",
            "--id",
            "smoke-demo-alpha",
            "--objective",
            "Disposable smoke-test task for /op:project prefix matching.",
        ],
        cwd=ledger_root,
        timeout=30,
    )
    if created.returncode != 0:
        raise RuntimeError(f"task-create failed: {created.stdout}\n{created.stderr}")


def install_extension(consumer: Path, ledger_root: Path) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            sys.executable,
            str(INSTALLER),
            "--target",
            str(consumer),
            "--source",
            str(ROOT),
            "--ledger",
            str(ledger_root),
            "--method",
            "copy",
            "--yes",
        ],
        cwd=ROOT,
        timeout=30,
    )


def classify_blob(blob: str) -> str | None:
    lowered = blob.lower()
    if "cannot find package '@earendil-works/pi-server'" in lowered:
        return (
            "optional package @earendil-works/pi-server is not installed; "
            "real pi session import path requires it. "
            "Existing selftest registerHooks coverage is not equivalent."
        )
    if "cannot find package" in lowered:
        first = next(
            (line for line in blob.splitlines() if "cannot find package" in line.lower()),
            blob[:300],
        )
        return f"missing optional package/environment: {first.strip()}"
    if "not authenticated" in lowered or "api key" in lowered or "no api key" in lowered:
        return (
            "session fell through to a model call; credentials were "
            "intentionally not copied into the isolated Pi config."
        )
    return None


def _parse_jsonl(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows


def run_pi_rpc(consumer: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    """Exercise slash commands via the documented RPC handler path.

    Print mode (``pi -p``) can accept an extension command and exit 0 without
    printing TUI-only ``appendEntry`` / ``notify`` output. RPC ``prompt`` of
    ``/op:*`` is the supported headless path (Pi 0.85 rpc.md). stdin is kept
    open until the prompt responses arrive; closing it after get_commands
    made pi exit before handling /op:next-steps.
    """
    argv = [
        "pi",
        "--mode",
        "rpc",
        "--offline",
        "--approve",
        "--no-context-files",
        "--no-skills",
        "--session-dir",
        env["PI_CODING_AGENT_SESSION_DIR"],
        "--no-session",
    ]
    proc = subprocess.Popen(
        argv,
        cwd=str(consumer),
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    events: list[dict[str, Any]] = []
    stdout_parts: list[str] = []
    command_names: list[str] = []
    err_chunks: list[str] = []
    out_q: queue.Queue[str | None] = queue.Queue()

    def read_stdout() -> None:
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                out_q.put(line)
        finally:
            out_q.put(None)

    def read_stderr() -> None:
        assert proc.stderr is not None
        err_chunks.append(proc.stderr.read() or "")

    t_out = threading.Thread(target=read_stdout, daemon=True)
    t_err = threading.Thread(target=read_stderr, daemon=True)
    t_out.start()
    t_err.start()

    def send(obj: dict[str, Any]) -> None:
        assert proc.stdin is not None
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def ingest(line: str) -> dict[str, Any] | None:
        stdout_parts.append(line)
        stripped = line.strip()
        if not stripped.startswith("{"):
            return None
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            return None
        if isinstance(event, dict):
            events.append(event)
            return event
        return None

    def collect_until(request_id: str, deadline: float) -> dict[str, Any] | None:
        while time.monotonic() < deadline:
            remaining = max(0.05, deadline - time.monotonic())
            try:
                line = out_q.get(timeout=min(0.5, remaining))
            except queue.Empty:
                if proc.poll() is not None and out_q.empty():
                    break
                continue
            if line is None:
                break
            event = ingest(line)
            if event and event.get("type") == "response" and event.get("id") == request_id:
                return event
        return None

    exit_code: int | None = None
    try:
        deadline = time.monotonic() + timeout
        send({"id": "cmd-list", "type": "get_commands"})
        listed = collect_until("cmd-list", deadline)
        if listed:
            data = listed.get("data") or {}
            commands = data.get("commands") if isinstance(data, dict) else None
            if isinstance(commands, list):
                for item in commands:
                    if isinstance(item, dict) and isinstance(item.get("name"), str):
                        command_names.append(item["name"])
        send({"id": "next-steps", "type": "prompt", "message": "/op:next-steps"})
        collect_until("next-steps", deadline)
        collect_until("__drain-next__", min(deadline, time.monotonic() + 1.5))
        send({"id": "project", "type": "prompt", "message": "/op:project smoke-demo"})
        collect_until("project", deadline)
        collect_until("__drain-project__", min(deadline, time.monotonic() + 1.5))
    finally:
        if proc.stdin:
            try:
                proc.stdin.close()
            except OSError:
                pass
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        while True:
            try:
                line = out_q.get_nowait()
            except queue.Empty:
                break
            if line:
                ingest(line)
        exit_code = proc.returncode
    stdout = "".join(stdout_parts)
    stderr = "".join(err_chunks)
    blob = stdout + "\n" + stderr
    return {
        "argv": argv,
        "exit": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "events": events,
        "command_names": command_names,
        "blob": blob,
        "print_mode_note": (
            "pi -p /op:next-steps was observed to exit 0 with empty stdout because "
            "print mode has hasUI=false; RPC is the supported handler path used here."
        ),
    }


def run_smoke(work: Path, *, timeout: int) -> dict[str, Any]:
    ledger_root = work / "control-plane"
    consumer = work / "consumer"
    pi_home = work / "pi-agent"
    session_dir = work / "pi-sessions"
    ledger_root.mkdir()
    consumer.mkdir()
    pi_home.mkdir()
    session_dir.mkdir()
    setup_temp_ledger(ledger_root)
    install = install_extension(consumer, ledger_root)
    contract = consumer / ".pi" / "operator-ledger.json"
    report: dict[str, Any] = {
        "smoke": "poe-route-c-pi-trusted-consumer",
        "work": str(work),
        "ledger_root": str(ledger_root),
        "consumer": str(consumer),
        "pi_home": str(pi_home),
        "session_dir": str(session_dir),
        "host_trust_json": str(Path.home() / ".pi" / "agent" / "trust.json"),
        "copied_credentials": False,
        "install_exit": install.returncode,
        "install_stdout": install.stdout,
        "install_stderr": install.stderr,
        "contract_exists": contract.is_file(),
        "commands": {},
        "ok": False,
        "blocker": None,
    }
    if install.returncode != 0 or not contract.is_file():
        report["blocker"] = f"install failed: {install.stderr or install.stdout}"
        return report
    contract_data = json.loads(contract.read_text(encoding="utf-8"))
    report["contract_ledger_root"] = contract_data.get("ledger_root")
    report["runtime_ledger_copied"] = contract_data.get("runtime_ledger_copied")
    if contract_data.get("ledger_root") != str(ledger_root.resolve()):
        report["blocker"] = "contract ledger_root is not the temp ledger"
        return report
    if contract_data.get("runtime_ledger_copied") is not False:
        report["blocker"] = "installer copied runtime ledger data"
        return report
    env = isolated_env(pi_home, session_dir)
    which = shutil.which("pi")
    report["pi_bin"] = which
    if not which:
        report["blocker"] = "pi executable not found on PATH"
        return report
    version = _run(["pi", "--version"], env=env, timeout=15)
    report["pi_version"] = (version.stdout or version.stderr or "").strip()
    try:
        rpc = run_pi_rpc(consumer, env, timeout)
    except subprocess.TimeoutExpired as exc:
        report["blocker"] = f"timeout after {timeout}s running {exc.cmd}"
        return report
    report["commands"]["rpc"] = {
        "argv": rpc["argv"],
        "exit": rpc["exit"],
        "stdout": rpc["stdout"],
        "stderr": rpc["stderr"],
        "command_names": rpc["command_names"],
        "event_types": [str(event.get("type")) for event in rpc["events"]],
        "print_mode_note": rpc["print_mode_note"],
    }
    blocker = classify_blob(rpc["blob"])
    if blocker:
        report["blocker"] = blocker
        return report
    names = set(rpc["command_names"])
    if "op:next-steps" not in names or "op:project" not in names:
        report["blocker"] = (
            "RPC get_commands did not list op:next-steps and op:project after "
            "--approve in the disposable consumer. "
            f"seen={sorted(names)[:40]}"
        )
        return report
    blob_l = rpc["blob"].lower()
    if "no operator ledger" in blob_l or "malformed ledger" in blob_l:
        report["blocker"] = "extension loaded but findLedger failed: " + rpc["blob"][-500:]
        return report
    appended = [
        event.get("entry", {}).get("data", {}).get("command")
        for event in rpc["events"]
        if event.get("type") == "entry_appended"
    ]
    if "/op:next-steps" not in appended or "/op:project" not in appended:
        report["blocker"] = (
            "RPC prompt succeeded but operator-report entries were missing. "
            f"appended={appended} excerpt={(rpc['stdout'] + rpc['stderr'])[-700:]}"
        )
        return report
    if "smoke-demo" not in blob_l:
        report["blocker"] = (
            "RPC /op:project ran but output did not mention the temp task prefix "
            "smoke-demo. Not treating as a live pass. "
            f"excerpt={(rpc['stdout'] + rpc['stderr'])[-700:]}"
        )
        return report
    trust_in_isolated = pi_home / "trust.json"
    host_trust = Path.home() / ".pi" / "agent" / "trust.json"
    report["isolated_trust_written"] = trust_in_isolated.is_file()
    report["host_trust_untouched_by_this_script"] = True
    report["host_trust_exists"] = host_trust.is_file()
    report["ok"] = True
    return report


def cleanup(work: Path) -> None:
    resolved = work.resolve()
    if SMOKE_PREFIX not in resolved.name:
        raise RuntimeError(f"refusing to delete unexpected path {resolved}")
    tmp = Path(tempfile.gettempdir()).resolve()
    if not (resolved == tmp or str(resolved).startswith(str(tmp) + os.sep)):
        raise RuntimeError(f"refusing to delete path outside tempdir: {resolved}")
    shutil.rmtree(resolved, ignore_errors=False)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Disposable Pi trusted-consumer smoke (Route C)")
    parser.add_argument("--keep", action="store_true", help="leave the temp tree in place")
    parser.add_argument("--work", type=Path, default=None)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    work = args.work
    created = False
    if work is None:
        work = Path(tempfile.mkdtemp(prefix=SMOKE_PREFIX, dir="/tmp"))
        created = True
    else:
        work.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any]
    try:
        report = run_smoke(work, timeout=args.timeout)
    except subprocess.TimeoutExpired as exc:
        report = {
            "ok": False,
            "blocker": f"timeout after {args.timeout}s running {exc.cmd}",
            "work": str(work),
        }
    except Exception as exc:  # noqa: BLE001 - smoke must record the exact blocker
        report = {"ok": False, "blocker": f"{type(exc).__name__}: {exc}", "work": str(work)}
    report["kept"] = bool(args.keep)
    text = json.dumps(report, indent=2)
    if args.out is not None:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)
    if not args.keep and created:
        try:
            cleanup(work)
            report["cleaned"] = True
        except Exception as exc:  # noqa: BLE001
            print(f"cleanup failed: {exc}", file=sys.stderr)
            return 1
    if report.get("ok"):
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
