#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pbc_lint


class TestPbcLint(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)

    def write_pbc(self, name: str, body: str) -> Path:
        path = Path(self.temp_dir) / name
        path.write_text(body, encoding="utf-8")
        return path

    def test_rules_must_not_carry_trust_proposed(self) -> None:
        path = self.write_pbc(
            "bad.pbc.md",
            "---\nstatus: active\n---\n"
            "```pbc:rules\n- id: X-RUL-001\n  trust: proposed\n```\n",
        )
        errors = pbc_lint.lint_file(path, ledger_names=None)
        self.assertTrue(any("trust: proposed" in e for e in errors))

    def test_id_cannot_be_proposed_and_ratified(self) -> None:
        path = self.write_pbc(
            "dup.pbc.md",
            "---\nstatus: draft\n---\n"
            "```pbc:rules\n- id: X-RUL-001\n  trust: trusted\n```\n"
            "```pbc:proposed-rules\n- id: X-RUL-001\n  trust: proposed\n```\n",
        )
        errors = pbc_lint.lint_file(path, ledger_names=None)
        self.assertTrue(any("both proposed and ratified" in e for e in errors))

    def test_active_contract_needs_rules_block(self) -> None:
        path = self.write_pbc(
            "empty-active.pbc.md",
            "---\nstatus: active\n---\n```pbc:actors\n- id: user\n```\n",
        )
        errors = pbc_lint.lint_file(path, ledger_names=None)
        self.assertTrue(any("no pbc:rules block" in e for e in errors))

    def test_proposed_without_ledger_is_not_invariant_two(self) -> None:
        path = self.write_pbc(
            "open.pbc.md",
            "---\nstatus: draft\n---\n"
            "```pbc:proposed-rules\n- id: X-RUL-010\n  trust: proposed\n```\n",
        )
        errors = pbc_lint.lint_file(path, ledger_names=None)
        self.assertEqual(errors, [])

    def test_proposed_missing_from_ledger_fails_invariant_two(self) -> None:
        path = self.write_pbc(
            "open.pbc.md",
            "---\nstatus: draft\n---\n"
            "```pbc:proposed-rules\n- id: X-RUL-010\n  trust: proposed\n```\n",
        )
        errors = pbc_lint.lint_file(path, ledger_names=set())
        self.assertTrue(any("not reachable from a frozen claim" in e for e in errors))

    def test_proposed_named_in_ledger_passes_invariant_two(self) -> None:
        path = self.write_pbc(
            "open.pbc.md",
            "---\nstatus: draft\n---\n"
            "```pbc:proposed-rules\n- id: X-RUL-010\n  trust: proposed\n```\n",
        )
        errors = pbc_lint.lint_file(path, ledger_names={"open.pbc.md"})
        self.assertEqual(errors, [])

    def test_main_lints_repo_pbc_dir_without_ledger(self) -> None:
        repo = Path(__file__).resolve().parents[1] / "owners-manual" / "pbc"
        rc = pbc_lint.main([str(repo)])
        self.assertEqual(rc, 0)
