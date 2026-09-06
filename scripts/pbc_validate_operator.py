#!/usr/bin/env python3
"""Local Operator PBC compatibility wrapper (POE-FUT-014 Route C).

Invokes the pinned upstream ``pbc-spec`` CLI JSON validator, allowlists
Operator lifecycle fences and named local vocabulary, then runs
``pbc_lint.py`` invariants 1-4. This is **not** an upstream --profile flag
(the pinned CLI has none).

Route C records a compatibility check. It does **not** ratify proposed
rules, rewrite ``proposed-*`` into ``pbc:rules``, or relabel provenance.

Allowlist (by name only; everything else stays an error):

* E004 ``proposed-rules`` / ``proposed-behavior`` / ``proposed-outcomes``
* E011 provenance ``confidence: measured`` (empirical measurement; not
  ``verified`` / established). Other E011 values still fail.

Never blanket-ignores E004/E011. Allowlisted findings remain in the
report as ``allowlisted`` rows. Unknown block types, malformed YAML,
missing frontmatter, and unsupported confidence values still fail closed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import poe_fut014_audit

import pbc_lint

PINNED_COMMIT = "ca97caf63329cee5ecf2b92dfe1120374ab90a81"
PINNED_SPEC_VERSION = "0.6.0-draft"
PINNED_CLI_PACKAGE_VERSION = "0.1.0"
WRAPPER_NAME = "pbc_validate_operator"
ROUTE = "C"

ALLOWLISTED_PROPOSED_BLOCKS = frozenset(
    {"proposed-rules", "proposed-behavior", "proposed-outcomes"}
)
ALLOWLISTED_LOCAL_CONFIDENCE = frozenset({"measured"})
ALLOWLISTED_LOCAL_TRUST = frozenset(
    {
        "proposed",
        "verified",
        "agreed",
        "agreed-pending-operator",
    }
)
UPSTREAM_TRUST = frozenset({"trusted", "provisional", "scaffolding"})
ALLOWLISTED_LOCAL_STATUS = frozenset({"active"})
UPSTREAM_STATUS = frozenset({"draft", "review", "agreed", "deprecated"})

E004_TYPE_RE = re.compile(r"pbc:([A-Za-z0-9_-]+)")
E011_VALUE_RE = re.compile(r'invalid confidence value "([^"]+)"')

CONFIDENCE_MEASURED_NOTE = (
    "Operator-local provenance confidence 'measured' means an empirical "
    "measurement or study citation; it is not UID-isolated verification and "
    "is not relabeled to verified/inferred/assumed."
)


def _block_type_from_row(row: dict[str, Any]) -> str | None:
    raw = row.get("blockType")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    message = str(row.get("message") or "")
    match = E004_TYPE_RE.search(message)
    if match:
        return match.group(1)
    return None


def _confidence_value_from_row(row: dict[str, Any]) -> str | None:
    message = str(row.get("message") or "")
    match = E011_VALUE_RE.search(message)
    if match:
        return match.group(1)
    return None


def classify_cli_row(row: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of *row* with wrapper classification.

    ``disposition`` is one of: error, warning, allowlisted.
    """
    item = dict(row)
    check_id = str(item.get("checkId") or "")
    severity = str(item.get("severity") or "")
    if check_id == "E004" and severity == "error":
        block_type = _block_type_from_row(item)
        if block_type in ALLOWLISTED_PROPOSED_BLOCKS:
            item["disposition"] = "allowlisted"
            item["allowlist_reason"] = (
                f"Operator lifecycle fence pbc:{block_type} (Route C local wrapper; "
                "not an upstream block type; not ratification)"
            )
            return item
        item["disposition"] = "error"
        item["wrapper_note"] = (
            f"unknown block type {block_type!r} is not in the Operator proposed-* "
            "allowlist; E004 is kept"
        )
        return item
    if check_id == "E011" and severity == "error":
        value = _confidence_value_from_row(item)
        if value in ALLOWLISTED_LOCAL_CONFIDENCE:
            item["disposition"] = "allowlisted"
            item["allowlist_reason"] = CONFIDENCE_MEASURED_NOTE
            item["confidence_value"] = value
            return item
        item["disposition"] = "error"
        item["wrapper_note"] = (
            "E011 kept: missing or unsupported provenance confidence "
            f"(value={value!r}; measured is the only Operator-local allowlist entry)"
        )
        return item
    if severity == "error":
        item["disposition"] = "error"
        return item
    item["disposition"] = "warning" if severity == "warning" else severity or "info"
    if check_id == "W013":
        item["wrapper_note"] = (
            "local trust vocabulary on a known block is a CLI warning, not an error; "
            f"Operator-local extras: {sorted(ALLOWLISTED_LOCAL_TRUST)}; "
            "pbc_lint invariant 1 still rejects trust: proposed inside pbc:rules"
        )
    if check_id == "W011":
        item["wrapper_note"] = (
            "status: active is Operator-local (pbc_lint invariant 4); "
            "upstream recommended statuses stay draft/review/agreed/deprecated"
        )
    return item


