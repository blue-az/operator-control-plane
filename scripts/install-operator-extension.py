#!/usr/bin/env python3
"""Opt-in installer for the project-local Operator Pi extension.

Copies or links the extension into a consumer repository and records an
explicit ledger-path contract. It never copies runtime ledger data under
``.operator/`` and never publishes a pi package. ``core.ts`` ``findLedger``
reads this contract (``wired_into_findLedger: true``).

See ``.pi/extensions/operator/install-guide.md``.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONTRACT_SCHEMA = "operator-pi-extension-ledger-contract/v1"
INSTALLED_BY = "operator-pi-extension-install-helper"
CONTRACT_RELATIVE = Path(".pi") / "operator-ledger.json"
STARTER_RELATIVE = Path(".pi") / "operator-extension-starter.md"
EXTENSION_RELATIVE = Path(".pi") / "extensions" / "operator"
LEDGER_DIR_NAME = ".operator"
OPERATOR_BIN_NAME = "operator"

REQUIRED_RUNTIME_FILES = ("index.ts", "core.ts", "render.ts", "targets.json")
NEVER_COPY_NAMES = ("selftest.ts",)
SKIP_DIR_NAMES = {".operator", "node_modules", "__pycache__"}

DISCOVERY = {
    "pi_project_local": (
        "cwd/.pi/extensions/*.ts and cwd/.pi/extensions/*/index.ts; "
        "cwd only, after project trust; no parent walk"
    ),
    "pi_settings_extensions": (
        ".pi/settings.json or ~/.pi/agent/settings.json 'extensions' array; "
        "this helper does not write settings.json"
    ),
    "pi_packages": (
        "settings.json 'packages' (npm/git/local); this helper does not run pi install"
    ),
    "operator_findLedger": (
        "core.ts walks up from cwd collecting the first sibling .operator/ directory "
        "plus a file named operator, and the first .pi/operator-ledger.json; a valid "
        "v1 contract with an absolute ledger_root that has that pair is used; "
        "disagreeing canonical roots or a malformed contract fail closed"
    ),
}

INTEGRATION_REQUIREMENT = (
    "core.ts findLedger walks up once, collects the first sibling "
    ".operator/+operator pair and the first .pi/operator-ledger.json, fails closed "
    "if they disagree or the contract is malformed, and otherwise uses the "
    "contract's absolute ledger_root after validating the same pair there. "
    "wired_into_findLedger is true."
)


class InstallError(Exception):
    """User-facing failure; exit status 1."""


@dataclass
class ControlPlane:
    root: Path
    operator_bin: Path
    ledger_dir: Path


@dataclass
class ExtensionSource:
    root: Path
    extension_dir: Path
    files: tuple[str, ...]


@dataclass
class PlannedAction:
    kind: str
    path: str
    detail: str


@dataclass
class Plan:
    action: str
    method: str
    target: Path
    source: ExtensionSource | None
    ledger: ControlPlane | None
    dry_run: bool
    overwrite: bool
    actions: list[PlannedAction] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        ledger_root = str(self.ledger.root) if self.ledger else None
        return {
            "action": self.action,
            "method": self.method,
            "target": str(self.target),
            "ledger_root": ledger_root,
            "extension_dest": str(self.target / EXTENSION_RELATIVE),
            "contract": str(self.target / CONTRACT_RELATIVE),
            "starter": str(self.target / STARTER_RELATIVE),
            "files": list(self.source.files) if self.source else [],
            "runtime_ledger_copied": False,
            "wired_into_findLedger": True,
            "installed_by": INSTALLED_BY,
            "dry_run": self.dry_run,
            "overwrite": self.overwrite,
            "notes": list(self.notes),
            "steps": [{"kind": a.kind, "path": a.path, "detail": a.detail} for a in self.actions],
        }


def canonical(path: Path) -> Path:
    return path.expanduser().resolve()


def is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def default_source_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _path_inside(root: Path, candidate: Path) -> bool:
    try:
        root_real = root.resolve()
        cand_real = candidate.resolve()
    except OSError:
        return False
    if cand_real == root_real:
        return True
    return str(cand_real).startswith(str(root_real) + os.sep)


def list_runtime_files(extension_dir: Path) -> tuple[str, ...]:
    files: list[str] = []
    for path in sorted(extension_dir.rglob("*")):
        rel = path.relative_to(extension_dir)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        if rel.is_absolute() or ".." in rel.parts:
            raise InstallError(
                f"error: refusing to copy path that is not a relative file: {rel.as_posix()}"
            )
        if not _path_inside(extension_dir, path):
            raise InstallError(
                f"error: refusing to copy {rel.as_posix()}: resolves outside {extension_dir}"
            )
        if path.is_symlink():
            raise InstallError(
                f"error: refusing to copy symlink {rel.as_posix()} under {extension_dir} "
                "(symlink and path-traversal surprises are fail-closed)"
            )
        if not path.is_file():
            continue
        if rel.name in NEVER_COPY_NAMES:
            continue
        files.append(rel.as_posix())
    return tuple(files)


def load_extension_source(source_root: Path) -> ExtensionSource:
    root = canonical(source_root)
    extension_dir = root / EXTENSION_RELATIVE
    if not is_dir(extension_dir):
        raise InstallError(
            f"error: no extension source at {extension_dir}: expected "
            f"{EXTENSION_RELATIVE} under --source"
        )
    missing = [name for name in REQUIRED_RUNTIME_FILES if not is_file(extension_dir / name)]
    if missing:
        raise InstallError(
            f"error: extension source at {extension_dir} is missing required files: "
            + ", ".join(missing)
        )
    files = list_runtime_files(extension_dir)
    extra = [name for name in files if Path(name).name in NEVER_COPY_NAMES]
    if extra:
        raise InstallError(f"error: refusing to copy {', '.join(extra)}")
    return ExtensionSource(root=root, extension_dir=extension_dir, files=files)


def load_control_plane(ledger_root: Path, *, label: str) -> ControlPlane:
    root = canonical(ledger_root)
    if not is_dir(root):
        raise InstallError(f"error: missing ledger: {label} is not a directory: {ledger_root}")
    ledger_dir = root / LEDGER_DIR_NAME
    operator_bin = root / OPERATOR_BIN_NAME
    missing: list[str] = []
    if not is_dir(ledger_dir):
        missing.append(f"{LEDGER_DIR_NAME}/")
    if not is_file(operator_bin):
        missing.append(f"file {OPERATOR_BIN_NAME}")
    if missing:
        raise InstallError(
            "error: missing ledger at "
            f"{root}: need both a {LEDGER_DIR_NAME}/ directory and a file named "
            f"{OPERATOR_BIN_NAME} (missing: {', '.join(missing)}). "
            "findLedger will not guess an external path."
        )
    return ControlPlane(root=root, operator_bin=operator_bin, ledger_dir=ledger_dir)


def resolve_ledger(source: ExtensionSource, ledger_arg: Path | None) -> ControlPlane:
    if ledger_arg is not None:
        ledger = load_control_plane(ledger_arg, label="--ledger")
        source_has_pair = is_dir(source.root / LEDGER_DIR_NAME) and is_file(
            source.root / OPERATOR_BIN_NAME
        )
        if source_has_pair and canonical(source.root) != ledger.root:
            # Source may be the extension checkout while --ledger names the
            # intended control plane. That is the supported split. It is not
            # ambiguous unless the *target* also has a different .operator/.
            pass
        return ledger
    try:
        return load_control_plane(source.root, label="--source (used as --ledger)")
    except InstallError as err:
        raise InstallError(
            "error: missing ledger: pass --ledger to a directory holding both "
            f"{LEDGER_DIR_NAME}/ and a file named {OPERATOR_BIN_NAME}. "
            f"{err}"
        ) from err


def existing_consumer_ledger(target: Path) -> Path | None:
    candidate = target / LEDGER_DIR_NAME
    if is_dir(candidate):
        return canonical(candidate)
    return None


def refuse_ambiguous_target(target: Path, ledger: ControlPlane) -> None:
    if canonical(target) == ledger.root:
        raise InstallError(
            "error: --target is the control-plane checkout itself; the extension "
            f"is already project-local at {ledger.root / EXTENSION_RELATIVE}"
        )
    local = existing_consumer_ledger(target)
    if local is not None and local != ledger.ledger_dir:
        raise InstallError(
            "error: ambiguous ledger: "
            f"{target / LEDGER_DIR_NAME} exists and is not {ledger.ledger_dir}. "
            "findLedger would wrap the consumer's local ledger, not the recorded "
            "control plane. Remove the local .operator/ or install into a tree "
            "that has none."
        )


def read_existing_contract(target: Path) -> dict[str, Any] | None:
    path = target / CONTRACT_RELATIVE
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise InstallError(f"error: cannot read existing contract {path}: {err}") from err
    if not isinstance(data, dict):
        raise InstallError(f"error: existing contract {path} is not a JSON object")
    return data


def refuse_ambiguous_contract(target: Path, ledger: ControlPlane, *, overwrite: bool) -> None:
    existing = read_existing_contract(target)
    if existing is None:
        return
    recorded = existing.get("ledger_root")
    if not recorded:
        return
    try:
        recorded_root = canonical(Path(str(recorded)))
    except OSError:
        return
    if recorded_root != ledger.root and not overwrite:
        raise InstallError(
            "error: ambiguous ledger: existing "
            f"{target / CONTRACT_RELATIVE} records {recorded_root}, not {ledger.root}. "
            "Re-run with --yes to replace the contract after reviewing it."
        )


def dest_exists(target: Path) -> list[Path]:
    paths = [
        target / EXTENSION_RELATIVE,
        target / CONTRACT_RELATIVE,
        target / STARTER_RELATIVE,
    ]
    return [path for path in paths if path.exists() or path.is_symlink()]


def confirm(prompt: str, *, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise InstallError(
            "error: refusing to write without --yes (stdin is not a TTY). "
            "This installer is explicit opt-in."
        )
    sys.stderr.write(prompt.rstrip() + "\nType 'yes' to continue: ")
    sys.stderr.flush()
    try:
        answer = input()
    except EOFError as err:
        raise InstallError("error: no confirmation received") from err
    if answer.strip().lower() != "yes":
        raise InstallError("error: declined; nothing written")


def contract_payload(source: ExtensionSource, ledger: ControlPlane, method: str) -> dict[str, Any]:
    return {
        "schema": CONTRACT_SCHEMA,
        "installed_by": INSTALLED_BY,
        "wired_into_findLedger": True,
        "runtime_ledger_copied": False,
        "method": method,
        "ledger_root": str(ledger.root),
        "operator_bin": str(ledger.operator_bin),
        "ledger_dir": str(ledger.ledger_dir),
        "extension_source": str(source.extension_dir),
        "files": list(source.files),
        "discovery": DISCOVERY,
        "integration_requirement": INTEGRATION_REQUIREMENT,
    }


def starter_text(ledger: ControlPlane) -> str:
    return (
        "Work only inside this consumer repository. The Operator Pi extension files\n"
        "under .pi/extensions/operator are a local copy or symlink; do not edit the\n"
        "control-plane sources unless that path is your assigned ownership.\n"
        "\n"
        f"The intended Operator ledger is {ledger.root}\n"
        f"(binary {ledger.operator_bin}, records {ledger.ledger_dir}).\n"
        "That path is also recorded in .pi/operator-ledger.json.\n"
        "\n"
        "Do not copy, symlink, or initialize .operator/ in this consumer. Do not run\n"
        "git commit, push, publish, model pulls, GPU jobs, or server changes. Do not\n"
        "claim verification and do not change identity policy.\n"
        "\n"
        "Pi will load .pi/extensions/operator/index.ts only after this project is\n"
        "trusted. /op:* resolve the ledger by walking up from cwd for a sibling\n"
        ".operator/ plus a file named operator, and by reading this contract at\n"
        ".pi/operator-ledger.json. A valid v1 contract with an absolute ledger_root\n"
        "that has that pair is used. Malformed JSON, a relative path, a missing pair,\n"
        "or a sibling pair whose canonical root disagrees with the contract fail closed.\n"
        "\n"
        "Do not run pi install, do not write ~/.pi/agent/settings.json, and do not\n"
        "publish this extension.\n"
    )


def plan_install(
    *,
    target: Path,
    source_root: Path,
    ledger_root: Path | None,
    method: str,
    dry_run: bool,
    assume_yes: bool,
) -> Plan:
    if method not in {"copy", "link"}:
        raise InstallError(f"error: unknown --method {method}")
    dest_root = canonical(target)
    if not is_dir(dest_root):
        raise InstallError(f"error: --target is not an existing directory: {target}")
    source = load_extension_source(source_root)
    ledger = resolve_ledger(source, ledger_root)
    refuse_ambiguous_target(dest_root, ledger)
    existing = dest_exists(dest_root)
    overwrite = bool(existing)
    refuse_ambiguous_contract(dest_root, ledger, overwrite=overwrite and assume_yes)

    plan = Plan(
        action="install",
        method=method,
        target=dest_root,
        source=source,
        ledger=ledger,
        dry_run=dry_run,
        overwrite=overwrite,
        notes=[
            "runtime ledger data is not copied",
            "core.ts findLedger reads the contract (wired_into_findLedger is true)",
            "Pi loads cwd/.pi/extensions/operator/index.ts only after project trust",
        ],
    )
    extension_dest = dest_root / EXTENSION_RELATIVE
    if method == "copy":
        plan.actions.append(
            PlannedAction(
                "copy-dir",
                str(extension_dest),
                "copy " + ", ".join(source.files),
            )
        )
    else:
        plan.actions.append(
            PlannedAction(
                "symlink",
                str(extension_dest),
                f"symlink -> {source.extension_dir}",
            )
        )
    plan.actions.append(PlannedAction("write", str(dest_root / CONTRACT_RELATIVE), CONTRACT_SCHEMA))
    plan.actions.append(
        PlannedAction("write", str(dest_root / STARTER_RELATIVE), "constrained subagent starter")
    )
    if overwrite:
        plan.notes.append(
            "existing install at "
            + ", ".join(str(path) for path in existing)
            + ("; will replace" if assume_yes or dry_run else "; needs confirmation")
        )
    return plan


def load_ownership_record(target: Path) -> dict[str, Any]:
    """Return the helper's contract or fail closed.

    Uninstall must not delete an unrelated ``.pi/extensions/operator`` tree
    that lacks this record.
    """
    path = target / CONTRACT_RELATIVE
    if not path.exists() and not path.is_symlink():
        raise InstallError(
            f"error: refusing to uninstall: no ownership record at {path}. "
            "This helper will not delete an unrelated installation."
        )
    if is_dir(path) and not path.is_symlink():
        raise InstallError(f"error: refusing to uninstall: ownership record {path} is a directory")
    existing = read_existing_contract(target)
    if existing is None:
        raise InstallError(
            f"error: refusing to uninstall: no ownership record at {path}. "
            "This helper will not delete an unrelated installation."
        )
    if existing.get("schema") != CONTRACT_SCHEMA:
        raise InstallError(
            "error: refusing to uninstall: ownership record schema is not "
            f"{CONTRACT_SCHEMA} at {path}"
        )
    if existing.get("installed_by") != INSTALLED_BY:
        raise InstallError(
            "error: refusing to uninstall: ownership record at "
            f"{path} was not written by {INSTALLED_BY}"
        )
    files = existing.get("files")
    if not isinstance(files, list) or not all(isinstance(name, str) and name for name in files):
        raise InstallError(
            f"error: refusing to uninstall: ownership record at {path} is missing a files list"
        )
    for name in files:
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            raise InstallError(
                f"error: refusing to uninstall: ownership file path is not a relative file: {name}"
            )
    return existing


def plan_uninstall(*, target: Path, dry_run: bool) -> Plan:
    dest_root = canonical(target)
    if not is_dir(dest_root):
        raise InstallError(f"error: --target is not an existing directory: {target}")
    ownership = load_ownership_record(dest_root)
    plan = Plan(
        action="uninstall",
        method="remove",
        target=dest_root,
        source=None,
        ledger=None,
        dry_run=dry_run,
        overwrite=False,
        notes=[
            "will not touch .operator/ or other .pi contents",
            "will not recursively delete unrelated user files",
            f"ownership record matched ({INSTALLED_BY})",
        ],
    )
    extension_dest = dest_root / EXTENSION_RELATIVE
    if extension_dest.exists() or extension_dest.is_symlink():
        kind = "unlink" if extension_dest.is_symlink() else "remove-owned-files"
        plan.actions.append(
            PlannedAction(kind, str(extension_dest), "owned extension files from the contract")
        )
    plan.actions.append(
        PlannedAction("unlink", str(dest_root / CONTRACT_RELATIVE), "ownership record")
    )
    starter = dest_root / STARTER_RELATIVE
    if starter.exists() or starter.is_symlink():
        plan.actions.append(PlannedAction("unlink", str(starter), "starter written by this helper"))
    files = ownership.get("files")
    if isinstance(files, list):
        plan.notes.append("owned files: " + ", ".join(str(name) for name in files))
    extensions_dir = dest_root / ".pi" / "extensions"
    plan.notes.append(
        f"remove {extensions_dir} only if it is empty after owned extension files are gone"
    )
    return plan


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _copy_runtime(source: ExtensionSource, dest: Path) -> None:
    """Overlay owned runtime files. Never rmtree the dest tree.

    Replacing a previous *link* install unlinks the dest symlink without
    following it. Extra user files under a previous copy are left in place.
    """
    if dest.is_symlink() or is_file(dest):
        dest.unlink()
    dest.mkdir(parents=True, exist_ok=True)
    if not _path_inside(dest, dest):
        raise InstallError(f"error: refusing to copy into {dest}: cannot resolve dest")
    for name in source.files:
        rel = Path(name)
        if rel.is_absolute() or ".." in rel.parts:
            raise InstallError(f"error: refusing to copy path that is not a relative file: {name}")
        src = source.extension_dir / rel
        out = dest / rel
        if not _path_inside(source.extension_dir, src):
            raise InstallError(
                f"error: refusing to copy {name}: source resolves outside the extension"
            )
        out.parent.mkdir(parents=True, exist_ok=True)
        if not _path_inside(dest, out.parent):
            raise InstallError(f"error: refusing to copy {name}: destination escapes {dest}")
        if out.is_symlink() or is_file(out):
            out.unlink()
        elif is_dir(out):
            raise InstallError(
                f"error: refusing to overwrite directory {out} with a file; "
                "uninstall extra paths by hand"
            )
        shutil.copy2(src, out)
        if not _path_inside(dest, out):
            raise InstallError(f"error: refusing to copy {name}: destination escaped {dest}")
    for name in NEVER_COPY_NAMES:
        leftover = dest / name
        if leftover.is_symlink() or is_file(leftover):
            leftover.unlink()
    forbidden = dest / LEDGER_DIR_NAME
    if forbidden.exists() or forbidden.is_symlink():
        raise InstallError(f"error: refused to leave {forbidden} in the consumer copy")


def _link_runtime(source: ExtensionSource, dest: Path) -> None:
    if dest.is_symlink() or is_file(dest):
        dest.unlink()
    elif is_dir(dest):
        raise InstallError(
            f"error: refusing to replace directory {dest} with a symlink "
            "(that would delete unrelated files). Uninstall first."
        )
    _ensure_parent(dest)
    os.symlink(source.extension_dir, dest, target_is_directory=True)


def apply_install(plan: Plan) -> None:
    assert plan.source is not None
    assert plan.ledger is not None
    dest = plan.target / EXTENSION_RELATIVE
    if plan.method == "copy":
        _copy_runtime(plan.source, dest)
    else:
        _link_runtime(plan.source, dest)
    contract_path = plan.target / CONTRACT_RELATIVE
    starter_path = plan.target / STARTER_RELATIVE
    _ensure_parent(contract_path)
    contract_path.write_text(
        json.dumps(
            contract_payload(plan.source, plan.ledger, plan.method), indent=2, sort_keys=True
        )
        + "\n",
        encoding="utf-8",
    )
    starter_path.write_text(starter_text(plan.ledger), encoding="utf-8")
    # Fail closed if a ledger tree appeared as a side effect of the copy.
    leaked = plan.target / LEDGER_DIR_NAME
    if leaked.exists() or leaked.is_symlink():
        raise InstallError(
            f"error: install produced {leaked}; runtime ledger copy is forbidden. "
            "Remove it by hand; this helper will not delete a ledger it did not create."
        )


def _owned_file(ext_root: Path, name: str) -> Path:
    rel = Path(name)
    if rel.is_absolute() or ".." in rel.parts:
        raise InstallError(
            f"error: refusing to uninstall: ownership file path is not a relative file: {name}"
        )
    path = ext_root / rel
    try:
        ext_real = ext_root.resolve()
        path_real = path.resolve()
    except OSError as err:
        raise InstallError(f"error: refusing to uninstall: cannot resolve {path}: {err}") from err
    if path_real != ext_real and not str(path_real).startswith(str(ext_real) + os.sep):
        raise InstallError(f"error: refusing to uninstall: owned path {path} escapes {ext_root}")
    return path


def _remove_owned_extension(dest: Path, files: list[str]) -> None:
    """Remove only files this helper installed. Never rmtree user trees."""
    if dest.is_symlink() or is_file(dest):
        dest.unlink()
        return
    if not is_dir(dest):
        return
    for name in files:
        path = _owned_file(dest, name)
        if path.is_symlink() or is_file(path):
            path.unlink()
        elif is_dir(path):
            raise InstallError(
                f"error: refusing to delete directory {path}; owned paths must be files"
            )
    dirs = sorted(
        (p for p in dest.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True
    )
    for directory in dirs:
        try:
            next(directory.iterdir())
        except StopIteration:
            directory.rmdir()
    if is_dir(dest):
        try:
            next(dest.iterdir())
        except StopIteration:
            dest.rmdir()


def apply_uninstall(plan: Plan) -> None:
    ownership = load_ownership_record(plan.target)
    files_raw = ownership.get("files")
    files = [str(name) for name in files_raw] if isinstance(files_raw, list) else []
    extension_dest = plan.target / EXTENSION_RELATIVE
    if extension_dest.exists() or extension_dest.is_symlink():
        _remove_owned_extension(extension_dest, files)
    for rel in (CONTRACT_RELATIVE, STARTER_RELATIVE):
        path = plan.target / rel
        if path.is_symlink() or is_file(path):
            path.unlink()
        elif is_dir(path):
            raise InstallError(
                f"error: refusing to delete directory {path}; expected a file written by this helper"
            )
    extensions_dir = plan.target / ".pi" / "extensions"
    if is_dir(extensions_dir) and not any(extensions_dir.iterdir()):
        extensions_dir.rmdir()


def emit_plan(plan: Plan) -> None:
    header = "DRY-RUN" if plan.dry_run else plan.action.upper()
    print(f"{header}: {plan.action} ({plan.method}) -> {plan.target}")
    if plan.ledger is not None:
        print(f"ledger_root: {plan.ledger.root}")
        print(f"operator_bin: {plan.ledger.operator_bin}")
        print(f"ledger_dir: {plan.ledger.ledger_dir}")
    for action in plan.actions:
        print(f"  {action.kind}: {action.path} ({action.detail})")
    for note in plan.notes:
        print(f"note: {note}")
    print("---")
    print(json.dumps(plan.summary(), indent=2, sort_keys=True))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Opt-in copy or link of the Operator Pi extension into a consumer repo. "
            "Records a ledger-path contract. Does not copy .operator/ runtime data "
            "and does not publish a pi package."
        )
    )
    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help="existing consumer repository root",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=None,
        help="checkout holding .pi/extensions/operator (default: this repository)",
    )
    parser.add_argument(
        "--ledger",
        type=Path,
        default=None,
        help=(
            "control-plane root to record (must contain .operator/ and operator). "
            "Defaults to --source when that pair exists; never inferred from --target"
        ),
    )
    parser.add_argument(
        "--method",
        choices=("copy", "link"),
        default="copy",
        help="copy runtime files (default) or symlink the extension directory",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the plan and write nothing",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="confirm the write without a prompt (required when stdin is not a TTY)",
    )
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help=(
            "remove owned extension files, contract, and starter; refuses without a "
            "matching ownership record and does not rmtree unrelated user files"
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    source_root = args.source if args.source is not None else default_source_root()
    try:
        if args.uninstall:
            plan = plan_uninstall(target=args.target, dry_run=args.dry_run)
            emit_plan(plan)
            if plan.dry_run:
                return 0
            confirm(
                f"Uninstall the Operator Pi extension files from {plan.target}?\n"
                "This does not touch .operator/ or unrelated user files.",
                assume_yes=args.yes,
            )
            apply_uninstall(plan)
            print("uninstalled")
            return 0
        plan = plan_install(
            target=args.target,
            source_root=source_root,
            ledger_root=args.ledger,
            method=args.method,
            dry_run=args.dry_run,
            assume_yes=args.yes,
        )
        emit_plan(plan)
        if plan.dry_run:
            return 0
        prompt = (
            f"Install the Operator Pi extension into {plan.target}?\n"
            f"Record ledger {plan.ledger.root if plan.ledger else '(none)'} in "
            f"{plan.target / CONTRACT_RELATIVE}.\n"
            "No .operator/ runtime data will be copied."
        )
        if plan.overwrite:
            prompt = "Overwrite the existing install.\n" + prompt
        confirm(prompt, assume_yes=args.yes)
        apply_install(plan)
        print("installed")
        return 0
    except InstallError as err:
        print(str(err), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
