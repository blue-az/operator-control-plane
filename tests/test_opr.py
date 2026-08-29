"""The opr binary is a deprecation stub that points at pi."""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OPR_BIN = REPO_ROOT / "opr"


class TestOprDeprecated(unittest.TestCase):
    def test_stub_exits_nonzero_and_points_at_pi(self) -> None:
        result = subprocess.run(
            [str(OPR_BIN)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        combined = result.stdout + result.stderr
        self.assertIn("deprecated", combined.lower())
        self.assertIn("pi is the runner", combined)
        self.assertIn("fe4211b09bc164c3dc0b7b48bad929e39ab68356", combined)

    def test_module_flag_is_set(self) -> None:
        import importlib.machinery
        import importlib.util

        loader = importlib.machinery.SourceFileLoader("opr_stub", str(OPR_BIN))
        spec = importlib.util.spec_from_loader("opr_stub", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        self.assertTrue(module.OPR_DEPRECATED)
        self.assertEqual(
            module.OPR_RESTORE_COMMIT,
            "fe4211b09bc164c3dc0b7b48bad929e39ab68356",
        )


if __name__ == "__main__":
    unittest.main()
