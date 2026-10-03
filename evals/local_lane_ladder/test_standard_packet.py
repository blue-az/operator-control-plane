from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runner
from run_standard_packet import LEVELS, TASKS, qualified_outcome, summarize


class StandardPacketTest(unittest.TestCase):
    def setUp(self):
        self.raw = {"passed": True, "level": "L0", "wall_clock_s": 2.0,
                    "proofs": {"dispatch": True, "scope": True, "grader": True,
                               "timing": True, "placement": False}}
        self.gate = {"passed": True, "remote": {"listener_pid": 123}}
        self.requests = [{"passed": True}]

    def test_pre_post_proof_qualifies_without_changing_legacy_record(self):
        before = copy.deepcopy(self.raw)
        self.assertEqual(qualified_outcome(self.raw, self.gate, self.gate, self.requests), "pass")
        self.assertEqual(self.raw, before)

    def test_failed_grade_is_a_failure_only_with_complete_proofs(self):
        self.raw["passed"] = False
        self.assertEqual(qualified_outcome(self.raw, self.gate, self.gate, self.requests), "fail")
        self.raw["proofs"]["dispatch"] = False
        self.assertEqual(qualified_outcome(self.raw, self.gate, self.gate, self.requests), "unproven")

    def test_missing_proof_demotes_even_a_legacy_pass(self):
        for key in ("dispatch", "scope", "grader", "timing"):
            with self.subTest(key=key):
                raw = copy.deepcopy(self.raw)
                raw["proofs"].pop(key)
                self.assertEqual(qualified_outcome(raw, self.gate, self.gate, self.requests), "unproven")

    def test_missing_or_rejected_requests(self):
        for requests in ([], [{"passed": False}], [{}]):
            with self.subTest(requests=requests):
                self.assertEqual(qualified_outcome(self.raw, self.gate, self.gate, requests), "unproven")

    def test_changed_listener_or_failed_gate(self):
        for after in ({"passed": False}, {"passed": True, "remote": {"listener_pid": 124}}):
            with self.subTest(after=after):
                self.assertEqual(qualified_outcome(self.raw, self.gate, after, self.requests), "unproven")

    def test_summary_does_not_count_unproven_raw_pass_as_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "RESULTS.md"
            summarize([{"outcome": "unproven", "raw": self.raw}], path)
            self.assertIn("| L0 | 0 | 0 | 1 | 1 |", path.read_text())

    def test_all_levels_present_and_baselines_fail_before_dispatch(self):
        tasks = runner.load_tasks(TASKS)
        self.assertEqual(len(tasks), 5)
        for task in tasks:
            self.assertTrue(set(LEVELS) <= set(task["prompts"]))
            runner.validate_task_baseline(task)

    def test_separate_decode_skips_legacy_probe(self):
        task = runner.load_tasks(["booking-off-by-one"])[0]
        completed = __import__("subprocess").CompletedProcess([], 0, "", "")
        with patch.object(runner, "validate_task_baseline"), \
             patch.object(runner, "ensure_pinned_model", return_value="test"), \
             patch.object(runner.subprocess, "run", return_value=completed), \
             patch.object(runner, "measure_tok_s") as probe:
            runner.run_trial(task, "L2", "test", 1, Path("."), False,
                             sampling={"skip_decode_probe": True})
            probe.assert_not_called()


class OllamaResetTest(unittest.TestCase):
    def fake(self, ps_sequence, load):
        calls = []
        def call(endpoint, path, body=None, timeout=15):
            calls.append((path, body))
            if path == "/api/ps":
                return ps_sequence.pop(0)
            if body.get("keep_alive") == 0:
                return {"done_reason": "unload"}
            return load
        return calls, call

    def test_unload_confirmed_then_prompt_free_reload(self):
        import run_standard_packet as rsp
        row = {"name": "m", "size_vram": 1}
        calls, call = self.fake([{"models": [row]}, {"models": []}, {"models": [row]}],
                                {"done_reason": "load", "response": ""})
        with patch.object(rsp, "call", call), patch.object(rsp.time, "sleep"):
            out = rsp.ollama_reset("http://x", "m")
        self.assertTrue(out["unloaded_confirmed"])
        self.assertEqual([c for c in calls if c[0] == "/api/generate"][1][1], {"model": "m", "keep_alive": -1})

    def test_reload_that_generated_is_refused(self):
        import run_standard_packet as rsp
        calls, call = self.fake([{"models": []}], {"done_reason": "stop", "response": "hi"})
        with patch.object(rsp, "call", call):
            with self.assertRaisesRegex(RuntimeError, "prompt-free"):
                rsp.ollama_reset("http://x", "m")

    def test_wrong_resident_model_is_refused(self):
        import run_standard_packet as rsp
        calls, call = self.fake([{"models": []}, {"models": [{"name": "other"}]}],
                                {"done_reason": "load", "response": ""})
        with patch.object(rsp, "call", call):
            with self.assertRaisesRegex(RuntimeError, "unexpected residency"):
                rsp.ollama_reset("http://x", "m")
