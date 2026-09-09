"""Temp-directory tests for the Operator Pi extension install helper.

Uses throwaway consumer repos and a throwaway control-plane ledger created
with the real ``./operator init``. Never writes the workspace runtime ledger
and never runs stored verification commands.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "install-operator-extension.py"
OPERATOR_BIN = REPO_ROOT / "operator"
EXTENSION_DIR = REPO_ROOT / ".pi" / "extensions" / "operator"
RUNTIME_FILES = ("index.ts", "core.ts", "render.ts", "targets.json", "client.ts")


def run_install(args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        input=stdin,
        timeout=60,
        check=False,
    )


def parse_summary(stdout: str) -> dict:
    marker = "\n---\n"
    if marker not in stdout:
        raise AssertionError(f"installer stdout had no JSON summary:\n{stdout}")
    payload = stdout.split(marker, 1)[1].lstrip()
    data, _end = json.JSONDecoder().raw_decode(payload)
    return data


def _node_supports_type_stripping(node: str) -> bool:
    try:
        raw = subprocess.run(
            [node, "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    if not raw.startswith("v"):
        return False
    try:
        major, minor = (int(part) for part in raw[1:].split(".")[:2])
    except ValueError:
        return False
    return (major, minor) >= (22, 6)


def resolve_find_ledger(start: Path, core_ts: Path) -> dict:
    """Run the consumer's copied core.ts findLedger against start."""
    node = shutil.which("node")
    if not node:
        raise unittest.SkipTest("node is not installed")
    if not _node_supports_type_stripping(node):
        raise unittest.SkipTest("node is older than 22.6 (no --experimental-strip-types)")
    resolver = core_ts.parent / ".resolve-findledger.ts"
    resolver.write_text(
        'import { findLedger } from "./core.ts";\n'
        "const dir = process.argv[2];\n"
        "try {\n"
        "  const ledger = findLedger(dir);\n"
        "  console.log(JSON.stringify({ ok: true, ledger }));\n"
        "} catch (err) {\n"
        "  const kind = err && typeof err === 'object' && 'kind' in err ? err.kind : null;\n"
        "  const message = err instanceof Error ? err.message : String(err);\n"
        "  console.log(JSON.stringify({ ok: false, kind, message }));\n"
        "}\n",
        encoding="utf-8",
    )
    try:
        completed = subprocess.run(
            [node, "--experimental-strip-types", str(resolver), str(start)],
            cwd=str(core_ts.parent),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        resolver.unlink(missing_ok=True)
    if not completed.stdout.strip():
        raise AssertionError(
            f"findLedger resolver produced no stdout\n"
            f"code={completed.returncode}\nstderr={completed.stderr}\nstdout={completed.stdout}"
        )
    try:
        return json.loads(completed.stdout.splitlines()[-1])
    except json.JSONDecodeError as err:
        raise AssertionError(
            f"findLedger resolver stdout was not JSON: {completed.stdout!r}\nstderr={completed.stderr}"
        ) from err


def make_control_plane(parent: Path) -> Path:
    root = parent / "control-plane"
    root.mkdir(parents=True)
    # Keep the real CLI for imports; findLedger only needs a sibling file named
    # operator next to .operator/, which a symlink satisfies.
    os.symlink(OPERATOR_BIN, root / "operator")
    completed = subprocess.run(
        [str(OPERATOR_BIN), "init"],
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(
            f"operator init failed in {root}: {completed.stderr or completed.stdout}"
        )
    if not (root / ".operator").is_dir():
        raise AssertionError(f"operator init did not create {root / '.operator'}")
    return root


def make_consumer(parent: Path, name: str) -> Path:
    path = parent / name
    path.mkdir()
    (path / "README.md").write_text(f"{name}\n", encoding="utf-8")
    return path


def ledger_files_under(path: Path) -> list[str]:
    found: list[str] = []
    operator_dir = path / ".operator"
    if operator_dir.exists() or operator_dir.is_symlink():
        found.append(".operator")
    for current in path.rglob("*"):
        if ".operator" in current.parts:
            found.append(str(current.relative_to(path)))
    return found


class InstallOperatorExtensionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = Path(tempfile.mkdtemp(prefix="op-ext-install-")).resolve()
        self.addCleanup(shutil.rmtree, self.temp, True)
        self.ledger = make_control_plane(self.temp)
        self.consumer_a = make_consumer(self.temp, "consumer-a")
        self.consumer_b = make_consumer(self.temp, "consumer-b")

    def install(
        self, target: Path, extra: list[str] | None = None
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "--target",
            str(target),
            "--source",
            str(REPO_ROOT),
            "--ledger",
            str(self.ledger),
            "--yes",
        ]
        if extra:
            args.extend(extra)
        return run_install(args)

    def test_two_consumers_share_control_plane_without_copying_runtime_ledger(self) -> None:
        first = self.install(self.consumer_a)
        second = self.install(self.consumer_b)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(second.returncode, 0, second.stderr)

        summary_a = parse_summary(first.stdout)
        summary_b = parse_summary(second.stdout)
        self.assertEqual(summary_a["ledger_root"], str(self.ledger))
        self.assertEqual(summary_b["ledger_root"], str(self.ledger))
        self.assertEqual(summary_a["ledger_root"], summary_b["ledger_root"])
        self.assertFalse(summary_a["runtime_ledger_copied"])
        self.assertFalse(summary_b["runtime_ledger_copied"])
        self.assertTrue(summary_a["wired_into_findLedger"])
        self.assertTrue(summary_b["wired_into_findLedger"])

        for consumer in (self.consumer_a, self.consumer_b):
            dest = consumer / ".pi" / "extensions" / "operator"
            for name in RUNTIME_FILES:
                self.assertTrue((dest / name).is_file(), f"{consumer} missing {name}")
            self.assertFalse((dest / "selftest.ts").exists())
            orientation = EXTENSION_DIR / "orientation" / "actions.ts"
            if orientation.is_file():
                self.assertTrue(
                    (dest / "orientation" / "actions.ts").is_file(),
                    f"{consumer} missing orientation/actions.ts imported by index.ts",
                )
            self.assertEqual(ledger_files_under(consumer), [])
            contract = json.loads(
                (consumer / ".pi" / "operator-ledger.json").read_text(encoding="utf-8")
            )
            self.assertEqual(contract["schema"], "operator-pi-extension-ledger-contract/v1")
            self.assertEqual(contract["ledger_root"], str(self.ledger))
            self.assertEqual(contract["ledger_dir"], str(self.ledger / ".operator"))
            self.assertEqual(contract["operator_bin"], str(self.ledger / "operator"))
            self.assertFalse(contract["runtime_ledger_copied"])
            self.assertTrue(contract["wired_into_findLedger"])
            self.assertEqual(contract["installed_by"], "operator-pi-extension-install-helper")
            self.assertIsInstance(contract["files"], list)
            self.assertIn("core.ts", contract["files"])
            starter = (consumer / ".pi" / "operator-extension-starter.md").read_text(
                encoding="utf-8"
            )
            self.assertIn(str(self.ledger), starter)
            self.assertIn("Do not copy, symlink, or initialize .operator/", starter)

        self.assertTrue((self.ledger / ".operator").is_dir())
        self.assertNotEqual(self.consumer_a, self.consumer_b)

        resolved_a = resolve_find_ledger(
            self.consumer_a, self.consumer_a / ".pi" / "extensions" / "operator" / "core.ts"
        )
        resolved_b = resolve_find_ledger(
            self.consumer_b, self.consumer_b / ".pi" / "extensions" / "operator" / "core.ts"
        )
        self.assertTrue(resolved_a.get("ok"), resolved_a)
        self.assertTrue(resolved_b.get("ok"), resolved_b)
        self.assertEqual(resolved_a["ledger"]["root"], str(self.ledger))
        self.assertEqual(resolved_b["ledger"]["root"], str(self.ledger))
        self.assertEqual(resolved_a["ledger"]["root"], resolved_b["ledger"]["root"])
        self.assertEqual(resolved_a["ledger"]["ledgerDir"], str(self.ledger / ".operator"))
        nested = self.consumer_a / "src" / "nested"
        nested.mkdir(parents=True)
        resolved_nested = resolve_find_ledger(
            nested, self.consumer_a / ".pi" / "extensions" / "operator" / "core.ts"
        )
        self.assertTrue(resolved_nested.get("ok"), resolved_nested)
        self.assertEqual(resolved_nested["ledger"]["root"], str(self.ledger))

    def test_dry_run_writes_nothing(self) -> None:
        before = list(self.consumer_a.rglob("*"))
        completed = self.install(self.consumer_a, extra=["--dry-run"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("DRY-RUN", completed.stdout)
        self.assertFalse((self.consumer_a / ".pi").exists())
        self.assertEqual(list(self.consumer_a.rglob("*")), before)
        summary = parse_summary(completed.stdout)
        self.assertTrue(summary["dry_run"])
        self.assertFalse(summary["runtime_ledger_copied"])

    def test_missing_ledger_fails_clearly_and_writes_nothing(self) -> None:
        missing = self.temp / "no-such-ledger"
        completed = run_install(
            [
                "--target",
                str(self.consumer_a),
                "--source",
                str(REPO_ROOT),
                "--ledger",
                str(missing),
                "--yes",
            ]
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("error: missing ledger", completed.stderr)
        self.assertFalse((self.consumer_a / ".pi").exists())

        empty = self.temp / "empty-ledger"
        empty.mkdir()
        completed = run_install(
            [
                "--target",
                str(self.consumer_a),
                "--source",
                str(REPO_ROOT),
                "--ledger",
                str(empty),
                "--yes",
            ]
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("error: missing ledger", completed.stderr)
        self.assertIn(".operator/", completed.stderr)
        self.assertFalse((self.consumer_a / ".pi").exists())

        no_bin = self.temp / "ledger-without-bin"
        no_bin.mkdir()
        (no_bin / ".operator").mkdir()
        completed = run_install(
            [
                "--target",
                str(self.consumer_a),
                "--source",
                str(REPO_ROOT),
                "--ledger",
                str(no_bin),
                "--yes",
            ]
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("error: missing ledger", completed.stderr)
        self.assertIn("operator", completed.stderr)
        self.assertFalse((self.consumer_a / ".pi").exists())

    def test_ambiguous_local_ledger_fails_clearly(self) -> None:
        foreign = make_control_plane(self.temp / "foreign")
        # Give the consumer its own .operator so findLedger would not see --ledger.
        shutil.copytree(foreign / ".operator", self.consumer_a / ".operator")
        completed = self.install(self.consumer_a)
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertIn("error: ambiguous ledger", completed.stderr)
        dest = self.consumer_a / ".pi" / "extensions" / "operator"
        self.assertFalse(dest.exists())
        self.assertFalse((self.consumer_a / ".pi" / "operator-ledger.json").exists())

    def test_overwrite_without_yes_is_refused(self) -> None:
        first = self.install(self.consumer_a)
        self.assertEqual(first.returncode, 0, first.stderr)
        stamp = self.consumer_a / ".pi" / "extensions" / "operator" / "index.ts"
        original = stamp.read_bytes()
        completed = run_install(
            [
                "--target",
                str(self.consumer_a),
                "--source",
                str(REPO_ROOT),
                "--ledger",
                str(self.ledger),
            ]
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("refusing to write without --yes", completed.stderr)
        self.assertEqual(stamp.read_bytes(), original)

    def test_link_method_and_uninstall(self) -> None:
        completed = self.install(self.consumer_a, extra=["--method", "link"])
        self.assertEqual(completed.returncode, 0, completed.stderr)
        dest = self.consumer_a / ".pi" / "extensions" / "operator"
        self.assertTrue(dest.is_symlink())
        self.assertEqual(dest.resolve(), EXTENSION_DIR.resolve())
        self.assertEqual(ledger_files_under(self.consumer_a), [])

        dry = run_install(["--target", str(self.consumer_a), "--uninstall", "--dry-run"])
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertTrue(dest.exists())

        removed = run_install(["--target", str(self.consumer_a), "--uninstall", "--yes"])
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertFalse(dest.exists())
        self.assertFalse((self.consumer_a / ".pi" / "operator-ledger.json").exists())
        self.assertFalse((self.consumer_a / ".pi" / "operator-extension-starter.md").exists())
        self.assertFalse((self.consumer_a / ".pi" / "extensions").exists())
        self.assertEqual(ledger_files_under(self.consumer_a), [])

    def test_omitted_ledger_from_extension_only_source_fails(self) -> None:
        source = self.temp / "extension-only-source"
        extension = source / ".pi" / "extensions" / "operator"
        extension.mkdir(parents=True)
        for name in RUNTIME_FILES:
            shutil.copy2(EXTENSION_DIR / name, extension / name)
        completed = run_install(
            ["--target", str(self.consumer_a), "--source", str(source), "--yes"]
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("error: missing ledger", completed.stderr)
        self.assertFalse((self.consumer_a / ".pi").exists())

    def test_refuses_install_into_control_plane_checkout(self) -> None:
        completed = run_install(
            [
                "--target",
                str(self.ledger),
                "--source",
                str(REPO_ROOT),
                "--ledger",
                str(self.ledger),
                "--yes",
            ]
        )
        self.assertEqual(completed.returncode, 1)
        self.assertIn("control-plane checkout", completed.stderr)

    def test_guide_and_script_document_findLedger_wiring(self) -> None:
        guide = (EXTENSION_DIR / "install-guide.md").read_text(encoding="utf-8")
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("wired_into_findLedger", guide)
        self.assertIn("findLedger", guide)
        self.assertIn("project trust", guide.lower())
        self.assertIn("wired_into_findLedger is true", script)
        self.assertNotIn("does not read this contract", script)
        self.assertNotIn("pi install npm:", script)
        self.assertIn("operator-pi-extension-ledger-contract/v1", guide)
        self.assertIn("ownership record", guide.lower())

    def test_uninstall_refuses_unrelated_extension_without_ownership(self) -> None:
        dest = self.consumer_a / ".pi" / "extensions" / "operator"
        dest.mkdir(parents=True)
        stamp = dest / "index.ts"
        stamp.write_text("not-ours\n", encoding="utf-8")
        notes = self.consumer_a / ".pi" / "user-notes.md"
        notes.write_text("keep me\n", encoding="utf-8")
        completed = run_install(["--target", str(self.consumer_a), "--uninstall", "--yes"])
        self.assertEqual(completed.returncode, 1)
        self.assertIn("refusing to uninstall", completed.stderr)
        self.assertIn("no ownership record", completed.stderr)
        self.assertTrue(stamp.is_file())
        self.assertEqual(stamp.read_text(encoding="utf-8"), "not-ours\n")
        self.assertTrue(notes.is_file())
        self.assertEqual(ledger_files_under(self.consumer_a), [])

    def test_uninstall_leaves_extra_user_files_and_other_dot_pi_contents(self) -> None:
        first = self.install(self.consumer_a)
        self.assertEqual(first.returncode, 0, first.stderr)
        extra = self.consumer_a / ".pi" / "extensions" / "operator" / "user-extra.txt"
        extra.write_text("do not delete me\n", encoding="utf-8")
        other = self.consumer_a / ".pi" / "user-notes.md"
        other.write_text("also keep\n", encoding="utf-8")
        sibling_ext = self.consumer_a / ".pi" / "extensions" / "other-ext"
        sibling_ext.mkdir()
        (sibling_ext / "index.ts").write_text("other\n", encoding="utf-8")
        removed = run_install(["--target", str(self.consumer_a), "--uninstall", "--yes"])
        self.assertEqual(removed.returncode, 0, removed.stderr)
        self.assertTrue(extra.is_file(), "uninstall must not rmtree extra user files")
        self.assertTrue(other.is_file())
        self.assertTrue((sibling_ext / "index.ts").is_file())
        self.assertFalse((self.consumer_a / ".pi" / "operator-ledger.json").exists())
        self.assertFalse((self.consumer_a / ".pi" / "operator-extension-starter.md").exists())
        self.assertFalse((self.consumer_a / ".pi" / "extensions" / "operator" / "core.ts").exists())
        self.assertEqual(ledger_files_under(self.consumer_a), [])

    def test_malformed_and_ambiguous_contracts_fail_closed_from_consumer(self) -> None:
        first = self.install(self.consumer_a)
        self.assertEqual(first.returncode, 0, first.stderr)
        core_ts = self.consumer_a / ".pi" / "extensions" / "operator" / "core.ts"
        contract = self.consumer_a / ".pi" / "operator-ledger.json"
        original = contract.read_text(encoding="utf-8")

        contract.write_text("{not json", encoding="utf-8")
        malformed = resolve_find_ledger(self.consumer_a, core_ts)
        self.assertFalse(malformed.get("ok"))
        self.assertEqual(malformed.get("kind"), "malformed")

        payload = json.loads(original)
        payload["ledger_root"] = "relative/path"
        contract.write_text(json.dumps(payload), encoding="utf-8")
        relative = resolve_find_ledger(self.consumer_a, core_ts)
        self.assertFalse(relative.get("ok"))
        self.assertEqual(relative.get("kind"), "malformed")

        payload = json.loads(original)
        payload["ledger_root"] = str(Path(self.ledger) / ".." / "nope")
        contract.write_text(json.dumps(payload), encoding="utf-8")
        traversal = resolve_find_ledger(self.consumer_a, core_ts)
        self.assertFalse(traversal.get("ok"))
        self.assertEqual(traversal.get("kind"), "malformed")

        payload = json.loads(original)
        empty = self.temp / "empty-root"
        empty.mkdir()
        payload["ledger_root"] = str(empty)
        contract.write_text(json.dumps(payload), encoding="utf-8")
        missing = resolve_find_ledger(self.consumer_a, core_ts)
        self.assertFalse(missing.get("ok"))
        self.assertEqual(missing.get("kind"), "missing-pair")

        contract.write_text(original, encoding="utf-8")
        shutil.copytree(self.ledger / ".operator", self.consumer_a / ".operator")
        os.symlink(OPERATOR_BIN, self.consumer_a / "operator")
        ambiguous = resolve_find_ledger(self.consumer_a, core_ts)
        self.assertFalse(ambiguous.get("ok"), ambiguous)
        self.assertEqual(ambiguous.get("kind"), "ambiguous")

    def test_overwrite_copy_leaves_extra_user_files(self) -> None:
        first = self.install(self.consumer_a)
        self.assertEqual(first.returncode, 0, first.stderr)
        extra = self.consumer_a / ".pi" / "extensions" / "operator" / "user-extra.txt"
        extra.write_text("keep extra\n", encoding="utf-8")
        notes = self.consumer_a / ".pi" / "user-notes.md"
        notes.write_text("also keep\n", encoding="utf-8")
        second = self.install(self.consumer_a)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertTrue(extra.is_file(), "copy overwrite must not rmtree extra user files")
        self.assertEqual(extra.read_text(encoding="utf-8"), "keep extra\n")
        self.assertTrue(notes.is_file())
        self.assertTrue((self.consumer_a / ".pi" / "extensions" / "operator" / "core.ts").is_file())
        self.assertEqual(ledger_files_under(self.consumer_a), [])

    def test_refuses_source_symlink_escape(self) -> None:
        source = self.temp / "symlink-source"
        extension = source / ".pi" / "extensions" / "operator"
        extension.mkdir(parents=True)
        for name in RUNTIME_FILES:
            shutil.copy2(EXTENSION_DIR / name, extension / name)
        outside = self.temp / "outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        os.symlink(outside, extension / "escaped.txt")
        completed = run_install(
            [
                "--target",
                str(self.consumer_a),
                "--source",
                str(source),
                "--ledger",
                str(self.ledger),
                "--yes",
            ]
        )
        self.assertEqual(completed.returncode, 1, completed.stdout)
        self.assertTrue(
            "refusing to copy symlink" in completed.stderr
            or "resolves outside" in completed.stderr,
            completed.stderr,
        )
        self.assertFalse((self.consumer_a / ".pi" / "extensions" / "operator").exists())
        self.assertEqual(ledger_files_under(self.consumer_a), [])

    def test_link_overwrite_refuses_existing_directory(self) -> None:
        first = self.install(self.consumer_a)
        self.assertEqual(first.returncode, 0, first.stderr)
        extra = self.consumer_a / ".pi" / "extensions" / "operator" / "user-extra.txt"
        extra.write_text("do not rmtree\n", encoding="utf-8")
        linked = self.install(self.consumer_a, extra=["--method", "link"])
        self.assertEqual(linked.returncode, 1, linked.stdout)
        self.assertIn("refusing to replace directory", linked.stderr)
        self.assertTrue(extra.is_file())
        self.assertFalse((self.consumer_a / ".pi" / "extensions" / "operator").is_symlink())
        self.assertEqual(ledger_files_under(self.consumer_a), [])


if __name__ == "__main__":
    unittest.main()
