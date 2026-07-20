#!/usr/bin/env python3
"""Unprivileged unit tests for dogfood_runner.py (Issue #8, slice 1).

Mirrors tests/test_authority_admin.py's fixture style: a disposable temp root,
InstallLayout.under(root), an identity built from the test process's own
uid/gid, and install_deployment(..., validate_accounts=False) for a real
(but unprivileged-friendly) installed deployment. Real-root-only assertions
(builder/verifier UID denial, crash-window fault-injection recovery) live in
tests/test_dogfood_runner_root.py instead -- see that file's module docstring
for why the split follows this same line.

Phase *execution* tests here run against monkeypatched PHASE_CATALOG entries
rather than the real audit_deployment/collect_evidence_deployment handlers,
because those default to validate_binding=True, which calls
validate_privileged_runtime() (requires /usr/bin/python3 to be a real,
root-owned, non-group-writable executable) -- exactly the kind of
environment-dependent check the existing authority_admin test suite already
avoids in its unprivileged tests (see its own validate_binding=False and
collector= overrides). Separate WiringTests below prove the phase handlers
delegate to the right authority_admin functions with the right arguments,
without depending on that host state.
"""

from __future__ import annotations

import grp
import json
import os
import pwd
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import authority_admin  # noqa: E402
import authority_broker as broker  # noqa: E402
import dogfood_runner  # noqa: E402


def fake_phase_catalog(**overrides) -> dict:
    catalog = dict(dogfood_runner.PHASE_CATALOG)
    for operation, handler in overrides.items():
        spec = catalog[operation]
        catalog[operation] = dogfood_runner.PhaseSpec(
            mutating=spec.mutating,
            args_schema=spec.args_schema,
            handler=handler,
            validate_args=spec.validate_args,
        )
    return catalog


class DogfoodRunnerTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="dogfood-runner-test.")).resolve()
        os.chmod(self.root, 0o700)
        self.layout = authority_admin.InstallLayout.under(self.root)
        self.dogfood_layout = dogfood_runner.DogfoodLayout.under(self.root)
        self.source = self.root / "release"
        self.source.mkdir(mode=0o700)
        for name in authority_admin.INSTALLED_SOURCE_ASSETS:
            shutil.copyfile(REPO_ROOT / name, self.source / name)
            os.chmod(self.source / name, 0o700 if name == "operator-admin" else 0o600)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir(mode=0o700)
        account = pwd.getpwuid(os.getuid())
        group = grp.getgrgid(os.getgid())
        self.identity = authority_admin.DeploymentIdentity(
            os.getuid(),
            os.getgid(),
            account.pw_name,
            os.getuid(),
            os.getgid(),
            group.gr_name,
            os.getgid(),
        )
        self.ledger_id = "ledger-dogfood"
        self.policy_id = "policy-dogfood"
        self.builder_uid = os.getuid() + 40000
        self.verifier_uid = os.getuid() + 40001

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def policy_object(self, generation: int, previous: str | None) -> dict:
        return {
            "policy_schema_version": 1,
            "policy_id": self.policy_id,
            "ledger_id": self.ledger_id,
            "policy_generation": generation,
            "previous_policy_sha256": previous,
            "mode": "enforced",
            "uid_names": {
                str(self.builder_uid): "fixture-builder",
                str(self.verifier_uid): "fixture-verifier",
            },
            "roles": {
                str(self.builder_uid): ["builder"],
                str(self.verifier_uid): ["verifier"],
            },
        }

    def write_policy(self, name: str, generation: int, previous: str | None):
        value = self.policy_object(generation, previous)
        path = self.inputs / name
        path.write_text(json.dumps(value) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
        return path, authority_admin.parse_policy_object(value)

    def install(self):
        path, policy = self.write_policy("generation-1.json", 1, None)
        result = authority_admin.install_deployment(
            self.layout, self.source, path, self.identity, validate_accounts=False
        )
        return result, policy, path

    def default_phases(self) -> list[dict]:
        return [
            {"phase_id": 1, "operation": "installation_verification", "args": {}, "mutating": False},
            {"phase_id": 2, "operation": "privilege_evidence", "args": {}, "mutating": True},
            {"phase_id": 3, "operation": "final_audit", "args": {}, "mutating": False},
        ]

    def valid_plan_object(self, policy: authority_admin.PolicyDocument, *, phases=None) -> dict:
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
            "phases": self.default_phases() if phases is None else phases,
        }

    def write_plan_file(self, plan_value: dict, name: str = "plan.json") -> Path:
        path = self.inputs / name
        path.write_text(json.dumps(plan_value) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)
        return path


# ---------------------------------------------------------------------------
# Plan parsing (pure function, no filesystem)
# ---------------------------------------------------------------------------