def _iter_targets(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".md":
            files.append(path)
        elif path.is_dir():
            files.extend(sorted(path.rglob("*.pbc.md")))
    return files


def validate_pin(pin: dict[str, Any], *, require_pin: bool) -> list[str]:
    problems: list[str] = []
    if pin.get("has_profile_flag"):
        problems.append("pinned CLI unexpectedly advertises --profile; wrapper must not claim it")
    if not require_pin:
        return problems
    commit = str(pin.get("commit") or "")
    if commit != PINNED_COMMIT:
        problems.append(f"upstream commit {commit or '(missing)'} != pinned {PINNED_COMMIT}")
        for err in pin.get("git_errors") or []:
            text = str(err).strip()
            if text:
                problems.append(f"git: {text}")
    spec = pin.get("spec_version")
    if spec != PINNED_SPEC_VERSION:
        problems.append(f"spec version {spec!r} != pinned {PINNED_SPEC_VERSION!r}")
    cli_version = pin.get("cli_package_version")
    if cli_version != PINNED_CLI_PACKAGE_VERSION:
        problems.append(
            f"cli package version {cli_version!r} != pinned {PINNED_CLI_PACKAGE_VERSION!r}"
        )
    return problems


def run_wrapper(
    targets: list[Path],
    pbc_spec: Path,
    *,
    ledger: Path | None = None,
    require_pin: bool = True,
) -> dict[str, Any]:
    pin = poe_fut014_audit.pin_upstream(pbc_spec)
    pin_problems = validate_pin(pin, require_pin=require_pin)
    files = _iter_targets(targets)
    classified: list[dict[str, Any]] = []
    cli_stderr: list[str] = []
    for path in files:
        _code, payload, stderr = poe_fut014_audit.run_upstream_validate(pbc_spec, path)
        if stderr:
            cli_stderr.append(stderr)
        for row in poe_fut014_audit.flatten_cli_results(payload):
            classified.append(classify_cli_row(row))

    ledger_names = pbc_lint._ledger_mentions(ledger) if ledger is not None else None
    lint_errors: list[str] = []
    for path in files:
        lint_errors.extend(pbc_lint.lint_file(path, ledger_names))

    errors = [row for row in classified if row.get("disposition") == "error"]
    warnings = [row for row in classified if row.get("disposition") == "warning"]
    allowlisted = [row for row in classified if row.get("disposition") == "allowlisted"]
    remaining_error_ids = sorted({str(row.get("checkId")) for row in errors})
    allowlisted_ids = sorted({str(row.get("checkId")) for row in allowlisted})

    fail_reasons: list[str] = []
    fail_reasons.extend(pin_problems)
    if not files:
        fail_reasons.append("no PBC files found")
    if errors:
        fail_reasons.append(
            f"{len(errors)} remaining CLI error(s): {', '.join(remaining_error_ids)}"
        )
    if lint_errors:
        fail_reasons.append(f"{len(lint_errors)} pbc_lint error(s)")

    return {
        "wrapper": WRAPPER_NAME,
        "route": ROUTE,
        "ratified": False,
        "upstream_profile_flag": False,
        "note": (
            "Local Operator wrapper around pinned pbc-spec CLI JSON output. "
            "Choice of Route C is a compatibility route, not ratification of "
            "proposed rules or upstream enum changes."
        ),
        "pinned_commit": PINNED_COMMIT,
        "allowlisted_proposed_blocks": sorted(ALLOWLISTED_PROPOSED_BLOCKS),
        "allowlisted_local_confidence": sorted(ALLOWLISTED_LOCAL_CONFIDENCE),
        "allowlisted_local_trust": sorted(ALLOWLISTED_LOCAL_TRUST),
        "allowlisted_local_status": sorted(ALLOWLISTED_LOCAL_STATUS),
        "upstream": pin,
        "files": [str(path) for path in files],
        "results": classified,
        "errors": errors,
        "warnings": warnings,
        "allowlisted": allowlisted,
        "remaining_error_ids": remaining_error_ids,
        "allowlisted_ids": allowlisted_ids,
        "pbc_lint_errors": lint_errors,
        "pin_problems": pin_problems,
        "cli_stderr": cli_stderr,
        "fail_reasons": fail_reasons,
        "ok": not fail_reasons,
    }


def format_text(report: dict[str, Any]) -> str:
    pin = report["upstream"]
    lines = [
        "Operator PBC wrapper (Route C; local, not upstream --profile)",
        f"pinned commit: {report['pinned_commit']}",
        f"observed commit: {pin.get('commit')}",
        f"spec: {pin.get('spec_version')}  cli: {pin.get('cli_package_name')}@{pin.get('cli_package_version')}",
        f"profile flag: {pin.get('has_profile_flag')}  ratified: {report['ratified']}",
        "",
        (
            f"files: {len(report['files'])}  "
            f"errors: {len(report['errors'])}  "
            f"allowlisted: {len(report['allowlisted'])}  "
            f"warnings: {len(report['warnings'])}  "
            f"pbc_lint: {len(report['pbc_lint_errors'])}"
        ),
    ]
    if report["allowlisted"]:
        lines.append("")
        lines.append("allowlisted (kept in report; not dropped; not ratified):")
        for row in report["allowlisted"]:
            lines.append(
                f"  {row.get('checkId')} {row.get('file')}:{row.get('line')} "
                f"{row.get('message')}"
            )
    if report["errors"]:
        lines.append("")
        lines.append("remaining errors:")
        for row in report["errors"]:
            lines.append(
                f"  {row.get('checkId')} {row.get('file')}:{row.get('line')} "
                f"{row.get('message')}"
            )
    if report["pbc_lint_errors"]:
        lines.append("")
        lines.append("pbc_lint:")
        for err in report["pbc_lint_errors"]:
            lines.append(f"  {err}")
    if report["fail_reasons"]:
        lines.append("")
        lines.append("fail: " + "; ".join(report["fail_reasons"]))
    else:
        lines.append("")
        lines.append(
            "ok: remaining CLI errors none; pbc_lint clean; "
            "allowlisted findings are local dialect, not upstream types"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Local Operator PBC wrapper (Route C). Uses pinned pbc-spec CLI JSON "
            "output; does not add or claim an upstream --profile flag."
        )
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        default=[ROOT / "owners-manual" / "pbc"],
        help="PBC files or directories (default: owners-manual/pbc).",
    )
    parser.add_argument("--pbc-spec", type=Path, default=None)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help="Optional .operator dir for pbc_lint invariant 2.",
    )
    parser.add_argument(
        "--allow-unpinned",
        action="store_true",
        help="Do not fail closed on upstream commit/spec mismatch (debug only).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional JSON report path. Must not be a runtime ledger record.",
    )
    args = parser.parse_args(argv)
    pbc_spec = poe_fut014_audit.resolve_pbc_spec(args.pbc_spec)
    if pbc_spec is None or not pbc_spec.is_dir():
        print("Error: pbc-spec path not found. Set POE_FUT014_PBC_SPEC.", file=sys.stderr)
        return 2
    cli_bin = pbc_spec / "cli" / "dist" / "bin" / "pbc.js"
    if not cli_bin.is_file():
        print(f"Error: pinned pbc CLI not built at {cli_bin}", file=sys.stderr)
        return 2
    report = run_wrapper(
        list(args.paths),
        pbc_spec,
        ledger=args.ledger,
        require_pin=not args.allow_unpinned,
    )
    if args.out is not None:
        args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.format == "json":
        print(json.dumps(report, indent=2))
    else:
        print(format_text(report))
    if not report["ok"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
