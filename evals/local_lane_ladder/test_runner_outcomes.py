"""Cell outcomes: a failing cell is not a model result until the proofs pass.

Each case here is a real incident from the September corpus, not a hypothetical.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import runner


def _proofs(**over):
    base = dict(
        returncode=0, stdout='{"ok": true}', trajectory={"no_dispatch": False},
        placement_verified=True, timed_out=False, grader_boundary_tested=True,
    )
    base.update(over)
    return base


class CellOutcomeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def report(self, **over):
        return runner.evaluate_proofs(fixture_root=self.fixture, **_proofs(**over))

    def test_clean_failure_is_a_model_result(self):
        report = self.report()
        self.assertEqual(report["missing"], [])
        self.assertEqual(runner.classify_outcome(False, report), "fail")
        self.assertEqual(runner.classify_outcome(True, report), "pass")

    def test_carrier_pollution_is_unproven_not_a_failure(self):
        """Incident 0155Z: 18 cells, returncode 0, no timeouts -- all carrier violations."""
        (self.fixture / ".pi-agent").mkdir()
        report = self.report()
        self.assertIn("scope", report["missing"])
        self.assertEqual(report["scope_violations"], [".pi-agent"])
        self.assertEqual(runner.classify_outcome(False, report), "unproven")

    def test_no_dispatch_is_unproven(self):
        """Native 0638Z: a dangling pi symlink, every cell with no tokens or calls."""
        report = self.report(trajectory={"no_dispatch": True})
        self.assertIn("dispatch", report["missing"])
        self.assertEqual(runner.classify_outcome(False, report), "unproven")

    def test_empty_output_and_nonzero_returncode_are_unproven(self):
        self.assertIn("dispatch", self.report(stdout="   ")["missing"])
        self.assertIn("dispatch", self.report(returncode=1)["missing"])

    def test_unverified_placement_is_unproven(self):
        """The published native L2 rows ran with require_gpu_residency False."""
        report = self.report(placement_verified=False)
        self.assertIn("placement", report["missing"])
        self.assertEqual(runner.classify_outcome(False, report), "unproven")

    def test_untested_grader_is_unproven(self):
        """Fusion L3 v2: 17 apparent failures were all grader false negatives."""
        report = self.report(grader_boundary_tested=False)
        self.assertIn("grader", report["missing"])
        self.assertEqual(runner.classify_outcome(False, report), "unproven")

    def test_a_pass_is_never_demoted(self):
        """Adding a gate must not invalidate the corpus wholesale."""
        (self.fixture / ".tmp").mkdir()
        report = self.report(placement_verified=False, grader_boundary_tested=False)
        self.assertTrue(report["missing"])
        self.assertEqual(runner.classify_outcome(True, report), "pass")


class CellSummaryTests(unittest.TestCase):
    def test_clean_cell_reads_as_before(self):
        cell = [{"passed": True, "outcome": "pass"}] * 6
        self.assertEqual(runner.cell_summary(cell), "6/6")

    def test_unproven_cells_are_named_and_stay_in_the_denominator(self):
        cell = [{"passed": True, "outcome": "pass"}] * 4 + [
            {"passed": False, "outcome": "unproven"},
            {"passed": False, "outcome": "fail"},
        ]
        self.assertEqual(runner.cell_summary(cell), "4/6 (1 unproven)")

    def test_empty_cell(self):
        self.assertEqual(runner.cell_summary([]), "—")




class PlacementProfileTests(unittest.TestCase):
    """ollama ps is corroboration; attributed card count is the proof.

    Testbench runs two daemons and the gpu1 one pins a model with
    OLLAMA_KEEP_ALIVE=8760h, so device totals are never a clean signal.
    """

    def _fake_run(self, *, listeners="", children="", gpus=((0, "GPU-aaa"), (1, "GPU-bbb")),
                  apps=(), blob_mib=None):
        def run(argv, **kwargs):
            class _R:
                stdout = ""
            text = ""
            if argv[0] == "ss":
                text = listeners
            elif argv[0] == "pgrep":
                text = children
            elif "--query-gpu=index,uuid" in argv:
                text = "\n".join(f"{i}, {u}" for i, u in gpus)
            elif "--query-compute-apps=gpu_uuid,pid,used_gpu_memory" in argv:
                text = "\n".join(f"{u}, {p}, {m}" for u, p, m in apps)
            elif argv[0] == "curl" and blob_mib is not None:
                import json as _json
                text = _json.dumps({"models": [{"name": "m", "size": blob_mib * 2 ** 20}]})
            _R.stdout = text
            return _R()
        return run

    def test_single_card_on_expected_device_passes(self):
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))',
                             apps=[("GPU-aaa", 100, 7400)])
        ev = runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                     run=run, endpoint="http://127.0.0.1:11436")
        self.assertTrue(ev["proved"])
        self.assertEqual(ev["attributed_mib_by_device"], {0: 7400})

    def test_another_daemons_resident_model_is_ignored(self):
        """gpu1's permanently resident model must not fail this run's placement proof."""
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))',
                             apps=[("GPU-aaa", 100, 7400), ("GPU-bbb", 999, 22000)])
        ev = runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                     run=run, endpoint="http://127.0.0.1:11436")
        self.assertEqual(ev["attributed_mib_by_device"], {0: 7400})

    def test_our_own_daemon_spread_over_both_cards_fails_closed(self):
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))', children="101",
                             apps=[("GPU-aaa", 101, 7400), ("GPU-bbb", 101, 6800)])
        with self.assertRaises(runner.GPUResidencyError) as cm:
            runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                    run=run, endpoint="http://127.0.0.1:11436")
        self.assertIn("spread over devices", str(cm.exception))

    def test_a_mostly_cpu_resident_model_fails_even_on_the_right_card(self):
        """2026-09-22: 4,468 MiB of a 17,742 MiB blob, and ollama ps said 100%."""
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))',
                             apps=[("GPU-aaa", 100, 4468)], blob_mib=17742)
        with self.assertRaises(runner.GPUResidencyError) as cm:
            runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                    run=run, endpoint="http://127.0.0.1:11436",
                                    ps_row={"size": 748 * 2**20, "size_vram": 748 * 2**20})
        self.assertIn("of a 17742 MiB model", str(cm.exception))

    def test_a_fully_resident_model_passes_and_records_its_share(self):
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))',
                             apps=[("GPU-aaa", 100, 22438)], blob_mib=17742)
        ev = runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                     run=run, endpoint="http://127.0.0.1:11436")
        self.assertEqual(ev["blob_mib"], 17742)
        self.assertGreater(ev["resident_share"], 1.0)

    def test_the_ps_ratio_can_no_longer_gate_anything(self):
        """It passed a 25%-resident model; it is recorded, not trusted."""
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))',
                             apps=[("GPU-aaa", 100, 22438)], blob_mib=17742)
        ev = runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                     run=run, endpoint="http://127.0.0.1:11436",
                                     ps_row={"size": 100, "size_vram": 1})
        self.assertEqual(ev["reported_ratio"], 0.01)
        self.assertTrue(ev["proved"])

    def test_wrong_card_fails(self):
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))',
                             apps=[("GPU-bbb", 100, 7400)])
        with self.assertRaises(runner.GPUResidencyError):
            runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                    run=run, endpoint="http://127.0.0.1:11436")

    def test_no_daemon_found_is_not_silently_passed(self):
        run = self._fake_run(listeners="", apps=[("GPU-aaa", 100, 7400)])
        with self.assertRaises(runner.GPUResidencyError) as cm:
            runner.verify_placement("m", profile="cuda-single-device", run=run,
                                    endpoint="http://127.0.0.1:11436")
        self.assertIn("no daemon process", str(cm.exception))

    def test_child_llama_server_allocation_is_attributed_to_us(self):
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))', children="101\n102",
                             apps=[("GPU-aaa", 102, 7400)])
        ev = runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                     run=run, endpoint="http://127.0.0.1:11436")
        self.assertIn(102, ev["daemon_pids"])

    def test_reported_ratio_is_only_corroboration(self):
        run = self._fake_run(listeners='users:(("ollama",pid=100,fd=3))',
                             apps=[("GPU-aaa", 100, 7400)])
        ev = runner.verify_placement("m", profile="cuda-single-device", expected_device=0,
                                     run=run, endpoint="http://127.0.0.1:11436",
                                     ps_row={"size": 100, "size_vram": 100})
        self.assertTrue(ev["reported_ratio_is_corroboration_only"])

    def test_unified_memory_does_not_ask_the_vram_question(self):
        ev = runner.verify_placement("m", profile="unified-memory",
                                     endpoint="http://127.0.0.1:11434",
                                     ps_row={"size": 17_000_000_000})
        self.assertEqual(ev["vram_residency"], "not_applicable_unified_memory")

    def test_unified_memory_rejects_a_tunnelled_endpoint(self):
        with self.assertRaises(runner.GPUResidencyError):
            runner.verify_placement("m", profile="unified-memory",
                                    endpoint="http://testbench:11434", ps_row={"size": 1})


class FailureClassTests(unittest.TestCase):
    """Real details from the September gemma runs."""

    def test_out_of_scope_test_files_are_their_own_class(self):
        self.assertEqual(
            runner.classify_failure(
                "1/2 checks failed: tests not edited: created out of scope: "
                "['test_tmp.py', 'test_tmp_v2.py']"),
            "out_of_scope")

    def test_context_truncation_is_not_a_capability_miss(self):
        """qwen3.8 L2 t2, 2026-09-22: cut off at 16,383 of 16,384 tokens."""
        detail = ("1/3 checks failed: battery passes: postcondition command exited 1: "
                  "AssertionError: got []")
        self.assertEqual(
            runner.classify_failure(detail, {"stopped_length": True}), "truncated")
        # same detail, turn completed -> a real capability miss
        self.assertEqual(
            runner.classify_failure(detail, {"stopped_length": False}), "capability")

    def test_truncation_is_detected_from_the_event_stream(self):
        self.assertTrue(runner.parse_trajectory('{"stopReason":"length"}')["stopped_length"])
        self.assertTrue(runner.parse_trajectory('{"rawStopReason":"length"}')["stopped_length"])
        self.assertFalse(runner.parse_trajectory('{"stopReason":"end_turn"}')["stopped_length"])

    def test_summary_names_truncation(self):
        cell = [{"passed": True, "outcome": "pass"}] * 17 + [
            {"passed": False, "outcome": "fail", "failure_class": "truncated"}]
        self.assertEqual(runner.cell_summary(cell), "17/18 (1 truncated)")

    def test_battery_failure_is_capability(self):
        self.assertEqual(
            runner.classify_failure(
                "1/2 checks failed: battery passes: postcondition command exited 1"),
            "capability")

    def test_other_checks_are_not_miscounted(self):
        self.assertEqual(
            runner.classify_failure("2/4 checks failed: staging line changed: regex did not match"),
            "other_check")
        self.assertIsNone(runner.classify_failure(None))

    def test_summary_names_out_of_scope_separately(self):
        cell = [{"passed": True, "outcome": "pass"}] * 16 + [
            {"passed": False, "outcome": "fail", "failure_class": "out_of_scope"},
            {"passed": False, "outcome": "fail", "failure_class": "capability"},
        ]
        self.assertEqual(runner.cell_summary(cell), "16/18 (1 out-of-scope)")

    def test_summary_reports_both_kinds_of_note(self):
        cell = [{"passed": True, "outcome": "pass"}] * 4 + [
            {"passed": False, "outcome": "unproven", "unproven_reasons": ["scope"]},
            {"passed": False, "outcome": "fail", "failure_class": "out_of_scope"},
        ]
        self.assertEqual(runner.cell_summary(cell), "4/6 (1 unproven, 1 out-of-scope)")


class ProvenanceTests(unittest.TestCase):
    def test_a_dirty_tree_is_named_in_the_stamp(self):
        """A bare sha names code that is not what ran when the tree is dirty."""
        runner._GIT_REV = None
        rev = runner._git_rev()
        self.addCleanup(lambda: setattr(runner, "_GIT_REV", None))
        self.assertTrue(rev)
        # This repo's ladder is dirty today; if it is ever clean the stamp is a
        # bare sha, which is equally correct. Both shapes are acceptable, a
        # silent sha over a dirty tree is not.
        if rev != "unknown":
            import subprocess
            out = subprocess.run(
                ["git", "status", "--porcelain", "--", "evals/local_lane_ladder"],
                cwd=runner.REPO_ROOT, capture_output=True, text=True, check=False,
            ).stdout
            tracked = [l for l in out.splitlines() if l.strip() and not l.startswith("??")]
            self.assertEqual(bool(tracked), "dirty" in rev)


class NoGitProvenanceTests(unittest.TestCase):
    def test_a_loose_copy_still_identifies_itself(self):
        """Host packages are not checkouts; "unknown" is not a stamp."""
        import hashlib, pathlib
        runner._GIT_REV = None
        self.addCleanup(lambda: setattr(runner, "_GIT_REV", None))
        real = runner.REPO_ROOT
        runner.REPO_ROOT = pathlib.Path("/nonexistent-not-a-repo")
        try:
            rev = runner._git_rev()
        finally:
            runner.REPO_ROOT = real
        self.assertTrue(rev.startswith("no-git:runner.py sha256:"), rev)
        digest = hashlib.sha256(pathlib.Path(runner.__file__).read_bytes()).hexdigest()[:16]
        self.assertIn(digest, rev)


class TraceContentTests(unittest.TestCase):
    def test_trace_carries_the_verdict_and_its_proofs(self):
        """A forensic reads the trace; passed=false alone is the old ambiguity."""
        import inspect
        src = inspect.getsource(runner.write_trace)
        for field in ("outcome", "proofs", "unproven_reasons", "placement_evidence"):
            self.assertIn(f'"{field}": record.get("{field}")', src)


if __name__ == "__main__":
    unittest.main()


class HollowGraderCheckTests(unittest.TestCase):
    """A graded check that fails having observed nothing is an untrusted grader.

    Fusion L3 v2 produced 17 such false negatives; the staged control's scope
    check failed an untouched fixture; PAI's scope axis failed six cells with
    every evidence list empty. In each the check reported a violation it could
    not name.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.fixture = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _report(self, checks):
        return runner.evaluate_proofs(
            returncode=0, stdout='{"ok": true}', trajectory={"no_dispatch": False},
            fixture_root=self.fixture, placement_verified=True, timed_out=False,
            grader_boundary_tested=True, grade_checks=checks,
        )

    def test_hollow_failing_check_makes_the_grader_untrusted(self):
        report = self._report([
            {"name": "scope respected", "passed": False, "detail": "", "hits": []},
        ])
        self.assertIn("grader", report["missing"])
        self.assertIn("scope respected", report["hollow_checks"])

    def test_a_check_that_names_its_violation_is_trusted(self):
        report = self._report([
            {"name": "tests not edited", "passed": False,
             "detail": "modified out of scope", "modified": ["tests/check.py"]},
        ])
        self.assertNotIn("grader", report["missing"])

    def test_passing_checks_never_make_the_grader_untrusted(self):
        report = self._report([{"name": "battery passes", "passed": True, "hits": []}])
        self.assertNotIn("grader", report["missing"])

    def test_a_hollow_check_turns_a_fail_into_unproven(self):
        report = self._report([
            {"name": "staging line changed", "passed": False, "detail": "", "hits": []},
        ])
        self.assertEqual(runner.classify_outcome(False, report), "unproven")


