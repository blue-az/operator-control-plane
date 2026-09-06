#!/usr/bin/env python3
"""Offline POE-FUT-014 compatibility audit runner.

Exercises the pinned local pbc-spec CLI and Operator pbc_lint.py against
poe_fut014 fixtures. Does not install packages, touch the network, modify
PBC sources, ratify rules, or execute stored verification commands.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURES = ROOT / "tests" / "fixtures" / "poe_fut014"
DEFAULT_PBC_SPEC = Path("/home/blueaz/Python/Evaluation/pbc-spec")
MANIFEST_NAME = "poe_fut014_manifest.json"

sys.path.insert(0, str(ROOT))
import pbc_lint


def resolve_pbc_spec(explicit: Path | None = None) -> Path | None:
    if explicit is not None:
        return explicit
    env = os.environ.get("POE_FUT014_PBC_SPEC")
    if env:
        return Path(env)
    if DEFAULT_PBC_SPEC.is_dir():
        return DEFAULT_PBC_SPEC
    return None


def resolved_git_root(pbc_spec: Path) -> Path | None:
    """Return the absolute git root only if *pbc_spec* is a directory with ``.git``.

    Used before any scoped ``safe.directory`` exception. Does not consult Git
    config and does not treat a wildcard or directory prefix as a valid root.
    """
    try:
        root = pbc_spec.resolve()
    except OSError:
        return None
    if not root.is_dir():
        return None
    if not (root / ".git").exists():
        return None
    return root


def scoped_safe_directory_value(root: Path) -> str | None:
    """Exact per-invocation ``safe.directory`` value, or None if it would be global.

    Never returns a wildcard, empty string, or a prefix that ends in ``/*``.
    """
    value = str(root)
    if not value or value == "*" or value.endswith("/*"):
        return None
    if not root.is_absolute():
        return None
    return value


def _git(pbc_spec: Path, *args: str) -> dict[str, Any]:
    """Run a read-only git command against a validated root.

    After the path is confirmed to be a git root, pass a **per-invocation**
    ``-c safe.directory=<resolved-root>`` so a distinct-UID verifier can read
    commit metadata in a checkout it does not own. This is not a global
    ``git config`` change and not a wildcard trust exception.
    """
    root = resolved_git_root(pbc_spec)
    if root is None:
        return {
            "stdout": "",
            "stderr": f"not a git repository at expected root {pbc_spec}",
            "returncode": 128,
            "argv": [],
            "root": None,
        }
    safe = scoped_safe_directory_value(root)
    if safe is None:
        return {
            "stdout": "",
            "stderr": f"refusing unscoped safe.directory for {root}",
            "returncode": 128,
            "argv": [],
            "root": str(root),
        }
    argv = ["git", "-c", f"safe.directory={safe}", *args]
    try:
        result = subprocess.run(
            argv,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except FileNotFoundError:
        return {
            "stdout": "",
            "stderr": "git executable not found",
            "returncode": 127,
            "argv": argv,
            "root": str(root),
        }
    return {
        "stdout": result.stdout.strip(),
        "stderr": (result.stderr or "").strip(),
        "returncode": int(result.returncode),
        "argv": argv,
        "root": str(root),
    }


def _record_git_error(result: dict[str, Any], errors: list[str]) -> str:
    stdout = str(result.get("stdout") or "")
    if int(result.get("returncode") or 0) == 0:
        return stdout
    err = str(result.get("stderr") or "").strip() or f"git exited {result.get('returncode')}"
    if err not in errors:
        errors.append(err)
    return stdout


def pin_upstream(pbc_spec: Path) -> dict[str, Any]:
    package_json = pbc_spec / "cli" / "package.json"
    cli_version = None
    if package_json.is_file():
        cli_version = json.loads(package_json.read_text(encoding="utf-8")).get("version")
    spec_path = pbc_spec / "docs" / "specs" / "pbc-spec-v0.6.md"
    spec_version = None
    if spec_path.is_file():
        for line in spec_path.read_text(encoding="utf-8").splitlines()[:8]:
            if "**Version:**" in line:
                spec_version = line.split("**Version:**", 1)[1].strip().strip("*").strip()
                break
    git_errors: list[str] = []
    commit = _record_git_error(_git(pbc_spec, "rev-parse", "HEAD"), git_errors)
    describe = _record_git_error(
        _git(pbc_spec, "describe", "--tags", "--long", "--always"), git_errors
    )
    branch = _record_git_error(_git(pbc_spec, "rev-parse", "--abbrev-ref", "HEAD"), git_errors)
    subject = _record_git_error(_git(pbc_spec, "log", "-1", "--format=%s"), git_errors)
    committed_at = _record_git_error(_git(pbc_spec, "log", "-1", "--format=%cI"), git_errors)
    status = _git(pbc_spec, "status", "--porcelain")
    if int(status.get("returncode") or 0) == 0:
        working_tree_clean = status.get("stdout") == ""
    else:
        _record_git_error(status, git_errors)
        working_tree_clean = False
    git_root = resolved_git_root(pbc_spec)
    return {
        "path": str(pbc_spec),
        "commit": commit,
        "describe": describe,
        "branch": branch,
        "subject": subject,
        "committed_at": committed_at,
        "spec_version": spec_version,
        "cli_package_name": "@pbc-spec/cli",
        "cli_package_version": cli_version,
        "cli_bin": str(pbc_spec / "cli" / "dist" / "bin" / "pbc.js"),
        "has_profile_flag": False,
        "working_tree_clean": working_tree_clean,
        "git_root": str(git_root) if git_root is not None else "",
        "git_errors": git_errors,
    }


def load_manifest(fixtures_dir: Path) -> dict[str, Any]:
    path = fixtures_dir / MANIFEST_NAME
    return json.loads(path.read_text(encoding="utf-8"))


def run_upstream_validate(
    pbc_spec: Path, target: Path
) -> tuple[int, dict[str, list[dict[str, Any]]], str]:
    cli_dir = pbc_spec / "cli"
    bin_js = cli_dir / "dist" / "bin" / "pbc.js"
    if not bin_js.is_file():
        raise FileNotFoundError(f"pbc CLI not built at {bin_js}")
    env = os.environ.copy()
    env["NO_COLOR"] = "1"
    env["FORCE_COLOR"] = "0"
    env["npm_config_offline"] = "true"
    proc = subprocess.run(
        ["node", str(bin_js), "validate", "--format", "json", str(target)],
        cwd=str(cli_dir),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
        check=False,
    )
    payload: dict[str, list[dict[str, Any]]] = {}
    stdout = proc.stdout.strip()
    if stdout:
        parsed = json.loads(stdout)
        if isinstance(parsed, dict):
            payload = parsed
    return proc.returncode, payload, proc.stderr


def flatten_cli_results(payload: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_path, results in payload.items():
        for row in results:
            item = dict(row)
            item.setdefault("file", file_path)
            rows.append(item)
    return rows


def run_pbc_lint(target: Path) -> tuple[int, list[str]]:
    errors = pbc_lint.lint_file(target, ledger_names=None)
    return (1 if errors else 0), errors


def check_no_silent_drop(rows: list[dict[str, Any]], required_types: list[str]) -> list[str]:
    problems: list[str] = []
    surfaced = {
        str(row.get("blockType"))
        for row in rows
        if row.get("checkId") == "E004" and row.get("severity") == "error"
    }
    messages = " ".join(str(row.get("message", "")) for row in rows)
    for block_type in required_types:
        if block_type in surfaced:
            continue
        if f"pbc:{block_type}" in messages or f"`pbc:{block_type}`" in messages:
            continue
        problems.append(f"unsupported block pbc:{block_type} was not reported as E004")
    return problems


def audit_fixture(pbc_spec: Path, fixtures_dir: Path, spec: dict[str, Any]) -> dict[str, Any]:
    path = fixtures_dir / spec["file"]
    cli_exit, payload, cli_stderr = run_upstream_validate(pbc_spec, path)
    rows = flatten_cli_results(payload)
    lint_exit, lint_errors = run_pbc_lint(path)
    error_ids = sorted({str(row.get("checkId")) for row in rows if row.get("severity") == "error"})
    warning_ids = sorted(
        {str(row.get("checkId")) for row in rows if row.get("severity") == "warning"}
    )
    silent_drop = check_no_silent_drop(rows, spec.get("must_surface_block_types") or [])
    mismatches: list[str] = []
    if cli_exit != spec["expect_cli_exit"]:
        mismatches.append(f"cli exit {cli_exit} != expected {spec['expect_cli_exit']}")
    for check_id in spec.get("expect_cli_error_ids") or []:
        if check_id not in error_ids:
            mismatches.append(f"missing CLI error {check_id}")
    for check_id in spec.get("expect_cli_warning_ids") or []:
        if check_id not in warning_ids:
            mismatches.append(f"missing CLI warning {check_id}")
    expect_lint = bool(spec.get("expect_pbc_lint_errors"))
    if expect_lint and lint_exit == 0:
        mismatches.append("pbc_lint produced no errors")
    if not expect_lint and lint_exit != 0:
        mismatches.append(f"pbc_lint errors: {lint_errors}")
    needle = spec.get("pbc_lint_must_match")
    if needle and not any(needle in err for err in lint_errors):
        mismatches.append(f"pbc_lint missing {needle!r}")
    mismatches.extend(silent_drop)
    return {
        "file": spec["file"],
        "class": spec["class"],
        "path": str(path),
        "cli_exit": cli_exit,
        "cli_error_ids": error_ids,
        "cli_warning_ids": warning_ids,
        "cli_results": rows,
        "cli_stderr": cli_stderr,
        "pbc_lint_exit": lint_exit,
        "pbc_lint_errors": lint_errors,
        "silent_drop": silent_drop,
        "mismatches": mismatches,
        "pbc_lint_gap": spec.get("pbc_lint_gap"),
        "ok": not mismatches,
    }


def run_audit(
    fixtures_dir: Path,
    pbc_spec: Path,
) -> dict[str, Any]:
    manifest = load_manifest(fixtures_dir)
    pin = pin_upstream(pbc_spec)
    results = [audit_fixture(pbc_spec, fixtures_dir, spec) for spec in manifest["fixtures"]]
    return {
        "audit": "POE-FUT-014",
        "ratified": False,
        "route_chosen": False,
        "upstream": pin,
        "fixtures_dir": str(fixtures_dir),
        "results": results,
        "fail_closed_violations": [
            row["file"] for row in results if row["silent_drop"] or not row["ok"]
        ],
    }


def format_text(report: dict[str, Any]) -> str:
    pin = report["upstream"]
    lines = [
        "POE-FUT-014 compatibility audit (not a ruling)",
        f"upstream commit: {pin.get('commit')}",
        f"upstream describe: {pin.get('describe')}",
        f"spec: {pin.get('spec_version')}  cli: {pin.get('cli_package_name')}@{pin.get('cli_package_version')}",
        f"branch: {pin.get('branch')}  profile flag: {pin.get('has_profile_flag')}",
        "",
        f"{'fixture':<48} {'cli':>4} {'lint':>4} errors              warnings",
    ]
    for row in report["results"]:
        mark = "ok" if row["ok"] else "FAIL"
        lines.append(
            f"{row['file']:<48} {row['cli_exit']:>4} {row['pbc_lint_exit']:>4} "
            f"{','.join(row['cli_error_ids']) or '-':<18} "
            f"{','.join(row['cli_warning_ids']) or '-'}  {mark}"
        )
        for mismatch in row["mismatches"]:
            lines.append(f"  mismatch: {mismatch}")
        if row.get("pbc_lint_gap") and row["pbc_lint_exit"] == 0:
            lines.append(f"  gap: {row['pbc_lint_gap']}")
    lines.append("")
    violations = report["fail_closed_violations"]
    if violations:
        lines.append("fail-closed violations: " + ", ".join(violations))
    else:
        lines.append("no silent-drop / expectation violations in fixture matrix")
    lines.append("route not chosen; no rules ratified")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="POE-FUT-014 offline PBC compatibility audit")
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument("--pbc-spec", type=Path, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional JSON report path. Must not be a runtime ledger record.",
    )
    args = parser.parse_args(argv)
    pbc_spec = resolve_pbc_spec(args.pbc_spec)
    if pbc_spec is None or not pbc_spec.is_dir():
        print("Error: pbc-spec path not found. Set POE_FUT014_PBC_SPEC.", file=sys.stderr)
        return 2
    report = run_audit(args.fixtures, pbc_spec)
    if args.out is not None:
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_text(report))
    if report["fail_closed_violations"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
