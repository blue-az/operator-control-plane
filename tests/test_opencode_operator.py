"""Run the source-only OpenCode adapter tests without launching OpenCode or a model."""

from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


class OpenCodeOperatorTest(unittest.TestCase):
    def test_core_adapter(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node 22.6+ is required for TypeScript stripping")
        version = subprocess.run(
            [node, "--version"], capture_output=True, text=True, timeout=15, check=True
        ).stdout.strip()
        parts = tuple(int(part) for part in version.lstrip("v").split(".")[:2])
        if parts < (22, 6):
            self.skipTest("Node 22.6+ is required for TypeScript stripping")
        result = subprocess.run(
            [
                node,
                "--experimental-strip-types",
                "--test",
                str(ROOT / "tests" / "opencode_operator.test.ts"),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=90,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("# fail 0", result.stdout)
