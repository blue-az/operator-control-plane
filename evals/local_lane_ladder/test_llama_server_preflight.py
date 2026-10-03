"""Pure checks for llama-server comparison contracts; no network, no models."""
from __future__ import annotations

import copy
import unittest

from comparison_preflight import (
    LLAMA_SCHEMA,
    PreflightError,
    validate_contract,
    validate_llama_placement,
    validate_llama_props,
    validate_request,
)

SHA = "a" * 64
GPU0, GPU1 = "GPU-0000", "GPU-1111"
TAG = "bonsai-27b-pq2"
PARAMS = {"num_ctx": 16384, "num_predict": 4096, "seed": 1234, "temperature": 0.7, "top_k": 20,
          "top_p": 0.8, "min_p": 0, "typical_p": 1, "repeat_last_n": 64, "repeat_penalty": 1,
          "presence_penalty": 0, "frequency_penalty": 0}


def contract(**overrides) -> dict:
    base = {"schema": LLAMA_SCHEMA, "think": "off", "endpoint": "http://127.0.0.1:11461",
            "engine": {"release": "prism-b10743-adfffbe", "archive_sha256": "b" * 64},
            "parameters": dict(PARAMS),
            "placement": {"host": "testbench", "ssh_host": "testbench", "port": 11460,
                          "gpu_uuid": GPU0, "minimum_weight_allocation_ratio": 0.9},
            "models": {TAG: {"gguf_sha256": SHA, "gguf_bytes": 1000 * 2**20,
                             "gguf_path": "/m/bonsai.gguf", "variant": "hybrid"}}}
    base.update(overrides)
    return base


def props(**param_overrides) -> dict:
    params = {"seed": 1234, "temperature": 0.699999988079071, "top_k": 20, "top_p": 0.800000011920929,
              "min_p": 0.0, "typical_p": 1.0, "repeat_last_n": 64, "repeat_penalty": 1.0,
              "presence_penalty": 0.0, "frequency_penalty": 0.0, "dry_multiplier": 0.0,
              "xtc_probability": 0.0, "mirostat": 0, "top_n_sigma": -1.0,
              "speculative.types": "none", "lora": []}
    params.update(param_overrides)
    return {"model_alias": TAG, "model_path": "/m/bonsai.gguf", "total_slots": 1,
            "default_generation_settings": {"n_ctx": 16384, "params": params}}


GGUF = {"path": "/m/bonsai.gguf", "sha256": SHA, "bytes": 1000 * 2**20}


def remote(apps=((GPU0, 50, 1000.0),)) -> dict:
    return {"host": "testbench", "port": 11460, "listener_pid": 50,
            "compute_apps": [{"gpu_uuid": g, "pid": p, "used_mib": m} for g, p, m in apps]}


class LlamaContractTests(unittest.TestCase):
    def test_valid_contract_passes(self):
        validate_contract(contract())

    def test_ollama_only_fields_are_rejected(self):
        c = contract()
        c["parameters"]["num_keep"] = 4
        with self.assertRaisesRegex(PreflightError, "every pin field"):
            validate_contract(c)

    def test_missing_field_is_rejected(self):
        c = contract()
        del c["parameters"]["min_p"]
        with self.assertRaisesRegex(PreflightError, "every pin field"):
            validate_contract(c)

    def test_thinking_profile_is_refused(self):
        with self.assertRaisesRegex(PreflightError, "thinking-off"):
            validate_contract(contract(think="on"))

    def test_engine_must_be_declared(self):
        with self.assertRaisesRegex(PreflightError, "engine"):
            validate_contract(contract(engine={"release": "x"}))


