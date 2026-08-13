"""Fixture repo generator for the local-lane eval ladder.

Builds a disposable directory tree per trial: a shared set of distractor
files (so L0 discovery is non-trivial, per LOCAL_LANE_CONTRACT_SPEC.md
Deliverable 3) plus the task's own files. Never run against a real repo --
every fixture lives under tempfile.gettempdir() and is owned by the caller
to clean up.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

# Shared scaffolding present in every fixture. A handful of directories deep,
# ~a dozen files, so an L0 (goal-only) prompt has real discovery work to do
# before it can even find the right file -- this is what makes L0 failure
# modes (repeated list_dir, wandering) reproducible rather than trivial.
DISTRACTOR_FILES: dict[str, str] = {
    "README.md": "# Sample project\n\nSee docs/ for more.\n",
    "docs/architecture.md": "# Architecture\n\nTBD.\n",
    "docs/CHANGELOG.md": "## v0.1.0\n\n- Initial release\n",
    "src/__init__.py": "",
    "src/utils.py": "def noop():\n    pass\n",
    "src/models.py": "class Placeholder:\n    pass\n",
    "tests/__init__.py": "",
    "tests/test_utils.py": "def test_noop():\n    assert True\n",
    "scripts/deploy.sh": "#!/bin/bash\necho deploying\n",
    "config/settings.ini": "[general]\ndebug = false\n",
    ".gitignore": "__pycache__/\n*.pyc\n",
    "LICENSE": "MIT\n",
}


def build_fixture(
    task_files: dict[str, str], *, prefix: str, remove: list[str] | None = None
) -> Path:
    """Create a disposable temp directory: distractor scaffolding plus the
    task's own files (task files win on any path collision, e.g. a task that
    wants to seed its own config/settings.ini content), minus any distractor
    paths the task explicitly removes (e.g. simulating a file that was moved
    away). Caller owns cleanup.
    """
    root = Path(tempfile.mkdtemp(prefix=f"opr-eval-{prefix}-")).resolve()
    for rel_path, spec in {**DISTRACTOR_FILES, **task_files}.items():
        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        # A task file may be a plain string, or {content: ..., mode: 0o755} when
        # it has to be executable -- a "fix the failing script" fixture cannot be
        # written any other way, since write_text always produces mode 644.
        if isinstance(spec, dict):
            target.write_text(spec["content"], encoding="utf-8")
            if "mode" in spec:
                target.chmod(spec["mode"])
        else:
            target.write_text(spec, encoding="utf-8")
    for rel_path in remove or []:
        target = root / rel_path
        if target.exists():
            target.unlink()
    return root


_IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache"}
_IGNORED_SUFFIXES = {".pyc", ".pyo"}


def hash_tree(root: Path) -> dict[str, str]:
    """Map every file under `root` to a SHA-256 of its bytes.

    Taken once before the model runs and once after, this is what makes
    LOCAL_LANE_CONTRACT R6 gradeable: the contract enumerates every file that may
    be touched, but nothing ever checked that the model obeyed. Hashing bytes
    rather than comparing mtimes means a rewrite with identical content counts as
    unchanged, which is the behaviour we want -- R6 is about the resulting tree,
    not about write syscalls.
    """
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel = path.relative_to(root)
        # Interpreter build output is not the model's doing and must never count
        # as an out-of-scope write. A postcondition that runs the fixture's test
        # battery creates __pycache__ as a side effect, which would otherwise
        # fail the scope check on every exec-graded task for every model.
        if any(part in _IGNORED_DIRS for part in rel.parts) or rel.suffix in _IGNORED_SUFFIXES:
            continue
        manifest[str(rel)] = hashlib.sha256(path.read_bytes()).hexdigest()
    return manifest


def cleanup_fixture(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)
