#!/usr/bin/env python3
"""Tests for study_runner.py.

Two layers:
- Pure unit tests of plan parsing/digest/rejection and the checkpoint state
  machine, using stub LedgerOps (no real .operator ledger needed).
- A full two-row fake-harness rehearsal driven through the real `operator`
  CLI (study-plan/study-run/study-status/study-resume), covering every
  operation in the closed vocabulary end to end -- no real Claude/Agy/Codex/
  Grok binary is ever invoked.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import harness_adapter as ha  # noqa: E402
import study_runner as sr  # noqa: E402

OPERATOR_BIN = str(Path(__file__).resolve().parents[1] / "operator")
_op_loader = importlib.machinery.SourceFileLoader("operator_mod_study", OPERATOR_BIN)
_op_spec = importlib.util.spec_from_file_location(
    "operator_mod_study", OPERATOR_BIN, loader=_op_loader
)
op_mod = importlib.util.module_from_spec(_op_spec)
_op_loader.exec_module(op_mod)


def write_fake_cli(directory: Path, name: str, body: str) -> str:
    path = directory / name
    path.write_text("#!/usr/bin/env python3\n" + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return str(path)


def base_plan_dict(**overrides) -> dict:
    plan = {
        "plan_schema_version": 1,
        "created_at": "2026-07-22T00:00:00+00:00",
        "study_id": "FFSI-TEST",
        "workspaces": {"row_a": "/tmp/row-a", "row_b": "/tmp/row-b", "shared": "/tmp/shared"},
        "task_ids": {"row_a": "task-row-a", "row_b": "task-row-b", "shared": "task-shared"},
        "phases": [
            {
                "phase_id": 1,
                "operation": "preflight",
                "row": None,
                "harness_id": None,
                "model": None,
                "args": {},
                "mutating": False,
            }
        ],
    }
    plan.update(overrides)
    return plan


class TestPlanParsing(unittest.TestCase):
    def test_valid_minimal_plan_parses_and_digests(self):
        plan = sr.parse_plan_object(base_plan_dict())
        self.assertEqual(len(plan.plan_digest), 64)
        self.assertEqual(plan.study_id, "FFSI-TEST")

    def test_digest_is_deterministic_and_content_addressed(self):
        p1 = sr.parse_plan_object(base_plan_dict())
        p2 = sr.parse_plan_object(base_plan_dict())
        self.assertEqual(p1.plan_digest, p2.plan_digest)

    def test_altered_plan_gets_a_different_digest(self):
        p1 = sr.parse_plan_object(base_plan_dict())
        altered = base_plan_dict(study_id="FFSI-DIFFERENT")
        p2 = sr.parse_plan_object(altered)
        self.assertNotEqual(p1.plan_digest, p2.plan_digest)

    def test_rejects_wrong_key_set(self):
        bad = base_plan_dict()
        bad["unexpected_field"] = "x"
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_non_sequential_phase_ids(self):
        bad = base_plan_dict()
        bad["phases"][0]["phase_id"] = 2
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_unknown_operation(self):
        bad = base_plan_dict()
        bad["phases"][0]["operation"] = "do_arbitrary_thing"
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_unknown_harness_id(self):
        bad = base_plan_dict(
            phases=[
                {
                    "phase_id": 1,
                    "operation": "judge",
                    "row": None,
                    "harness_id": "some-arbitrary-executable",
                    "model": "m",
                    "args": {"prompt": "hi"},
                    "mutating": False,
                }
            ]
        )
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_shell_string_as_validation_command(self):
        bad = base_plan_dict(
            phases=[
                {
                    "phase_id": 1,
                    "operation": "validation",
                    "row": "row_a",
                    "harness_id": None,
                    "model": None,
                    "args": {"command": "pytest tests/ && rm -rf /"},
                    "mutating": False,
                }
            ]
        )
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_argv_token_with_shell_metacharacter(self):
        bad = base_plan_dict(
            phases=[
                {
                    "phase_id": 1,
                    "operation": "validation",
                    "row": "row_a",
                    "harness_id": None,
                    "model": None,
                    "args": {"command": ["pytest", "tests/; rm -rf /"]},
                    "mutating": False,
                }
            ]
        )
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_accepts_argv_list_validation_command(self):
        good = base_plan_dict(
            phases=[
                base_plan_dict()["phases"][0],
                {
                    "phase_id": 2,
                    "operation": "validation",
                    "row": "row_a",
                    "harness_id": None,
                    "model": None,
                    "args": {"command": ["pytest", "-q"]},
                    "mutating": False,
                },
            ]
        )
        plan = sr.parse_plan_object(good)
        self.assertEqual(plan.phases[1]["args"]["command"], ["pytest", "-q"])

    def test_rejects_mutating_mismatch(self):
        bad = base_plan_dict(
            phases=[
                {
                    "phase_id": 1,
                    "operation": "validation",
                    "row": "row_a",
                    "harness_id": None,
                    "model": None,
                    "args": {"command": ["pytest"]},
                    "mutating": True,
                }
            ]
        )
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_row_on_shared_only_operation(self):
        bad = base_plan_dict()
        bad["phases"][0]["row"] = "row_a"
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_missing_row_on_row_required_operation(self):
        bad = base_plan_dict(
            phases=[
                {
                    "phase_id": 1,
                    "operation": "supervisor_design",
                    "row": None,
                    "harness_id": "claude",
                    "model": "m",
                    "args": {"prompt": "design"},
                    "mutating": False,
                }
            ]
        )
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_harness_id_on_non_harness_operation(self):
        bad = base_plan_dict()
        bad["phases"][0]["harness_id"] = "claude"
        bad["phases"][0]["model"] = "m"
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_rejects_relative_workspace_path(self):
        bad = base_plan_dict()
        bad["workspaces"]["row_a"] = "relative/path"
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)

    def test_implementation_requires_allowed_paths(self):
        bad = base_plan_dict(
            phases=[
                {
                    "phase_id": 1,
                    "operation": "implementation",
                    "row": "row_a",
                    "harness_id": "claude",
                    "model": "m",
                    "args": {"prompt": "implement"},
                    "mutating": True,
                }
            ]
        )
        with self.assertRaises(sr.StudyPlanError):
            sr.parse_plan_object(bad)


class TestBlindLabels(unittest.TestCase):
    def test_labels_are_deterministic_for_a_given_digest(self):
        digest = "aa" + "0" * 62
        self.assertEqual(sr.compute_blind_labels(digest), sr.compute_blind_labels(digest))

    def test_labels_are_a_valid_permutation(self):
        for digest in ("00" + "0" * 62, "01" + "0" * 62, "ff" + "0" * 62):
            labels = sr.compute_blind_labels(digest)
            self.assertEqual(set(labels.values()), {"A", "B"})


class StubLedgerOps:
    """A LedgerOps whose four callables just record what they were asked to
    do, for tests that don't need a real .operator ledger."""

    def __init__(self):
        self.calls = []

    def _make(self, name):
        def _fn(ns):
            self.calls.append((name, vars(ns)))
            return 0

        return _fn

    def as_ledger_ops(self) -> sr.LedgerOps:
        return sr.LedgerOps(
            session_start=self._make("session_start"),
            session_end=self._make("session_end"),
            evidence_attach=self._make("evidence_attach"),
            usage_import=self._make("usage_import"),
            claim_add=self._make("claim_add"),
        )


