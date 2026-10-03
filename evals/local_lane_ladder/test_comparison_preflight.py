"""Pure tests for comparison_preflight: every check passes a valid case and
fails closed on the specific drift it exists to catch. No network, no models."""
from __future__ import annotations

import copy
import unittest

from comparison_preflight import (
    PIN_FIELDS,
    PreflightError,
    parse_parameters,
    validate_contract,
    validate_model_snapshot,
    validate_remote_placement,
    validate_request,
)

TAG = "study-model:latest"
DIGEST = "a" * 64
WEIGHT = "b" * 64
GPU0, GPU1 = "GPU-0000-aaaa", "GPU-1111-bbbb"

PARAMS = {
    "num_ctx": 16384, "num_keep": 0, "num_predict": 4096, "seed": 1234,
    "temperature": 0.8, "top_k": 20, "top_p": 0.95, "min_p": 0.0, "typical_p": 1.0,
    "repeat_last_n": 64, "repeat_penalty": 1.0, "presence_penalty": 0.0,
    "frequency_penalty": 0.0, "draft_num_predict": 0,
}


def contract(**overrides) -> dict:
    c = {
        "schema": "local-lane-comparison/v1",
        "ollama_version": "0.32.12",
        "think": "off",
        "endpoint": "http://127.0.0.1:11444",
        "parameters": dict(PARAMS),
        "models": {TAG: {"digest": DIGEST, "weight_sha256": WEIGHT, "variant": "instruct",
                         "stop": ["<|im_end|>"], "weight_bytes": 20 * 2**30}},
        "placement": {"host": "testbench", "ssh_host": "testbench", "port": 11437,
                      "gpu_uuids": [GPU0, GPU1], "minimum_weight_allocation_ratio": 0.9},
    }
    c.update(overrides)
    return c


def parameters_text(params: dict, stop=("<|im_end|>",)) -> str:
    lines = [f"{k} {v}" for k, v in params.items()]
    lines += [f'stop "{s}"' for s in stop]
    return "\n".join(lines)


def snapshot(params: dict | None = None, **overrides) -> dict:
    s = {
        "name": TAG, "digest": DIGEST, "ollama_version": "0.32.12",
        "show": {
            "modelfile": f"FROM /models/blobs/sha256-{WEIGHT}\nTEMPLATE x\n",
            "parameters": parameters_text(PARAMS if params is None else params),
            "capabilities": ["completion", "tools"],
        },
    }
    s.update(overrides)
    return s


def request(**overrides) -> dict:
    r = {"model": TAG, "messages": [], "stream": True, "temperature": 0.8, "top_p": 0.95,
         "seed": 1234, "frequency_penalty": 0.0, "presence_penalty": 0.0,
         "max_tokens": 4096, "reasoning_effort": "none"}
    r.update(overrides)
    return r


def placement_pair(used=(9500.0, 9500.0), listener=100, app_pids=(101, 101)):
    local_ps = {"models": [{"name": TAG, "digest": DIGEST, "size": 1, "size_vram": 1}]}
    remote = {
        "host": "testbench", "port": 11437, "listener_pid": listener,
        "processes": [{"pid": 100, "ppid": 1}, {"pid": 101, "ppid": 100}, {"pid": 555, "ppid": 1}],
        "gpus": [{"uuid": GPU0, "name": "NVIDIA GeForce RTX 3090"},
                 {"uuid": GPU1, "name": "NVIDIA GeForce RTX 3090"}],
        "compute_apps": [{"gpu_uuid": GPU0, "pid": app_pids[0], "used_mib": used[0]},
                         {"gpu_uuid": GPU1, "pid": app_pids[1], "used_mib": used[1]}],
        "api_ps": {"models": [{"name": TAG, "digest": DIGEST, "size": 1, "size_vram": 1}]},
    }
    return local_ps, remote


class ContractTests(unittest.TestCase):
    def test_valid_contract_passes(self):
        validate_contract(contract())

    def test_every_pin_field_must_be_declared(self):
        for field in PIN_FIELDS:
            c = contract()
            del c["parameters"][field]
            with self.subTest(field=field), self.assertRaises(PreflightError):
                validate_contract(c)

    def test_extra_field_rejected(self):
        c = contract()
        c["parameters"]["mirostat"] = 0
        with self.assertRaises(PreflightError):
            validate_contract(c)

    def test_thinking_only_model_cannot_join_thinking_off_cohort(self):
        c = contract()
        c["models"][TAG]["variant"] = "thinking"
        with self.assertRaisesRegex(PreflightError, "reasoning-only"):
            validate_contract(c)

    def test_other_ollama_version_refused(self):
        with self.assertRaises(PreflightError):
            validate_contract(contract(ollama_version="0.33.0"))

    def test_short_digest_refused(self):
        c = contract()
        c["models"][TAG]["digest"] = "b2ebb986e4e9"
        with self.assertRaisesRegex(PreflightError, "digest"):
            validate_contract(c)