class LlamaPropsTests(unittest.TestCase):
    def test_matching_server_passes_despite_float32_rounding(self):
        result = validate_llama_props(contract(), TAG, props(), GGUF)
        self.assertEqual(result["gguf_sha256"], SHA)

    def test_each_sampler_drift_fails(self):
        for key, value in (("temperature", 0.8), ("top_k", 40), ("top_p", 0.95), ("min_p", 0.05),
                           ("seed", 1), ("repeat_penalty", 1.1), ("typical_p", 0.9)):
            with self.subTest(key=key), self.assertRaises(PreflightError):
                validate_llama_props(contract(), TAG, props(**{key: value}), GGUF)

    def test_speculation_and_extra_samplers_fail(self):
        for override in ({"speculative.types": "draft"}, {"dry_multiplier": 0.8},
                         {"xtc_probability": 0.5}, {"mirostat": 2}, {"lora": [{"id": 0}]}):
            with self.subTest(override=override), self.assertRaises(PreflightError):
                validate_llama_props(contract(), TAG, props(**override), GGUF)

    def test_wrong_file_or_hash_fails(self):
        for gguf in ({**GGUF, "sha256": "c" * 64}, {**GGUF, "bytes": 5}, {**GGUF, "path": "/other"}):
            with self.subTest(gguf=gguf), self.assertRaises(PreflightError):
                validate_llama_props(contract(), TAG, props(), gguf)

    def test_wrong_alias_ctx_or_slots_fail(self):
        for mutate in (lambda p: p.update(model_alias="other"), lambda p: p.update(total_slots=4),
                       lambda p: p["default_generation_settings"].update(n_ctx=32768),
                       lambda p: p.update(model_path="/m/other.gguf")):
            p = props()
            mutate(p)
            with self.assertRaises(PreflightError):
                validate_llama_props(contract(), TAG, p, GGUF)

    def test_ollama_contract_is_refused(self):
        c = copy.deepcopy(contract())
        c["schema"] = "local-lane-comparison/v1"
        with self.assertRaises(PreflightError):
            validate_llama_props(c, TAG, props(), GGUF)


class LlamaPlacementTests(unittest.TestCase):
    def test_single_card_allocation_passes(self):
        self.assertTrue(validate_llama_placement(contract(), TAG, remote())["proved"])

    def test_spill_to_second_card_fails(self):
        with self.assertRaisesRegex(PreflightError, "expected only"):
            validate_llama_placement(contract(), TAG, remote(((GPU0, 50, 900.0), (GPU1, 50, 100.0))))

    def test_under_allocation_fails(self):
        with self.assertRaisesRegex(PreflightError, "below bound"):
            validate_llama_placement(contract(), TAG, remote(((GPU0, 50, 500.0),)))

    def test_unrelated_workload_fails(self):
        with self.assertRaisesRegex(PreflightError, "unrelated"):
            validate_llama_placement(contract(), TAG, remote(((GPU0, 50, 1000.0), (GPU1, 77, 2000.0))))


class SplitModelPlacementTests(unittest.TestCase):
    """A model deliberately split across GPU and CPU to fit a smaller card."""

    def split_contract(self, **placement):
        c = contract()
        c["models"][TAG]["placement"] = {"minimum_weight_allocation_ratio": 0.4, "maximum_mib": 600, **placement}
        c["placement"]["memory_clock_mhz"] = 5001
        return c

    def remote(self, mib, clock=5001):
        r = remote(((GPU0, 50, mib),))
        r["memory_clock_mhz"] = {GPU0: clock, GPU1: 9751}
        return r

    def test_split_within_bounds_passes(self):
        result = validate_llama_placement(self.split_contract(), TAG, self.remote(550.0))
        self.assertEqual(result["maximum_mib"], 600)

    def test_above_ceiling_fails(self):
        with self.assertRaisesRegex(PreflightError, "above ceiling"):
            validate_llama_placement(self.split_contract(), TAG, self.remote(650.0))

    def test_below_own_lower_bound_fails(self):
        with self.assertRaisesRegex(PreflightError, "below bound"):
            validate_llama_placement(self.split_contract(), TAG, self.remote(300.0))

    def test_unlocked_memory_clock_fails(self):
        with self.assertRaisesRegex(PreflightError, "memory clock"):
            validate_llama_placement(self.split_contract(), TAG, self.remote(550.0, clock=9751))

    def test_missing_clock_reading_fails(self):
        r = remote(((GPU0, 50, 550.0),))
        with self.assertRaisesRegex(PreflightError, "memory clock"):
            validate_llama_placement(self.split_contract(), TAG, r)

    def test_unknown_override_key_fails(self):
        with self.assertRaisesRegex(PreflightError, "unknown placement override"):
            validate_contract(self.split_contract(ceiling=1))


class LlamaRequestTests(unittest.TestCase):
    def body(self, **overrides):
        body = {"model": TAG, "messages": [], "temperature": 0.7, "top_p": 0.8, "seed": 1234,
                "frequency_penalty": 0, "presence_penalty": 0, "max_tokens": 4096,
                "reasoning_effort": "none"}
        body.update(overrides)
        return body

    def test_pinned_body_passes(self):
        validate_request(contract(), self.body())

    def test_drifted_body_fails(self):
        for override in ({"temperature": 0.8}, {"max_tokens": 8192}, {"top_k": 40}, {"reasoning_effort": "low"}):
            with self.subTest(override=override), self.assertRaises(PreflightError):
                validate_request(contract(), self.body(**override))


if __name__ == "__main__":
    unittest.main()