class UnifiedMemoryWarmupTests(unittest.TestCase):
    """The unified-memory proof reads /api/ps, which is empty on a cold daemon.

    Without a warm-up the first cell aborts on "no loaded model reported by the
    local daemon" -- a placement check that never had a chance to run, which is
    an instrument failure dressed as a placement failure.
    """

    def test_unified_memory_needs_a_ps_row(self):
        with self.assertRaises(runner.GPUResidencyError) as cm:
            runner.verify_placement("m", profile="unified-memory",
                                    endpoint="http://127.0.0.1:11434", ps_row=None)
        self.assertIn("no loaded model", str(cm.exception))

    def test_a_warmed_row_proves_placement(self):
        ev = runner.verify_placement("m", profile="unified-memory",
                                     endpoint="http://127.0.0.1:11434",
                                     ps_row={"size": 17_000_000_000})
        self.assertTrue(ev["proved"])
        self.assertEqual(ev["vram_residency"], "not_applicable_unified_memory")

    def test_run_trial_warms_before_asking(self):
        import inspect
        src = inspect.getsource(runner.run_trial)
        i_warm = src.index("/api/generate")
        i_verify = src.index('verify_placement(\n            dispatch_model, profile=profile, ps_row=ps_row)')
        self.assertLess(i_warm, i_verify, "warm-up must precede the placement check")
