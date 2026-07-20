#!/usr/bin/env python3
"""Guarded real-root tests for dogfood_runner.py (Issue #8, slice 1).

Mirrors tests/test_authority_admin_root.py: skipped unless running as real
root, uses a disposable root-owned temp tree via InstallLayout.under()/
DogfoodLayout.under(), and a real "nobody" account as the broker identity.

Two things this file proves that the unprivileged suite structurally cannot:

1. A real, unprivileged UID cannot reach a privileged dogfood phase through
   the runner (acceptance criterion 7) -- proven via a real subprocess and a
   real os.setresuid() drop, not a mock of require_root().
2. A durable crash between "phase attempt recorded" and "handler invoked"
   recovers deterministically on resume (acceptance criterion 4), using
   write_protected_file's own fault-injection hook against real root-owned
   files -- not something meaningful to simulate without real privilege.

Like tests/test_authority_admin_root.py's own root suite (see its
privilege_preflight mock), the real host-inspection collector
(collect_privilege_evidence) is replaced with a synthetic one for the
end-to-end flow test below: exercising real sudo/polkit/mount probing is
exactly the kind of environment-dependent behavior even the existing root
suite avoids. What *is* exercised for real here is everything this module
adds: root-owned checkpoint/run-state writes under
/var/lib/operator-control-plane-admin, the identity-binding check inside
audit_deployment/collect_evidence_deployment (validate_binding stays at its
real default), and the require_root() gate on every dogfood subcommand.
"""

from __future__ import annotations

import json
import os
import pwd
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import authority_admin  # noqa: E402
import authority_broker as broker  # noqa: E402
import dogfood_runner  # noqa: E402