class PlanParsingTests(unittest.TestCase):
    def valid_raw(self, **overrides) -> dict:
        value = {
            "plan_schema_version": 1,
            "created_at": "2026-07-20T00:00:00Z",
            "created_by_uid": 0,
            "ledger_id": "ledger-x",
            "policy_binding": {"policy_id": "policy-x", "generation": 1, "sha256": "a" * 64},
            "expected_release_digest": "b" * 64,
            "host_paths": {
                "install_root": "/usr/libexec/operator-control-plane",
                "config_root": "/etc/operator-control-plane",
                "state_root": "/var/lib/operator-control-plane",
                "runtime_root": "/run/operator-control-plane",
            },
            "phases": [
                {"phase_id": 1, "operation": "installation_verification", "args": {}, "mutating": False},
                {"phase_id": 2, "operation": "privilege_evidence", "args": {}, "mutating": True},
                {"phase_id": 3, "operation": "final_audit", "args": {}, "mutating": False},
            ],
        }
        value.update(overrides)
        return value

    def test_valid_plan_round_trips(self) -> None:
        plan = dogfood_runner.parse_plan_object(self.valid_raw())
        self.assertEqual(len(plan.phases), 3)
        self.assertEqual(len(plan.plan_digest), 64)
        int(plan.plan_digest, 16)  # hex

    def test_digest_is_deterministic_and_key_order_independent(self) -> None:
        raw = self.valid_raw()
        reordered = json.loads(json.dumps(raw))  # same content, dict built fresh
        first = dogfood_runner.parse_plan_object(raw)
        second = dogfood_runner.parse_plan_object(reordered)
        self.assertEqual(first.plan_digest, second.plan_digest)

    def test_different_content_yields_different_digest(self) -> None:
        first = dogfood_runner.parse_plan_object(self.valid_raw())
        second = dogfood_runner.parse_plan_object(self.valid_raw(ledger_id="ledger-y"))
        self.assertNotEqual(first.plan_digest, second.plan_digest)

    def test_unknown_top_level_field_rejected(self) -> None:
        raw = self.valid_raw()
        raw["extra"] = True
        with self.assertRaisesRegex(authority_admin.AdminError, "unknown"):
            dogfood_runner.parse_plan_object(raw)

    def test_unknown_operation_rejected(self) -> None:
        raw = self.valid_raw()
        raw["phases"][0]["operation"] = "rm_rf_everything"
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "unknown_operation")

    def test_arbitrary_command_in_args_rejected(self) -> None:
        raw = self.valid_raw()
        raw["phases"][0]["args"] = {"shell": "rm -rf /"}
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "unknown_field")

    def test_mutating_flag_mismatch_rejected(self) -> None:
        raw = self.valid_raw()
        raw["phases"][1]["mutating"] = False  # privilege_evidence is actually mutating
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "mutating_flag_mismatch")

    def test_non_sequential_phase_ids_rejected(self) -> None:
        raw = self.valid_raw()
        raw["phases"][1]["phase_id"] = 5
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "invalid_phase_sequence")

    def test_missing_policy_binding_subkey_rejected(self) -> None:
        raw = self.valid_raw()
        del raw["policy_binding"]["sha256"]
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "missing_field")

    def test_created_by_uid_must_be_zero(self) -> None:
        raw = self.valid_raw(created_by_uid=1000)
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.parse_plan_object(raw)

    def test_empty_phases_rejected(self) -> None:
        raw = self.valid_raw(phases=[])
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.parse_plan_object(raw)

    def test_non_dict_plan_rejected(self) -> None:
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.parse_plan_object(["not", "a", "dict"])


class ServiceLifecycleAndEnrollmentArgsTests(unittest.TestCase):
    """Slice 2: value-level (not just key-set) validation for the two operations
    with non-empty args_schema -- closed vocabulary, no free-form strings."""

    def valid_raw_with_phase(self, phase: dict) -> dict:
        return {
            "plan_schema_version": 1,
            "created_at": "2026-07-20T00:00:00Z",
            "created_by_uid": 0,
            "ledger_id": "ledger-x",
            "policy_binding": {"policy_id": "policy-x", "generation": 1, "sha256": "a" * 64},
            "expected_release_digest": "b" * 64,
            "host_paths": {
                "install_root": "/usr/libexec/operator-control-plane",
                "config_root": "/etc/operator-control-plane",
                "state_root": "/var/lib/operator-control-plane",
                "runtime_root": "/run/operator-control-plane",
            },
            "phases": [phase],
        }

    def test_service_lifecycle_valid_actions_accepted(self) -> None:
        for action in sorted(dogfood_runner.SERVICE_LIFECYCLE_ACTIONS):
            with self.subTest(action=action):
                raw = self.valid_raw_with_phase(
                    {
                        "phase_id": 1,
                        "operation": "service_lifecycle",
                        "args": {"action": action},
                        "mutating": True,
                    }
                )
                plan = dogfood_runner.parse_plan_object(raw)
                self.assertEqual(plan.phases[0]["args"], {"action": action})

    def test_service_lifecycle_unknown_action_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "service_lifecycle",
                "args": {"action": "reboot_the_host"},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "invalid_plan")

    def test_service_lifecycle_missing_action_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {"phase_id": 1, "operation": "service_lifecycle", "args": {}, "mutating": True}
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "missing_field")

    def test_service_lifecycle_arbitrary_command_in_action_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "service_lifecycle",
                "args": {"action": "start; rm -rf /"},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "invalid_plan")

    def test_enrollment_valid_absolute_path_accepted(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "enrollment",
                "args": {"repository_path": "/home/erik/some-repo"},
                "mutating": True,
            }
        )
        plan = dogfood_runner.parse_plan_object(raw)
        self.assertEqual(plan.phases[0]["args"], {"repository_path": "/home/erik/some-repo"})

    def test_enrollment_relative_path_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "enrollment",
                "args": {"repository_path": "some-repo"},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "invalid_plan")

    def test_enrollment_empty_path_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "enrollment",
                "args": {"repository_path": ""},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.parse_plan_object(raw)

    def test_enrollment_non_string_path_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "enrollment",
                "args": {"repository_path": 12345},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.parse_plan_object(raw)

    def test_enrollment_extra_field_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "enrollment",
                "args": {"repository_path": "/x", "shell": "rm -rf /"},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "unknown_field")

    def test_mutating_false_rejected_for_both_new_operations(self) -> None:
        for operation, args in (
            ("service_lifecycle", {"action": "start"}),
            ("enrollment", {"repository_path": "/x"}),
        ):
            with self.subTest(operation=operation):
                raw = self.valid_raw_with_phase(
                    {"phase_id": 1, "operation": operation, "args": args, "mutating": False}
                )
                with self.assertRaises(authority_admin.AdminError) as ctx:
                    dogfood_runner.parse_plan_object(raw)
                self.assertEqual(ctx.exception.code, "mutating_flag_mismatch")


