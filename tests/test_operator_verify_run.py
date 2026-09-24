"""Verifier runner contract tests. No sudo, provider calls, or privileged writes."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from scripts import operator_verify_run as runner


class VerifyRunnerTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.uid = os.getuid()
        if self.uid == 0:
            self.skipTest("runner deliberately refuses root verifiers")
        self.ledger = self.root / ".operator"
        for name in ("claims", "tasks", "review_delegations"):
            (self.ledger / name).mkdir(parents=True)
        self.bundle_id = "review-claim-0001-fixture"
        self.bundle = self.ledger / "review_delegations" / f"{self.bundle_id}.yaml"
        self.claim = self.ledger / "claims" / "claim-0001.yaml"
        self.policy = self.ledger / "identity.yaml"
        self.dump(
            self.claim,
            {
                "claim_id": "claim-0001",
                "task_id": "fixture",
                "author_executor": {"uid": self.uid + 1},
            },
        )
        self.dump(self.ledger / "tasks" / "fixture.yaml", {"task_id": "fixture"})
        self.dump(
            self.policy,
            {"mode": "enforced", "uids": {self.uid: {"name": "verifier", "roles": ["verifier"]}}},
        )
        self.dump(
            self.bundle,
            {
                "delegation_id": self.bundle_id,
                "mode": "uid-isolated",
                "repo_root": str(self.root),
                "claim_id": "claim-0001",
                "task_id": "fixture",
                "review_user": "verifier",
                "model": "example/test-model",
                "verify_cmd": "python3 -m pytest tests/",
            },
        )
        for mock in (
            patch.dict(
                os.environ, {"HOME": str(self.home), "PATH": os.environ.get("PATH", "")}, clear=True
            ),
            patch.object(
                runner.pwd,
                "getpwnam",
                return_value=SimpleNamespace(pw_uid=self.uid, pw_dir=str(self.home)),
            ),
            patch.object(runner.authority_client, "resolve_enrollment", return_value=None),
            patch.object(runner.shutil, "which", return_value="/usr/bin/pi"),
        ):
            mock.start()
            self.addCleanup(mock.stop)

    def dump(self, path, data):
        path.write_text(yaml.safe_dump(data))

    def plan(self):
        return runner.inspect(self.root, self.bundle_id)

    def invoke(self):
        return runner.run(self.root, self.bundle_id, self.plan()["token"])

    def reviewer(self, verdict=None, code=0, mutation=None):
        def execute(argv, root, env, output, timeout):
            self.assertIn("--no-approve", argv)
            self.assertNotIn("sudo", argv)
            self.assertNotIn("-E", argv)
            output.write("Review/test output\n")
            if verdict is not None:
                path = Path(output.name).parent / "decision.json"
                path.write_text(json.dumps(verdict))
                path.chmod(0o600)
            if mutation:
                mutation()
            return code

        return patch.object(runner, "execute_review", side_effect=execute)

    def approval(self):
        return {
            "claim_id": "claim-0001",
            "approve": True,
            "reason": "Independent checks support the claim",
            "checks": ["Reran gate; assessed claim scope"],
        }

    def test_inspect_readonly_and_bound_to_inputs(self):
        before = sorted(self.root.rglob("*"))
        plan = self.plan()
        self.assertEqual(sorted(self.root.rglob("*")), before)
        self.assertEqual(plan["verifier_uid"], self.uid)
        self.assertNotEqual(plan["verifier_uid"], plan["author_uid"])
        self.assertEqual(len(plan["token"]), 64)
        self.claim.write_text(self.claim.read_text() + "text: changed\n")
        self.assertNotEqual(self.plan()["token"], plan["token"])

    def test_stale_confirmation_never_launches(self):
        token = self.plan()["token"]
        self.claim.write_text(self.claim.read_text() + "text: changed\n")
        with patch.object(runner, "execute_review") as execute:
            with self.assertRaisesRegex(ValueError, "changed"):
                runner.run(self.root, self.bundle_id, token)
            execute.assert_not_called()

    def test_same_uid_root_unregistered_and_single_user_refused(self):
        with (
            patch.object(
                runner.pwd,
                "getpwnam",
                return_value=SimpleNamespace(pw_uid=self.uid + 1, pw_dir=str(self.home)),
            ),
            self.assertRaisesRegex(ValueError, "distinct"),
        ):
            self.plan()
        with (
            patch.object(
                runner.pwd,
                "getpwnam",
                return_value=SimpleNamespace(pw_uid=0, pw_dir=str(self.home)),
            ),
            self.assertRaisesRegex(ValueError, "non-root"),
        ):
            self.plan()
        self.dump(self.policy, {"mode": "single_user", "uids": {}})
        with self.assertRaisesRegex(ValueError, "enforced"):
            self.plan()
        self.dump(
            self.policy,
            {"mode": "enforced", "uids": {self.uid: {"name": "builder", "roles": ["builder"]}}},
        )
        with self.assertRaisesRegex(ValueError, "verifier"):
            self.plan()

    def test_spoof_enrollment_and_traversal_refused(self):
        with (
            patch.dict(os.environ, {"OPERATOR_TEST_UID": "42"}),
            self.assertRaisesRegex(ValueError, "overrides"),
        ):
            self.plan()
        with (
            patch.object(runner.authority_client, "resolve_enrollment", return_value=object()),
            self.assertRaisesRegex(ValueError, "broker"),
        ):
            self.plan()
        with self.assertRaises(ValueError):
            runner.inspect(self.root, "../claim-0001")
        content = self.bundle.read_text()
        self.bundle.unlink()
        other = self.root / "other.yaml"
        other.write_text(content)
        self.bundle.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.plan()

    def test_wrong_executor_or_home_cannot_run(self):
        token = self.plan()["token"]
        with (
            patch.object(runner.os, "getuid", return_value=self.uid + 2),
            self.assertRaisesRegex(ValueError, "execute as"),
        ):
            runner.run(self.root, self.bundle_id, token)
        with (
            patch.dict(os.environ, {"HOME": "/tmp"}),
            self.assertRaisesRegex(ValueError, "HOME"),
        ):
            runner.run(self.root, self.bundle_id, token)

    def test_exit_zero_without_decision_does_not_attach(self):
        with self.reviewer(), patch.object(runner.subprocess, "run") as attach:
            result = self.invoke()
            self.assertFalse(result["attached"])
            self.assertEqual(result["outcome"], "refused")
            self.assertTrue(Path(result["log"]).is_file())
            attach.assert_not_called()

    def test_rejection_failure_and_timeout_do_not_attach(self):
        verdict = {**self.approval(), "approve": False}
        for decision, code in ((verdict, 0), (self.approval(), 2)):
            with (
                self.subTest(code=code),
                self.reviewer(decision, code),
                patch.object(runner.subprocess, "run") as attach,
            ):
                self.assertFalse(self.invoke()["attached"])
                attach.assert_not_called()
        with (
            patch.object(
                runner, "execute_review", side_effect=subprocess.TimeoutExpired("pi", 600)
            ),
            patch.object(runner.subprocess, "run") as attach,
        ):
            result = self.invoke()
            self.assertEqual(result["outcome"], "timeout")
            attach.assert_not_called()

    def test_approval_attaches_closed_hash_bound_log_under_verifier(self):
        with (
            self.reviewer(self.approval()),
            patch.object(
                runner.subprocess,
                "run",
                return_value=SimpleNamespace(
                    returncode=0, stdout="Attached evidence-0001", stderr=""
                ),
            ) as attach,
        ):
            result = self.invoke()
            self.assertTrue(result["attached"])
            argv = attach.call_args.args[0]
            self.assertEqual(argv[argv.index("--verified-by") + 1], "verifier")
            self.assertEqual(argv[argv.index("--claim") + 1], "claim-0001")
            self.assertIn("Review/test output", Path(result["artifact"]).read_text())
            self.assertEqual(Path(result["run_dir"]).stat().st_mode & 0o777, 0o700)
            self.assertEqual(Path(result["log"]).stat().st_uid, self.uid)
            self.assertTrue((Path(result["run_dir"]) / "result.json").is_file())

    def test_changed_claim_malformed_or_wrong_claim_decision_refused(self):
        variants = [
            {**self.approval(), "claim_id": "claim-9999"},
            {**self.approval(), "approve": "true"},
            {**self.approval(), "checks": []},
        ]
        for verdict in variants:
            with (
                self.subTest(verdict=verdict),
                self.reviewer(verdict),
                patch.object(runner.subprocess, "run") as attach,
            ):
                self.assertFalse(self.invoke()["attached"])
                attach.assert_not_called()
        with (
            self.reviewer(
                self.approval(),
                mutation=lambda: self.claim.write_text(self.claim.read_text() + "text: changed\n"),
            ),
            patch.object(runner.subprocess, "run") as attach,
        ):
            self.assertFalse(self.invoke()["attached"])
            attach.assert_not_called()

    def test_attachment_failure_keeps_logs_and_does_not_claim_success(self):
        with (
            self.reviewer(self.approval()),
            patch.object(
                runner.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stdout="", stderr="gate refused"),
            ),
        ):
            result = self.invoke()
            self.assertFalse(result["attached"])
            self.assertEqual(result["outcome"], "attachment-failed")
            self.assertTrue(Path(result["log"]).exists())

    def test_private_directory_and_decision_symlinks_refused(self):
        base = self.home / ".operator-verifier-runs"
        base.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            runner.private_directory(self.home, "test")
        base.unlink()
        verdict = self.root / "verdict.json"
        verdict.write_text(json.dumps(self.approval()))
        link = self.root / "link.json"
        link.symlink_to(verdict)
        with self.assertRaises(ValueError):
            runner.decision(link, "claim-0001")

    def test_precreated_artifact_symlink_does_not_write_or_attach(self):
        outside = self.root / "outside.txt"
        outside.write_text("unchanged")

        def plant():
            directory = next((self.home / ".operator-verifier-runs").iterdir())
            (directory / "evidence.txt").symlink_to(outside)

        with (
            self.reviewer(self.approval(), mutation=plant),
            patch.object(runner.subprocess, "run") as attach,
        ):
            result = self.invoke()
            self.assertFalse(result["attached"])
            self.assertEqual(outside.read_text(), "unchanged")
            attach.assert_not_called()

    def test_logging_failure_does_not_hide_successful_attachment(self):
        def plant():
            directory = next((self.home / ".operator-verifier-runs").iterdir())
            (directory / "attachment.log").write_text("preexisting")
            (directory / "result.json").write_text("preexisting")

        with (
            self.reviewer(self.approval(), mutation=plant),
            patch.object(
                runner.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=0, stdout="attached", stderr=""),
            ),
        ):
            result = self.invoke()
            self.assertTrue(result["attached"])
            self.assertIn("attachment_log_error", result)
            self.assertIn("manifest_error", result)

    def test_real_operator_attachment_gate_with_simulated_author_uid(self):
        # Only claim construction uses the documented test identity hook. The
        # runner itself refuses those hooks and attaches using the real UID.
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            env = {
                **os.environ,
                "OPERATOR_TEST_UID": str(self.uid + 1),
                "OPERATOR_TEST_SENTINEL": "1",
            }

            def cli(*args):
                process = subprocess.run(
                    [sys.executable, str(runner.SOURCE / "operator"), *args],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
                return process

            cli("init")
            cli("task-create", "--id", "fixture", "--objective", "Verifier integration fixture")
            gate = root / "gate.txt"
            gate.write_text("test fixture")
            cli(
                "claim-add",
                "--task",
                "fixture",
                "--type",
                "file_exists",
                "--text",
                "Gate exists",
                "--gate",
                str(gate),
                "--verify-cmd",
                "test -f gate.txt",
                "--by",
                "pi-author-fixture",
            )
            ledger = root / ".operator"
            self.dump(
                ledger / "identity.yaml",
                {
                    "mode": "enforced",
                    "uids": {
                        self.uid: {"name": "verifier", "roles": ["verifier"]},
                        self.uid + 1: {"name": "builder", "roles": ["builder"]},
                    },
                },
            )
            bundles = ledger / "review_delegations"
            bundles.mkdir()
            bundle = yaml.safe_load(self.bundle.read_text())
            bundle["repo_root"] = str(root)
            self.dump(bundles / self.bundle.name, bundle)
            plan = runner.inspect(root, self.bundle_id)
            with self.reviewer(self.approval()):
                result = runner.run(root, self.bundle_id, plan["token"])
            attachment_log = Path(result["run_dir"]) / "attachment.log"
            self.assertTrue(
                result["attached"],
                attachment_log.read_text() if attachment_log.exists() else result,
            )
            claim = yaml.safe_load((ledger / "claims" / "claim-0001.yaml").read_text())
            self.assertIs(claim["verification_status"], True)
            self.assertEqual(claim["verification_authority"], "uid_isolated")

    def test_timeout_kills_review_process_group(self):
        with (
            patch.object(runner.subprocess, "Popen") as popen,
            patch.object(runner.os, "killpg") as kill,
        ):
            process = popen.return_value
            process.pid = 12345
            process.wait.side_effect = [subprocess.TimeoutExpired("pi", 1), 1]
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.execute_review(["pi"], str(self.root), {}, None, 1)
            kill.assert_called_once_with(12345, runner.signal.SIGKILL)
            self.assertTrue(popen.call_args.kwargs["start_new_session"])