class ParameterParsingTests(unittest.TestCase):
    def test_parses_numbers_and_repeated_stop(self):
        parsed = parse_parameters('temperature 0.8\nstop "<|a|>"\nstop "<|b|>"\n')
        self.assertEqual(parsed, {"temperature": 0.8, "stop": ["<|a|>", "<|b|>"]})

    def test_duplicate_parameter_refused(self):
        with self.assertRaises(PreflightError):
            parse_parameters("temperature 0.8\ntemperature 0.6\n")


class SnapshotTests(unittest.TestCase):
    def test_matching_snapshot_passes(self):
        out = validate_model_snapshot(contract(), TAG, snapshot())
        self.assertEqual(out["weight_sha256"], WEIGHT)

    def test_unset_sampler_field_fails(self):
        # The 2026-09-27 finding: an unset field falls back to a per-model default.
        params = dict(PARAMS)
        del params["presence_penalty"]
        with self.assertRaisesRegex(PreflightError, "presence_penalty"):
            validate_model_snapshot(contract(), TAG, snapshot(params))

    def test_different_sampler_value_fails(self):
        params = dict(PARAMS, presence_penalty=1.5)
        with self.assertRaisesRegex(PreflightError, "presence_penalty"):
            validate_model_snapshot(contract(), TAG, snapshot(params))

    def test_changed_tag_digest_fails(self):
        with self.assertRaisesRegex(PreflightError, "digest changed"):
            validate_model_snapshot(contract(), TAG, snapshot(digest="c" * 64))

    def test_different_weight_blob_fails(self):
        s = snapshot()
        s["show"]["modelfile"] = f"FROM /models/blobs/sha256-{'d' * 64}\n"
        with self.assertRaisesRegex(PreflightError, "weight blob"):
            validate_model_snapshot(contract(), TAG, s)

    def test_undeclared_runtime_parameter_fails(self):
        s = snapshot()
        s["show"]["parameters"] += "\nmirostat 2"
        with self.assertRaisesRegex(PreflightError, "undeclared"):
            validate_model_snapshot(contract(), TAG, s)

    def test_serving_version_change_fails(self):
        with self.assertRaisesRegex(PreflightError, "version"):
            validate_model_snapshot(contract(), TAG, snapshot(ollama_version="0.32.13"))

    def test_think_on_requires_thinking_capability(self):
        with self.assertRaisesRegex(PreflightError, "thinking requested"):
            validate_model_snapshot(contract(think="on"), TAG, snapshot())


class RequestTests(unittest.TestCase):
    def test_explicit_request_passes(self):
        validate_request(contract(), request())

    def test_omitted_temperature_fails(self):
        # Ollama 0.32.12's OpenAI adapter supplies 1.0 when temperature is omitted.
        body = request()
        del body["temperature"]
        with self.assertRaisesRegex(PreflightError, "temperature"):
            validate_request(contract(), body)

    def test_wrong_top_p_fails(self):
        with self.assertRaisesRegex(PreflightError, "top_p"):
            validate_request(contract(), request(top_p=1.0))

    def test_reasoning_effort_must_match_think_profile(self):
        with self.assertRaisesRegex(PreflightError, "reasoning_effort"):
            validate_request(contract(), request(reasoning_effort="medium"))
        validate_request(contract(think="on"), request(reasoning_effort="medium"))

    def test_unreviewed_field_fails(self):
        with self.assertRaisesRegex(PreflightError, "unreviewed"):
            validate_request(contract(), request(options={"top_k": 99}))

    def test_model_outside_roster_fails(self):
        with self.assertRaisesRegex(PreflightError, "roster"):
            validate_request(contract(), request(model="other:latest"))


