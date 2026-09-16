"""Run the pi-yank core selftest (no Pi, no clipboard)."""

from __future__ import annotations

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SELFTEST = REPO_ROOT / "extensions" / "pi-yank" / "selftest.ts"


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


class PiYankSelftest(unittest.TestCase):
    def test_selftest_passes(self) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        if not _node_supports_type_stripping(node):
            self.skipTest("node is older than 22.6 (no --experimental-strip-types)")
        completed = subprocess.run(
            [node, "--experimental-strip-types", str(SELFTEST)],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            0,
            f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
        self.assertIn("passed", completed.stdout)
        self.assertNotIn("FAIL", completed.stdout)


if __name__ == "__main__":
    sys.exit(unittest.main())