class TestCheckpointAndPlanStore(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.op_dir = self.tmp / ".operator"
        self.op_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_store_and_load_plan_roundtrip(self):
        plan = sr.parse_plan_object(base_plan_dict())
        sr.store_plan(str(self.op_dir), plan)
        loaded = sr.load_stored_plan(str(self.op_dir), plan.plan_digest)
        self.assertEqual(loaded.plan_digest, plan.plan_digest)

    def test_storing_same_digest_twice_is_a_no_op(self):
        plan = sr.parse_plan_object(base_plan_dict())
        sr.store_plan(str(self.op_dir), plan)
        sr.store_plan(str(self.op_dir), plan)  # must not raise

    def test_create_run_and_checkpoint_state_lifecycle(self):
        plan = sr.parse_plan_object(base_plan_dict())
        sr.store_plan(str(self.op_dir), plan)
        run_id = sr.create_run(str(self.op_dir), plan)
        self.assertTrue(sr.RUN_ID_RE.fullmatch(run_id))

        phase = plan.phases[0]
        state, payload = sr.phase_checkpoint_state(str(self.op_dir), run_id, phase)
        self.assertEqual(state, "not_started")

        sr.write_checkpoint(str(self.op_dir), run_id, phase, "pending", {"x": 1})
        state, _ = sr.phase_checkpoint_state(str(self.op_dir), run_id, phase)
        self.assertEqual(state, "pending")

        sr.write_checkpoint(str(self.op_dir), run_id, phase, "completed", {"x": 2})
        state, payload = sr.phase_checkpoint_state(str(self.op_dir), run_id, phase)
        self.assertEqual(state, "completed")
        self.assertEqual(payload["x"], 2)

    def _prepare_workspaces_and_task_bindings(self, plan) -> None:
        import yaml

        for key in sr.WORKSPACE_FIELDS:
            Path(plan.workspaces[key]).mkdir(parents=True, exist_ok=True)
        tasks_dir = self.op_dir / "tasks"
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for row in ("row_a", "row_b"):
            task_id = plan.task_ids[row]
            (tasks_dir / f"{task_id}.yaml").write_text(
                yaml.safe_dump({"task_id": task_id, "repo": plan.workspaces[row]})
            )

    def test_execute_phase_idempotent_replay_on_matching_digest(self):
        plan = sr.parse_plan_object(base_plan_dict())
        run_id = sr.create_run(str(self.op_dir), plan)
        ctx = sr.PhaseContext(str(self.op_dir), run_id, plan, StubLedgerOps().as_ledger_ops())
        phase = plan.phases[0]
        self._prepare_workspaces_and_task_bindings(plan)

        first = sr.execute_phase(ctx, phase, approve_phase=None, acknowledge_quota_reset=False)
        self.assertEqual(first["status"], "completed")
        self.assertFalse(first["idempotent_replay"])

        second = sr.execute_phase(ctx, phase, approve_phase=None, acknowledge_quota_reset=False)
        self.assertEqual(second["status"], "completed")
        self.assertTrue(second["idempotent_replay"])

    def test_execute_phase_rejects_replaced_plan_on_digest_mismatch(self):
        plan = sr.parse_plan_object(base_plan_dict())
        run_id = sr.create_run(str(self.op_dir), plan)
        ctx = sr.PhaseContext(str(self.op_dir), run_id, plan, StubLedgerOps().as_ledger_ops())
        phase = plan.phases[0]
        self._prepare_workspaces_and_task_bindings(plan)

        sr.execute_phase(ctx, phase, approve_phase=None, acknowledge_quota_reset=False)

        tampered_phase = dict(phase)
        tampered_phase["args"] = {"tampered": True}
        with self.assertRaises(sr.StudyError):
            sr.execute_phase(ctx, tampered_phase, approve_phase=None, acknowledge_quota_reset=False)


def init_git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "README.md").write_text("initial\n")
    for git_args in (
        ["init", "-q"],
        ["config", "user.email", "test@example.com"],
        ["config", "user.name", "Test"],
        ["add", "-A"],
        ["commit", "-q", "-m", "initial"],
    ):
        subprocess.run(["git", *git_args], cwd=str(path), check=True, capture_output=True)