class RotationArgsTests(unittest.TestCase):
    """Slice 3: rotation's policy_file arg gets the same value-level, closed-shape
    validation as enrollment's repository_path -- an absolute path, not a free string."""

    def valid_raw_with_phase(self, phase: dict) -> dict:
        return {
            "plan_schema_version": 1,
            "created_at": "2026-07-20T00:00:00Z",
            "created_by_uid": 0,
            "ledger_id": "ledger-x",
            "policy_binding": {"policy_id": "policy-x", "generation": 1, "sha256": "a" * 64},
            "expected_release_digest": "b" * 64,
            "host_paths": {
                "install_root": "/usr/libexec/operator-control-plane",
                "config_root": "/etc/operator-control-plane",
                "state_root": "/var/lib/operator-control-plane",
                "runtime_root": "/run/operator-control-plane",
            },
            "phases": [phase],
        }

    def test_valid_absolute_policy_file_accepted(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "rotation",
                "args": {"policy_file": "/home/erik/generation-2.json"},
                "mutating": True,
            }
        )
        plan = dogfood_runner.parse_plan_object(raw)
        self.assertEqual(plan.phases[0]["args"], {"policy_file": "/home/erik/generation-2.json"})

    def test_relative_policy_file_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "rotation",
                "args": {"policy_file": "generation-2.json"},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "invalid_plan")

    def test_empty_policy_file_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {"phase_id": 1, "operation": "rotation", "args": {"policy_file": ""}, "mutating": True}
        )
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.parse_plan_object(raw)

    def test_non_string_policy_file_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {"phase_id": 1, "operation": "rotation", "args": {"policy_file": 42}, "mutating": True}
        )
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.parse_plan_object(raw)

    def test_missing_policy_file_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {"phase_id": 1, "operation": "rotation", "args": {}, "mutating": True}
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "missing_field")

    def test_extra_field_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "rotation",
                "args": {"policy_file": "/x", "shell": "rm -rf /"},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "unknown_field")

    def test_mutating_false_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "rotation",
                "args": {"policy_file": "/x"},
                "mutating": False,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "mutating_flag_mismatch")


