"""Gate logic of request_gate_proxy, without a network."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from comparison_preflight import PreflightError
from request_gate_proxy import Gate
from test_comparison_preflight import TAG, contract, request


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.gate = Gate([contract()], "http://127.0.0.1:9", d / "log.jsonl", d / "cap")

    def tearDown(self):
        self.tmp.cleanup()

    def test_conforming_request_passes_and_is_captured(self):
        body = request()
        errors = self.gate.check(body)
        self.gate.record(body, errors)
        self.assertEqual(errors, [])
        self.assertTrue((self.gate.capture_dir / (TAG.replace(":", "_") + ".json")).exists())

    def test_request_missing_temperature_is_rejected(self):
        body = request()
        del body["temperature"]
        errors = self.gate.check(body)
        self.gate.record(body, errors)
        self.assertTrue(errors)
        self.assertFalse(any(self.gate.capture_dir.iterdir()))
        entry = json.loads(self.gate.log.read_text().splitlines()[-1])
        self.assertFalse(entry["passed"])
        self.assertNotIn("messages", entry["fields"])

    def test_model_outside_contracts_is_rejected(self):
        self.assertTrue(self.gate.check(request(model="other:latest")))

    def test_model_in_two_contracts_refused_at_startup(self):
        with self.assertRaisesRegex(PreflightError, "more than one contract"):
            Gate([contract(), contract()], "http://127.0.0.1:9",
                 self.gate.log, self.gate.capture_dir)
