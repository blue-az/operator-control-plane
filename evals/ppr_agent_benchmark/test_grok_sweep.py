"""Offline runner regression tests; no model calls."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_grok_sweep as sweep


class SweepTests(unittest.TestCase):
    def test_routes(self):
        with patch.object(sweep.subprocess, "run") as run:
            run.return_value = subprocess.CompletedProcess([], 0, "ok", "")
            for provider, model in [("xai", "grok-4.3"), ("ollama", "qwen3.8:27b")]:
                self.assertEqual(sweep.submit_model(provider, model, "prompt")["returncode"], 0)
                self.assertEqual(
                    run.call_args.args[0][:5], ["pi", "--provider", provider, "--model", model]
                )

    def test_timeout_and_missing_executable(self):
        for error, code in [
            (subprocess.TimeoutExpired("pi", 1), 124),
            (FileNotFoundError("pi"), 127),
        ]:
            with patch.object(sweep.subprocess, "run", side_effect=error):
                self.assertEqual(sweep.submit_model("ollama", "model", "p")["returncode"], code)

    def test_isolation_and_manifest(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(sweep, "RUNS_DIR", Path(tmp) / "runs"),
            patch.object(
                sweep,
                "submit_model",
                return_value={"returncode": 0, "stdout": "ok", "stderr": "", "elapsed_s": 0},
            ),
        ):
            for _ in range(2):
                self.assertEqual(sweep.main(["--models", "qwen38"]), 0)
            dirs = list(sweep.RUNS_DIR.iterdir())
            self.assertEqual(len(dirs), 2)
            manifest = json.loads((dirs[0] / "manifest.json").read_text())
            self.assertEqual(len(manifest["results"]), 3)
            for row in manifest["results"]:
                self.assertEqual(row["provider"], "ollama")
                self.assertEqual(row["returncode"], 0)
                self.assertTrue((dirs[0] / row["stdout_path"]).is_file())
            before = (dirs[0] / "manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):
                sweep.main(["--models", "qwen38", "--run-dir", str(dirs[0])])
            self.assertEqual((dirs[0] / "manifest.json").read_bytes(), before)

    def test_first_failure_survives_later_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            for code, expected in [(124, 124), (127, 127), (-15, 143)]:
                results = [
                    {"returncode": rc, "stdout": "", "stderr": "", "elapsed_s": 0}
                    for rc in [code, 0, 0]
                ]
                with patch.object(sweep, "submit_model", side_effect=results):
                    self.assertEqual(
                        sweep.main(["--models", "qwen38", "--run-dir", str(Path(tmp) / str(code))]),
                        expected,
                    )

    def test_invalid_selection(self):
        for args in [["--models", "unknown"], ["--models", ""], [], ["--rescore"], ["--write"]]:
            with self.assertRaises(SystemExit) as exc:
                sweep.main(args)
            self.assertEqual(exc.exception.code, 2)

    def test_process_exit_and_rescore(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pi = root / "pi"
            pi.write_text("#!/bin/sh\necho failed >&2\nexit 7\n")
            pi.chmod(0o755)
            out = root / "output"
            result = subprocess.run(
                [
                    sys.executable,
                    str(Path(sweep.__file__)),
                    "--models",
                    "qwen38",
                    "--run-dir",
                    str(out),
                ],
                env={**os.environ, "PATH": str(root) + os.pathsep + os.environ["PATH"]},
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 7, result.stderr)
            rows = json.loads((out / "manifest.json").read_text())["results"]
            self.assertEqual([r["returncode"] for r in rows], [7, 7, 7])
            result = subprocess.run(
                [sys.executable, str(Path(sweep.__file__)), "--rescore", "--run-dir", str(out)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse((out / "scores_strict.json").exists())


if __name__ == "__main__":
    unittest.main()