class OutageRecoveryArgsTests(unittest.TestCase):
    """Slice 4: outage_recovery has an empty args_schema like installation_verification/
    privilege_evidence/final_audit, but is mutating (unlike those three read-only ones),
    so it needs its own mutating-flag and empty-args coverage rather than inheriting it
    from the other empty-args operations."""

    def valid_raw_with_phase(self, phase: dict) -> dict:
        return {
            "plan_schema_version": 1,
            "created_at": "2026-07-20T00:00:00Z",
            "created_by_uid": 0,
            "ledger_id": "ledger-x",
            "policy_binding": {"policy_id": "policy-x", "generation": 1, "sha256": "a" * 64},
            "expected_release_digest": "b" * 64,
            "host_paths": {
                "install_root": "/usr/libexec/operator-control-plane",
                "config_root": "/etc/operator-control-plane",
                "state_root": "/var/lib/operator-control-plane",
                "runtime_root": "/run/operator-control-plane",
            },
            "phases": [phase],
        }

    def test_empty_args_accepted(self) -> None:
        raw = self.valid_raw_with_phase(
            {"phase_id": 1, "operation": "outage_recovery", "args": {}, "mutating": True}
        )
        plan = dogfood_runner.parse_plan_object(raw)
        self.assertEqual(plan.phases[0]["args"], {})

    def test_extra_field_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {
                "phase_id": 1,
                "operation": "outage_recovery",
                "args": {"max_wait_seconds": 300},
                "mutating": True,
            }
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "unknown_field")

    def test_mutating_false_rejected(self) -> None:
        raw = self.valid_raw_with_phase(
            {"phase_id": 1, "operation": "outage_recovery", "args": {}, "mutating": False}
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.parse_plan_object(raw)
        self.assertEqual(ctx.exception.code, "mutating_flag_mismatch")


# ---------------------------------------------------------------------------
# validate_plan_bindings -- redirection/tamper resistance
# ---------------------------------------------------------------------------


class ValidatePlanBindingsTests(DogfoodRunnerTestBase):
    def test_valid_plan_passes(self) -> None:
        _, policy, _ = self.install()
        plan = dogfood_runner.parse_plan_object(self.valid_plan_object(policy))
        dogfood_runner.validate_plan_bindings(plan, self.layout, self.identity)

    def test_host_paths_mismatch_rejected(self) -> None:
        _, policy, _ = self.install()
        raw = self.valid_plan_object(policy)
        raw["host_paths"]["config_root"] = "/tmp/somewhere-else"
        plan = dogfood_runner.parse_plan_object(raw)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.validate_plan_bindings(plan, self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "host_paths_mismatch")

    def test_release_digest_mismatch_rejected(self) -> None:
        _, policy, _ = self.install()
        raw = self.valid_plan_object(policy)
        raw["expected_release_digest"] = "0" * 64
        plan = dogfood_runner.parse_plan_object(raw)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.validate_plan_bindings(plan, self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "release_digest_mismatch")

    def test_release_digest_mismatch_after_installed_asset_changes(self) -> None:
        _, policy, _ = self.install()
        plan = dogfood_runner.parse_plan_object(self.valid_plan_object(policy))
        # Live install drifted (e.g. a later upgrade) after the plan was authored.
        target = self.layout.install_root / "authority_broker.py"
        data = bytearray(target.read_bytes())
        data.append(ord(b"\n"))
        authority_admin.write_protected_file(
            target, bytes(data), 0o600, self.identity.admin_uid, self.identity.admin_gid,
            self.layout, self.identity, replace=True,
        )
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.validate_plan_bindings(plan, self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "release_digest_mismatch")

    def test_ledger_mismatch_rejected(self) -> None:
        _, policy, _ = self.install()
        raw = self.valid_plan_object(policy)
        raw["ledger_id"] = "some-other-ledger"
        plan = dogfood_runner.parse_plan_object(raw)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.validate_plan_bindings(plan, self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "ledger_mismatch")

    def test_policy_binding_mismatch_rejected(self) -> None:
        _, policy, _ = self.install()
        raw = self.valid_plan_object(policy)
        raw["policy_binding"]["sha256"] = "f" * 64
        plan = dogfood_runner.parse_plan_object(raw)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.validate_plan_bindings(plan, self.layout, self.identity)
        self.assertEqual(ctx.exception.code, "policy_binding_mismatch")


# ---------------------------------------------------------------------------
# Path-attack suite
# ---------------------------------------------------------------------------


class PathAttackTests(DogfoodRunnerTestBase):
    def test_symlinked_runs_root_fails_closed(self) -> None:
        _, policy, _ = self.install()
        plan = dogfood_runner.parse_plan_object(self.valid_plan_object(policy))
        identity = self.identity
        dogfood_runner.ensure_dogfood_layout(self.dogfood_layout, self.layout, identity)
        elsewhere = self.root / "elsewhere-runs"
        elsewhere.mkdir(mode=0o700)
        shutil.rmtree(self.dogfood_layout.runs_root)
        self.dogfood_layout.runs_root.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.create_run(plan, self.dogfood_layout, self.layout, identity)

    def test_hardlinked_checkpoint_fails_closed(self) -> None:
        _, policy, _ = self.install()
        plan = dogfood_runner.parse_plan_object(self.valid_plan_object(policy))
        identity = self.identity
        dogfood_runner.ensure_dogfood_layout(self.dogfood_layout, self.layout, identity)
        run_id = dogfood_runner.create_run(plan, self.dogfood_layout, self.layout, identity)
        phase = plan.phases[0]
        dogfood_runner.write_checkpoint(
            self.dogfood_layout, run_id, phase, "completed",
            {"operation_key": "x", "request_digest": "y", "phase_id": 1, "operation": phase["operation"]},
            self.layout, identity,
        )
        path = dogfood_runner.checkpoint_path(
            self.dogfood_layout, run_id, phase["phase_id"], phase["operation"], "completed"
        )
        hardlink = self.root / "checkpoint-hardlink"
        os.link(path, hardlink)
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.phase_checkpoint_state(
                self.dogfood_layout, run_id, phase, self.layout, identity
            )
        hardlink.unlink()

    def test_group_writable_ancestor_fails_closed(self) -> None:
        _, policy, _ = self.install()
        identity = self.identity
        dogfood_runner.ensure_dogfood_layout(self.dogfood_layout, self.layout, identity)
        os.chmod(self.dogfood_layout.admin_root, 0o777)
        try:
            plan = dogfood_runner.parse_plan_object(self.valid_plan_object(policy))
            with self.assertRaises(authority_admin.AdminError):
                dogfood_runner.create_run(plan, self.dogfood_layout, self.layout, identity)
        finally:
            os.chmod(self.dogfood_layout.admin_root, 0o700)

    def test_wrong_owner_run_state_fails_closed(self) -> None:
        _, policy, _ = self.install()
        plan = dogfood_runner.parse_plan_object(self.valid_plan_object(policy))
        identity = self.identity
        dogfood_runner.ensure_dogfood_layout(self.dogfood_layout, self.layout, identity)
        run_id = dogfood_runner.create_run(plan, self.dogfood_layout, self.layout, identity)
        wrong_identity = authority_admin.DeploymentIdentity(
            identity.admin_uid + 1, identity.admin_gid, identity.broker_user,
            identity.broker_uid, identity.broker_gid, identity.socket_group, identity.socket_gid,
        )
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.write_run_state(
                self.dogfood_layout, run_id, plan, 2, "running", self.layout, wrong_identity
            )


# ---------------------------------------------------------------------------
# Idempotency, interruption, and resume mechanics (monkeypatched handlers)
# ---------------------------------------------------------------------------


class ExecutionEngineTests(DogfoodRunnerTestBase):
    def setUp(self) -> None:
        super().setUp()
        _, self.policy, _ = self.install()
        self.plan = dogfood_runner.parse_plan_object(self.valid_plan_object(self.policy))
        dogfood_runner.ensure_dogfood_layout(self.dogfood_layout, self.layout, self.identity)
        dogfood_runner.store_plan(self.plan, self.dogfood_layout, self.layout, self.identity)

    def run_command(self, *, run_id=None, approve_phase=None):
        return dogfood_runner.dogfood_run_command(
            self.layout, self.dogfood_layout, self.plan.plan_digest, run_id, approve_phase,
            self.identity.admin_uid, self.identity.admin_gid,
        )

    def resume_command(self, run_id, *, approve_phase=None, acknowledge_recovered=False):
        return dogfood_runner.dogfood_resume_command(
            self.layout, self.dogfood_layout, run_id, approve_phase, acknowledge_recovered,
            self.identity.admin_uid, self.identity.admin_gid,
        )

    def status(self, run_id):
        return dogfood_runner.dogfood_status_command(
            self.layout, self.dogfood_layout, run_id, self.identity.admin_uid, self.identity.admin_gid
        )

    def test_full_run_stops_before_mutating_phase_then_completes_on_approval(self) -> None:
        fake_catalog = fake_phase_catalog(
            installation_verification=lambda layout, uid, gid, args: {"ok": True, "phase": "verify"},
            privilege_evidence=lambda layout, uid, gid, args: {"ok": True, "phase": "evidence"},
            final_audit=lambda layout, uid, gid, args: {"ok": True, "phase": "audit"},
        )
        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_catalog):
            first = self.run_command()
            self.assertEqual(first["status"], "awaiting_approval")
            self.assertEqual(first["next_phase"], 2)
            run_id = first["run_id"]

            second = self.run_command(run_id=run_id, approve_phase=2)
            self.assertEqual(second["status"], "completed")
            self.assertEqual([p["phase_id"] for p in second["executed"]], [1, 2, 3])
            by_phase = {p["phase_id"]: p["idempotent_replay"] for p in second["executed"]}
            self.assertTrue(by_phase[1])  # already completed in the first call -- replayed
            self.assertFalse(by_phase[2])  # freshly approved and executed this call
            self.assertFalse(by_phase[3])  # freshly executed this call

        status = self.status(run_id)
        self.assertEqual(status["status"], "completed")
        self.assertTrue(all(p["state"] == "completed" for p in status["phases"]))

    def test_exact_retry_is_idempotent_no_new_checkpoint(self) -> None:
        calls = {"count": 0}

        def counting_handler(layout, uid, gid, args):
            calls["count"] += 1
            return {"ok": True, "call": calls["count"]}

        fake_catalog = fake_phase_catalog(installation_verification=counting_handler)
        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_catalog):
            first = self.run_command()
            run_id = first["run_id"]
            self.assertEqual(calls["count"], 1)

            # Same run, same plan digest -- retrying phase 1's completed checkpoint must
            # not re-invoke the handler.
            second = self.run_command(run_id=run_id)
            self.assertEqual(calls["count"], 1)
            self.assertTrue(second["executed"][0]["idempotent_replay"])

    def test_different_run_bound_to_same_run_id_and_wrong_plan_digest_rejected(self) -> None:
        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_phase_catalog(
            installation_verification=lambda layout, uid, gid, args: {"ok": True}
        )):
            first = self.run_command()
            run_id = first["run_id"]
        other_raw = self.valid_plan_object(self.policy, phases=[
            {"phase_id": 1, "operation": "installation_verification", "args": {}, "mutating": False},
        ])
        other_raw["ledger_id"] = self.ledger_id  # keep valid otherwise; only phases differ
        other_plan = dogfood_runner.parse_plan_object(other_raw)
        dogfood_runner.store_plan(other_plan, self.dogfood_layout, self.layout, self.identity)
        with self.assertRaises(authority_admin.AdminError) as ctx:
            dogfood_runner.dogfood_run_command(
                self.layout, self.dogfood_layout, other_plan.plan_digest, run_id, None,
                self.identity.admin_uid, self.identity.admin_gid,
            )
        self.assertEqual(ctx.exception.code, "plan_replaced")

    def test_interruption_leaves_pending_checkpoint_and_resume_reinvokes(self) -> None:
        state = {"raise_next": True}

        class SimulatedCrash(Exception):
            """Not in execute_phase's caught tuple -- models a process kill mid-handler."""

        def crashing_then_succeeding(layout, uid, gid, args):
            if state["raise_next"]:
                state["raise_next"] = False
                raise SimulatedCrash("process killed mid-handler")
            return {"ok": True, "recovered": True}

        fake_catalog = fake_phase_catalog(installation_verification=crashing_then_succeeding)
        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_catalog):
            with self.assertRaises(SimulatedCrash):
                self.run_command()

            # Not raised via dogfood_run_command's own return path, so we need the run_id.
            runs = list(self.dogfood_layout.runs_root.iterdir())
            self.assertEqual(len(runs), 1)
            run_id = runs[0].name

            phase = self.plan.phases[0]
            state_after_crash, _ = dogfood_runner.phase_checkpoint_state(
                self.dogfood_layout, run_id, phase, self.layout, self.identity
            )
            self.assertEqual(state_after_crash, "pending")

            result = self.resume_command(run_id)
        self.assertEqual(result["status"], "awaiting_approval")
        self.assertEqual(result["executed"][0]["phase_id"], 1)
        self.assertFalse(result["executed"][0]["idempotent_replay"])

    def test_failed_phase_blocks_resume_without_acknowledgement(self) -> None:
        def always_fails(layout, uid, gid, args):
            raise authority_admin.AdminError("synthetic_failure", "boom")

        fake_catalog = fake_phase_catalog(installation_verification=always_fails)
        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_catalog):
            with self.assertRaises(authority_admin.AdminError) as ctx:
                self.run_command()
            self.assertEqual(ctx.exception.code, "synthetic_failure")

            runs = list(self.dogfood_layout.runs_root.iterdir())
            run_id = runs[0].name

            status = self.status(run_id)
            self.assertEqual(status["phases"][0]["state"], "failed")
            self.assertEqual(status["status"], "failed")

            # Resume without acknowledgement must not advance past the failed gate.
            with self.assertRaises(authority_admin.AdminError) as ctx2:
                self.resume_command(run_id)
            self.assertEqual(ctx2.exception.code, "failed_phase_requires_acknowledgement")

            # dogfood-run (not resume) never bypasses the gate either.
            with self.assertRaises(authority_admin.AdminError) as ctx3:
                self.run_command(run_id=run_id)
            self.assertEqual(ctx3.exception.code, "failed_phase_requires_acknowledgement")

        # Fix the handler, then resume with explicit acknowledgement.
        fixed_catalog = fake_phase_catalog(
            installation_verification=lambda layout, uid, gid, args: {"ok": True},
            privilege_evidence=lambda layout, uid, gid, args: {"ok": True},
            final_audit=lambda layout, uid, gid, args: {"ok": True},
        )
        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fixed_catalog):
            recovered = self.resume_command(run_id, acknowledge_recovered=True)
        self.assertEqual(recovered["status"], "awaiting_approval")
        self.assertEqual(recovered["next_phase"], 2)

    def test_tampered_completed_checkpoint_fails_closed_on_next_read(self) -> None:
        with mock.patch.object(dogfood_runner, "PHASE_CATALOG", fake_phase_catalog(
            installation_verification=lambda layout, uid, gid, args: {"ok": True}
        )):
            first = self.run_command()
            run_id = first["run_id"]

        phase = self.plan.phases[0]
        path = dogfood_runner.checkpoint_path(
            self.dogfood_layout, run_id, phase["phase_id"], phase["operation"], "completed"
        )
        raw = bytearray(path.read_bytes())
        raw[10] = raw[10] ^ 0xFF  # flip a byte inside the JSON body
        path.write_bytes(bytes(raw))
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.phase_checkpoint_state(
                self.dogfood_layout, run_id, phase, self.layout, self.identity
            )


