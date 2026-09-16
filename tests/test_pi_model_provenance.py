"""Live Pi identity capture (GitHub #16). No ledger writes except one attach smoke."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))
import pi_model_provenance  # noqa: E402

OPERATOR_BIN = REPO_ROOT / "operator"
CRYSTAL = REPO_ROOT / "tests" / "fixtures" / "crystals" / "valid-session.md"


class CaptureLivePiIdentityTest(unittest.TestCase):
    def test_missing_env_is_unknown_not_inferred(self) -> None:
        ident = pi_model_provenance.capture_live_pi_identity(
            environ={},
            now=datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(ident["harness"], "pi")
        self.assertEqual(ident["harness_version"], "unknown")
        self.assertEqual(ident["observed"]["provider"], "unknown")
        self.assertEqual(ident["observed"]["model"], "unknown")
        self.assertEqual(ident["observed"]["session_id"], "unknown")
        self.assertEqual(ident["captured_at"], "2026-09-16T12:00:00Z")
        self.assertNotIn("claimed", ident)
        self.assertNotIn("mismatch", ident)

    def test_observed_from_allowlisted_env_only(self) -> None:
        ident = pi_model_provenance.capture_live_pi_identity(
            environ={
                "PI_PROVIDER": "openai-codex",
                "PI_MODEL": "gpt-5.6-luna",
                "PI_SESSION_ID": "01a05bf2-a906-7c10-b8e0-00624af580c8",
                "PI_CODING_AGENT_VERSION": "0.85.1",
                "OPENAI_API_KEY": "sk-not-for-artifacts",
                "HOME": "/home/blueaz",
            }
        )
        self.assertEqual(ident["observed"]["provider"], "openai-codex")
        self.assertEqual(ident["observed"]["model"], "gpt-5.6-luna")
        self.assertEqual(ident["harness_version"], "0.85.1")
        blob = repr(ident)
        self.assertNotIn("sk-not-for-artifacts", blob)
        self.assertNotIn("/home/blueaz", blob)
        self.assertFalse(pi_model_provenance.contains_secret_material(ident))

    def test_mismatch_records_claimed_and_observed(self) -> None:
        ident = pi_model_provenance.capture_live_pi_identity(
            claimed_provider="xai",
            claimed_model="grok-4.6",
            environ={"PI_PROVIDER": "openai-codex", "PI_MODEL": "gpt-5.6-luna"},
        )
        self.assertEqual(ident["claimed"]["provider"], "xai")
        self.assertEqual(ident["claimed"]["model"], "grok-4.6")
        self.assertEqual(ident["observed"]["provider"], "openai-codex")
        fields = {row["field"] for row in ident["mismatch"]}
        self.assertEqual(fields, {"provider", "model"})
        warning = pi_model_provenance.format_mismatch_warning(ident)
        self.assertIsNotNone(warning)
        self.assertIn("claimed 'xai'", warning)
        self.assertIn("observed 'openai-codex'", warning)

    def test_claimed_without_live_env_is_not_a_mismatch(self) -> None:
        ident = pi_model_provenance.capture_live_pi_identity(
            claimed_provider="xai",
            environ={},
        )
        self.assertEqual(ident["observed"]["provider"], "unknown")
        self.assertNotIn("mismatch", ident)
        self.assertIsNone(pi_model_provenance.format_mismatch_warning(ident))

    def test_secret_values_are_redacted(self) -> None:
        ident = pi_model_provenance.capture_live_pi_identity(
            claimed_model="sk-abcdefghijklmnopqrstuvwxyz",
            environ={"PI_PROVIDER": "gho_abcdefghijklmnopqrstuvwxyz0123456789"},
        )
        self.assertEqual(ident["observed"]["provider"], "redacted")
        self.assertEqual(ident["claimed"]["model"], "redacted")
        self.assertFalse(pi_model_provenance.contains_secret_material(ident))
        self.assertNotIn("gho_", repr(ident))
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", repr(ident))


class CrystalAttachProvenanceSmoke(unittest.TestCase):
    def test_attach_records_observed_identity_without_secrets(self) -> None:
        if not CRYSTAL.is_file():
            self.skipTest(f"missing fixture {CRYSTAL}")
        temp = Path(tempfile.mkdtemp(prefix="op-prov-")).resolve()
        self.addCleanup(shutil.rmtree, temp, True)
        env = os.environ.copy()
        env.update(
            {
                "PI_PROVIDER": "openai-codex",
                "PI_MODEL": "gpt-5.6-luna",
                "PI_SESSION_ID": "sess-smoke",
                "PI_CODING_AGENT_VERSION": "0.85.1",
                "OPENAI_API_KEY": "sk-should-never-land",
            }
        )
        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [str(OPERATOR_BIN), *args],
                cwd=str(temp),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

        self.assertEqual(run("init").returncode, 0)
        created = run("task-create", "--id", "prov-smoke", "--objective", "provenance smoke")
        self.assertEqual(created.returncode, 0, created.stderr)
        use = run("task-use", "prov-smoke")
        self.assertEqual(use.returncode, 0, use.stderr)
        crystal = temp / "crystal.md"
        shutil.copy2(CRYSTAL, crystal)
        res = run(
            "crystal-attach",
            str(crystal),
            "--by",
            "codex",
            "--claimed-provider",
            "xai",
            "--claimed-model",
            "grok-4.6",
        )
        self.assertEqual(res.returncode, 0, res.stderr + res.stdout)
        self.assertIn("[Warning]", res.stderr)
        self.assertIn("openai-codex", res.stderr)
        evidence_dir = temp / ".operator" / "evidence" / "prov-smoke"
        files = list(evidence_dir.glob("evidence-*.yaml"))
        self.assertTrue(files)
        data = yaml.safe_load(files[0].read_text(encoding="utf-8"))
        ident = data["live_pi_identity"]
        self.assertEqual(ident["observed"]["provider"], "openai-codex")
        self.assertEqual(ident["observed"]["model"], "gpt-5.6-luna")
        self.assertEqual(ident["claimed"]["provider"], "xai")
        blob = files[0].read_text(encoding="utf-8") + res.stdout + res.stderr
        self.assertNotIn("sk-should-never-land", blob)
        self.assertFalse(pi_model_provenance.contains_secret_material(ident))
        digest = hashlib.sha256(crystal.read_bytes()).hexdigest()
        self.assertEqual(data["hash"], digest)

    def test_fail_mode_refuses_mismatch_without_writing_evidence(self) -> None:
        if not CRYSTAL.is_file():
            self.skipTest(f"missing fixture {CRYSTAL}")
        temp = Path(tempfile.mkdtemp(prefix="op-prov-fail-")).resolve()
        self.addCleanup(shutil.rmtree, temp, True)
        env = os.environ.copy()
        env.update({"PI_PROVIDER": "openai-codex", "PI_MODEL": "gpt-5.6-luna"})
        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [str(OPERATOR_BIN), *args],
                cwd=str(temp),
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )

        self.assertEqual(run("init").returncode, 0)
        self.assertEqual(
            run("task-create", "--id", "prov-fail", "--objective", "fail mode").returncode,
            0,
        )
        self.assertEqual(run("task-use", "prov-fail").returncode, 0)
        crystal = temp / "crystal.md"
        shutil.copy2(CRYSTAL, crystal)
        res = run(
            "crystal-attach",
            str(crystal),
            "--by",
            "codex",
            "--claimed-provider",
            "xai",
            "--provenance-mode",
            "fail",
        )
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("provenance mismatch", res.stderr)
        evidence_dir = temp / ".operator" / "evidence" / "prov-fail"
        written = list(evidence_dir.glob("evidence-*.yaml")) if evidence_dir.exists() else []
        self.assertEqual(written, [])


if __name__ == "__main__":
    unittest.main()
