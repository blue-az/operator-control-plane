#!/usr/bin/env python3
"""Postcondition suite for gated_runner.py (task `gated-runner-p0`).

This file is the gate. It is author-pinned per GATED_RUNNER_SPEC.md section 3
and was written before the implementation; the implementing agent may not edit
it. Every assertion here is a structural property of the enforcing runner, not
a style preference.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import gated_runner  # noqa: E402


def write_cell(root: Path, **overrides) -> Path:
    cell = {
        "cell_id": "audio-default-sink",
        "objective": "Point the default sink at the HDMI stereo device.",
        "brief": "Step 1: run `true`.\nPostcondition: `echo ok` outputs ok",
        "workspace": str(root),
        "gate": {"command": ["echo", "ok"], "expect": "ok"},
    }
    cell.update(overrides)
    path = root / "cell.json"
    path.write_text(json.dumps(cell))
    return path


class LoadCellTests(unittest.TestCase):
    def test_loads_a_well_formed_cell(self):
        with tempfile.TemporaryDirectory() as tmp:
            cell = gated_runner.load_cell(write_cell(Path(tmp)))
            self.assertEqual(cell.cell_id, "audio-default-sink")
            self.assertEqual(cell.gate.command, ["echo", "ok"])
            self.assertEqual(cell.gate.expect, "ok")

    def test_missing_gate_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_cell(Path(tmp))
            data = json.loads(path.read_text())
            del data["gate"]
            path.write_text(json.dumps(data))
            with self.assertRaises(gated_runner.CellError):
                gated_runner.load_cell(path)

    def test_gate_command_must_be_exec_form_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_cell(Path(tmp), gate={"command": "echo ok", "expect": "ok"})
            with self.assertRaises(gated_runner.CellError):
                gated_runner.load_cell(path)

    def test_empty_gate_command_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_cell(Path(tmp), gate={"command": [], "expect": "ok"})
            with self.assertRaises(gated_runner.CellError):
                gated_runner.load_cell(path)

    def test_mutating_gate_command_rejected(self):
        """A gate that repairs state cannot detect whether the agent did."""
        for argv in (
            ["pactl", "set-default-sink", "foo"],
            ["rm", "-rf", "/tmp/x"],
            ["systemctl", "restart", "pipewire"],
        ):
            with tempfile.TemporaryDirectory() as tmp:
                path = write_cell(Path(tmp), gate={"command": argv, "expect": "ok"})
                with self.assertRaises(gated_runner.CellError):
                    gated_runner.load_cell(path)

    def test_read_only_gate_command_accepted(self):
        for argv in (
            ["pactl", "get-default-sink"],
            ["cat", "/etc/hostname"],
        ):
            with tempfile.TemporaryDirectory() as tmp:
                path = write_cell(Path(tmp), gate={"command": argv, "expect": "ok"})
                cell = gated_runner.load_cell(path)
                self.assertEqual(cell.gate.command, argv)


class ProbeTests(unittest.TestCase):
    def test_probe_captures_stdout_and_rc(self):
        gate = gated_runner.Gate(command=["echo", "hello"], expect="hello")
        probe = gated_runner.probe(gate)
        self.assertEqual(probe.stdout.strip(), "hello")
        self.assertEqual(probe.returncode, 0)

    def test_probe_records_failure_without_raising(self):
        gate = gated_runner.Gate(command=["false"], expect="")
        probe = gated_runner.probe(gate)
        self.assertNotEqual(probe.returncode, 0)


class EvaluateTests(unittest.TestCase):
    """evaluate() must not accept the agent transcript. See spec section 3."""

    def test_evaluate_signature_excludes_agent_output(self):
        import inspect

        params = set(inspect.signature(gated_runner.evaluate).parameters)
        for forbidden in ("transcript", "agent_output", "stdout_of_agent", "report"):
            self.assertNotIn(forbidden, params)

    def _probe(self, stdout, rc=0):
        return gated_runner.GateProbe(stdout=stdout, stderr="", returncode=rc)

    def test_pass_when_pre_unsatisfied_and_post_satisfied(self):
        gate = gated_runner.Gate(command=["echo", "ok"], expect="ok")
        verdict = gated_runner.evaluate(self._probe("nope"), self._probe("ok"), gate)
        self.assertEqual(verdict.status, "pass")

    def test_fail_when_post_unsatisfied(self):
        gate = gated_runner.Gate(command=["echo", "ok"], expect="ok")
        verdict = gated_runner.evaluate(self._probe("nope"), self._probe("still nope"), gate)
        self.assertEqual(verdict.status, "fail")

    def test_vacuous_when_pre_already_satisfied(self):
        gate = gated_runner.Gate(command=["echo", "ok"], expect="ok")
        verdict = gated_runner.evaluate(self._probe("ok"), self._probe("ok"), gate)
        self.assertEqual(verdict.status, "vacuous")

    def test_error_when_gate_command_fails_to_run(self):
        gate = gated_runner.Gate(command=["echo", "ok"], expect="ok")
        verdict = gated_runner.evaluate(self._probe("nope"), self._probe("", rc=127), gate)
        self.assertEqual(verdict.status, "error")

    def test_comparison_is_whitespace_insensitive_at_the_edges(self):
        gate = gated_runner.Gate(command=["echo", "ok"], expect="ok")
        verdict = gated_runner.evaluate(self._probe("nope"), self._probe("  ok\n"), gate)
        self.assertEqual(verdict.status, "pass")


class LedgerArgumentTests(unittest.TestCase):
    """The wrapper records; the agent never does."""

    def test_verified_status_for_pass(self):
        verdict = gated_runner.Verdict(status="pass", detail="")
        args = gated_runner.evidence_args(verdict)
        self.assertIn("--status", args)
        self.assertEqual(args[args.index("--status") + 1], "verified")

    def test_false_status_for_fail(self):
        verdict = gated_runner.Verdict(status="fail", detail="")
        args = gated_runner.evidence_args(verdict)
        self.assertEqual(args[args.index("--status") + 1], "false")

    def test_vacuous_is_not_recorded_as_verified(self):
        verdict = gated_runner.Verdict(status="vacuous", detail="")
        args = gated_runner.evidence_args(verdict)
        self.assertNotEqual(args[args.index("--status") + 1], "verified")


if __name__ == "__main__":
    unittest.main()