# ---------------------------------------------------------------------------
# Wiring: phase handlers delegate to the right authority_admin functions
# ---------------------------------------------------------------------------


class PhaseHandlerWiringTests(unittest.TestCase):
    def test_installation_verification_delegates_to_audit_deployment(self) -> None:
        sentinel = object()
        with mock.patch.object(authority_admin, "audit_deployment", return_value=sentinel) as mocked:
            result = dogfood_runner.phase_installation_verification("layout", 0, 0, {})
        mocked.assert_called_once_with("layout", 0, 0)
        self.assertIs(result, sentinel)

    def test_final_audit_delegates_to_audit_deployment(self) -> None:
        sentinel = object()
        with mock.patch.object(authority_admin, "audit_deployment", return_value=sentinel) as mocked:
            result = dogfood_runner.phase_final_audit("layout", 0, 0, {})
        mocked.assert_called_once_with("layout", 0, 0)
        self.assertIs(result, sentinel)

    def test_privilege_evidence_delegates_to_collect_evidence_deployment(self) -> None:
        sentinel = object()
        with mock.patch.object(
            authority_admin, "collect_evidence_deployment", return_value=sentinel
        ) as mocked:
            result = dogfood_runner.phase_privilege_evidence("layout", 0, 0, {})
        mocked.assert_called_once_with("layout", 0, 0)
        self.assertIs(result, sentinel)


