import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

import ab_local


class AbLocalTests(unittest.TestCase):
    def setUp(self):
        self.arms = (
            ab_local.Arm("A", "model-a", "0", Path("/tmp/a")),
            ab_local.Arm("B", "model-b", "1", Path("/tmp/b")),
        )

    def test_round1_winner_stops(self):
        calls = []

        def invoke(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(exit_state="success")

        def gate(workspace, command):
            return (0, "", "") if workspace == self.arms[0].workspace else (1, "", "B failed")

        result = ab_local.run_race(
            prompt="do it", gate_cmd=["gate"], arm_a=self.arms[0], arm_b=self.arms[1],
            invoke_fn=invoke, run_gate_fn=gate,
        )
        self.assertEqual(result.winner, "A")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(c["harness_id"] == "opencode" for c in calls))

    def test_second_round_uses_own_stderr(self):
        calls = []

        def invoke(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(exit_state="success")

        def gate(workspace, command):
            if len([c for c in calls if c["workspace"] == workspace]) == 2:
                return (0, "", "") if workspace == self.arms[0].workspace else (1, "", "")
            marker = "A unique marker" if workspace == self.arms[0].workspace else "B unique marker"
            return (1, "", marker)

        result = ab_local.run_race(
            prompt="do it", gate_cmd=["gate"], arm_a=self.arms[0], arm_b=self.arms[1],
            invoke_fn=invoke, run_gate_fn=gate,
        )
        self.assertEqual(result.winner, "A")
        a_prompt = [c["prompt"] for c in calls if c["workspace"] == self.arms[0].workspace][1]
        self.assertIn("A unique marker", a_prompt)
        self.assertNotIn("B unique marker", a_prompt)

    def test_no_winner_when_neither_local_passes(self):
        calls = []

        def invoke(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(exit_state="success")

        def gate(workspace, command):
            return (1, "", "failed")

        result = ab_local.run_race(
            prompt="do it", gate_cmd=["gate"], arm_a=self.arms[0], arm_b=self.arms[1],
            max_rounds=2, invoke_fn=invoke, run_gate_fn=gate,
        )
        self.assertIsNone(result.winner)
        self.assertEqual(len(calls), 4)
        self.assertTrue(all(c["harness_id"] == "opencode" for c in calls))

    def test_rejects_identical_models(self):
        same = ab_local.Arm("B", "model-a", "1", Path("/tmp/b"))
        with self.assertRaises(ValueError):
            ab_local.run_race(
                prompt="do it",
                gate_cmd=["gate"],
                arm_a=self.arms[0],
                arm_b=same,
                invoke_fn=lambda **k: SimpleNamespace(exit_state="success"),
                run_gate_fn=lambda *a: (1, "", ""),
            )

    def test_concurrent_start(self):
        starts = []
        finishes = []
        lock = threading.Lock()

        def invoke(**kwargs):
            with lock:
                starts.append(time.monotonic())
            time.sleep(0.2)
            with lock:
                finishes.append(time.monotonic())
            return SimpleNamespace(exit_state="success")

        def gate(workspace, command):
            return (1, "", "failed")

        ab_local.run_race(
            prompt="do it", gate_cmd=["gate"], arm_a=self.arms[0], arm_b=self.arms[1],
            max_rounds=1, invoke_fn=invoke, run_gate_fn=gate,
        )
        self.assertGreaterEqual(len(starts), 2)
        self.assertLess(max(starts[:2]), min(finishes[:2]))

    def test_cuda_env_forwarded(self):
        envs = {}
        local_envs = {}

        def invoke(**kwargs):
            envs[kwargs["workspace"]] = kwargs["extra_env"]
            if kwargs["harness_id"] == "opencode":
                local_envs[kwargs["workspace"]] = kwargs["extra_env"]
            return SimpleNamespace(exit_state="success")

        def gate(workspace, command):
            return (1, "", "failed")

        ab_local.run_race(
            prompt="do it", gate_cmd=["gate"], arm_a=self.arms[0], arm_b=self.arms[1],
            max_rounds=1, invoke_fn=invoke, run_gate_fn=gate,
        )
        self.assertEqual(local_envs[self.arms[0].workspace], {"CUDA_VISIBLE_DEVICES": "0"})
        self.assertEqual(local_envs[self.arms[1].workspace], {"CUDA_VISIBLE_DEVICES": "1"})


if __name__ == "__main__":
    unittest.main()