class PlacementTests(unittest.TestCase):
    def test_attributed_allocation_passes(self):
        local_ps, remote = placement_pair()
        out = validate_remote_placement(contract(), TAG, local_ps, remote)
        self.assertTrue(out["proved"])
        self.assertFalse(out["zero_cpu_offload_proved"])

    def test_allocation_below_bound_fails(self):
        local_ps, remote = placement_pair(used=(4000.0, 4000.0))
        with self.assertRaisesRegex(PreflightError, "below bound"):
            validate_remote_placement(contract(), TAG, local_ps, remote)

    def test_memory_owned_by_unrelated_process_is_not_counted(self):
        local_ps, remote = placement_pair(app_pids=(555, 555))
        with self.assertRaises(PreflightError):
            validate_remote_placement(contract(), TAG, local_ps, remote)

    def test_tunnel_and_remote_disagree_fails(self):
        local_ps, remote = placement_pair()
        local_ps["models"][0]["size_vram"] = 0
        with self.assertRaisesRegex(PreflightError, "disagree"):
            validate_remote_placement(contract(), TAG, local_ps, remote)

    def test_wrong_host_fails(self):
        local_ps, remote = placement_pair()
        remote = dict(remote, host="desktop")
        with self.assertRaisesRegex(PreflightError, "host"):
            validate_remote_placement(contract(), TAG, local_ps, remote)

    def test_single_card_contract_passes_on_that_card(self):
        c = contract()
        c["placement"]["gpu_uuids"] = [GPU0]
        local_ps, remote = placement_pair(used=(19000.0, 0.0))
        remote["compute_apps"] = remote["compute_apps"][:1]
        self.assertTrue(validate_remote_placement(c, TAG, local_ps, remote)["proved"])

    def test_single_card_contract_refuses_the_other_card(self):
        c = contract()
        c["placement"]["gpu_uuids"] = [GPU0]
        local_ps, remote = placement_pair()
        with self.assertRaisesRegex(PreflightError, "outside allowed GPU set"):
            validate_remote_placement(c, TAG, local_ps, remote)

    def test_duplicate_gpu_declaration_refused(self):
        c = contract()
        c["placement"]["gpu_uuids"] = [GPU0, GPU0]
        local_ps, remote = placement_pair()
        with self.assertRaisesRegex(PreflightError, "distinct"):
            validate_remote_placement(c, TAG, local_ps, remote)

    def test_second_loaded_model_fails(self):
        local_ps, remote = placement_pair()
        remote = copy.deepcopy(remote)
        remote["api_ps"]["models"].append({"name": "other", "digest": "e" * 64})
        with self.assertRaisesRegex(PreflightError, "exactly one"):
            validate_remote_placement(contract(), TAG, local_ps, remote)


if __name__ == "__main__":
    unittest.main()


class CliTests(unittest.TestCase):
    """preflight_comparison.main with the network and SSH faked."""

    def run_cli(self, tmpdir, nonce_ok=True, with_request=True):
        import json
        import subprocess
        import sys
        from pathlib import Path
        from unittest.mock import patch

        import preflight_comparison as pc

        c = contract()
        cpath = Path(tmpdir) / "contract.json"
        cpath.write_text(json.dumps(c))
        capture = Path(tmpdir) / "gate.json"
        argv = ["preflight_comparison.py", "--contract", str(cpath), "--model", TAG,
                "--capture", str(capture)]
        if with_request:
            rpath = Path(tmpdir) / "request.json"
            rpath.write_text(json.dumps(request()))
            argv += ["--request-body", str(rpath)]
        local_ps, remote = placement_pair()

        def fake_get(base, path, data=None):
            return {"/api/version": {"version": "0.32.12"},
                    "/api/tags": {"models": [{"name": TAG, "digest": DIGEST}]},
                    "/api/show": snapshot()["show"],
                    "/api/ps": local_ps}[path]

        def fake_run(args, input, **kwargs):
            nonce = args[-1] if nonce_ok else "stale"
            return subprocess.CompletedProcess(args, 0, json.dumps(dict(remote, nonce=nonce)), "")

        with patch.object(pc, "get", side_effect=fake_get), \
                patch.object(pc.subprocess, "run", side_effect=fake_run), \
                patch.object(sys, "argv", argv), \
                patch("builtins.print"):
            code = pc.main()
        return code, json.loads(capture.read_text())

    def test_all_checks_pass(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            code, report = self.run_cli(d)
        self.assertEqual(code, 0, report["errors"])
        self.assertTrue(report["passed"])

    def test_stale_remote_capture_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            code, report = self.run_cli(d, nonce_ok=False)
        self.assertEqual(code, 2)
        self.assertTrue(any("stale" in e for e in report["errors"]))

    def test_missing_request_capture_fails(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            code, report = self.run_cli(d, with_request=False)
        self.assertEqual(code, 2)
        self.assertTrue(any("outbound request" in e for e in report["errors"]))


class ExtraBlobTests(unittest.TestCase):
    def two_blob_snapshot(self, second):
        s = snapshot()
        s["show"]["modelfile"] = f"FROM /b/sha256-{WEIGHT}\nFROM /b/sha256-{second}\n"
        return s

    def test_declared_projector_blob_passes(self):
        c = contract()
        c["models"][TAG]["extra_blob_sha256s"] = ["f" * 64]
        validate_model_snapshot(c, TAG, self.two_blob_snapshot("f" * 64))

    def test_undeclared_extra_blob_fails(self):
        with self.assertRaisesRegex(PreflightError, "blob"):
            validate_model_snapshot(contract(), TAG, self.two_blob_snapshot("f" * 64))

    def test_wrong_declared_blob_fails(self):
        c = contract()
        c["models"][TAG]["extra_blob_sha256s"] = ["f" * 64]
        with self.assertRaisesRegex(PreflightError, "blob"):
            validate_model_snapshot(c, TAG, self.two_blob_snapshot("e" * 64))