@unittest.skipUnless(os.geteuid() == 0, "requires root for a real broker UID drop")
class TestDogfoodRunnerRootBoundary(unittest.TestCase):
    def setUp(self) -> None:
        self.mounted: list[Path] = []
        self.root = Path(tempfile.mkdtemp(prefix="dogfood-runner-root.")).resolve()
        os.chmod(self.root, 0o755)
        (self.root / "var/lib").mkdir(parents=True, mode=0o755)
        os.chmod(self.root / "var", 0o755)
        os.chmod(self.root / "var/lib", 0o755)
        self.layout = authority_admin.InstallLayout.under(self.root)
        self.dogfood_layout = dogfood_runner.DogfoodLayout.under(self.root)
        self.source = self.root / "release"
        self.source.mkdir(mode=0o700)
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(REPO_ROOT / name, self.source / name)
            os.chmod(self.source / name, 0o700 if name == "operator-admin" else 0o600)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir(mode=0o700)

        broker_account = pwd.getpwnam("nobody")
        socket_gid = 0 if broker_account.pw_gid != 0 else 1
        self.identity = authority_admin.DeploymentIdentity(
            0, 0, broker_account.pw_name, broker_account.pw_uid, broker_account.pw_gid,
            "root", socket_gid,
        )
        self.nobody_uid = broker_account.pw_uid

        self.ledger_id = "root-boundary-ledger"
        self.policy_id = "root-boundary-policy"
        self.builder_uid = 200001
        self.verifier_uid = 200002
        self.policy_value = {
            "policy_schema_version": 1,
            "policy_id": self.policy_id,
            "ledger_id": self.ledger_id,
            "policy_generation": 1,
            "previous_policy_sha256": None,
            "mode": "enforced",
            "uid_names": {
                str(self.builder_uid): "fixture-builder",
                str(self.verifier_uid): "fixture-verifier",
            },
            "roles": {str(self.builder_uid): ["builder"], str(self.verifier_uid): ["verifier"]},
        }
        self.policy_file = self.inputs / "policy.json"
        self.policy_file.write_text(json.dumps(self.policy_value) + "\n", encoding="ascii")
        os.chmod(self.policy_file, 0o600)

    def tearDown(self) -> None:
        for path in reversed(self.mounted):
            subprocess.run(["/usr/bin/umount", str(path)], check=False)
        shutil.rmtree(self.root, ignore_errors=True)

    def install(self) -> authority_admin.PolicyDocument:
        policy = authority_admin.parse_policy_object(self.policy_value)
        authority_admin.install_deployment(
            self.layout, self.source, self.policy_file, self.identity, validate_accounts=False
        )
        return policy

    def synthetic_evidence(self, policy: authority_admin.PolicyDocument) -> dict:
        checks = {
            check_id: {"status": "pass", "evidence": {"synthetic": True}}
            for check_id in authority_admin.EVIDENCE_CHECK_IDS
        }
        return {
            "evidence_schema_version": authority_admin.EVIDENCE_SCHEMA_VERSION,
            "ledger_id": policy.ledger_id,
            "policy_id": policy.policy_id,
            "policy_generation": policy.generation,
            "policy_sha256": policy.sha256,
            "collected_at": int(time.time()),
            "checks": checks,
        }

    def valid_plan_object(self, policy: authority_admin.PolicyDocument) -> dict:
        assets = authority_admin.read_source_assets(self.layout.install_root, self.layout, self.identity)
        release_digest = authority_admin.compute_release_digest(authority_admin.hash_source_assets(assets))
        return {
            "plan_schema_version": 1,
            "created_at": "2026-07-20T00:00:00Z",
            "created_by_uid": 0,
            "ledger_id": self.ledger_id,
            "policy_binding": {
                "policy_id": policy.policy_id,
                "generation": policy.generation,
                "sha256": policy.sha256,
            },
            "expected_release_digest": release_digest,
            "host_paths": {
                "install_root": str(self.layout.install_root),
                "config_root": str(self.layout.config_root),
                "state_root": str(self.layout.state_root),
                "runtime_root": str(self.layout.runtime_root),
            },
            "phases": [
                {"phase_id": 1, "operation": "installation_verification", "args": {}, "mutating": False},
                {"phase_id": 2, "operation": "privilege_evidence", "args": {}, "mutating": True},
                {"phase_id": 3, "operation": "final_audit", "args": {}, "mutating": False},
            ],
        }

    # -- Acceptance criterion 7: a real non-root UID cannot reach a privileged
    # dogfood phase through the runner. -----------------------------------

    def test_nonroot_uid_cannot_invoke_dogfood_commands(self) -> None:
        for command_args in (
            ["dogfood-plan", "--plan", str(self.policy_file)],
            ["dogfood-run", "--plan-digest", "a" * 64],
            ["dogfood-status", "--run-id", "b" * 32],
            ["dogfood-resume", "--run-id", "c" * 32],
        ):
            with self.subTest(command=command_args[0]):
                completed = subprocess.run(
                    [sys.executable, str(REPO_ROOT / "authority_admin.py"), *command_args],
                    cwd="/",
                    text=True,
                    capture_output=True,
                    check=False,
                    preexec_fn=lambda: os.setresuid(self.nobody_uid, self.nobody_uid, self.nobody_uid),
                )
                self.assertNotEqual(completed.returncode, 0, completed.stdout)
                self.assertIn("root_required", completed.stderr)

    # -- Real end-to-end flow: plan -> run (stop for approval) -> approve ->
    # status -> resume-is-a-no-op, against a real root-owned install, real
    # audit_deployment/collect_evidence_deployment identity-binding checks,
    # real write_protected_file checkpoint persistence. ---------------------

    def test_real_install_dogfood_plan_run_approve_status(self) -> None:
        policy = self.install()
        plan_path = self.inputs / "plan.json"
        plan_path.write_text(json.dumps(self.valid_plan_object(policy)) + "\n", encoding="ascii")
        os.chmod(plan_path, 0o600)

        fake_catalog = dict(dogfood_runner.PHASE_CATALOG)
        real_spec = fake_catalog["privilege_evidence"]

        def synthetic_privilege_evidence(layout, admin_uid, admin_gid, args):
            return authority_admin.collect_evidence_deployment(
                layout, admin_uid, admin_gid,
                collector=lambda _layout, _identity, _policy: self.synthetic_evidence(policy),
            )

        fake_catalog["privilege_evidence"] = dogfood_runner.PhaseSpec(
            mutating=real_spec.mutating, args_schema=real_spec.args_schema,
            handler=synthetic_privilege_evidence,
        )

        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_catalog):
            plan_result = dogfood_runner.dogfood_plan_command(
                self.layout, self.dogfood_layout, plan_path, 0, 0
            )
            self.assertTrue(plan_result["ok"])

            first = dogfood_runner.dogfood_run_command(
                self.layout, self.dogfood_layout, plan_result["plan_digest"], None, None, 0, 0
            )
            self.assertEqual(first["status"], "awaiting_approval")
            self.assertEqual(first["next_phase"], 2)
            run_id = first["run_id"]

            # Root-owned checkpoint/run-state files, structurally separate from the
            # broker's own state_root -- component-wise (is_within), not a naive string
            # prefix check: "operator-control-plane-admin" would wrongly look "nested"
            # under "operator-control-plane" to a plain str.startswith().
            plan_json = self.dogfood_layout.runs_root / run_id / "plan.json"
            self.assertEqual(plan_json.stat().st_uid, 0)
            self.assertEqual(stat.S_IMODE(plan_json.stat().st_mode), 0o600)
            self.assertFalse(
                authority_admin.is_within(self.dogfood_layout.admin_root, self.layout.state_root)
            )
            self.assertFalse(
                authority_admin.is_within(self.layout.state_root, self.dogfood_layout.admin_root)
            )

            second = dogfood_runner.dogfood_run_command(
                self.layout, self.dogfood_layout, plan_result["plan_digest"], run_id, 2, 0, 0
            )
            self.assertEqual(second["status"], "completed")

            status = dogfood_runner.dogfood_status_command(
                self.layout, self.dogfood_layout, run_id, 0, 0
            )
            self.assertEqual(status["status"], "completed")
            self.assertTrue(all(p["state"] == "completed" for p in status["phases"]))

            # A resume against a fully-completed run is a pure idempotent no-op.
            resumed = dogfood_runner.dogfood_resume_command(
                self.layout, self.dogfood_layout, run_id, None, False, 0, 0
            )
            self.assertEqual(resumed["status"], "completed")
            self.assertTrue(all(p["idempotent_replay"] for p in resumed["executed"]))

    # -- Acceptance criterion 4: a durable crash between "phase attempt
    # recorded" and "handler invoked" recovers deterministically. -----------

    def test_crash_between_pending_checkpoint_and_handler_recovers_on_resume(self) -> None:
        policy = self.install()
        plan = dogfood_runner.parse_plan_object(self.valid_plan_object(policy))
        dogfood_runner.ensure_dogfood_layout(self.dogfood_layout, self.layout, self.identity)
        dogfood_runner.store_plan(plan, self.dogfood_layout, self.layout, self.identity)
        run_id = dogfood_runner.create_run(plan, self.dogfood_layout, self.layout, self.identity)

        calls = {"count": 0}

        def counting_handler(layout, uid, gid, args):
            calls["count"] += 1
            return {"ok": True}

        fired = {"once": False}

        class SimulatedCrash(Exception):
            """Raised after the pending checkpoint is durably on disk, before the
            handler runs -- write_protected_file's fault hook fires at
            "after_publish", i.e. strictly after the rename that makes the pending
            checkpoint visible, so this models a process kill in the real crash
            window rather than a torn write."""

        def fault(event: str, path: Path) -> None:
            if event == "after_publish" and path.name.endswith(".pending.json") and not fired["once"]:
                fired["once"] = True
                raise SimulatedCrash

        fake_catalog = dict(dogfood_runner.PHASE_CATALOG)
        real_spec = fake_catalog["installation_verification"]
        fake_catalog["installation_verification"] = dogfood_runner.PhaseSpec(
            mutating=real_spec.mutating, args_schema=real_spec.args_schema, handler=counting_handler
        )

        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_catalog):
            with self.assertRaises(SimulatedCrash):
                dogfood_runner.execute_run(
                    plan, run_id, None, self.dogfood_layout, self.layout, self.identity, 0, 0,
                    acknowledge_recovered=False, fault=fault,
                )
            self.assertEqual(calls["count"], 0, "handler must not run before the pending checkpoint is durable")

            state, _ = dogfood_runner.phase_checkpoint_state(
                self.dogfood_layout, run_id, plan.phases[0], self.layout, self.identity
            )
            self.assertEqual(state, "pending")

            result = dogfood_runner.execute_run(
                plan, run_id, None, self.dogfood_layout, self.layout, self.identity, 0, 0,
                acknowledge_recovered=False,
            )
        self.assertEqual(calls["count"], 1)
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertFalse(result["executed"][0]["idempotent_replay"])


if __name__ == "__main__":
    unittest.main()
