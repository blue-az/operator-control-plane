"""uma_placement: attribution, foreign memory, power profile and mixed labelling. No network."""
from __future__ import annotations

import copy
import unittest

from comparison_preflight import PreflightError
from uma_placement import validate_uma_placement

TAG = "m"
GIB = 2**30


def contract(**placement):
    c = {"placement": {"kind": "uma-amdgpu", "host": "z13", "port": 18669, "platform_profile": "balanced",
                       "maximum_foreign_mib": 1536, **placement},
         "models": {TAG: {"gguf_bytes": 16 * GIB, "digest": "d"}}}
    return c


def remote(attributed_gib=17.0, foreign_mib=400.0, profile="balanced", ac=("1", "1", "0")):
    kib = int(attributed_gib * GIB / 1024)
    return {"host": "z13", "port": 18669, "listener_pid": 100,
            "processes": [{"pid": 100, "ppid": 1}, {"pid": 101, "ppid": 100}, {"pid": 555, "ppid": 1}],
            "drm_clients": [{"pid": 101, "vram_kib": 4 * 2**20, "gtt_kib": kib - 4 * 2**20},
                            {"pid": 555, "vram_kib": int(foreign_mib * 1024), "gtt_kib": 0}],
            "gpu": {"vram_used": 4 * GIB + int(foreign_mib * 2**20), "vram_total": 4 * GIB,
                    "gtt_used": int(attributed_gib * GIB) - 4 * GIB, "gtt_total": 20 * GIB},
            "meminfo_kib": {"MemTotal": 28 << 20, "MemAvailable": 9 << 20, "SwapTotal": 8 << 20, "SwapFree": 7 << 20},
            "ac_online": list(ac), "platform_profile": profile,
            "api_ps": {"models": [{"name": TAG, "digest": "d", "size": 10, "size_vram": 10}]}}


class UmaPlacementTest(unittest.TestCase):
    def test_resident_model_passes_and_records_pressure(self):
        out = validate_uma_placement(contract(), TAG, remote())
        self.assertEqual(out["label"], "gpu-resident")
        self.assertAlmostEqual(out["foreign_mib"], 400.0, delta=1)
        self.assertEqual(out["mem_available_mib"], 9 * 1024)
        self.assertEqual(out["swap_used_mib"], 1024)

    def test_mixed_is_labelled_not_refused(self):
        self.assertEqual(validate_uma_placement(contract(), TAG, remote(attributed_gib=8))["label"], "mixed")

    def test_declared_model_minimum_is_enforced(self):
        c = contract(); c["models"][TAG]["placement"] = {"minimum_weight_allocation_ratio": 0.9}
        with self.assertRaisesRegex(PreflightError, "below declared bound"):
            validate_uma_placement(c, TAG, remote(attributed_gib=8))

    def test_foreign_memory_above_ceiling_refused(self):
        with self.assertRaisesRegex(PreflightError, "foreign GPU memory"):
            validate_uma_placement(contract(), TAG, remote(foreign_mib=3000))

    def test_unrelated_process_memory_is_not_attributed(self):
        r = remote(); r["drm_clients"][0]["pid"] = 555
        r["drm_clients"] = [r["drm_clients"][0] | {"pid": 555}]
        with self.assertRaises(PreflightError):
            validate_uma_placement(contract(), TAG, r)

    def test_battery_and_profile_drift_refused(self):
        with self.assertRaisesRegex(PreflightError, "AC power"):
            validate_uma_placement(contract(), TAG, remote(ac=("0", "0")))
        with self.assertRaisesRegex(PreflightError, "platform profile"):
            validate_uma_placement(contract(), TAG, remote(profile="performance"))

    def test_wrong_host_or_kind_refused(self):
        with self.assertRaisesRegex(PreflightError, "host"):
            validate_uma_placement(contract(), TAG, remote() | {"host": "testbench"})
        with self.assertRaisesRegex(PreflightError, "unified-memory"):
            validate_uma_placement(contract(kind="nvidia"), TAG, remote())

    def test_ollama_ps_identity_checked(self):
        r = remote()
        out = validate_uma_placement(contract(), TAG, r, copy.deepcopy(r["api_ps"]))
        self.assertEqual(out["ollama_size_vram_ratio"], 1.0)
        bad = copy.deepcopy(r["api_ps"]); bad["models"][0]["digest"] = "x"
        with self.assertRaisesRegex(PreflightError, "identity"):
            validate_uma_placement(contract(), TAG, r, bad)


if __name__ == "__main__":
    unittest.main()
