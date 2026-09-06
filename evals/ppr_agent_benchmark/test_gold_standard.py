"""Gold-standard checker tests (stdlib unittest)."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECK_RUN = HERE / "check_run.py"
MANIFEST_PATH = HERE / "manifests" / "gold_manifest_v1.json"
RUN_EMPTY = HERE / "runs" / "20260826-204632"
PPR_AGENT = Path("/home/blueaz/Python/ppr-agent")
LANE_A_IDS = (
    "ppr1_product_boundary",
    "ppr2_gate_query_semantics",
    "ppr3_real_data_report",
)


class TestGoldManifestSchema(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_PATH.read_text())

    def test_meta_ids_lanes_sha256(self) -> None:
        meta = self.manifest["meta"]
        self.assertEqual(meta["version"], "v1")
        self.assertEqual(meta["lanes"], ["A", "B"])
        frozen = meta["frozen_inputs"]
        db = frozen["ppr_agent.db"]
        self.assertIn("sha256", db)
        self.assertEqual(
            db["sha256"],
            "753123e5d05de9008d6ddfdfa813a214cdfc5df1241fe8f2156b3f81974daf89",
        )
        self.assertTrue(meta.get("ppr_agent_head"))

    def test_lane_a_task_ids(self) -> None:
        ids = [task["id"] for task in self.manifest["lane_a"]]
        self.assertEqual(ids, list(LANE_A_IDS))
        for task in self.manifest["lane_a"]:
            self.assertTrue(task["required_headings"])
            self.assertTrue(task["required_values"])
            self.assertTrue(task["forbidden_values"])
            self.assertTrue(task["score_weights"])

    def test_lane_b_entries_have_command_and_expected(self) -> None:
        entries = self.manifest["lane_b"]
        self.assertGreaterEqual(len(entries), 7)
        ids = [e["id"] for e in entries]
        self.assertIn("ppr_stats", ids)
        self.assertIn("ppr_tools", ids)
        self.assertIn("ppr_gate_mdt_2030", ids)
        self.assertIn("ppr_gate_st_jude_2007", ids)
        self.assertIn("ppr_query_compare_icd_2023", ids)
        self.assertIn("ppr_run_top_devices_2023", ids)
        self.assertIn("ppr_run_hhi_icd_2023", ids)
        for entry in entries:
            self.assertIsInstance(entry["command"], list)
            self.assertTrue(entry["command"])
            self.assertIsInstance(entry["expected"], dict)
            self.assertTrue(entry["expected"])


class TestLaneAEmptyContentRegression(unittest.TestCase):
    def test_freetoken_reasoning_only_run_fails(self) -> None:
        self.assertTrue(RUN_EMPTY.is_dir(), f"missing historical run {RUN_EMPTY}")
        proc = subprocess.run(
            [sys.executable, str(CHECK_RUN), str(RUN_EMPTY)],
            capture_output=True,
            text=True,
            cwd=HERE,
            check=False,
        )
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        combined = proc.stdout + proc.stderr
        self.assertIn("finish_reason_length_or_reasoning_only", combined)


@unittest.skipUnless(
    PPR_AGENT.is_dir() and (PPR_AGENT / "ppr").is_file(),
    f"ppr-agent repo not present at {PPR_AGENT}",
)
class TestLaneBLiveExecution(unittest.TestCase):
    def test_lane_b_against_ppr_agent(self) -> None:
        proc = subprocess.run(
            [
                sys.executable,
                str(CHECK_RUN),
                "--lane-b",
                "--cwd",
                str(PPR_AGENT),
            ],
            capture_output=True,
            text=True,
            cwd=HERE,
            check=False,
        )
        self.assertEqual(
            proc.returncode,
            0,
            proc.stdout + proc.stderr,
        )
        self.assertIn("fully_pass=True", proc.stdout)


if __name__ == "__main__":
    unittest.main()