class ServiceLifecyclePhaseHandlerTests(unittest.TestCase):
    """Never invokes real systemctl -- stop_service/start_service/probe_service_active
    shell out against a unit *name*, not anything relative to a disposable test root
    (unlike probe_socket_health, which is a real Unix-socket connect and so is safe to
    exercise for real); the existing authority_admin test suite avoids this for the
    same reason (grep shows zero unmocked calls to those three anywhere in it)."""

    def test_stop_action_calls_stop_service_and_confirms_inactive(self) -> None:
        with mock.patch.object(authority_admin, "stop_service") as stop_mock, \
             mock.patch.object(authority_admin, "start_service") as start_mock, \
             mock.patch.object(authority_admin, "probe_service_active", return_value=False) as probe_mock:
            result = dogfood_runner.phase_service_lifecycle("layout", 0, 0, {"action": "stop"})
        stop_mock.assert_called_once_with("layout")
        start_mock.assert_not_called()
        probe_mock.assert_called_once_with("layout")
        self.assertEqual(result, {"action": "stop", "active": False})

    def test_stop_action_raises_if_service_still_active(self) -> None:
        with mock.patch.object(authority_admin, "stop_service"), \
             mock.patch.object(authority_admin, "probe_service_active", return_value=True):
            with self.assertRaises(authority_admin.AdminError) as ctx:
                dogfood_runner.phase_service_lifecycle("layout", 0, 0, {"action": "stop"})
        self.assertEqual(ctx.exception.code, "service_still_active")

    def test_start_action_calls_start_service_and_confirms_healthy(self) -> None:
        with mock.patch.object(authority_admin, "stop_service") as stop_mock, \
             mock.patch.object(authority_admin, "start_service") as start_mock, \
             mock.patch.object(authority_admin, "probe_socket_health", return_value=True) as probe_mock:
            result = dogfood_runner.phase_service_lifecycle("layout", 0, 0, {"action": "start"})
        stop_mock.assert_not_called()
        start_mock.assert_called_once_with("layout")
        probe_mock.assert_called_once_with("layout")
        self.assertEqual(result, {"action": "start", "active": True, "socket_healthy": True})

    def test_start_action_raises_if_socket_not_healthy(self) -> None:
        with mock.patch.object(authority_admin, "start_service"), \
             mock.patch.object(authority_admin, "probe_socket_health", return_value=False):
            with self.assertRaises(authority_admin.AdminError) as ctx:
                dogfood_runner.phase_service_lifecycle("layout", 0, 0, {"action": "start"})
        self.assertEqual(ctx.exception.code, "service_not_healthy")

    def test_restart_action_calls_stop_then_start(self) -> None:
        calls = []
        with mock.patch.object(authority_admin, "stop_service", side_effect=lambda layout: calls.append("stop")), \
             mock.patch.object(authority_admin, "start_service", side_effect=lambda layout: calls.append("start")), \
             mock.patch.object(authority_admin, "probe_socket_health", return_value=True):
            result = dogfood_runner.phase_service_lifecycle("layout", 0, 0, {"action": "restart"})
        self.assertEqual(calls, ["stop", "start"])
        self.assertEqual(result, {"action": "restart", "active": True, "socket_healthy": True})