# Role-aware fake CLIs: each inspects its own argv for the real role flag
# study_runner/harness_adapter actually injects (--permission-mode acceptEdits
# vs plan, --mode accept-edits vs plan) and only writes a file when invoked
# in the edit-enabled role -- exactly mirroring what a real CLI is expected
# to do, so one fixture script per harness covers both its supervisor and
# implementer phases correctly instead of needing per-phase profile-swapping.
CLAUDE_ROLE_AWARE = """
import sys, json
sys.stdin.read()
if "acceptEdits" in sys.argv:
    import os
    os.makedirs("allowed_dir", exist_ok=True)
    with open("allowed_dir/output.txt", "w") as f:
        f.write("implemented by claude\\n")
    print(json.dumps({"result": "implemented", "session_id": "sess-claude-001"}))
else:
    print(json.dumps({"result": "claude supervisory text", "session_id": "sess-claude-001"}))
"""

AGY_ROLE_AWARE = """
import sys
if "accept-edits" in sys.argv:
    import os
    os.makedirs("allowed_dir", exist_ok=True)
    with open("allowed_dir/output.txt", "w") as f:
        f.write("implemented by agy\\n")
    print("agy implementation done")
else:
    print("agy supervisory text response")
"""

GROK_SUPERVISOR_ECHO = """
import json
print(json.dumps({"result": "grok final verdict text"}))
"""

