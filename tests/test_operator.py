#!/usr/bin/env python3
"""
Integration test suite for the Operator Control Plane CLI.
Validates the full spine of commands using a temporary workspace.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

OPERATOR_BIN = str(Path(__file__).resolve().parents[1] / "operator")


class TestOperatorCLI(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self.old_cwd = os.getcwd()
        os.chdir(self.temp_dir)

    def tearDown(self) -> None:
        os.chdir(self.old_cwd)
        shutil.rmtree(self.temp_dir)

    def run_operator(
        self,
        *args: str,
        stdin_data: str | None = None,
        env: dict | None = None,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [OPERATOR_BIN] + list(args)
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        return subprocess.run(
            cmd,
            input=stdin_data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=run_env,
            timeout=timeout,
        )

    def rebaseline_ledger(self) -> None:
        db_path = Path(self.temp_dir) / ".operator" / "ledger.sqlite3"
        for suffix in ("", "-wal", "-shm"):
            Path(f"{db_path}{suffix}").unlink(missing_ok=True)
        res = self.run_operator("init")
        self.assertEqual(res.returncode, 0, res.stderr)

    def read_ledger_events(self) -> list[sqlite3.Row]:
        db_path = Path(self.temp_dir) / ".operator" / "ledger.sqlite3"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            return conn.execute(
                "SELECT * FROM ledger_events ORDER BY record_type, record_id, version"
            ).fetchall()
        finally:
            conn.close()

    def write_identity_registry(self, mode: str, uids: dict) -> Path:
        identity_path = Path(self.temp_dir) / ".operator" / "identity.yaml"
        identity_path.write_text(yaml.safe_dump({"mode": mode, "uids": uids}, sort_keys=False))
        return identity_path

    def trust_state_snapshot(self) -> dict:
        operator_dir = Path(self.temp_dir) / ".operator"
        projection_roots = ["tasks", "claims", "evidence", "handoffs", "usage"]
        projections = []
        for root in projection_roots:
            root_path = operator_dir / root
            if not root_path.exists():
                continue
            projections.extend(
                (str(path.relative_to(operator_dir)), path.read_bytes())
                for path in sorted(root_path.rglob("*"))
                if path.is_file()
            )
        return {
            "projections": projections,
            "events": [tuple(row) for row in self.read_ledger_events()],
        }

    def setup_p2_enforced_claim(self, uids: dict | None = None) -> tuple[Path, Path]:
        self.assertEqual(self.run_operator("init").returncode, 0)
        task = self.run_operator(
            "task-create",
            "--objective",
            "Exercise P2 verifier isolation",
            "--id",
            "p2-task",
            "--assign",
            "codex",
            "--review",
            "claude",
        )
        self.assertEqual(task.returncode, 0, task.stderr)
        self.write_identity_registry(
            "enforced",
            uids
            or {
                1001: {"name": "codex", "roles": ["builder"]},
                1002: {"name": "claude", "roles": ["verifier"]},
            },
        )
        claim = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "P2 isolated verification works",
            "--gate",
            "test-gate",
            env={"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertEqual(claim.returncode, 0, claim.stderr)
        gate = Path(self.temp_dir) / "test-gate"
        gate.write_text("structural gate")
        evidence = Path(self.temp_dir) / "p2-evidence.txt"
        evidence.write_text("p2 evidence")
        return gate, evidence

    def test_init_creates_structure(self) -> None:
        res = self.run_operator("init")
        self.assertEqual(res.returncode, 0, f"init failed: {res.stderr}")
        self.assertIn("Initialized empty Operator Control Plane repository", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"
        self.assertTrue(op_path.exists())
        self.assertTrue((op_path / "harnesses").exists())
        self.assertTrue((op_path / "tasks").exists())
        self.assertTrue((op_path / "claims").exists())
        self.assertTrue((op_path / "evidence").exists())
        self.assertTrue((op_path / "usage").exists())
        self.assertTrue((op_path / "briefs").exists())
        self.assertTrue((op_path / "ledger.sqlite3").exists())

        # Verify default harnesses
        self.assertTrue((op_path / "harnesses" / "codex.yaml").exists())
        self.assertTrue((op_path / "harnesses" / "claude.yaml").exists())
        self.assertTrue((op_path / "harnesses" / "grok.yaml").exists())

    def test_durable_event_ledger_tracks_record_history(self) -> None:
        self.assertEqual(self.run_operator("init").returncode, 0)
        self.assertEqual(
            self.run_operator(
                "task-create",
                "--objective",
                "Exercise durable writes",
                "--id",
                "durable-task",
                "--assign",
                "codex",
            ).returncode,
            0,
        )
        self.assertEqual(
            self.run_operator(
                "claim-add",
                "--type",
                "real_data",
                "--text",
                "A bounded claim",
                "--gate",
                "manual provenance review",
            ).returncode,
            0,
        )

        source = Path(self.temp_dir) / "evidence.txt"
        source.write_text("evidence")
        self.assertEqual(
            self.run_operator(
                "evidence-attach",
                "--claim",
                "claim-0001",
                "--type",
                "manifest",
                str(source),
            ).returncode,
            0,
        )
        self.assertEqual(
            self.run_operator(
                "session-start", "--task", "durable-task", "--harness", "codex"
            ).returncode,
            0,
        )
        self.assertEqual(
            self.run_operator(
                "session-end", "usage-0001", "--outcome", "useful", "--cost", "0"
            ).returncode,
            0,
        )
        self.assertEqual(
            self.run_operator(
                "usage-add",
                "--harness",
                "codex",
                "--task",
                "durable-task",
                stdin_data="manual usage snapshot",
            ).returncode,
            0,
        )
        self.assertEqual(
            self.run_operator(
                "handoff-add",
                "--task",
                "durable-task",
                "--changed",
                "Durable history exercised",
                "--next-action",
                "Review the event rows",
            ).returncode,
            0,
        )

        rows = self.read_ledger_events()
        self.assertEqual(
            {row["record_type"] for row in rows},
            {"task", "claim", "evidence", "usage", "handoff"},
        )
        by_record = {}
        for row in rows:
            by_record.setdefault((row["record_type"], row["record_id"]), []).append(row)

        self.assertGreater(len(by_record[("task", "durable-task")]), 1)
        self.assertEqual([row["version"] for row in by_record[("claim", "claim-0001")]], [1, 2])
        session_rows = by_record[("usage", "usage-0001")]
        self.assertEqual(
            [row["event_type"] for row in session_rows], ["session_started", "session_ended"]
        )
        self.assertEqual(session_rows[1]["previous_event_hash"], session_rows[0]["event_hash"])
        self.assertEqual(
            [row["source_command"] for row in session_rows], ["session-start", "session-end"]
        )

        db_path = Path(self.temp_dir) / ".operator" / "ledger.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE ledger_events SET event_type = 'changed'")
            conn.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM ledger_events")
        finally:
            conn.close()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_local_evidence_fingerprint_detects_source_and_snapshot_staleness(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create", "--objective", "Fingerprint evidence", "--id", "fingerprint-task"
        )
        self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Evidence bytes remain current",
            "--gate",
            "manual review",
        )

        source = Path(self.temp_dir) / "evidence.bin"
        source.write_bytes(b"alpha")
        sentinel = Path(self.temp_dir) / "verification-command-ran"
        res = self.run_operator(
            "evidence-attach",
            str(source),
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            "--status",
            "verified",
            "--verified-by",
            "reviewer",
            "--verify-cmd",
            f"touch {sentinel}",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        evidence_path = (
            Path(self.temp_dir)
            / ".operator"
            / "evidence"
            / "fingerprint-task"
            / "evidence-0001.yaml"
        )
        evidence = yaml.safe_load(evidence_path.read_text())
        expected_hash = hashlib.sha256(b"alpha").hexdigest()
        self.assertEqual(evidence["hash"], expected_hash)
        self.assertEqual(evidence["fingerprint"]["algorithm"], "sha256")
        self.assertEqual(evidence["fingerprint"]["value"], expected_hash)
        self.assertEqual(evidence["fingerprint"]["size_bytes"], 5)
        self.assertIsInstance(evidence["fingerprint"]["mtime_ns"], int)
        self.assertEqual(evidence["source"]["kind"], "local_file")
        self.assertEqual(evidence["source"]["locator"], str(source.resolve()))
        self.assertEqual(evidence["source"]["fingerprint"]["value"], expected_hash)

        event = next(row for row in self.read_ledger_events() if row["record_type"] == "evidence")
        event_payload = json.loads(event["payload_json"])
        self.assertEqual(event_payload["fingerprint"], evidence["fingerprint"])
        self.assertFalse(sentinel.exists())
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(sentinel.exists())

        del evidence["hash"]
        evidence["claim_id"] = None
        evidence_path.write_text(yaml.safe_dump(evidence))
        self.rebaseline_ledger()
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertFalse(sentinel.exists())

        source.unlink()
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("local source is unavailable; retained snapshot remains current", res.stdout)
        self.assertFalse(sentinel.exists())

        source.write_bytes(b"omega")
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("verified local source content changed since attachment", res.stdout)
        self.assertFalse(sentinel.exists())

        source.write_bytes(b"alpha")
        retained_snapshot = Path(evidence["path_or_url"])
        retained_snapshot.write_bytes(b"bravo")
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("retained snapshot content changed", res.stdout)
        self.assertFalse(sentinel.exists())

        retained_snapshot.unlink()
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("retained snapshot is missing", res.stdout)
        self.assertFalse(sentinel.exists())

        os.mkfifo(retained_snapshot)
        res = self.run_operator("doctor", timeout=5)
        self.assertEqual(res.returncode, 1, res.stdout + res.stderr)
        self.assertIn("retained snapshot is unreadable", res.stdout)
        self.assertIn("is not a regular file", res.stdout)
        self.assertFalse(sentinel.exists())

    def test_expected_evidence_hash_is_validated_before_trust_writes(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create", "--objective", "Expected fingerprint", "--id", "expected-hash-task"
        )
        self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Expected digest matches bytes",
            "--gate",
            "manual review",
        )
        source = Path(self.temp_dir) / "expected.bin"
        source.write_bytes(b"expected bytes")
        evidence_dir = Path(self.temp_dir) / ".operator" / "evidence" / "expected-hash-task"
        ledger_path = Path(self.temp_dir) / ".operator" / "ledger.sqlite3"
        for path in ledger_path.parent.glob("ledger.sqlite3*"):
            path.unlink()

        for supplied_hash, expected_message in (
            ("not-a-sha256", "must be exactly 64 hexadecimal characters"),
            ("0" * 64, "does not match local evidence bytes"),
        ):
            res = self.run_operator(
                "evidence-attach",
                str(source),
                "--claim",
                "claim-0001",
                "--type",
                "manifest",
                "--status",
                "verified",
                "--verified-by",
                "reviewer",
                "--hash",
                supplied_hash,
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn(expected_message, res.stderr)
            self.assertEqual(list(evidence_dir.glob("*")), [])
            self.assertFalse(ledger_path.exists())

        source_dir = Path(self.temp_dir) / "not-a-file"
        source_dir.mkdir()
        res = self.run_operator(
            "evidence-attach",
            str(source_dir),
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            "--hash",
            hashlib.sha256(b"").hexdigest(),
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("is not a regular file", res.stderr)
        self.assertEqual(list(evidence_dir.glob("*")), [])
        self.assertFalse(ledger_path.exists())

        missing_source = Path(self.temp_dir) / "missing-evidence.bin"
        for missing_locator in (str(missing_source), f"FILE://{missing_source}"):
            res = self.run_operator(
                "evidence-attach",
                missing_locator,
                "--claim",
                "claim-0001",
                "--type",
                "manifest",
                "--status",
                "verified",
                "--verified-by",
                "reviewer",
                "--hash",
                hashlib.sha256(b"invented").hexdigest(),
                "--verify-cmd",
                "true",
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Local evidence file does not exist", res.stderr)
            self.assertFalse(ledger_path.exists())

        expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        res = self.run_operator(
            "evidence-attach",
            str(source),
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            "--status",
            "verified",
            "--verified-by",
            "reviewer",
            "--hash",
            expected_hash.upper(),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        evidence = yaml.safe_load((evidence_dir / "evidence-0001.yaml").read_text())
        self.assertEqual(evidence["hash"], expected_hash)
        self.assertEqual(evidence["fingerprint"]["value"], expected_hash)

    def test_evidence_copy_never_clobbers_or_deletes_an_existing_artifact(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create", "--objective", "No-clobber evidence copy", "--id", "copy-safety-task"
        )
        evidence_dir = Path(self.temp_dir) / ".operator" / "evidence" / "copy-safety-task"
        evidence_dir.mkdir(exist_ok=True)
        existing_artifact = evidence_dir / "evidence-0001.txt"
        existing_artifact.write_text("must survive")

        res = self.run_operator("evidence-attach", str(existing_artifact), "--type", "manifest")
        self.assertEqual(res.returncode, 1)
        self.assertIn("artifact destination already exists", res.stderr)
        self.assertEqual(existing_artifact.read_text(), "must survive")
        self.assertFalse((evidence_dir / "evidence-0001.yaml").exists())
        self.assertFalse(any(row["record_type"] == "evidence" for row in self.read_ledger_events()))

    def test_remote_evidence_is_explicitly_uncheckable_and_commands_are_not_run(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create", "--objective", "Remote evidence", "--id", "remote-evidence-task"
        )
        self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Remote evidence remains structural",
            "--gate",
            "manual review",
        )
        sentinel = Path(self.temp_dir) / "remote-verification-command-ran"
        remote_url = "https://example.invalid/evidence.json"
        expected_hash = "a" * 64

        res = self.run_operator(
            "evidence-attach",
            remote_url,
            "--claim",
            "claim-0001",
            "--type",
            "external_doc",
            "--status",
            "verified",
            "--verified-by",
            "reviewer",
            "--hash",
            expected_hash,
            "--verify-cmd",
            f"touch {sentinel}",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        evidence_path = (
            Path(self.temp_dir)
            / ".operator"
            / "evidence"
            / "remote-evidence-task"
            / "evidence-0001.yaml"
        )
        evidence = yaml.safe_load(evidence_path.read_text())
        self.assertEqual(evidence["source"], {"kind": "remote_url", "locator": remote_url})
        self.assertEqual(
            evidence["fingerprint"],
            {
                "algorithm": "sha256",
                "value": expected_hash,
                "size_bytes": None,
                "mtime_ns": None,
            },
        )

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        self.assertIn("remote freshness is uncheckable without a local snapshot", res.stdout)
        self.assertIn("verification command was not executed", res.stdout)
        self.assertFalse(sentinel.exists())

    def test_doctor_accepts_legacy_raw_hash_evidence(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create", "--objective", "Legacy fingerprint", "--id", "legacy-hash-task"
        )
        source = Path(self.temp_dir) / "legacy.txt"
        source.write_text("legacy evidence")
        res = self.run_operator("evidence-attach", str(source), "--type", "manifest")
        self.assertEqual(res.returncode, 0, res.stderr)

        evidence_path = (
            Path(self.temp_dir)
            / ".operator"
            / "evidence"
            / "legacy-hash-task"
            / "evidence-0001.yaml"
        )
        evidence = yaml.safe_load(evidence_path.read_text())
        del evidence["fingerprint"]
        del evidence["source"]
        evidence_path.write_text(yaml.safe_dump(evidence))
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_doctor_reconciles_yaml_with_durable_history(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create", "--objective", "Reconcile projections", "--id", "reconcile-task"
        )
        self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Original claim",
            "--gate",
            "manual provenance review",
        )
        source = Path(self.temp_dir) / "source.yaml"
        source.write_text("source: true\n")
        self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            str(source),
        )

        op_path = Path(self.temp_dir) / ".operator"
        evidence_record = yaml.safe_load(
            (op_path / "evidence" / "reconcile-task" / "evidence-0001.yaml").read_text()
        )
        self.assertTrue(evidence_record["path_or_url"].endswith("artifact-evidence-0001.yaml"))
        self.assertTrue(Path(evidence_record["path_or_url"]).exists())
        self.assertEqual(self.run_operator("doctor").returncode, 0)
        claim_path = op_path / "claims" / "claim-0001.yaml"
        original_claim = claim_path.read_text()
        changed_claim = yaml.safe_load(original_claim)
        changed_claim["text"] = "Changed outside the CLI"
        claim_path.write_text(yaml.safe_dump(changed_claim))

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("Durable ledger mismatch for claim claim-0001", res.stdout)

        claim_path.write_text(": [malformed")
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("cannot parse YAML projection claims/claim-0001.yaml", res.stdout)

        claim_path.write_text(original_claim)
        evidence_path = op_path / "evidence" / "reconcile-task" / "evidence-0001.yaml"
        evidence_path.unlink()
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "Durable ledger latest evidence reconcile-task/evidence-0001 has no YAML projection",
            res.stdout,
        )

    def test_concurrent_claim_creation_keeps_ids_distinct(self) -> None:
        self.run_operator("init")
        task_ids = [f"concurrent-task-{index}" for index in range(8)]
        for task_id in task_ids:
            res = self.run_operator(
                "task-create", "--objective", f"Task {task_id}", "--id", task_id
            )
            self.assertEqual(res.returncode, 0, res.stderr)

        def add_claim(task_id: str) -> subprocess.CompletedProcess[str]:
            return self.run_operator(
                "claim-add",
                "--task",
                task_id,
                "--type",
                "real_data",
                "--text",
                f"Claim for {task_id}",
                "--gate",
                "manual review",
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(task_ids)) as pool:
            results = list(pool.map(add_claim, task_ids))
        for result in results:
            self.assertEqual(result.returncode, 0, result.stderr)

        op_path = Path(self.temp_dir) / ".operator"
        claim_files = sorted((op_path / "claims").glob("claim-*.yaml"))
        self.assertEqual(len(claim_files), len(task_ids))
        claims = [yaml.safe_load(path.read_text()) for path in claim_files]
        self.assertEqual({claim["task_id"] for claim in claims}, set(task_ids))
        self.assertEqual(len({claim["claim_id"] for claim in claims}), len(task_ids))

        rows = [row for row in self.read_ledger_events() if row["record_type"] == "claim"]
        self.assertEqual(len(rows), len(task_ids))
        self.assertTrue(all(row["version"] == 1 for row in rows))
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_multirecord_write_preflights_and_doctor_finds_orphans(self) -> None:
        self.run_operator("init")
        self.run_operator("task-create", "--objective", "Preflight task", "--id", "preflight-task")
        op_path = Path(self.temp_dir) / ".operator"
        task_path = op_path / "tasks" / "preflight-task.yaml"
        original_task = task_path.read_text()
        changed_task = yaml.safe_load(original_task)
        changed_task["objective"] = "Changed outside the CLI"
        task_path.write_text(yaml.safe_dump(changed_task))

        res = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Must not be partially written",
            "--gate",
            "manual review",
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("differs from the durable ledger", res.stderr)
        self.assertEqual(list((op_path / "claims").glob("claim-*.yaml")), [])
        self.assertFalse(any(row["record_type"] == "claim" for row in self.read_ledger_events()))

        task_path.write_text(original_task)
        res = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Referenced claim",
            "--gate",
            "manual review",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        task_data = yaml.safe_load(task_path.read_text())
        task_data["claims"] = []
        task_path.write_text(yaml.safe_dump(task_data))
        self.rebaseline_ledger()
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "Claim claim-0001 is not referenced by owning task preflight-task", res.stdout
        )

    def test_evidence_cannot_cross_task_claim_boundaries(self) -> None:
        self.run_operator("init")
        self.run_operator("task-create", "--objective", "Task A", "--id", "task-a")
        self.run_operator("task-create", "--objective", "Task B", "--id", "task-b")
        self.run_operator(
            "claim-add",
            "--task",
            "task-b",
            "--type",
            "real_data",
            "--text",
            "Task B claim",
            "--gate",
            "manual review",
        )
        source = Path(self.temp_dir) / "cross-task.txt"
        source.write_text("evidence")

        res = self.run_operator(
            "evidence-attach",
            "--task",
            "task-a",
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            str(source),
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("belongs to task 'task-b', not 'task-a'", res.stderr)
        self.assertEqual(
            list((Path(self.temp_dir) / ".operator" / "evidence" / "task-a").glob("*")),
            [],
        )
        self.assertFalse(any(row["record_type"] == "evidence" for row in self.read_ledger_events()))
        self.assertEqual(self.run_operator("doctor").returncode, 0)

    def test_existing_yaml_ledger_bootstraps_on_init(self) -> None:
        self.run_operator("init")
        self.run_operator("task-create", "--objective", "Legacy YAML task", "--id", "legacy-task")
        self.rebaseline_ledger()

        rows = self.read_ledger_events()
        task_rows = [
            row
            for row in rows
            if row["record_type"] == "task" and row["record_id"] == "legacy-task"
        ]
        self.assertEqual(len(task_rows), 1)
        self.assertEqual(task_rows[0]["version"], 1)
        self.assertEqual(task_rows[0]["event_type"], "baseline_imported")
        self.assertEqual(task_rows[0]["source_command"], "legacy-bootstrap")

        res = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Post-migration claim",
            "--gate",
            "manual review",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_symlinked_operator_directory_keeps_event_logging_enabled(self) -> None:
        self.run_operator("init")
        original_operator_dir = Path(self.temp_dir) / ".operator"
        shared_ledger = Path(self.temp_dir) / "shared-ledger"
        original_operator_dir.rename(shared_ledger)

        workspace = Path(self.temp_dir) / "workspace"
        workspace.mkdir()
        (workspace / ".operator").symlink_to(shared_ledger, target_is_directory=True)
        os.chdir(workspace)

        res = self.run_operator(
            "task-create", "--objective", "Symlinked ledger", "--id", "symlink-task"
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        conn = sqlite3.connect(shared_ledger / "ledger.sqlite3")
        try:
            task_event_count = conn.execute(
                """
                SELECT COUNT(*) FROM ledger_events
                WHERE record_type = 'task' AND record_id = 'symlink-task'
                """
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(task_event_count, 1)
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)

    def test_task_ids_cannot_escape_the_ledger_layout(self) -> None:
        self.run_operator("init")
        for task_id in ("../escaped-task", "nested/task", ".hidden-task"):
            res = self.run_operator(
                "task-create", "--objective", "Invalid task ID", "--id", task_id
            )
            self.assertEqual(res.returncode, 1)
            self.assertIn("Task ID must start with an alphanumeric character", res.stderr)

        op_path = Path(self.temp_dir) / ".operator"
        self.assertFalse((op_path / "escaped-task.yaml").exists())
        self.assertFalse((op_path / "tasks" / "nested" / "task.yaml").exists())
        self.assertEqual(self.run_operator("doctor").returncode, 0)

    def test_lookup_ids_cannot_escape_the_ledger_layout(self) -> None:
        self.run_operator("init")
        self.run_operator("task-create", "--objective", "Safe task", "--id", "safe-task")
        op_path = Path(self.temp_dir) / ".operator"

        victim_task_id = str(Path(self.temp_dir) / "victim-task")
        victim_task_path = Path(f"{victim_task_id}.yaml")
        victim_task_path.write_text(
            yaml.safe_dump(
                {
                    "task_id": victim_task_id,
                    "objective": "Outside the ledger",
                    "claims": [],
                }
            )
        )
        original_task = victim_task_path.read_text()
        res = self.run_operator(
            "claim-add",
            "--task",
            victim_task_id,
            "--type",
            "real_data",
            "--text",
            "Must not touch an external task file",
            "--gate",
            "manual review",
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Task ID must start with an alphanumeric character", res.stderr)
        self.assertEqual(victim_task_path.read_text(), original_task)
        self.assertEqual(list((op_path / "claims").glob("claim-*.yaml")), [])

        safe_task_path = op_path / "tasks" / "safe-task.yaml"
        original_safe_task = safe_task_path.read_text()
        mismatched_task = yaml.safe_load(original_safe_task)
        mismatched_task["task_id"] = "different-task"
        safe_task_path.write_text(yaml.safe_dump(mismatched_task))
        res = self.run_operator(
            "claim-add",
            "--task",
            "safe-task",
            "--type",
            "real_data",
            "--text",
            "Must reject a mismatched task projection",
            "--gate",
            "manual review",
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("contains mismatched task_id 'different-task'", res.stderr)
        self.assertEqual(list((op_path / "claims").glob("claim-*.yaml")), [])
        safe_task_path.write_text(original_safe_task)

        victim_claim_id = str(Path(self.temp_dir) / "victim-claim")
        victim_claim_path = Path(f"{victim_claim_id}.yaml")
        victim_claim_path.write_text(
            yaml.safe_dump(
                {
                    "claim_id": victim_claim_id,
                    "task_id": "safe-task",
                    "text": "Outside the ledger",
                    "evidence_refs": [],
                }
            )
        )
        original_claim = victim_claim_path.read_text()
        evidence_source = Path(self.temp_dir) / "proof.txt"
        evidence_source.write_text("proof")
        res = self.run_operator(
            "evidence-attach",
            "--task",
            "safe-task",
            "--claim",
            victim_claim_id,
            "--type",
            "manifest",
            str(evidence_source),
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Claim ID must use the form claim-NNNN", res.stderr)
        self.assertEqual(victim_claim_path.read_text(), original_claim)
        self.assertEqual(list((op_path / "evidence" / "safe-task").glob("*")), [])
        self.assertFalse(
            any(row["record_type"] in {"claim", "evidence"} for row in self.read_ledger_events())
        )
        self.assertEqual(self.run_operator("doctor").returncode, 0)

    def test_session_end_rejects_unsafe_task_id_embedded_in_usage(self) -> None:
        self.run_operator("init")
        op_path = Path(self.temp_dir) / ".operator"

        victim_task_id = str(Path(self.temp_dir) / "victim-session-task")
        victim_task_path = Path(f"{victim_task_id}.yaml")
        victim_task_path.write_text(
            yaml.safe_dump({"task_id": victim_task_id, "status": "running"})
        )
        original_task = victim_task_path.read_text()

        usage_path = op_path / "usage" / "legacy.yaml"
        usage_path.write_text(
            yaml.safe_dump(
                [
                    {
                        "usage_id": "usage-9999",
                        "task_id": victim_task_id,
                        "started_at": "2026-01-01T00:00:00Z",
                        "ended_at": None,
                    }
                ]
            )
        )
        original_usage = usage_path.read_text()

        res = self.run_operator(
            "session-end",
            "usage-9999",
            "--outcome",
            "partial",
            "--cost",
            "1.0",
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("Task ID must start with an alphanumeric character", res.stderr)
        self.assertEqual(victim_task_path.read_text(), original_task)
        self.assertEqual(usage_path.read_text(), original_usage)
        self.assertFalse(any(row["record_type"] == "usage" for row in self.read_ledger_events()))

    def test_atomic_projection_writes_preserve_file_modes(self) -> None:
        self.run_operator("init")
        self.run_operator("task-create", "--objective", "Shared ledger mode", "--id", "shared-mode")
        op_path = Path(self.temp_dir) / ".operator"
        task_path = op_path / "tasks" / "shared-mode.yaml"
        task_path.chmod(0o660)
        original_stat = task_path.stat()

        res = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Preserve projection mode",
            "--gate",
            "manual review",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        updated_stat = task_path.stat()
        self.assertEqual(stat.S_IMODE(updated_stat.st_mode), 0o660)
        self.assertEqual(
            (updated_stat.st_uid, updated_stat.st_gid), (original_stat.st_uid, original_stat.st_gid)
        )

        current_umask = os.umask(0)
        os.umask(current_umask)
        expected_new_mode = 0o666 & ~current_umask
        claim_path = op_path / "claims" / "claim-0001.yaml"
        self.assertEqual(stat.S_IMODE(claim_path.stat().st_mode), expected_new_mode)

    def test_newer_event_store_schema_fails_closed(self) -> None:
        self.run_operator("init")
        db_path = Path(self.temp_dir) / ".operator" / "ledger.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA user_version = 2")
        finally:
            conn.close()

        res = self.run_operator("init")
        self.assertEqual(res.returncode, 1)
        self.assertIn("schema version 2 is newer", res.stderr)
        conn = sqlite3.connect(db_path)
        try:
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 2)
        finally:
            conn.close()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("schema version 2 is unsupported", res.stdout)

    def test_task_lifecycle_and_quarantine_flow(self) -> None:
        # 1. Initialize
        self.run_operator("init")

        # 2. Create Task
        res = self.run_operator(
            "task-create",
            "--objective",
            "Audit the PROX-HIL-002 real-data claim",
            "--id",
            "prox-hil-002-audit",
            "--assign",
            "codex",
            "--review",
            "claude",
            "--assumption",
            "Session 3 physical-capture provenance is undocumented.",
        )
        self.assertEqual(res.returncode, 0, f"task-create failed: {res.stderr}")
        self.assertIn("Task 'prox-hil-002-audit' created successfully", res.stdout)

        # Verify files on disk
        op_path = Path(self.temp_dir) / ".operator"
        task_file = op_path / "tasks" / "prox-hil-002-audit.yaml"
        self.assertTrue(task_file.exists())

        # 3. Show Task (Active defaults)
        res = self.run_operator("task-show")
        self.assertEqual(res.returncode, 0, f"task-show failed: {res.stderr}")
        self.assertIn("Task ID:          prox-hil-002-audit", res.stdout)
        self.assertIn("Objective:        Audit the PROX-HIL-002 real-data claim", res.stdout)
        self.assertIn("Status:           assigned", res.stdout)
        self.assertIn("Session 3 physical-capture provenance is undocumented.", res.stdout)

        # 4. Add Claim
        res = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "PROX-HIL-002 validates real sensor data.",
            "--gate",
            "data provenance chain",
        )
        self.assertEqual(res.returncode, 0, f"claim-add failed: {res.stderr}")
        self.assertIn("Registered claim 'claim-0001'", res.stdout)
        self.assertTrue((op_path / "claims" / "claim-0001.yaml").exists())

        # 5. Show Claim (Initial)
        res = self.run_operator("claim-show", "claim-0001")
        self.assertEqual(res.returncode, 0, f"claim-show failed: {res.stderr}")
        self.assertIn("Claim ID:            claim-0001", res.stdout)
        self.assertIn("Verification status: UNVERIFIED", res.stdout)
        self.assertIn("Required Gate:       data provenance chain", res.stdout)

        # Create dummy evidence file
        evidence_file = Path(self.temp_dir) / "manifest.json"
        evidence_file.write_text('{"session": 3, "source": "replay"}')

        # 6. Attach Evidence and Quarantine Claim
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            "--status",
            "quarantined",
            "--verified-by",
            "claude",
            "--verdict",
            "Session 3 is database replay with undocumented provenance, not real-data evidence.",
            str(evidence_file),
        )
        self.assertEqual(res.returncode, 0, f"evidence-attach failed: {res.stderr}")
        self.assertIn("Attached evidence 'evidence-0001'", res.stdout)

        evidence_record_path = op_path / "evidence" / "prox-hil-002-audit" / "evidence-0001.yaml"
        evidence_record = yaml.safe_load(evidence_record_path.read_text())
        expected_hash = hashlib.sha256(evidence_file.read_bytes()).hexdigest()
        self.assertEqual(evidence_record.get("hash"), expected_hash)

        # 7. Verify Claim status has updated to quarantined
        res = self.run_operator("claim-show", "claim-0001")
        self.assertIn("Verification status: QUARANTINED", res.stdout)
        self.assertIn(
            "Verdict:             Session 3 is database replay with undocumented provenance",
            res.stdout,
        )

        # 8. Verify Task status has updated to quarantined
        res = self.run_operator("task-show")
        self.assertIn("Status:           quarantined", res.stdout)

        # 9. Generate and verify Brief
        res = self.run_operator("brief", "--for", "codex")
        self.assertEqual(res.returncode, 0, f"brief failed: {res.stderr}")
        self.assertIn("Target Harness:** Codex", res.stdout)
        self.assertIn("claim-0001", res.stdout)
        self.assertIn("quarantined", res.stdout)

        # 10. Record Usage
        stdin_usage = "/status\nOllama running: gemma4:26b\nContext: 8k/16k"
        res = self.run_operator(
            "usage-add",
            "--harness",
            "codex",
            "--model",
            "gemma4:26b",
            "--cost",
            "0.05",
            "--outcome",
            "useful",
            stdin_data=stdin_usage,
        )
        self.assertEqual(res.returncode, 0, f"usage-add failed: {res.stderr}")
        self.assertIn("Usage record 'usage-0001' successfully added", res.stdout)

        # 11. Run Usage Summary
        res = self.run_operator("usage-summary", "--by-task")
        self.assertEqual(res.returncode, 0, f"usage-summary failed: {res.stderr}")
        self.assertIn("Total Estimated Cost: $0.0500 USD", res.stdout)
        self.assertIn("useful: 1", res.stdout)
        self.assertIn("SUMMARY BY TASK", res.stdout)
        self.assertIn("Task ID:      prox-hil-002-audit", res.stdout)

        res = self.run_operator("usage-summary", "--by-harness")
        self.assertEqual(res.returncode, 0, f"usage-summary --by-harness failed: {res.stderr}")
        self.assertIn("SUMMARY BY HARNESS", res.stdout)
        self.assertIn("Harness ID:   codex", res.stdout)

        res = self.run_operator("usage-summary", "--by-model")
        self.assertEqual(res.returncode, 0, f"usage-summary --by-model failed: {res.stderr}")
        self.assertIn("SUMMARY BY MODEL", res.stdout)
        self.assertIn("Model ID:     gemma4:26b", res.stdout)

        # 12. Add Handoff
        res = self.run_operator(
            "handoff-add",
            "--changed",
            "Audit notes documented",
            "--verified",
            "Session 3 data is database replay",
            "--claimed",
            "None",
            "--open",
            "Provenance is undocumented",
            "--assumptions",
            "None",
            "--next-action",
            "Replay proximity data on physical bench",
        )
        self.assertEqual(res.returncode, 0, f"handoff-add failed: {res.stderr}")
        self.assertIn("Successfully recorded handoff 'handoff-0001'", res.stdout)

        handoff_file = op_path / "handoffs" / "prox-hil-002-audit" / "handoff-0001.yaml"
        handoff_record = yaml.safe_load(handoff_file.read_text())
        self.assertEqual(handoff_record.get("what_verified"), "Session 3 data is database replay")
        self.assertEqual(
            handoff_record.get("next_action"), "Replay proximity data on physical bench"
        )

        # 13. Add Handoff from YAML file
        yaml_handoff_file = Path(self.temp_dir) / "handoff.yaml"
        yaml_handoff_file.write_text(
            "what_changed: Added file-loaded handoff\n"
            "what_verified: YAML handoff parsing works\n"
            "next_action: Review file-loaded handoff\n"
        )
        res = self.run_operator("handoff-add", "--file", str(yaml_handoff_file))
        self.assertEqual(res.returncode, 0, f"handoff-add --file failed: {res.stderr}")
        self.assertIn("Successfully recorded handoff 'handoff-0002'", res.stdout)

        # 14. Add Handoff from stdin YAML
        stdin_handoff = (
            "what_changed: Added stdin handoff\n"
            "what_verified: Stdin handoff parsing works\n"
            "next_action: Review stdin handoff\n"
        )
        res = self.run_operator("handoff-add", "--file", "-", stdin_data=stdin_handoff)
        self.assertEqual(res.returncode, 0, f"handoff-add --file - failed: {res.stderr}")
        self.assertIn("Successfully recorded handoff 'handoff-0003'", res.stdout)

        # 15. Reject invalid and empty handoff payloads
        res = self.run_operator("handoff-add", "--file", "-", stdin_data="- not\n- a mapping\n")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("must be a YAML mapping/object", res.stderr)

        res = self.run_operator("handoff-add", "--file", "-", stdin_data="{}\n")
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Handoff is empty", res.stderr)

        # Verify that task-show includes the handoff and updated next action
        res = self.run_operator("task-show")
        self.assertEqual(res.returncode, 0, f"task-show with handoffs failed: {res.stderr}")
        self.assertIn("Handoffs:", res.stdout)
        self.assertIn("handoffs/prox-hil-002-audit/handoff-0001.yaml", res.stdout)
        self.assertIn("handoffs/prox-hil-002-audit/handoff-0002.yaml", res.stdout)
        self.assertIn("handoffs/prox-hil-002-audit/handoff-0003.yaml", res.stdout)
        self.assertIn("Next Action:      Review stdin handoff", res.stdout)

        # 16. Generate and verify brief using handoff state
        res = self.run_operator("brief", "--for", "claude")
        self.assertEqual(res.returncode, 0, f"brief with handoffs failed: {res.stderr}")
        self.assertIn("Latest Harness Handoff Closeout", res.stdout)
        self.assertIn("Added stdin handoff", res.stdout)
        self.assertIn("Recommended Next Action:** `Review stdin handoff`", res.stdout)

    def test_doctor_next_action_warning_respects_task_status(self) -> None:
        # The next_action-mismatch warning is operational guidance for in-flight
        # work. Once a task is verified/complete, its next_action has
        # legitimately moved past the last handoff, so doctor must stay silent.
        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Next-action status guard",
            "--id",
            "next-action-task",
        )

        res = self.run_operator(
            "handoff-add",
            "--changed",
            "Work logged",
            "--next-action",
            "Replay proximity data on physical bench",
        )
        self.assertEqual(res.returncode, 0, f"handoff-add failed: {res.stderr}")

        op_path = Path(self.temp_dir) / ".operator"
        task_file = op_path / "tasks" / "next-action-task.yaml"

        # Task has since moved its own next_action away from the handoff's.
        task_data = yaml.safe_load(task_file.read_text())
        task_data["next_action"] = "Ship the paper"
        task_data["status"] = "running"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)
        self.rebaseline_ledger()

        # In-flight: the divergence is worth flagging.
        res = self.run_operator("doctor")
        self.assertIn("next_action differs", res.stdout)

        # Terminal statuses: the divergence is expected, so doctor stays silent.
        for terminal_status in ("verified", "complete"):
            task_data["status"] = terminal_status
            with open(task_file, "w") as f:
                yaml.safe_dump(task_data, f)
            self.rebaseline_ledger()
            res = self.run_operator("doctor")
            self.assertNotIn(
                "next_action differs",
                res.stdout,
                f"doctor must not warn on next_action for a '{terminal_status}' task",
            )

    def test_doctor_diagnostic_rules(self) -> None:
        import yaml

        self.run_operator("init")

        self.run_operator(
            "task-create",
            "--objective",
            "Test task for doctor",
            "--id",
            "doctor-test-task",
        )

        res = self.run_operator("claim-add", "--type", "real_data", "--text", "Doctor claim test.")
        self.assertEqual(res.returncode, 0)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("has no required_gate defined", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"
        claim_file = op_path / "claims" / "claim-0001.yaml"

        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["required_gate"] = "test gate"
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

        claim_data["evidence_refs"] = ["evidence/doctor-test-task/missing-evidence.yaml"]
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("evidence reference points to missing file", res.stdout)

        claim_data["evidence_refs"] = []
        claim_data["verification_outcome"] = "quarantined"
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        task_file = op_path / "tasks" / "doctor-test-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        task_data["status"] = "verified"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("while claims are quarantined: claim-0001", res.stdout)

        # Inverse rule: a task may not be quarantined while a claim under it is
        # still marked verified. This is the mirror of the check above and
        # guards against quarantining a task without retracting its claims.
        claim_data["verification_outcome"] = "verified"
        claim_data["verification_status"] = True
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        task_data["status"] = "quarantined"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "is quarantined while claims are still marked verified: claim-0001",
            res.stdout,
        )

        # Retracting the claim verdict to match the quarantined task clears the
        # inconsistency entirely (task quarantined + claim quarantined is valid).
        claim_data["verification_outcome"] = "quarantined"
        claim_data["verification_status"] = False
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertNotIn("still marked verified", res.stdout)

        claim_data["verification_outcome"] = None
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        task_data["status"] = "assigned"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)
        self.rebaseline_ledger()

        self.run_operator("handoff-add", "--changed", "test changed", "--next-action", "Action A")
        task_data = yaml.safe_load(task_file.read_text())
        task_data["next_action"] = "Action B"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "next_action differs from the latest handoff recommended next action",
            res.stdout,
        )

    def test_supervision_credit_layer_fr12(self) -> None:
        """FR-12: supervision_credit claims must name a layer or be flagged ambiguous."""
        import yaml

        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Supervision layer enforcement",
            "--id",
            "fr12-task",
        )

        # A supervision_credit claim with no --layer is accepted but warns.
        res = self.run_operator(
            "claim-add",
            "--type",
            "supervision_credit",
            "--text",
            "Claude supervised this work.",
            "--gate",
            "explicit supervision layer",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("has no --layer", res.stderr)

        op_path = Path(self.temp_dir) / ".operator"
        claim_file = op_path / "claims" / "claim-0001.yaml"
        claim_data = yaml.safe_load(claim_file.read_text())
        self.assertIsNone(claim_data.get("supervision_layer"))

        # doctor flags the ambiguous credit, and claim-show surfaces it.
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("supervision_credit with no named layer", res.stdout)

        res = self.run_operator("claim-show", "claim-0001")
        self.assertIn("Supervision Layer:   AMBIGUOUS (no layer)", res.stdout)

        # Naming the layer clears the flag and is shown verbatim.
        claim_data["supervision_layer"] = "end_to_end"
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertNotIn("no named layer", res.stdout)

        res = self.run_operator("claim-show", "claim-0001")
        self.assertIn("Supervision Layer:   end_to_end", res.stdout)

        # The --layer choice set is enforced at the CLI boundary.
        res = self.run_operator(
            "claim-add",
            "--type",
            "supervision_credit",
            "--text",
            "Bad layer value.",
            "--gate",
            "explicit supervision layer",
            "--layer",
            "not_a_layer",
        )
        self.assertNotEqual(res.returncode, 0)

        # A supervision_credit claim created with a valid --layer stores it directly.
        res = self.run_operator(
            "claim-add",
            "--type",
            "supervision_credit",
            "--text",
            "Codex supervised execution.",
            "--gate",
            "explicit supervision layer",
            "--layer",
            "execution",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertNotIn("has no --layer", res.stderr)
        claim2 = yaml.safe_load((op_path / "claims" / "claim-0002.yaml").read_text())
        self.assertEqual(claim2.get("supervision_layer"), "execution")

    def test_session_start(self) -> None:
        import yaml

        self.run_operator("init")

        self.run_operator(
            "task-create",
            "--objective",
            "Verify session start flow",
            "--id",
            "session-test-task",
            "--assign",
            "claude",
        )

        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0, f"session-start failed: {res.stderr}")
        self.assertIn("SESSION INITIALIZED: session-test-task", res.stdout)
        self.assertIn("Usage placeholder recorded: usage-0001", res.stdout)
        self.assertIn("Paste instructions:", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"

        # Verify export brief exists
        brief_file = op_path / "briefs" / "session-test-task.claude.export.md"
        self.assertTrue(brief_file.exists())
        self.assertIn("Verify session start flow", brief_file.read_text())

        # Verify usage placeholder file exists
        import datetime

        utc_now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{utc_now_date}.yaml"
        self.assertTrue(usage_file.exists())

        usage_records = yaml.safe_load(usage_file.read_text())
        self.assertEqual(len(usage_records), 1)
        rec = usage_records[0]
        self.assertEqual(rec.get("usage_id"), "usage-0001")
        self.assertEqual(rec.get("task_id"), "session-test-task")
        self.assertEqual(rec.get("harness_id"), "claude")
        self.assertEqual(rec.get("outcome"), "unknown")
        self.assertIsNone(rec.get("ended_at"))

        # Verify task status is updated to running
        task_file = op_path / "tasks" / "session-test-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

    def test_session_lifecycle(self) -> None:
        import datetime

        import yaml

        self.run_operator("init")

        # 1. Create task
        self.run_operator(
            "task-create",
            "--objective",
            "Verify session lifecycle flow",
            "--id",
            "lifecycle-test-task",
            "--assign",
            "claude",
        )

        # 2. Start session
        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Usage placeholder recorded: usage-0001", res.stdout)

        # Verify task is running
        op_path = Path(self.temp_dir) / ".operator"
        task_file = op_path / "tasks" / "lifecycle-test-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

        # 3. Duplicate session-start fails without --force
        res2 = self.run_operator("session-start", "--harness", "claude")
        self.assertNotEqual(res2.returncode, 0)
        self.assertIn("is already running. Use --force to override.", res2.stderr)

        # 4. Duplicate session-start succeeds with --force
        res3 = self.run_operator("session-start", "--harness", "claude", "--force")
        self.assertEqual(res3.returncode, 0)
        self.assertIn("Usage placeholder recorded: usage-0002", res3.stdout)

        # 5. End session (using --usage alias)
        # We end usage-0001
        res4 = self.run_operator(
            "session-end",
            "--usage",
            "usage-0001",
            "--outcome",
            "useful",
            "--cost",
            "0.05",
            stdin_data="/status Notes on run",
        )
        self.assertEqual(res4.returncode, 0, res4.stderr)
        self.assertIn("Successfully closed usage session 'usage-0001'", res4.stdout)

        # Verify usage record update
        utc_now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{utc_now_date}.yaml"
        usage_records = yaml.safe_load(usage_file.read_text())

        rec1 = next(r for r in usage_records if r["usage_id"] == "usage-0001")
        self.assertEqual(rec1.get("outcome"), "useful")
        self.assertEqual(rec1.get("cost_estimate_usd"), 0.05)
        self.assertIsNotNone(rec1.get("ended_at"))
        self.assertEqual(rec1.get("raw_payload"), "/status Notes on run")

        # 6. Re-ending usage-0001 fails without --force
        res5 = self.run_operator(
            "session-end", "usage-0001", "--outcome", "useful", "--cost", "0.05"
        )
        self.assertNotEqual(res5.returncode, 0)
        self.assertIn("is already closed", res5.stderr)

        # 7. Re-ending usage-0001 succeeds with --force
        res6 = self.run_operator(
            "session-end",
            "usage-0001",
            "--outcome",
            "partial",
            "--cost",
            "0.10",
            "--force",
        )
        self.assertEqual(res6.returncode, 0, res6.stderr)

        # Verify task remains running because forced usage-0002 is still open.
        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

        res_doctor = self.run_operator("doctor")
        self.assertEqual(res_doctor.returncode, 0, res_doctor.stdout)

        # 8. Close the forced duplicate and verify the task defaults back to assigned.
        res7 = self.run_operator(
            "session-end", "usage-0002", "--outcome", "partial", "--cost", "0.00"
        )
        self.assertEqual(res7.returncode, 0, res7.stderr)

        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "assigned")

        # 9. Start again to test explicit status closeout
        res8 = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res8.returncode, 0)
        self.assertIn("Usage placeholder recorded: usage-0003", res8.stdout)

        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "running")

        # End and set status to complete
        res9 = self.run_operator(
            "session-end",
            "usage-0003",
            "--outcome",
            "useful",
            "--cost",
            "0.12",
            "--status",
            "complete",
        )
        self.assertEqual(res9.returncode, 0, res9.stderr)

        task_data = yaml.safe_load(task_file.read_text())
        self.assertEqual(task_data.get("status"), "complete")

    def test_session_list_open_and_filters(self) -> None:
        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Verify session-list reporting",
            "--id",
            "session-list-task",
            "--assign",
            "claude",
        )

        # No sessions yet.
        res = self.run_operator("session-list")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions found in ledger.", res.stdout)

        # Start a session -> one open session.
        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)

        # session-list shows usage-0001 marked open while the session is active.
        res = self.run_operator("session-list")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("open", res.stdout)

        # --open surfaces the active session (the core blind spot this command fixes).
        res = self.run_operator("session-list", "--open")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("open", res.stdout)
        self.assertNotIn("closed", res.stdout)

        # Close it.
        res = self.run_operator(
            "session-end", "usage-0001", "--outcome", "useful", "--cost", "0.05"
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # --open now matches nothing; plain list shows the closed session.
        res = self.run_operator("session-list", "--open")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions matched the filters.", res.stdout)

        res = self.run_operator("session-list")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("closed", res.stdout)

        # Open a second session: --open must discriminate the live one from the closed one.
        res = self.run_operator("session-start", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("session-list", "--open")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0002", res.stdout)
        self.assertNotIn("usage-0001", res.stdout)

        # --task filter: matching task returns both, unknown task returns none.
        res = self.run_operator("session-list", "--task", "session-list-task")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        self.assertIn("usage-0002", res.stdout)

        res = self.run_operator("session-list", "--task", "nonexistent-task")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions matched the filters.", res.stdout)

        # --harness filter: claude matches, codex does not.
        res = self.run_operator("session-list", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)

        res = self.run_operator("session-list", "--harness", "codex")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("No sessions matched the filters.", res.stdout)

    def test_usage_add_file_payload_fidelity(self) -> None:
        import datetime

        self.run_operator("init")
        self.run_operator(
            "task-create",
            "--objective",
            "Verify usage payload fidelity",
            "--id",
            "payload-fidelity-task",
            "--assign",
            "copilot",
        )

        # Payload contains a "$0.00" that a shell would mangle to "bash.00" via
        # $0 expansion. The --file capture path must store it verbatim.
        payload = "Copilot Chat session.\nEstimated cost: $0.00 (Copilot flat rate subscription)."
        payload_file = Path(self.temp_dir) / "usage_payload.txt"
        payload_file.write_text(payload)

        res = self.run_operator(
            "usage-add",
            "--harness",
            "copilot",
            "--model",
            "copilot-chat",
            "--cost",
            "0.0",
            "--outcome",
            "useful",
            "--file",
            str(payload_file),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Usage record 'usage-0001' successfully added", res.stdout)

        op_path = Path(self.temp_dir) / ".operator"
        utc_now_date = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{utc_now_date}.yaml"
        records = yaml.safe_load(usage_file.read_text())
        rec = records[0]

        # Regression guard for the stored "bash.00" corruption.
        self.assertEqual(rec.get("raw_payload"), payload)
        self.assertIn("$0.00", rec.get("raw_payload"))
        self.assertNotIn("bash.00", rec.get("raw_payload"))

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_machine_provenance_and_by_machine_summary(self) -> None:
        import datetime
        import socket

        self.run_operator("init")
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        op_path = Path(self.temp_dir) / ".operator"
        shutil.copy(fixtures_dir / "pricing.yaml", op_path / "pricing.yaml")

        res = self.run_operator(
            "task-create",
            "--objective",
            "Test machine provenance",
            "--id",
            "machine-task",
            "--repo",
            str(Path(self.temp_dir) / "project-phoenix"),
            "--assign",
            "claude",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        payload_file = Path(self.temp_dir) / "payload.txt"
        payload_file.write_text("machine provenance payload")

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{today}.yaml"

        # 1. usage-import --source-dir + --machine: provenance is the producer,
        # not the importer (synced-logs-from-another-machine path). The session
        # placeholder is the only unmatched record, so matching is deterministic.
        res = self.run_operator("session-start", "--task", "machine-task", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)
        data = yaml.safe_load(usage_file.read_text())
        for r in data:
            if r.get("usage_id") == "usage-0001":
                r["started_at"] = "2026-05-29T06:00:00Z"
        usage_file.write_text(yaml.safe_dump(data))
        self.rebaseline_ledger()

        res = self.run_operator(
            "usage-import",
            "--harness",
            "claude",
            "--task",
            "machine-task",
            "--source-dir",
            str(fixtures_dir / "claude"),
            "--machine",
            "z13-test",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("usage-0001", res.stdout)
        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0001")
        self.assertEqual(rec["executor"]["machine"], "z13-test")
        self.assertEqual(rec["executor"]["machine_source"], "manual")

        # 2. OPERATOR_MACHINE override stamps the executor on new records.
        res = self.run_operator(
            "usage-add",
            "--harness",
            "claude",
            "--model",
            "claude-opus-4-8",
            "--cost",
            "0.0",
            "--outcome",
            "useful",
            "--file",
            str(payload_file),
            env={"OPERATOR_MACHINE": "desktop-test"},
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0002")
        self.assertEqual(rec["executor"]["machine"], "desktop-test")

        # 3. Without override, machine defaults to the short hostname.
        res = self.run_operator(
            "usage-add",
            "--harness",
            "claude",
            "--model",
            "claude-opus-4-8",
            "--cost",
            "0.0",
            "--outcome",
            "useful",
            "--file",
            str(payload_file),
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0003")
        expected_host = socket.gethostname().split(".")[0] or "unknown"
        self.assertEqual(rec["executor"]["machine"], expected_host)

        # 4. A missing --source-dir path fails loudly, not silently.
        res = self.run_operator(
            "usage-import",
            "--harness",
            "claude",
            "--task",
            "machine-task",
            "--source-dir",
            str(Path(self.temp_dir) / "does-not-exist"),
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("--source-dir path does not exist", res.stderr)

        # 5. --by-machine groups executor provenance.
        res = self.run_operator("usage-summary", "--by-machine")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("SUMMARY BY MACHINE × HARNESS", res.stdout)
        self.assertIn("desktop-test", res.stdout)
        self.assertIn("z13-test", res.stdout)

    def test_usage_autoimport_and_annotation(self) -> None:
        import datetime

        self.run_operator("init")

        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        op_path = Path(self.temp_dir) / ".operator"

        # Copy the pricing.yaml table so that pricing rate lookup succeeds in test environment.
        # Sourced from tests/fixtures/ (not the gitignored runtime .operator/ ledger) so the
        # suite is self-contained on a clean clone.
        shutil.copy(fixtures_dir / "pricing.yaml", op_path / "pricing.yaml")

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{today}.yaml"

        def adjust_start_time(usage_id, new_start):
            data = yaml.safe_load(usage_file.read_text())
            for r in data:
                if r.get("usage_id") == usage_id:
                    r["started_at"] = new_start
            usage_file.write_text(yaml.safe_dump(data))
            self.rebaseline_ledger()

        # 1. Claude import testing
        res = self.run_operator(
            "task-create",
            "--objective",
            "Test Claude import",
            "--id",
            "claude-task",
            "--repo",
            str(Path(self.temp_dir) / "project-phoenix"),
            "--assign",
            "claude",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("session-start", "--task", "claude-task", "--harness", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)
        adjust_start_time("usage-0001", "2026-05-29T06:00:00Z")

        env_claude = {"OPERATOR_TEST_CLAUDE_DIR": str(fixtures_dir / "claude")}
        res = self.run_operator(
            "usage-import",
            "--harness",
            "claude",
            "--task",
            "claude-task",
            env=env_claude,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("Successfully imported usage record", res.stdout)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0001")
        self.assertEqual(rec["harness_id"], "claude")
        self.assertEqual(rec["model"], "claude-opus-4-8")
        self.assertEqual(rec["metering"], "tokens")
        self.assertEqual(rec["tokens_in"], 3272)
        self.assertEqual(rec["tokens_out"], 2839)
        self.assertEqual(rec["tokens_cache_read"], 9105)
        self.assertEqual(rec["tokens_cache_write"], 12958)
        self.assertEqual(rec["activity"]["tool_calls"], 3)
        self.assertEqual(rec["activity"]["turns"], 2)
        self.assertEqual(rec["field_sources"]["tokens_in"], "auto")
        self.assertAlmostEqual(rec["cost_estimate_usd"], 0.5186, places=4)

        # 2. Codex import testing
        res = self.run_operator(
            "task-create",
            "--objective",
            "Test Codex import",
            "--id",
            "codex-task",
            "--repo",
            str(Path(self.temp_dir) / "project-phoenix"),
            "--assign",
            "codex",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("session-start", "--task", "codex-task", "--harness", "codex")
        self.assertEqual(res.returncode, 0, res.stderr)
        adjust_start_time("usage-0002", "2026-05-29T06:00:00Z")

        env_codex = {"OPERATOR_TEST_CODEX_DIR": str(fixtures_dir / "codex")}
        res = self.run_operator(
            "usage-import", "--harness", "codex", "--task", "codex-task", env=env_codex
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0002")
        self.assertEqual(rec["harness_id"], "codex")
        self.assertEqual(rec["model"], "gpt-5.5")
        self.assertEqual(rec["metering"], "tokens")
        self.assertEqual(rec["tokens_in"], 11000)
        self.assertEqual(rec["tokens_cache_read"], 4000)
        self.assertEqual(rec["tokens_out"], 800)
        self.assertEqual(rec["activity"]["turns"], 2)
        self.assertEqual(rec["activity"]["tool_calls"], 1)
        self.assertEqual(rec["cost_estimate_usd"], 0.0)

        # 3. Gemini-Agy import testing
        res = self.run_operator(
            "task-create",
            "--objective",
            "Test Gemini-Agy import",
            "--id",
            "agy-task",
            "--assign",
            "gemini-agy",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("session-start", "--task", "agy-task", "--harness", "gemini-agy")
        self.assertEqual(res.returncode, 0, res.stderr)
        adjust_start_time("usage-0003", "2026-05-29T06:00:00Z")

        env_gemini = {"OPERATOR_TEST_GEMINI_DIR": str(fixtures_dir / "gemini")}
        res = self.run_operator(
            "usage-import",
            "--harness",
            "gemini-agy",
            "--task",
            "agy-task",
            "--session-id",
            "agy-test-brain",
            env=env_gemini,
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["harness_id"], "gemini-agy")
        self.assertEqual(rec["model"], "configured-gemini-model")
        self.assertEqual(rec["metering"], "activity")
        self.assertEqual(rec["tokens_in"], None)
        self.assertEqual(rec["cost_estimate_usd"], None)
        self.assertEqual(rec["activity"]["turns"], 2)
        self.assertEqual(rec["activity"]["tool_calls"], 3)
        self.assertEqual(rec["activity"]["quota_events"], 2)

        # 4. Idempotency test
        res = self.run_operator(
            "usage-import",
            "--harness",
            "gemini-agy",
            "--task",
            "agy-task",
            "--session-id",
            "agy-test-brain",
            env=env_gemini,
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        records = yaml.safe_load(usage_file.read_text())
        self.assertEqual(len(records), 3)

        # 5. Manual override / usage-annotate
        res = self.run_operator(
            "usage-annotate",
            "usage-0003",
            "--cost",
            "1.50",
            "--active-start",
            "2026-05-29T12:00:00Z",
            "--active-end",
            "2026-05-29T12:05:00Z",
            "--quota-events",
            "5",
            "--note",
            "Annotated notes",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        records = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in records if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["cost_estimate_usd"], 1.50)
        self.assertEqual(rec["activity"]["active_s"], 300)
        self.assertEqual(rec["activity"]["quota_events"], 5)
        self.assertEqual(rec["field_sources"]["cost_estimate_usd"], "manual")
        self.assertEqual(rec["field_sources"]["active_s"], "manual")
        self.assertEqual(rec["field_sources"]["quota_events"], "manual")
        self.assertEqual(rec["auto_values"]["quota_events"], 2)
        self.assertEqual(rec["raw_payload"], "Annotated notes")

        # 6. Usage summary --metering test
        res = self.run_operator("usage-summary", "--metering", "--by-harness")
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn("TOKENS-METERED", res.stdout)
        self.assertIn("ACTIVITY-METERED", res.stdout)
        self.assertIn("Harness ID:   claude", res.stdout)
        self.assertIn("Harness ID:   gemini-agy", res.stdout)
        self.assertIn("Turns:", res.stdout)
        self.assertIn("not cross-comparable", res.stdout)

        # 7. Doctor warnings/errors tests
        res = self.run_operator("doctor")
        self.assertIn("manual/auto divergence on quota_events", res.stdout)

    def test_verified_by_guard_integrity(self) -> None:
        import yaml

        self.run_operator("init")

        # Create task: assign=codex, review=claude
        res = self.run_operator(
            "task-create",
            "--objective",
            "Verify the guard",
            "--id",
            "guard-task",
            "--assign",
            "codex",
            "--review",
            "claude",
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # Add claim
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "A test claim",
            "--gate",
            "test-gate",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        # Create the gate file
        gate_file = Path(self.temp_dir) / "test-gate"
        gate_file.write_text("mock gate content")

        evidence_file = Path(self.temp_dir) / "test_evidence.txt"
        evidence_file.write_text("dummy evidence content")

        # 4. missing --verified-by rejected: evidence-attach --status verified (no --verified-by) -> exits non-zero, claim unchanged
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            str(evidence_file),
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("Error: --verified-by is required when setting --status", res.stderr)

        claim_file = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim_data = yaml.safe_load(claim_file.read_text())
        self.assertFalse(claim_data.get("verification_status"))
        self.assertIsNone(claim_data.get("verified_by"))

        # Helper helper function to set claim status/verified-by
        def update_claim(status_val, verifier):
            # We overwrite by running evidence-attach again
            return self.run_operator(
                "evidence-attach",
                "--claim",
                "claim-0001",
                "--type",
                "test_output",
                "--status",
                status_val,
                "--verified-by",
                verifier,
                "--verify-cmd",
                "pytest",
                str(evidence_file),
            )

        # 1. self-verify blocked by doctor: verified_by == made_by (codex) -> doctor exits 1 with Error
        res = update_claim("verified", "codex")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("[Error] claim claim-0001 is self-verified by 'codex'", res.stdout)

        # 3. wrong verifier warns: --verified-by gemini-agy (not review_harness claude) -> doctor warns, exits 1
        res = update_claim("verified", "gemini-agy")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn(
            "[Warning] claim claim-0001 verified by 'gemini-agy', not the task's review harness 'claude'",
            res.stdout,
        )
        self.assertNotIn("[Error] claim claim-0001 is self-verified", res.stdout)

        # 2. reviewer verify clean: --verified-by claude -> doctor clean (exit 0)
        res = update_claim("verified", "claude")
        self.assertEqual(res.returncode, 0, res.stderr)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

        # 5. legacy is Info, not failure: hand-write a claim with verification_status: true and no verified_by -> doctor prints Info and exits 0
        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["verification_status"] = True
        claim_data["verification_outcome"] = "verified"
        claim_data.pop("verified_by", None)
        for field in (
            "author_executor",
            "verification_executor",
            "verification_authority",
            "verification_mode",
        ):
            claim_data.pop(field, None)
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("[Info] Claim claim-0001 has unknown verifier (legacy claim)", res.stdout)

    def test_executor_identity_binding(self) -> None:
        import yaml

        self.run_operator("init")

        # 1. executor stamped: any write records executor.uid / executor.user
        res = self.run_operator("task-create", "--objective", "Test executor", "--id", "exec-task")
        self.assertEqual(res.returncode, 0, res.stderr)
        task_file = Path(self.temp_dir) / ".operator" / "tasks" / "exec-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        self.assertIn("executor", task_data)
        self.assertIn("uid", task_data["executor"])
        self.assertIn("user", task_data["executor"])

        # 2. derive + match: identity map with mode: enforced
        identity_file = Path(self.temp_dir) / ".operator" / "identity.yaml"
        identity_file.write_text(
            "mode: enforced\n" "uids:\n" "  1001: gemini-agy\n" "  1002: claude\n"
        )

        # Create a claim under the task
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "Test claim",
            "--gate",
            "test-gate",
            env={"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        # Create the gate file
        gate_file = Path(self.temp_dir) / "test-gate"
        gate_file.write_text("mock gate content")

        claim_file = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        evidence_file = Path(self.temp_dir) / "test_ev.txt"
        evidence_file.write_text("ev content")

        # Simulated uid 1002 setting status verified using test override and sentinel
        env_claude = {"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"}
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            "--verify-cmd",
            "pytest",
            str(evidence_file),
            env=env_claude,
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # Check claim verifier and executor block
        claim_data = yaml.safe_load(claim_file.read_text())
        self.assertEqual(claim_data.get("verified_by"), "claude")
        self.assertEqual(claim_data.get("executor", {}).get("uid"), 1002)

        # Doctor error when mapping is enforced but override active flag is on
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("contains write made with test-override active", res.stdout)

        # Hand-modify both claim and evidence to clear test_override_active for testing doctor mismatch checks
        for field in ("executor", "author_executor", "verification_executor"):
            claim_data[field]["test_override_active"] = False
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        ev_file = (
            Path(self.temp_dir) / ".operator" / "evidence" / "exec-task" / "evidence-0001.yaml"
        )
        ev_data = yaml.safe_load(ev_file.read_text())
        ev_data["executor"]["test_override_active"] = False
        with open(ev_file, "w") as f:
            yaml.safe_dump(ev_data, f)
        self.rebaseline_ledger()

        # Now doctor should be clean
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)

        # 3. mismatch rejected: simulated uid 1001 trying to verify as claude -> error
        env_gemini = {"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"}
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence_file),
            env=env_gemini,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("does not match the executing identity", res.stderr)

        # 4. unknown uid fails closed: uid not in map -> error
        env_unknown = {"OPERATOR_TEST_UID": "9999", "OPERATOR_TEST_SENTINEL": "1"}
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence_file),
            env=env_unknown,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertIn("is not a known identity", res.stderr)

        # 5. doctor impersonation catch: hand-write a mismatch -> Error
        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["verified_by"] = "claude"
        claim_data["verification_status"] = True
        claim_data["verification_outcome"] = "verified"
        claim_data["executor"] = {"uid": 1001, "user": "gemini-agy"}
        claim_data["verification_executor"] = {"uid": 1001, "user": "gemini-agy"}
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        self.rebaseline_ledger()

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("verification identity mismatch", res.stdout)

        # 6. Policy changes remain visible without relabeling the recorded authority.
        identity_file.write_text(
            "mode: single_user\n" "uids:\n" "  1001: gemini-agy\n" "  1002: claude\n"
        )
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1, res.stdout)
        self.assertIn("current identity policy is single_user", res.stdout)

        # 7. test-hook guard: a ledger write made under OPERATOR_TEST_UID without the test sentinel -> doctor Error
        env_spoof = {"OPERATOR_TEST_UID": "1002"}
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "Spoof claim",
            "--gate",
            "test-gate",
            env=env_spoof,
        )
        self.assertEqual(res.returncode, 0)

        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1)
        self.assertIn("contains write with unauthorized test-override attempt", res.stdout)

    def test_p2_structured_roles_record_distinct_uid_authority_without_execution(self) -> None:
        _, evidence = self.setup_p2_enforced_claim()
        builder_env = {"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"}
        verifier_env = {"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"}

        draft = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            str(evidence),
            env=builder_env,
        )
        self.assertEqual(draft.returncode, 0, draft.stderr)

        sentinel = Path(self.temp_dir) / "verification-command-ran"
        verified = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            "--verify-cmd",
            f"touch {sentinel}",
            str(evidence),
            env=verifier_env,
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)

        claim_path = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim = yaml.safe_load(claim_path.read_text())
        self.assertEqual(claim["author_executor"]["uid"], 1001)
        self.assertEqual(claim["verification_executor"]["uid"], 1002)
        self.assertEqual(claim["verification_authority"], "uid_isolated")
        self.assertEqual(claim["verification_mode"], "enforced")
        self.assertEqual(claim["verified_by"], "claude")

        claim_event_rows = [
            row
            for row in self.read_ledger_events()
            if row["record_type"] == "claim" and row["record_id"] == "claim-0001"
        ]
        claim_events = [json.loads(row["payload_json"]) for row in claim_event_rows]
        self.assertEqual(claim_events[-1]["verification_authority"], "uid_isolated")
        self.assertEqual(claim_events[-1]["author_executor"]["uid"], 1001)
        self.assertEqual(claim_events[-1]["verification_executor"]["uid"], 1002)
        self.assertEqual(claim_event_rows[-1]["actor_uid"], 1002)
        self.assertFalse(sentinel.exists())

        shown = self.run_operator("claim-show", "claim-0001")
        self.assertEqual(shown.returncode, 0, shown.stderr)
        self.assertIn("Authority:           uid_isolated", shown.stdout)
        self.assertIn("Author Executor:      uid 1001", shown.stdout)
        self.assertIn("Verifier Executor:    uid 1002", shown.stdout)

        doctor = self.run_operator("doctor")
        self.assertEqual(doctor.returncode, 1, doctor.stdout)
        self.assertIn("test-override active", doctor.stdout)
        self.assertRegex(doctor.stdout.lower(), r"uid[-_]isolated")
        self.assertFalse(sentinel.exists())

    def test_p2_status_rejections_are_atomic(self) -> None:
        _, evidence = self.setup_p2_enforced_claim(
            {
                1001: {"name": "codex", "roles": ["builder", "verifier"]},
                1002: {"name": "claude", "roles": ["verifier"]},
                1003: {"name": "observer", "roles": []},
            }
        )

        attempts = [
            (
                {"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"},
                "codex",
                ("uid", "differ"),
            ),
            (
                {"OPERATOR_TEST_UID": "9999", "OPERATOR_TEST_SENTINEL": "1"},
                "unknown",
                ("known", "uid"),
            ),
            (
                {"OPERATOR_TEST_UID": "1003", "OPERATOR_TEST_SENTINEL": "1"},
                "observer",
                ("verifier", "role"),
            ),
            (
                {"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"},
                "not-claude",
                ("does not match", "identity"),
            ),
        ]
        for env, verifier, expected_words in attempts:
            with self.subTest(verifier=verifier):
                before = self.trust_state_snapshot()
                result = self.run_operator(
                    "evidence-attach",
                    "--claim",
                    "claim-0001",
                    "--type",
                    "test_output",
                    "--status",
                    "verified",
                    "--verified-by",
                    verifier,
                    str(evidence),
                    env=env,
                )
                self.assertNotEqual(result.returncode, 0)
                diagnostic = (result.stdout + result.stderr).lower()
                for word in expected_words:
                    self.assertIn(word, diagnostic)
                self.assertEqual(self.trust_state_snapshot(), before)

        claim_path = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim = yaml.safe_load(claim_path.read_text())
        claim.pop("author_executor")
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()
        before = self.trust_state_snapshot()
        legacy_author = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
            env={"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertNotEqual(legacy_author.returncode, 0)
        self.assertIn("author uid", (legacy_author.stdout + legacy_author.stderr).lower())
        self.assertEqual(self.trust_state_snapshot(), before)

        claim = yaml.safe_load(claim_path.read_text())
        claim["author_executor"] = {"uid": -1, "user": "invalid"}
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()
        before = self.trust_state_snapshot()
        negative_author = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
            env={"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertNotEqual(negative_author.returncode, 0)
        self.assertIn("valid author uid", negative_author.stderr.lower())
        self.assertEqual(self.trust_state_snapshot(), before)

    def test_p2_verifier_only_uid_cannot_use_builder_paths(self) -> None:
        self.assertEqual(self.run_operator("init").returncode, 0)
        task = self.run_operator(
            "task-create",
            "--objective",
            "P2 role boundary",
            "--id",
            "p2-task",
            "--assign",
            "codex",
            "--review",
            "claude",
        )
        self.assertEqual(task.returncode, 0, task.stderr)
        self.write_identity_registry(
            "enforced",
            {
                1001: {"name": "codex", "roles": ["builder"]},
                1002: {"name": "claude", "roles": ["verifier"]},
            },
        )
        verifier_env = {"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"}

        before = self.trust_state_snapshot()
        claim = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Verifier must not author this claim",
            "--gate",
            "manual review",
            env=verifier_env,
        )
        self.assertNotEqual(claim.returncode, 0)
        self.assertIn("builder role", (claim.stdout + claim.stderr).lower())
        self.assertEqual(self.trust_state_snapshot(), before)

        builder = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Builder claim",
            "--gate",
            "manual review",
            env={"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertEqual(builder.returncode, 0, builder.stderr)
        evidence = Path(self.temp_dir) / "draft.txt"
        evidence.write_text("draft")
        before = self.trust_state_snapshot()
        attached = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            str(evidence),
            env=verifier_env,
        )
        self.assertNotEqual(attached.returncode, 0)
        self.assertIn("builder role", (attached.stdout + attached.stderr).lower())
        self.assertEqual(self.trust_state_snapshot(), before)

    def test_p2_malformed_identity_policy_fails_closed(self) -> None:
        self.assertEqual(self.run_operator("init").returncode, 0)
        self.assertEqual(
            self.run_operator(
                "task-create",
                "--objective",
                "P2 malformed identity policy",
                "--id",
                "p2-policy",
            ).returncode,
            0,
        )
        identity_path = Path(self.temp_dir) / ".operator" / "identity.yaml"
        identity_path.write_text(
            "mode: enforced\n" "uids:\n" "  1001:\n" "    name: codex\n" "    roles: builder\n"
        )

        before = self.trust_state_snapshot()
        result = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Malformed policy must not authorize",
            "--gate",
            "manual review",
            env={"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("invalid identity policy", result.stderr.lower())
        self.assertEqual(self.trust_state_snapshot(), before)

        doctor = self.run_operator("doctor")
        self.assertEqual(doctor.returncode, 1, doctor.stdout)
        self.assertIn("invalid identity policy", doctor.stdout.lower())

        identity_path.write_text("mode: enforced\n" "uids:\n" "  1001: codex\n" "  1001: claude\n")
        before = self.trust_state_snapshot()
        duplicate = self.run_operator(
            "claim-add",
            "--type",
            "real_data",
            "--text",
            "Duplicate policy keys must not authorize",
            "--gate",
            "manual review",
            env={"OPERATOR_TEST_UID": "1001", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("duplicate key", duplicate.stderr.lower())
        self.assertEqual(self.trust_state_snapshot(), before)

        duplicate_doctor = self.run_operator("doctor")
        self.assertEqual(duplicate_doctor.returncode, 1, duplicate_doctor.stdout)
        self.assertIn("duplicate key", duplicate_doctor.stdout.lower())

    def test_p2_single_user_verification_is_explicitly_advisory(self) -> None:
        self.assertEqual(self.run_operator("init").returncode, 0)
        task = self.run_operator(
            "task-create",
            "--objective",
            "P2 advisory mode",
            "--id",
            "p2-advisory",
            "--assign",
            "codex",
            "--review",
            "claude",
        )
        self.assertEqual(task.returncode, 0, task.stderr)
        claim = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "Advisory verification remains usable",
            "--gate",
            "test-gate",
        )
        self.assertEqual(claim.returncode, 0, claim.stderr)
        (Path(self.temp_dir) / "test-gate").write_text("gate")
        evidence = Path(self.temp_dir) / "advisory.txt"
        evidence.write_text("advisory")
        sentinel = Path(self.temp_dir) / "advisory-command-ran"

        result = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            "--verify-cmd",
            f"touch {sentinel}",
            str(evidence),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        claim_path = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim_data = yaml.safe_load(claim_path.read_text())
        self.assertEqual(claim_data["verification_authority"], "advisory")
        self.assertNotEqual(claim_data["verification_authority"], "uid_isolated")
        self.assertEqual(claim_data["verification_mode"], "single_user")
        self.assertEqual(
            claim_data["author_executor"]["uid"],
            claim_data["verification_executor"]["uid"],
        )
        self.assertFalse(sentinel.exists())

        doctor = self.run_operator("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
        self.assertIn("advisory", doctor.stdout.lower())
        self.assertFalse(sentinel.exists())

        false_result = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "false",
            "--verified-by",
            "claude",
            str(evidence),
        )
        self.assertEqual(false_result.returncode, 0, false_result.stderr)
        claim_data = yaml.safe_load(claim_path.read_text())
        self.assertEqual(claim_data["verification_outcome"], "false")
        self.assertEqual(claim_data["verification_authority"], "advisory")
        false_doctor = self.run_operator("doctor")
        self.assertEqual(false_doctor.returncode, 0, false_doctor.stdout)
        self.assertIn("advisory", false_doctor.stdout.lower())
        self.assertFalse(sentinel.exists())

    def test_p2_legacy_scalar_registry_remains_usable(self) -> None:
        _, evidence = self.setup_p2_enforced_claim({1001: "codex", 1002: "claude"})
        result = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
            env={"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        claim_path = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim = yaml.safe_load(claim_path.read_text())
        self.assertEqual(claim["author_executor"]["uid"], 1001)
        self.assertEqual(claim["verification_executor"]["uid"], 1002)
        self.assertEqual(claim["verification_authority"], "uid_isolated")

    def test_p2_legacy_claim_remains_nonfatal_and_advisory(self) -> None:
        self.assertEqual(self.run_operator("init").returncode, 0)
        self.assertEqual(
            self.run_operator(
                "task-create",
                "--objective",
                "P2 legacy claim",
                "--id",
                "p2-legacy",
                "--assign",
                "codex",
                "--review",
                "claude",
            ).returncode,
            0,
        )
        self.assertEqual(
            self.run_operator(
                "claim-add",
                "--type",
                "real_data",
                "--text",
                "Legacy claim remains readable",
                "--gate",
                "manual review",
            ).returncode,
            0,
        )
        evidence = Path(self.temp_dir) / "legacy.txt"
        evidence.write_text("legacy")
        verified = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "manifest",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
        )
        self.assertEqual(verified.returncode, 0, verified.stderr)
        claim_path = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim = yaml.safe_load(claim_path.read_text())
        for field in (
            "author_executor",
            "verification_executor",
            "verification_authority",
            "verification_mode",
        ):
            claim.pop(field, None)
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()

        doctor = self.run_operator("doctor")
        self.assertEqual(doctor.returncode, 0, doctor.stdout)
        self.assertIn("legacy", doctor.stdout.lower())
        self.assertIn("advisory", doctor.stdout.lower())

        self.write_identity_registry("enforced", {1002: {"name": "claude", "roles": ["verifier"]}})
        enforced_doctor = self.run_operator("doctor")
        self.assertEqual(enforced_doctor.returncode, 0, enforced_doctor.stdout)
        self.assertIn("legacy", enforced_doctor.stdout.lower())
        self.assertIn("remains advisory", enforced_doctor.stdout.lower())

    def test_p2_doctor_distinguishes_valid_malformed_and_test_override_authority(self) -> None:
        self.assertEqual(self.run_operator("init").returncode, 0)
        self.assertEqual(
            self.run_operator(
                "task-create",
                "--objective",
                "P2 doctor authority",
                "--id",
                "p2-doctor",
                "--assign",
                "codex",
                "--review",
                "claude",
            ).returncode,
            0,
        )
        self.assertEqual(
            self.run_operator(
                "claim-add",
                "--type",
                "real_data",
                "--text",
                "Doctor classifies authority",
                "--gate",
                "manual review",
            ).returncode,
            0,
        )
        evidence = Path(self.temp_dir) / "doctor-authority.txt"
        evidence.write_text("authority")
        self.assertEqual(
            self.run_operator(
                "evidence-attach",
                "--claim",
                "claim-0001",
                "--type",
                "manifest",
                "--status",
                "verified",
                "--verified-by",
                "claude",
                str(evidence),
            ).returncode,
            0,
        )
        self.write_identity_registry("enforced", {1001: "codex", 1002: "claude"})
        claim_path = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        claim = yaml.safe_load(claim_path.read_text())
        claim.update(
            {
                "made_by": "codex",
                "verified_by": "claude",
                "author_executor": {"uid": 1001, "user": "uid-1001"},
                "verification_executor": {"uid": 1002, "user": "uid-1002"},
                "verification_authority": "uid_isolated",
                "verification_mode": "enforced",
                "executor": {"uid": 1002, "user": "uid-1002"},
            }
        )
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()

        valid = self.run_operator("doctor")
        self.assertEqual(valid.returncode, 0, valid.stdout)
        self.assertIn("[Info]", valid.stdout)
        self.assertRegex(valid.stdout.lower(), r"uid[-_]isolated")

        claim = yaml.safe_load(claim_path.read_text())
        claim["executor"]["uid"] = 1001
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()
        contradictory = self.run_operator("doctor")
        self.assertEqual(contradictory.returncode, 1, contradictory.stdout)
        self.assertIn("compatibility executor uid", contradictory.stdout.lower())
        self.assertIn("disagrees", contradictory.stdout.lower())

        claim = yaml.safe_load(claim_path.read_text())
        claim["executor"]["uid"] = 1002
        claim["verification_outcome"] = "false"
        claim["verification_status"] = False
        claim["verification_executor"]["uid"] = 1001
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()
        same_uid = self.run_operator("doctor")
        self.assertEqual(same_uid.returncode, 1, same_uid.stdout)
        self.assertIn("same author and verifier uid", same_uid.stdout.lower())

        claim = yaml.safe_load(claim_path.read_text())
        claim["verification_executor"]["uid"] = 9999
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()
        unregistered = self.run_operator("doctor")
        self.assertEqual(unregistered.returncode, 1, unregistered.stdout)
        self.assertIn("unregistered verifier uid", unregistered.stdout.lower())

        claim = yaml.safe_load(claim_path.read_text())
        claim["verification_executor"]["uid"] = 1002
        claim["verification_mode"] = "single_user"
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()
        malformed = self.run_operator("doctor")
        self.assertEqual(malformed.returncode, 1, malformed.stdout)
        self.assertRegex(malformed.stdout.lower(), r"uid[-_]isolated")
        self.assertIn("enforced", malformed.stdout.lower())

        claim = yaml.safe_load(claim_path.read_text())
        claim["verification_mode"] = "enforced"
        claim["author_executor"]["test_override_active"] = True
        claim_path.write_text(yaml.safe_dump(claim, sort_keys=False))
        self.rebaseline_ledger()
        overridden = self.run_operator("doctor")
        self.assertEqual(overridden.returncode, 1, overridden.stdout)
        self.assertIn("test-override active", overridden.stdout)

    def test_doctor_flags_enforcement_downgrade(self) -> None:
        # A configured identity map left in single_user mode silently accepts claims that
        # enforced mode would reject as impersonation. doctor must surface that relaxation
        # (warn-only: it stays exit 0, but the downgrade is no longer invisible).
        import yaml

        self.run_operator("init")
        self.run_operator("task-create", "--objective", "Downgrade check", "--id", "dg-task")
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "a claim",
            "--gate",
            "test-gate",
        )
        self.assertEqual(res.returncode, 0, res.stderr)
        # Create the gate file
        gate_file = Path(self.temp_dir) / "test-gate"
        gate_file.write_text("mock gate content")

        # Attach evidence + a clean verification (single_user is the default mode here).
        evidence_file = Path(self.temp_dir) / "ev.txt"
        evidence_file.write_text("evidence")
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            "--verify-cmd",
            "pytest",
            str(evidence_file),
        )
        self.assertEqual(res.returncode, 0, res.stderr)

        # Configure an identity map but leave enforcement relaxed to single_user.
        identity_file = Path(self.temp_dir) / ".operator" / "identity.yaml"
        identity_file.write_text("mode: single_user\nuids:\n  1001: gemini-agy\n  1002: claude\n")

        claim_file = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"

        def set_executor(uid: int, user: str) -> None:
            data = yaml.safe_load(claim_file.read_text())
            data["executor"] = {"uid": uid, "user": user}
            data["verification_executor"] = {"uid": uid, "user": user}
            claim_file.write_text(yaml.safe_dump(data))
            self.rebaseline_ledger()

        # Mismatch: executor maps to gemini-agy (uid 1001) but verified_by is claude.
        # enforced mode would reject this; single_user accepts it -> doctor must warn, exit 0.
        set_executor(1001, "gemini-agy")
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertIn("would be REJECTED under enforced mode", res.stdout)
        self.assertIn("enforcement appears relaxed to single_user", res.stdout)

        # Control: executor maps to claude (uid 1002), matching verified_by -> no downgrade warning.
        set_executor(1002, "claude")
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout)
        self.assertNotIn("would be REJECTED under enforced mode", res.stdout)

    def test_status_requires_claim(self) -> None:
        # A bare evidence-attach with --status but no --claim must fail closed: status is only ever
        # recorded on a claim, so without one it would silently drop, leaving the operator thinking
        # trust advanced when it did not.
        self.run_operator("init")
        self.run_operator("task-create", "--objective", "gate", "--id", "g-task")
        evidence = Path(self.temp_dir) / "ev.txt"
        evidence.write_text("evidence")

        res = self.run_operator(
            "evidence-attach",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
        )
        self.assertNotEqual(res.returncode, 0, "bare --status with no --claim should fail closed")
        self.assertIn("--status requires --claim", res.stderr)

        # Control: the same write WITH a claim succeeds.
        self.run_operator("claim-add", "--type", "test_passes", "--text", "a claim", "--gate", "g")
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            "--status",
            "verified",
            "--verified-by",
            "claude",
            str(evidence),
        )
        self.assertEqual(res.returncode, 0, res.stderr)

    def test_usage_lane_tagging(self) -> None:
        import datetime

        import yaml

        self.run_operator("init")
        fixtures_dir = Path(__file__).resolve().parent / "fixtures"
        op_path = Path(self.temp_dir) / ".operator"
        shutil.copy(fixtures_dir / "pricing.yaml", op_path / "pricing.yaml")

        today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        usage_file = op_path / "usage" / f"{today}.yaml"

        # 1. session-start with lane/class
        res = self.run_operator("task-create", "--objective", "tagging", "--id", "t-tagging")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator(
            "session-start",
            "--task",
            "t-tagging",
            "--harness",
            "claude",
            "--lane",
            "frontier_author",
            "--class",
            "bounded",
        )
        self.assertEqual(res.returncode, 0)

        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0001")
        self.assertEqual(rec["lane"], "frontier_author")
        self.assertEqual(rec["task_class"], "bounded")
        self.assertEqual(rec.get("field_sources", {}).get("lane"), "manual")
        self.assertEqual(rec.get("field_sources", {}).get("task_class"), "manual")

        # End usage-0001 so it's not left open
        res = self.run_operator(
            "session-end",
            "usage-0001",
            "--outcome",
            "useful",
            "--cost",
            "0.0",
            "--status",
            "complete",
        )
        self.assertEqual(res.returncode, 0)

        # 2. usage-add with lane/class
        payload_file = Path(self.temp_dir) / "payload.txt"
        payload_file.write_text("dummy usage payload")
        res = self.run_operator(
            "usage-add",
            "--harness",
            "gemini-agy",
            "--task",
            "t-tagging",
            "--lane",
            "local",
            "--class",
            "bounded",
            "--cost",
            "0.0",
            "--file",
            str(payload_file),
        )
        self.assertEqual(res.returncode, 0)

        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0002")
        self.assertEqual(rec["lane"], "local")
        self.assertEqual(rec["task_class"], "bounded")

        # 3. usage-import defaults untagged lane to unknown, without brand inference.
        # Create a task for claude-import
        res = self.run_operator("task-create", "--objective", "claude-imp", "--id", "claude-task")
        self.assertEqual(res.returncode, 0)
        res = self.run_operator("session-start", "--task", "claude-task", "--harness", "claude")
        self.assertEqual(res.returncode, 0)

        # Update started_at of usage-0003 so that autoimport matches it
        data = yaml.safe_load(usage_file.read_text())
        for r in data:
            if r["usage_id"] == "usage-0003":
                r["started_at"] = "2026-05-29T06:00:00Z"
        usage_file.write_text(yaml.safe_dump(data))
        self.rebaseline_ledger()

        env_claude = {"OPERATOR_TEST_CLAUDE_DIR": str(fixtures_dir / "claude")}
        res = self.run_operator(
            "usage-import",
            "--harness",
            "claude",
            "--task",
            "claude-task",
            env=env_claude,
        )
        self.assertEqual(res.returncode, 0)

        # Set task status to complete to avoid doctor consistency warning (since session is closed)
        task_file = op_path / "tasks" / "claude-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        task_data["status"] = "complete"
        task_file.write_text(yaml.safe_dump(task_data))
        self.rebaseline_ledger()

        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["lane"], "unknown")
        self.assertEqual(rec["task_class"], "unknown")
        self.assertEqual(rec.get("field_sources", {}).get("lane"), "auto")
        self.assertEqual(rec.get("field_sources", {}).get("task_class"), "auto")

        # 4. usage-annotate override
        res = self.run_operator(
            "usage-annotate", "usage-0003", "--lane", "local", "--class", "hard"
        )
        self.assertEqual(res.returncode, 0)
        data = yaml.safe_load(usage_file.read_text())
        rec = next(r for r in data if r["usage_id"] == "usage-0003")
        self.assertEqual(rec["lane"], "local")
        self.assertEqual(rec["task_class"], "hard")
        self.assertEqual(rec.get("field_sources", {}).get("lane"), "manual")
        self.assertEqual(rec.get("field_sources", {}).get("task_class"), "manual")

        # 5. usage-summary --by-lane
        # Let's add another frontier_driver + bounded record to verify avoidable rollup and offload audit
        res = self.run_operator(
            "usage-add",
            "--harness",
            "codex",
            "--task",
            "t-tagging",
            "--lane",
            "frontier_driver",
            "--class",
            "bounded",
            "--cost",
            "1.50",
            "--file",
            str(payload_file),
        )
        self.assertEqual(res.returncode, 0)

        res = self.run_operator("usage-summary", "--by-lane")
        self.assertEqual(res.returncode, 0)
        self.assertIn("SUMMARY BY LANE × TASK_CLASS", res.stdout)
        self.assertIn("Lane:         frontier_author", res.stdout)
        self.assertIn("Task Class:   bounded", res.stdout)
        self.assertIn("Lane:         frontier_driver", res.stdout)
        self.assertIn("Avoidable Rollup Cost:", res.stdout)

        # 6. usage-summary --offload-audit
        # usage-0001 (frontier_author, bounded, cost 0.0) -> avoidable
        # usage-0002 (local, bounded, cost 0.0) -> ignored (starts with local)
        # usage-0003 (local, hard, cost 0.5186) -> ignored
        # usage-0004 (frontier_driver, bounded, cost 1.50) -> avoidable
        # Total frontier spend: usage-0001 ($0.0) + usage-0004 ($1.5) = $1.50
        # Avoidable spend: usage-0001 ($0.0) + usage-0004 ($1.5) = $1.50 (100.0%)
        res = self.run_operator("usage-summary", "--offload-audit")
        self.assertEqual(res.returncode, 0)
        self.assertIn("100.0% of frontier spend went to bounded work", res.stdout)

        # 7. doctor advisory check
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0)
        self.assertIn("is an offload candidate", res.stdout)

    def test_doctor_new_warnings(self) -> None:
        import yaml

        self.run_operator("init")

        # Create task with a nonexistent repo
        res = self.run_operator(
            "task-create",
            "--objective",
            "Test new doctor warnings",
            "--id",
            "warnings-task",
            "--repo",
            "/nonexistent/repo/dir",
        )
        self.assertEqual(res.returncode, 0)

        # Create claim under it
        res = self.run_operator(
            "claim-add",
            "--type",
            "test_passes",
            "--text",
            "Verified gate claim",
            "--gate",
            "missing-gate.py",
        )
        self.assertEqual(res.returncode, 0)

        claim_file = Path(self.temp_dir) / ".operator" / "claims" / "claim-0001.yaml"
        evidence_file = Path(self.temp_dir) / "test_ev.txt"
        evidence_file.write_text("ev content")

        # Attach evidence as draft (not verified)
        env_claude = {"OPERATOR_TEST_UID": "1002", "OPERATOR_TEST_SENTINEL": "1"}
        res = self.run_operator(
            "evidence-attach",
            "--claim",
            "claim-0001",
            "--type",
            "test_output",
            str(evidence_file),
            env=env_claude,
        )
        self.assertEqual(res.returncode, 0)

        # Clear test_override_active in claim
        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["executor"]["test_override_active"] = False
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        ev_file = (
            Path(self.temp_dir) / ".operator" / "evidence" / "warnings-task" / "evidence-0001.yaml"
        )
        # Let's customize the evidence file to use url_or_external provenance
        # with no hash/verification_command, and nonexistent path_or_url
        ev_file = (
            Path(self.temp_dir) / ".operator" / "evidence" / "warnings-task" / "evidence-0001.yaml"
        )
        ev_data = yaml.safe_load(ev_file.read_text())
        ev_data["provenance"] = "url_or_external"
        ev_data["hash"] = None
        ev_data["fingerprint"] = None
        ev_data["verification_command"] = None
        ev_data["path_or_url"] = (
            "relative/nonexistent/test_output.log"  # relative path to test CWD resolution
        )
        ev_data["source"] = {
            "kind": "external_reference",
            "locator": ev_data["path_or_url"],
        }
        ev_data["executor"]["test_override_active"] = False
        with open(ev_file, "w") as f:
            yaml.safe_dump(ev_data, f)

        task_file = Path(self.temp_dir) / ".operator" / "tasks" / "warnings-task.yaml"
        task_data = yaml.safe_load(task_file.read_text())
        task_data["evidence"] = [ev_data["path_or_url"]]
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)

        # Clear test_override_active in claim
        claim_data = yaml.safe_load(claim_file.read_text())
        claim_data["executor"]["test_override_active"] = False
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)

        self.rebaseline_ledger()

        # First Doctor check: Draft state -> all non-fatal warnings -> returns 0
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 0, res.stdout + "\n" + res.stderr)
        self.assertIn("Records consistent, but non-fatal warnings exist.", res.stdout)
        self.assertIn(
            "[Warning] Task warnings-task repo path does not exist on disk: /nonexistent/repo/dir",
            res.stdout,
        )
        self.assertIn(
            "[Warning] Claim claim-0001 draft test_passes required_gate file does not exist: missing-gate.py",
            res.stdout,
        )
        self.assertIn(
            "[Warning] Claim claim-0001 draft test_passes has no evidence reference with a verification_command.",
            res.stdout,
        )
        self.assertIn(
            "[Warning] Claim claim-0001 draft on unverifiable evidence: evidence/warnings-task/evidence-0001.yaml",
            res.stdout,
        )
        # Test CWD relative resolution check: resolves to /nonexistent/repo/dir/relative/nonexistent/test_output.log
        self.assertIn(
            "[Warning] Evidence evidence/warnings-task/evidence-0001.yaml test_output file does not exist: /nonexistent/repo/dir/relative/nonexistent/test_output.log",
            res.stdout,
        )

        # Now, mark the claim as verified
        claim_data["verification_outcome"] = "verified"
        claim_data["verification_status"] = True
        with open(claim_file, "w") as f:
            yaml.safe_dump(claim_data, f)
        self.rebaseline_ledger()

        # Second Doctor check: Verified claim -> checks escalate to Error -> returns 1 (failure)
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1, res.stdout + "\n" + res.stderr)
        self.assertIn(
            "[Error] Claim claim-0001 verified test_passes required_gate file does not exist: missing-gate.py",
            res.stdout,
        )
        self.assertIn(
            "[Error] Claim claim-0001 verified test_passes has no evidence reference with a verification_command.",
            res.stdout,
        )
        self.assertIn(
            "[Error] Claim claim-0001 verified on unverifiable evidence: evidence/warnings-task/evidence-0001.yaml",
            res.stdout,
        )
        self.assertIn(
            "[Error] Evidence evidence/warnings-task/evidence-0001.yaml test_output file does not exist: /nonexistent/repo/dir/relative/nonexistent/test_output.log",
            res.stdout,
        )
        # But repo path is still [Warning] because task is not verified/complete status
        self.assertIn(
            "[Warning] Task warnings-task repo path does not exist on disk: /nonexistent/repo/dir",
            res.stdout,
        )

        # Finally, mark the task status as complete
        task_data = yaml.safe_load(task_file.read_text())
        task_data["status"] = "complete"
        with open(task_file, "w") as f:
            yaml.safe_dump(task_data, f)
        self.rebaseline_ledger()

        # Third Doctor check: Verified task -> repo missing escalates to Error
        res = self.run_operator("doctor")
        self.assertEqual(res.returncode, 1, res.stdout + "\n" + res.stderr)
        self.assertIn(
            "[Error] Task warnings-task repo path does not exist on disk: /nonexistent/repo/dir",
            res.stdout,
        )


if __name__ == "__main__":
    unittest.main()