class OutageRecoveryPhaseHandlerTests(unittest.TestCase):
    """Never invokes real systemctl, same rationale as ServiceLifecyclePhaseHandlerTests."""

    def test_already_healthy_is_a_no_op(self) -> None:
        with mock.patch.object(authority_admin, "probe_service_active", return_value=True), \
             mock.patch.object(authority_admin, "probe_socket_health", return_value=True), \
             mock.patch.object(authority_admin, "stop_service") as stop_mock, \
             mock.patch.object(authority_admin, "start_service") as start_mock:
            result = dogfood_runner.phase_outage_recovery("layout", 0, 0, {})
        stop_mock.assert_not_called()
        start_mock.assert_not_called()
        self.assertEqual(
            result,
            {
                "action": "outage_recovery",
                "already_healthy": True,
                "restarted": False,
                "active": True,
                "socket_healthy": True,
            },
        )

    def test_active_but_socket_unhealthy_restarts_and_recovers(self) -> None:
        with mock.patch.object(authority_admin, "probe_service_active", return_value=True), \
             mock.patch.object(authority_admin, "probe_socket_health", return_value=True) as probe_mock, \
             mock.patch.object(authority_admin, "stop_service") as stop_mock, \
             mock.patch.object(authority_admin, "start_service") as start_mock:
            # First call (the already-healthy check) reports unhealthy; the second call
            # (post-restart recovery probe) reports healthy.
            probe_mock.side_effect = [False, True]
            result = dogfood_runner.phase_outage_recovery("layout", 0, 0, {})
        stop_mock.assert_called_once_with("layout")
        start_mock.assert_called_once_with("layout")
        self.assertEqual(probe_mock.call_count, 2)
        # The recovery probe uses a generous, explicitly-longer timeout than the bare
        # default service_lifecycle relies on -- the one real behavioral difference from
        # "service_lifecycle(restart) then installation_verification" composed by hand.
        _, recovery_kwargs = probe_mock.call_args_list[1]
        self.assertEqual(
            recovery_kwargs.get("timeout"), dogfood_runner.OUTAGE_RECOVERY_HEALTH_TIMEOUT_SECONDS
        )
        self.assertTrue(result["restarted"])
        self.assertFalse(result["already_healthy"])

    def test_inactive_service_skips_initial_socket_probe_then_restarts(self) -> None:
        with mock.patch.object(authority_admin, "probe_service_active", return_value=False), \
             mock.patch.object(authority_admin, "probe_socket_health", return_value=True) as probe_mock, \
             mock.patch.object(authority_admin, "stop_service") as stop_mock, \
             mock.patch.object(authority_admin, "start_service") as start_mock:
            result = dogfood_runner.phase_outage_recovery("layout", 0, 0, {})
        stop_mock.assert_called_once_with("layout")
        start_mock.assert_called_once_with("layout")
        # Short-circuited: probe_service_active already False, so the initial
        # already-healthy socket check never runs -- only the post-restart recovery probe.
        self.assertEqual(probe_mock.call_count, 1)
        self.assertTrue(result["restarted"])

    def test_raises_if_service_never_becomes_healthy_within_timeout(self) -> None:
        with mock.patch.object(authority_admin, "probe_service_active", return_value=False), \
             mock.patch.object(authority_admin, "probe_socket_health", return_value=False), \
             mock.patch.object(authority_admin, "stop_service"), \
             mock.patch.object(authority_admin, "start_service"):
            with self.assertRaises(authority_admin.AdminError) as ctx:
                dogfood_runner.phase_outage_recovery("layout", 0, 0, {})
        self.assertEqual(ctx.exception.code, "service_not_healthy")


class EnrollmentPhaseHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = authority_admin.InstallLayout.production()

    def test_success_delegates_through_audit_and_preflight_to_enroll_repository(self) -> None:
        sentinel = object()
        deployment = {"current": {"state": "active"}, "ledger_id": "ledger-x"}
        boundary = {"boundary_ready": True, "checks": []}
        with mock.patch.object(authority_admin, "audit_deployment", return_value=deployment) as audit_mock, \
             mock.patch.object(authority_admin, "privilege_preflight", return_value=boundary) as preflight_mock, \
             mock.patch.object(authority_admin, "enroll_repository", return_value=sentinel) as enroll_mock:
            result = dogfood_runner.phase_enrollment(
                self.layout, 0, 0, {"repository_path": "/home/erik/repo"}
            )
        audit_mock.assert_called_once_with(self.layout, 0, 0)
        preflight_mock.assert_called_once_with(self.layout, 0, 0)
        enroll_mock.assert_called_once_with(
            authority_admin.REGISTRY_PATH, Path("/home/erik/repo"), "ledger-x", self.layout.socket_path
        )
        self.assertIs(result, sentinel)

    def test_revoked_policy_blocks_before_preflight_or_enroll(self) -> None:
        deployment = {"current": {"state": "revoked"}, "ledger_id": "ledger-x"}
        with mock.patch.object(authority_admin, "audit_deployment", return_value=deployment), \
             mock.patch.object(authority_admin, "privilege_preflight") as preflight_mock, \
             mock.patch.object(authority_admin, "enroll_repository") as enroll_mock:
            with self.assertRaises(authority_admin.AdminError) as ctx:
                dogfood_runner.phase_enrollment(self.layout, 0, 0, {"repository_path": "/x"})
        self.assertEqual(ctx.exception.code, "policy_revoked")
        preflight_mock.assert_not_called()
        enroll_mock.assert_not_called()

    def test_boundary_not_ready_blocks_before_enroll(self) -> None:
        deployment = {"current": {"state": "active"}, "ledger_id": "ledger-x"}
        boundary = {
            "boundary_ready": False,
            "checks": [{"id": "sudo.authorization", "status": "fail"}],
        }
        with mock.patch.object(authority_admin, "audit_deployment", return_value=deployment), \
             mock.patch.object(authority_admin, "privilege_preflight", return_value=boundary), \
             mock.patch.object(authority_admin, "enroll_repository") as enroll_mock:
            with self.assertRaises(authority_admin.AdminError) as ctx:
                dogfood_runner.phase_enrollment(self.layout, 0, 0, {"repository_path": "/x"})
        self.assertEqual(ctx.exception.code, "privilege_precondition_unproven")
        self.assertEqual(ctx.exception.details["unresolved_checks"], ["sudo.authorization"])
        enroll_mock.assert_not_called()


class RotationPhaseHandlerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.layout = authority_admin.InstallLayout.production()

    def test_delegates_to_rotate_deployment_with_validate_accounts_true(self) -> None:
        sentinel = object()
        with mock.patch.object(
            authority_admin, "rotate_deployment", return_value=sentinel
        ) as mocked:
            result = dogfood_runner.phase_rotation(
                self.layout, 0, 0, {"policy_file": "/home/erik/generation-2.json"}
            )
        mocked.assert_called_once_with(
            self.layout, Path("/home/erik/generation-2.json"), 0, 0, validate_accounts=True
        )
        self.assertIs(result, sentinel)


# ---------------------------------------------------------------------------
# dogfood-plan command
# ---------------------------------------------------------------------------


class DogfoodPlanCommandTests(DogfoodRunnerTestBase):
    def test_dogfood_plan_stores_digest_named_file(self) -> None:
        _, policy, _ = self.install()
        plan_path = self.write_plan_file(self.valid_plan_object(policy))
        result = dogfood_runner.dogfood_plan_command(
            self.layout, self.dogfood_layout, plan_path,
            self.identity.admin_uid, self.identity.admin_gid,
        )
        self.assertTrue(result["ok"])
        stored = dogfood_runner.plan_store_path(self.dogfood_layout, result["plan_digest"])
        self.assertTrue(stored.exists())
        self.assertEqual(stat.S_IMODE(stored.stat().st_mode), 0o600)

    def test_dogfood_plan_repeat_call_is_a_no_op_verify(self) -> None:
        _, policy, _ = self.install()
        plan_path = self.write_plan_file(self.valid_plan_object(policy))
        first = dogfood_runner.dogfood_plan_command(
            self.layout, self.dogfood_layout, plan_path,
            self.identity.admin_uid, self.identity.admin_gid,
        )
        second = dogfood_runner.dogfood_plan_command(
            self.layout, self.dogfood_layout, plan_path,
            self.identity.admin_uid, self.identity.admin_gid,
        )
        self.assertEqual(first["plan_digest"], second["plan_digest"])

    def test_dogfood_plan_rejects_binding_mismatch_before_storing(self) -> None:
        _, policy, _ = self.install()
        raw = self.valid_plan_object(policy)
        raw["ledger_id"] = "wrong-ledger"
        plan_path = self.write_plan_file(raw)
        with self.assertRaises(authority_admin.AdminError):
            dogfood_runner.dogfood_plan_command(
                self.layout, self.dogfood_layout, plan_path,
                self.identity.admin_uid, self.identity.admin_gid,
            )
        # ensure_dogfood_layout creates empty scaffolding directories up front (harmless),
        # but no plan file may be written under plans_root when binding validation fails.
        plans = (
            list(self.dogfood_layout.plans_root.glob("*.json"))
            if self.dogfood_layout.plans_root.exists()
            else []
        )
        self.assertEqual(plans, [])


if __name__ == "__main__":
    unittest.main()