CODEX_JSONL_JUDGE = """
import json
print(json.dumps({"event": "start"}))
print(json.dumps({"event": "final", "result": "judge verdict text"}))
"""


class OperatorCliIntegrationTestCase(unittest.TestCase):
    """Base class: builds a real .operator ledger (via op_mod, in-process,
    not subprocess -- so fake harness_adapter.PROFILES monkeypatches in this
    test process are visible to the code under test) with row_a/row_b/shared
    workspaces and correctly repo-bound tasks."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ledger_dir = self.tmp / "ledger"
        self.ledger_dir.mkdir()
        self.old_cwd = Path.cwd()
        os.chdir(self.ledger_dir)

        self.row_a_ws = self.tmp / "row-a"
        self.row_b_ws = self.tmp / "row-b"
        self.shared_ws = self.tmp / "shared"
        init_git_repo(self.row_a_ws)
        init_git_repo(self.row_b_ws)
        self.shared_ws.mkdir()

        rc = op_mod.init_cmd(argparse.Namespace())
        self.assertEqual(rc, 0)

        self._create_task("task-row-a", str(self.row_a_ws), assign="gemini-agy", review="claude")
        self._create_task("task-row-b", str(self.row_b_ws), assign="claude", review="gemini-agy")
        self._create_task("task-shared", str(self.shared_ws), assign=None, review=None)

        self._fake_cli_dir = Path(tempfile.mkdtemp())
        self._original_profiles = dict(ha.PROFILES)

    def tearDown(self):
        ha.PROFILES.clear()
        ha.PROFILES.update(self._original_profiles)
        os.chdir(self.old_cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)
        shutil.rmtree(self._fake_cli_dir, ignore_errors=True)

    def _create_task(self, task_id, repo, assign, review):
        rc = op_mod.task_create_cmd(
            argparse.Namespace(
                objective=f"study task {task_id}",
                task_id=task_id,
                repo=repo,
                assign=assign,
                review=review,
                assumptions=[],
            )
        )
        self.assertEqual(rc, 0)

    def fake_profile(self, harness_id: str, script_body: str, **overrides) -> None:
        real = self._original_profiles[harness_id]
        exe = write_fake_cli(self._fake_cli_dir, f"fake-{harness_id}", script_body)
        kwargs = dict(
            harness_id=harness_id,
            executable=exe,
            base_args=real.base_args,
            prompt_transport=real.prompt_transport,
            output_format=real.output_format,
            role_args=real.role_args,
            prompt_file_flag=real.prompt_file_flag,
            prompt_arg_flag=real.prompt_arg_flag,
        )
        kwargs.update(overrides)
        ha.PROFILES[harness_id] = ha.HarnessProfile(**kwargs)

    def op_dir(self) -> str:
        return str(self.ledger_dir / ".operator")

    def build_plan(self) -> dict:
        return {
            "plan_schema_version": 1,
            "created_at": "2026-07-22T00:00:00+00:00",
            "study_id": "FFSI-REHEARSAL",
            "workspaces": {
                "row_a": str(self.row_a_ws),
                "row_b": str(self.row_b_ws),
                "shared": str(self.shared_ws),
            },
            "task_ids": {"row_a": "task-row-a", "row_b": "task-row-b", "shared": "task-shared"},
            "phases": [
                {
                    "phase_id": 1,
                    "operation": "preflight",
                    "row": None,
                    "harness_id": None,
                    "model": None,
                    "args": {},
                    "mutating": False,
                },
                {
                    "phase_id": 2,
                    "operation": "supervisor_design",
                    "row": "row_a",
                    "harness_id": "claude",
                    "model": "test-model",
                    "args": {"prompt": "design row a"},
                    "mutating": False,
                },
                {
                    "phase_id": 3,
                    "operation": "supervisor_design",
                    "row": "row_b",
                    "harness_id": "agy",
                    "model": "test-model",
                    "args": {"prompt": "design row b"},
                    "mutating": False,
                },
                {
                    "phase_id": 4,
                    "operation": "implementation",
                    "row": "row_a",
                    "harness_id": "agy",
                    "model": "test-model",
                    "args": {"prompt": "implement row a", "allowed_paths": ["allowed_dir"]},
                    "mutating": True,
                },
                {
                    "phase_id": 5,
                    "operation": "implementation",
                    "row": "row_b",
                    "harness_id": "claude",
                    "model": "test-model",
                    "args": {"prompt": "implement row b", "allowed_paths": ["allowed_dir"]},
                    "mutating": True,
                },
                {
                    "phase_id": 6,
                    "operation": "validation",
                    "row": "row_a",
                    "harness_id": None,
                    "model": None,
                    "args": {"command": ["python3", "-c", "print('row a validators pass')"]},
                    "mutating": False,
                },
                {
                    "phase_id": 7,
                    "operation": "validation",
                    "row": "row_b",
                    "harness_id": None,
                    "model": None,
                    "args": {"command": ["python3", "-c", "print('row b validators pass')"]},
                    "mutating": False,
                },
                {
                    "phase_id": 8,
                    "operation": "supervisor_review",
                    "row": "row_a",
                    "harness_id": "claude",
                    "model": "test-model",
                    "args": {"prompt": "review row a"},
                    "mutating": False,
                },
                {
                    "phase_id": 9,
                    "operation": "supervisor_review",
                    "row": "row_b",
                    "harness_id": "agy",
                    "model": "test-model",
                    "args": {"prompt": "review row b"},
                    "mutating": False,
                },
                {
                    "phase_id": 10,
                    "operation": "repair",
                    "row": "row_a",
                    "harness_id": "agy",
                    "model": "test-model",
                    "args": {"prompt": "repair row a", "allowed_paths": ["allowed_dir"]},
                    "mutating": True,
                },
                {
                    "phase_id": 11,
                    "operation": "final_verdict",
                    "row": "row_a",
                    "harness_id": "claude",
                    "model": "test-model",
                    "args": {"prompt": "final verdict row a"},
                    "mutating": False,
                },
                {
                    "phase_id": 12,
                    "operation": "final_verdict",
                    "row": "row_b",
                    "harness_id": "grok",
                    "model": "test-model",
                    "args": {"prompt": "final verdict row b"},
                    "mutating": False,
                },
                {
                    "phase_id": 13,
                    "operation": "blinding",
                    "row": None,
                    "harness_id": None,
                    "model": None,
                    "args": {},
                    "mutating": False,
                },
                {
                    "phase_id": 14,
                    "operation": "judge",
                    "row": None,
                    "harness_id": "codex",
                    "model": "test-model",
                    "args": {"prompt": "judge both rows"},
                    "mutating": False,
                },
                {
                    "phase_id": 15,
                    "operation": "export",
                    "row": None,
                    "harness_id": None,
                    "model": None,
                    "args": {},
                    "mutating": False,
                },
            ],
        }


class TestFullTwoRowRehearsal(OperatorCliIntegrationTestCase):
    def test_full_rehearsal_through_blinding_and_export(self):
        self.fake_profile("claude", CLAUDE_ROLE_AWARE)
        self.fake_profile("agy", AGY_ROLE_AWARE)
        self.fake_profile("grok", GROK_SUPERVISOR_ECHO)
        self.fake_profile("codex", CODEX_JSONL_JUDGE, output_format="jsonl")

        plan_dict = self.build_plan()
        plan_path = self.tmp / "plan.json"
        plan_path.write_text(json.dumps(plan_dict))

        rc = op_mod.study_plan_cmd(argparse.Namespace(plan=str(plan_path)))
        self.assertEqual(rc, 0)

        plan = sr.parse_plan_object(plan_dict)
        digest = plan.plan_digest

        # First call: creates the run, executes preflight + both
        # supervisor_design phases (2, 3), then halts before implementation
        # (phase 4) since mutating phases need separate approval.
        rc = op_mod.study_run_cmd(
            argparse.Namespace(plan_digest=digest, run_id=None, approve_phase=None)
        )
        self.assertEqual(rc, 1)  # not "completed" yet

        runs = list((self.ledger_dir / ".operator" / "studies" / "runs").iterdir())
        self.assertEqual(len(runs), 1)
        run_id = runs[0].name

        status = sr.compute_run_status(self.op_dir(), run_id)
        self.assertEqual(status["status"], "awaiting_approval")
        self.assertEqual(
            [p["state"] for p in status["phases"][:3]], ["completed", "completed", "completed"]
        )

        # Approving the wrong phase_id must not advance phase 4.
        rc = op_mod.study_resume_cmd(
            argparse.Namespace(run_id=run_id, approve_phase=999, acknowledge_quota_reset=False)
        )
        self.assertEqual(rc, 1)
        status = sr.compute_run_status(self.op_dir(), run_id)
        self.assertEqual(status["phases"][3]["state"], "not_started")

        # Approve phase 4 (row_a implementation) specifically.
        rc = op_mod.study_resume_cmd(
            argparse.Namespace(run_id=run_id, approve_phase=4, acknowledge_quota_reset=False)
        )
        self.assertEqual(rc, 1)  # halts again before phase 5 (also mutating)
        status = sr.compute_run_status(self.op_dir(), run_id)
        self.assertEqual(status["phases"][3]["state"], "completed")
        self.assertEqual(status["phases"][4]["state"], "not_started")
        self.assertTrue((self.row_a_ws / "allowed_dir" / "output.txt").exists())

        # Approve phase 5 (row_b implementation) -- runs 6, 7, 8, 9, then
        # halts before phase 10 (repair, also mutating).
        rc = op_mod.study_resume_cmd(
            argparse.Namespace(run_id=run_id, approve_phase=5, acknowledge_quota_reset=False)
        )
        self.assertEqual(rc, 1)
        status = sr.compute_run_status(self.op_dir(), run_id)
        for i in (4, 5, 6, 7, 8):
            self.assertEqual(status["phases"][i]["state"], "completed", status["phases"][i])
        self.assertEqual(status["phases"][9]["state"], "not_started")

        # Approve phase 10 (repair) -- runs through to completion (11-15).
        rc = op_mod.study_resume_cmd(
            argparse.Namespace(run_id=run_id, approve_phase=10, acknowledge_quota_reset=False)
        )
        self.assertEqual(rc, 0)
        status = sr.compute_run_status(self.op_dir(), run_id)
        self.assertEqual(status["status"], "completed")
        self.assertTrue(all(p["state"] == "completed" for p in status["phases"]))

        # Re-running is a clean idempotent replay of every phase.
        rc = op_mod.study_resume_cmd(
            argparse.Namespace(run_id=run_id, approve_phase=None, acknowledge_quota_reset=False)
        )
        self.assertEqual(rc, 0)

        # Evidence and claims actually landed in the ledger.
        evidence_dir_a = self.ledger_dir / ".operator" / "evidence" / "task-row-a"
        self.assertTrue(evidence_dir_a.exists())
        self.assertTrue(any(evidence_dir_a.iterdir()))

        claims_dir = self.ledger_dir / ".operator" / "claims"
        supervision_claims = [
            c for c in claims_dir.glob("claim-*.yaml") if "supervision_credit" in c.read_text()
        ]
        self.assertGreaterEqual(len(supervision_claims), 4)  # 2 designs + 2 reviews at minimum


class TestIntegrityViolationDetection(OperatorCliIntegrationTestCase):
    def _single_phase_plan(self, phase: dict) -> dict:
        return {
            "plan_schema_version": 1,
            "created_at": "2026-07-22T00:00:00+00:00",
            "study_id": "FFSI-VIOLATION",
            "workspaces": {
                "row_a": str(self.row_a_ws),
                "row_b": str(self.row_b_ws),
                "shared": str(self.shared_ws),
            },
            "task_ids": {"row_a": "task-row-a", "row_b": "task-row-b", "shared": "task-shared"},
            "phases": [
                {
                    "phase_id": 1,
                    "operation": "preflight",
                    "row": None,
                    "harness_id": None,
                    "model": None,
                    "args": {},
                    "mutating": False,
                },
                phase,
            ],
        }

    def _run_to_completion_or_failure(self, plan_dict: dict, approve_phase=None):
        plan_path = self.tmp / "plan.json"
        plan_path.write_text(json.dumps(plan_dict))
        op_mod.study_plan_cmd(argparse.Namespace(plan=str(plan_path)))
        plan = sr.parse_plan_object(plan_dict)
        op_mod.study_run_cmd(
            argparse.Namespace(plan_digest=plan.plan_digest, run_id=None, approve_phase=None)
        )
        runs = list((self.ledger_dir / ".operator" / "studies" / "runs").iterdir())
        run_id = runs[0].name
        if approve_phase is not None:
            op_mod.study_resume_cmd(
                argparse.Namespace(
                    run_id=run_id, approve_phase=approve_phase, acknowledge_quota_reset=False
                )
            )
        status = sr.compute_run_status(self.op_dir(), run_id)
        return run_id, status

    def test_implementer_writing_outside_allowed_paths_is_a_failed_checkpoint(self):
        write_fake_cli(
            self._fake_cli_dir,
            "fake-out-of-scope",
            """
            with open("outside_scope.txt", "w") as f:
                f.write("oops\\n")
            print('{"result": "wrote outside declared scope"}')
            """,
        )
        exe = str(self._fake_cli_dir / "fake-out-of-scope")
        real = self._original_profiles["claude"]
        ha.PROFILES["claude"] = ha.HarnessProfile(
            harness_id="claude",
            executable=exe,
            base_args=real.base_args,
            prompt_transport=ha.PromptTransport.STDIN,
            output_format="json",
            role_args=real.role_args,
        )
        plan_dict = self._single_phase_plan(
            {
                "phase_id": 2,
                "operation": "implementation",
                "row": "row_a",
                "harness_id": "claude",
                "model": "test-model",
                "args": {"prompt": "implement", "allowed_paths": ["allowed_dir"]},
                "mutating": True,
            }
        )
        run_id, status = self._run_to_completion_or_failure(plan_dict, approve_phase=2)
        self.assertEqual(status["phases"][1]["state"], "failed")

    def test_supervisor_phase_filesystem_change_invalidates_row(self):
        write_fake_cli(
            self._fake_cli_dir,
            "fake-sneaky-supervisor",
            """
            with open("sneaky.txt", "w") as f:
                f.write("a supervisor should never write this\\n")
            print('{"result": "looked read-only, was not"}')
            """,
        )
        exe = str(self._fake_cli_dir / "fake-sneaky-supervisor")
        real = self._original_profiles["claude"]
        ha.PROFILES["claude"] = ha.HarnessProfile(
            harness_id="claude",
            executable=exe,
            base_args=real.base_args,
            prompt_transport=ha.PromptTransport.STDIN,
            output_format="json",
            role_args=real.role_args,
        )
        plan_dict = self._single_phase_plan(
            {
                "phase_id": 2,
                "operation": "supervisor_design",
                "row": "row_a",
                "harness_id": "claude",
                "model": "test-model",
                "args": {"prompt": "design"},
                "mutating": False,
            }
        )
        run_id, status = self._run_to_completion_or_failure(plan_dict)
        self.assertEqual(status["phases"][1]["state"], "failed")


class TestQuotaExhaustion(OperatorCliIntegrationTestCase):
    def test_quota_exhaustion_pauses_without_failure_and_resumes_after_acknowledgement(self):
        marker = self._fake_cli_dir / "quota_cleared"
        write_fake_cli(
            self._fake_cli_dir,
            "fake-quota-then-ok",
            f"""
            import sys, json, os
            if "--version" in sys.argv:
                print("1.0.0-fake")
                sys.exit(0)
            sys.stdin.read()
            if os.path.exists({str(marker)!r}):
                print(json.dumps({{"result": "ok now", "session_id": "sess-001"}}))
            else:
                sys.stderr.write("Error: rate limit exceeded\\n")
                sys.exit(1)
            """,
        )
        exe = str(self._fake_cli_dir / "fake-quota-then-ok")
        real = self._original_profiles["claude"]
        ha.PROFILES["claude"] = ha.HarnessProfile(
            harness_id="claude",
            executable=exe,
            base_args=real.base_args,
            prompt_transport=ha.PromptTransport.STDIN,
            output_format="json",
            role_args=real.role_args,
        )
        plan_dict = {
            "plan_schema_version": 1,
            "created_at": "2026-07-22T00:00:00+00:00",
            "study_id": "FFSI-QUOTA",
            "workspaces": {
                "row_a": str(self.row_a_ws),
                "row_b": str(self.row_b_ws),
                "shared": str(self.shared_ws),
            },
            "task_ids": {"row_a": "task-row-a", "row_b": "task-row-b", "shared": "task-shared"},
            "phases": [
                {
                    "phase_id": 1,
                    "operation": "preflight",
                    "row": None,
                    "harness_id": None,
                    "model": None,
                    "args": {},
                    "mutating": False,
                },
                {
                    "phase_id": 2,
                    "operation": "supervisor_design",
                    "row": "row_a",
                    "harness_id": "claude",
                    "model": "test-model",
                    "args": {"prompt": "design"},
                    "mutating": False,
                },
            ],
        }
        plan_path = self.tmp / "plan.json"
        plan_path.write_text(json.dumps(plan_dict))
        op_mod.study_plan_cmd(argparse.Namespace(plan=str(plan_path)))
        plan = sr.parse_plan_object(plan_dict)

        op_mod.study_run_cmd(
            argparse.Namespace(plan_digest=plan.plan_digest, run_id=None, approve_phase=None)
        )
        run_id = list((self.ledger_dir / ".operator" / "studies" / "runs").iterdir())[0].name
        status = sr.compute_run_status(self.op_dir(), run_id)
        self.assertEqual(status["phases"][1]["state"], "waiting_quota")

        # Resuming without acknowledgement stays paused, does not retry.
        rc = op_mod.study_resume_cmd(
            argparse.Namespace(run_id=run_id, approve_phase=None, acknowledge_quota_reset=False)
        )
        self.assertEqual(rc, 1)
        status = sr.compute_run_status(self.op_dir(), run_id)
        self.assertEqual(status["phases"][1]["state"], "waiting_quota")

        # No claim should have been recorded for the still-pending phase.
        claims_dir = self.ledger_dir / ".operator" / "claims"
        self.assertEqual(len(list(claims_dir.glob("claim-*.yaml"))), 0)

        # "Tokens reset": acknowledging retries, and now it succeeds.
        marker.write_text("ready")
        rc = op_mod.study_resume_cmd(
            argparse.Namespace(run_id=run_id, approve_phase=None, acknowledge_quota_reset=True)
        )
        self.assertEqual(rc, 0)
        status = sr.compute_run_status(self.op_dir(), run_id)
        self.assertEqual(status["status"], "completed")


if __name__ == "__main__":
    unittest.main()
