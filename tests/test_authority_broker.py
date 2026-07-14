from __future__ import annotations

import concurrent.futures
import hashlib
import json
import multiprocessing
import os
import select
import shutil
import socket
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import authority_broker  # noqa: E402

BROKER_BIN = REPO_ROOT / "operator-broker"


def run_crashing_broker(
    store_path: str,
    content_dir: str,
    socket_path: str,
    ready_fd: int,
    committed_fd: int,
) -> None:
    store = authority_broker.AuthorityStore(Path(store_path), Path(content_dir))
    store.validate()

    def crash_after_commit(_receipt: dict) -> None:
        os.write(committed_fd, b"1")
        os.close(committed_fd)
        os._exit(86)

    server = authority_broker.BrokerServer(
        authority_broker.AuthorityBroker(store),
        Path(socket_path),
        after_commit=crash_after_commit,
        ready_fd=ready_fd,
    )
    server.serve_forever()


@unittest.skipUnless(
    hasattr(socket, "SO_PEERCRED"),
    "authority broker requires Linux SO_PEERCRED",
)
class TestAuthorityBroker(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = Path(tempfile.mkdtemp()).resolve()
        self.processes: list[subprocess.Popen[str]] = []
        self.child_processes: list[multiprocessing.Process] = []
        self.store_path = self.temp_dir / "authority.sqlite3"
        self.content_dir = self.temp_dir / "content"
        self.socket_path = self.temp_dir / "broker.sock"
        self.config_path = self.temp_dir / "bootstrap.json"
        self.request_index = 0
        self.request_lock = threading.Lock()

    def tearDown(self) -> None:
        for process in reversed(self.child_processes):
            if process.is_alive():
                process.terminate()
            process.join(timeout=5)
        for process in reversed(self.processes):
            self.stop_process(process)
        shutil.rmtree(self.temp_dir)

    def write_config(
        self,
        roles: dict[int, list[str]],
        *,
        ledger_ids: list[str] | None = None,
        path: Path | None = None,
    ) -> Path:
        config_path = path or self.config_path
        config_path.write_text(
            json.dumps(
                {
                    "policy_id": "standalone-policy",
                    "policy_generation": 1,
                    "ledgers": ledger_ids or ["ledger-test"],
                    "roles": {str(uid): uid_roles for uid, uid_roles in roles.items()},
                }
            )
        )
        return config_path

    def init_store(
        self,
        roles: dict[int, list[str]],
        *,
        ledger_ids: list[str] | None = None,
        store_path: Path | None = None,
        content_dir: Path | None = None,
        config_path: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        selected_store = store_path or self.store_path
        selected_content = content_dir or self.content_dir
        selected_config = self.write_config(roles, ledger_ids=ledger_ids, path=config_path)
        result = subprocess.run(
            [
                str(BROKER_BIN),
                "bootstrap-fixture",
                "--store",
                str(selected_store),
                "--content-dir",
                str(selected_content),
                "--bootstrap-config",
                str(selected_config),
            ],
            cwd=self.temp_dir,
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result

    def start_server(
        self,
        *,
        store_path: Path | None = None,
        content_dir: Path | None = None,
        socket_path: Path | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
    ) -> subprocess.Popen[str]:
        selected_store = store_path or self.store_path
        selected_content = content_dir or self.content_dir
        selected_socket = socket_path or self.socket_path
        read_fd, write_fd = os.pipe()
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        process = subprocess.Popen(
            [
                str(BROKER_BIN),
                "serve",
                "--store",
                str(selected_store),
                "--content-dir",
                str(selected_content),
                "--socket",
                str(selected_socket),
                "--ready-fd",
                str(write_fd),
            ],
            cwd=cwd or self.temp_dir,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            pass_fds=(write_fd,),
        )
        self.processes.append(process)
        os.close(write_fd)
        ready, _, _ = select.select([read_fd], [], [], 5)
        try:
            self.assertTrue(ready, "broker did not signal readiness")
            self.assertEqual(os.read(read_fd, 1), b"1")
        finally:
            os.close(read_fd)
        return process

    @staticmethod
    def stop_process(process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def claim_request(
        self,
        operation_key: str,
        *,
        claim_id: str = "claim-0001",
        task_id: str = "task-0001",
        text: str = "standalone authority claim",
    ) -> dict:
        return {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": operation_key,
            "operation": {
                "kind": "claim.create",
                "task_id": task_id,
                "claim_id": claim_id,
                "claim_type": "test_passes",
                "text": text,
                "required_gate": "tests/test_example.py",
            },
            "expected": [
                {
                    "record_type": "task",
                    "record_id": task_id,
                    "version": 0,
                    "event_hash": None,
                },
                {
                    "record_type": "claim",
                    "record_id": claim_id,
                    "version": 0,
                    "event_hash": None,
                },
            ],
        }

    def evidence_request(
        self,
        operation_key: str,
        task_head: dict,
        claim_head: dict,
        evidence_sha256: str,
        size_bytes: int,
        *,
        kind: str = "evidence.attach_draft",
        status: str | None = None,
        evidence_id: str = "evidence-0001",
    ) -> dict:
        operation = {
            "kind": kind,
            "task_id": "task-0001",
            "claim_id": "claim-0001",
            "evidence_id": evidence_id,
            "evidence_type": "test_output",
        }
        if status is not None:
            operation["verification_status"] = status
        return {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": operation_key,
            "operation": operation,
            "expected": [
                {
                    "record_type": "task",
                    "record_id": "task-0001",
                    "version": task_head["version"],
                    "event_hash": task_head["event_hash"],
                },
                {
                    "record_type": "claim",
                    "record_id": "claim-0001",
                    "version": claim_head["version"],
                    "event_hash": claim_head["event_hash"],
                },
                {
                    "record_type": "evidence",
                    "record_id": evidence_id,
                    "version": 0,
                    "event_hash": None,
                },
            ],
            "blob": {"sha256": evidence_sha256, "size_bytes": size_bytes},
        }

    def request(
        self,
        request: dict,
        *,
        socket_path: Path | None = None,
        cwd: Path | None = None,
        env: dict[str, str] | None = None,
        evidence_file: Path | None = None,
    ) -> tuple[int, subprocess.CompletedProcess[str], dict | None]:
        with self.request_lock:
            self.request_index += 1
            request_path = self.temp_dir / f"request-{self.request_index:04d}.json"
        request_path.write_text(json.dumps(request))
        run_env = os.environ.copy()
        if env:
            run_env.update(env)
        command = [
            str(BROKER_BIN),
            "request",
            "--socket",
            str(socket_path or self.socket_path),
            "--json",
            str(request_path),
        ]
        if evidence_file is not None:
            command.extend(["--evidence-file", str(evidence_file)])
        process = subprocess.Popen(
            command,
            cwd=cwd or self.temp_dir,
            env=run_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        stdout, stderr = process.communicate(timeout=10)
        completed = subprocess.CompletedProcess(
            process.args,
            process.returncode,
            stdout,
            stderr,
        )
        response = json.loads(stdout) if stdout.strip() else None
        return process.pid, completed, response

    def table_count(self, table: str, *, store_path: Path | None = None) -> int:
        conn = sqlite3.connect(store_path or self.store_path)
        try:
            return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        finally:
            conn.close()

    def test_root_enrollment_is_first_idempotent_broker_commit(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        identity = {
            "repository_path": str(self.temp_dir),
            "repository_device": 1,
            "repository_inode": 2,
            "operator_device": 1,
            "operator_inode": 3,
            "ledger_device": 1,
            "ledger_inode": 4,
        }
        anchors = [
            {
                "record_type": "task",
                "record_id": "legacy-task",
                "version": 2,
                "event_hash": "a" * 64,
            }
        ]
        request = {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": "enroll-test-ledger",
            "operation": {
                "kind": "ledger.enroll",
                "repository_identity": identity,
                "anchor_records": anchors,
                "legacy_anchor_sha256": authority_broker.sha256_text(
                    authority_broker.canonical_json(anchors)
                ),
            },
            "expected": [],
            "blob": None,
        }
        broker = authority_broker.AuthorityBroker(
            authority_broker.AuthorityStore(self.store_path, self.content_dir)
        )
        root_peer = authority_broker.PeerCredentials(123, 0, 0)
        response, committed = broker.handle(request, root_peer)
        self.assertTrue(committed)
        self.assertEqual(response["receipt"]["commit_sequence"], 1)
        self.assertEqual(response["receipt"]["operation"], "ledger.enroll")
        replay, committed = broker.handle(request, root_peer)
        self.assertFalse(committed)
        self.assertTrue(replay["idempotent_replay"])
        self.assertEqual(replay["receipt"], response["receipt"])

        with self.assertRaises(authority_broker.BrokerError) as caught:
            broker.handle(
                {**request, "operation_key": "enroll-not-root"},
                authority_broker.PeerCredentials(124, os.getuid(), os.getgid()),
            )
        self.assertEqual(caught.exception.code, "root_required")

    @staticmethod
    def event_for(receipt: dict, record_type: str) -> dict:
        return next(event for event in receipt["events"] if event["record_type"] == record_type)

    def test_authorization_uses_real_peer_credentials(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server(env={"OPERATOR_TEST_UID": "999999", "USER": "forged-server"})
        client_pid, completed, response = self.request(
            self.claim_request("real-peer-0001"),
            env={
                "OPERATOR_TEST_UID": "999998",
                "OPERATOR_TEST_SENTINEL": "1",
                "USER": "forged-client",
                "LOGNAME": "forged-client",
            },
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(response["ok"])
        actor = response["receipt"]["actor"]
        self.assertEqual(actor["pid"], client_pid)
        self.assertEqual(actor["uid"], os.getuid())
        self.assertEqual(actor["gid"], os.getgid())
        self.assertNotEqual(actor["uid"], 999998)

    def test_unknown_peer_and_wrong_role_are_rejected_without_commits(self) -> None:
        self.init_store({os.getuid() + 50000: ["builder"]})
        self.start_server()
        _, completed, response = self.request(self.claim_request("unknown-peer-0001"))
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "unknown_peer_uid")
        self.assertEqual(self.table_count("authority_commits"), 0)
        self.stop_process(self.processes.pop())

        second_store = self.temp_dir / "wrong-role.sqlite3"
        second_content = self.temp_dir / "wrong-role-content"
        second_socket = self.temp_dir / "wrong-role.sock"
        second_config = self.temp_dir / "wrong-role.json"
        self.init_store(
            {os.getuid(): ["builder"]},
            store_path=second_store,
            content_dir=second_content,
            config_path=second_config,
        )
        self.start_server(
            store_path=second_store,
            content_dir=second_content,
            socket_path=second_socket,
        )
        status_request = {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": "wrong-role-0001",
            "operation": {
                "kind": "evidence.attach_status",
                "task_id": "task-0001",
                "claim_id": "claim-0001",
                "evidence_id": "evidence-0001",
                "evidence_type": "test_output",
                "verification_status": "verified",
            },
            "expected": [
                {
                    "record_type": "task",
                    "record_id": "task-0001",
                    "version": 1,
                    "event_hash": "0" * 64,
                },
                {
                    "record_type": "claim",
                    "record_id": "claim-0001",
                    "version": 1,
                    "event_hash": "0" * 64,
                },
                {
                    "record_type": "evidence",
                    "record_id": "evidence-0001",
                    "version": 0,
                    "event_hash": None,
                },
            ],
            "blob": {"sha256": "0" * 64, "size_bytes": 0},
        }
        _, completed, response = self.request(status_request, socket_path=second_socket)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "missing_role")
        self.assertEqual(self.table_count("authority_commits", store_path=second_store), 0)

    def test_fixture_bootstrap_rejects_unknown_roles(self) -> None:
        self.write_config({os.getuid(): ["administrator"]})
        result = subprocess.run(
            [
                str(BROKER_BIN),
                "bootstrap-fixture",
                "--store",
                str(self.store_path),
                "--content-dir",
                str(self.content_dir),
                "--bootstrap-config",
                str(self.config_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stderr)["error"]["code"], "invalid_bootstrap")
        self.assertFalse(self.store_path.exists())

    def test_identical_retry_is_idempotent_and_changed_replay_is_rejected(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server()
        request = self.claim_request("retry-0001")

        first_pid, first_completed, first = self.request(request)
        second_pid, second_completed, second = self.request(request)
        self.assertEqual(first_completed.returncode, 0, first_completed.stderr)
        self.assertEqual(second_completed.returncode, 0, second_completed.stderr)
        self.assertNotEqual(first_pid, second_pid)
        self.assertFalse(first["idempotent_replay"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(first["receipt"], second["receipt"])
        self.assertEqual(first["receipt"]["actor"]["pid"], first_pid)
        self.assertEqual(self.table_count("authority_commits"), 1)
        self.assertEqual(self.table_count("authority_events"), 2)
        self.assertEqual(self.table_count("projection_outbox"), 1)
        self.assertEqual(self.table_count("authority_blobs"), 0)

        changed = self.claim_request("retry-0001", text="changed replay payload")
        _, changed_completed, changed_response = self.request(changed)
        self.assertNotEqual(changed_completed.returncode, 0)
        self.assertEqual(changed_response["error"]["code"], "operation_key_conflict")
        self.assertEqual(self.table_count("authority_commits"), 1)
        self.assertEqual(self.table_count("authority_events"), 2)
        self.assertEqual(self.table_count("projection_outbox"), 1)

        rejected = self.claim_request(
            "reject-then-retry-0001",
            claim_id="claim-0002",
            task_id="task-0002",
        )
        rejected["expected"][0]["version"] = 1
        rejected["expected"][0]["event_hash"] = "0" * 64
        _, rejected_completed, rejected_response = self.request(rejected)
        self.assertNotEqual(rejected_completed.returncode, 0)
        self.assertEqual(rejected_response["error"]["code"], "stale_record")

        corrected = self.claim_request(
            "reject-then-retry-0001",
            claim_id="claim-0002",
            task_id="task-0002",
        )
        _, corrected_completed, corrected_response = self.request(corrected)
        self.assertEqual(corrected_completed.returncode, 0, corrected_completed.stderr)
        self.assertFalse(corrected_response["idempotent_replay"])
        self.assertEqual(self.table_count("authority_commits"), 2)

    def test_operation_key_scope_blocks_cross_ledger_and_cross_uid_receipt_access(self) -> None:
        self.init_store(
            {os.getuid(): ["builder"]},
            ledger_ids=["ledger-test", "ledger-other"],
        )
        self.start_server()
        request = self.claim_request("scope-0001")
        _, completed, response = self.request(request)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(response["ok"])

        cross_ledger = self.claim_request(
            "scope-0001",
            claim_id="claim-other",
            task_id="task-other",
        )
        cross_ledger["ledger_id"] = "ledger-other"
        _, completed, response = self.request(cross_ledger)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "operation_key_scope_conflict")

        normalized = authority_broker.normalize_request(request)
        store = authority_broker.AuthorityStore(self.store_path, self.content_dir)
        with self.assertRaises(authority_broker.BrokerError) as caught:
            store.lookup_idempotent(
                normalized,
                authority_broker.PeerCredentials(
                    pid=os.getpid(),
                    uid=os.getuid() + 1,
                    gid=os.getgid(),
                ),
                authority_broker.digest_request(normalized),
            )
        self.assertEqual(caught.exception.code, "operation_key_scope_conflict")
        self.assertEqual(self.table_count("authority_commits"), 1)

    def test_broker_builds_domain_mutations_and_rejects_client_supplied_payloads(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server()
        malicious = self.claim_request("smuggled-state-0001")
        malicious["mutations"] = [
            {
                "record_type": "task",
                "record_id": "task-0001",
                "payload": {"status": "complete"},
            }
        ]
        _, completed, response = self.request(malicious)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "invalid_request")
        self.assertEqual(self.table_count("authority_commits"), 0)

        _, completed, response = self.request(self.claim_request("server-plan-0001"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        conn = sqlite3.connect(self.store_path)
        try:
            payload = json.loads(
                conn.execute(
                    """
                    SELECT payload_json FROM authority_events
                    WHERE record_type = 'task' AND record_id = 'task-0001'
                    """
                ).fetchone()[0]
            )
        finally:
            conn.close()
        self.assertEqual(payload["status"], "open")
        self.assertEqual(payload["claim_ids"], ["claim-0001"])

    def test_stale_preconditions_and_unverified_transitions_fail_closed(self) -> None:
        self.init_store({os.getuid(): ["builder", "verifier"]})
        self.start_server()
        _, completed, created = self.request(self.claim_request("transition-base-0001"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        task_head = self.event_for(created["receipt"], "task")

        transition = {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": "transition-stale-0001",
            "operation": {
                "kind": "task.transition",
                "task_id": "task-0001",
                "status": "verified",
                "claim_id": "claim-0001",
            },
            "expected": [
                {
                    "record_type": "task",
                    "record_id": "task-0001",
                    "version": task_head["version"],
                    "event_hash": "0" * 64,
                }
            ],
        }
        _, completed, response = self.request(transition)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "stale_record")

        transition["operation_key"] = "transition-version-stale-0001"
        transition["expected"][0]["version"] = task_head["version"] + 1
        transition["expected"][0]["event_hash"] = task_head["event_hash"]
        _, completed, response = self.request(transition)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "stale_record")

        transition["operation_key"] = "transition-unverified-0001"
        transition["expected"][0]["version"] = task_head["version"]
        _, completed, response = self.request(transition)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "unverified_claim")
        self.assertEqual(self.table_count("authority_commits"), 1)

    def test_history_is_append_only_and_survives_restart(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        server = self.start_server()
        for index in (1, 2):
            _, completed, response = self.request(
                self.claim_request(
                    f"append-{index:04d}",
                    claim_id=f"claim-{index:04d}",
                    task_id=f"task-{index:04d}",
                )
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(response["receipt"]["commit_sequence"], index)
        self.stop_process(server)
        self.processes.remove(server)

        conn = sqlite3.connect(self.store_path)
        try:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("UPDATE authority_commits SET operation = 'changed'")
            conn.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("DELETE FROM authority_events")
            conn.rollback()
        finally:
            conn.close()

        self.start_server()
        _, completed, response = self.request(
            self.claim_request(
                "append-0002",
                claim_id="claim-0002",
                task_id="task-0002",
            )
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(response["idempotent_replay"])
        self.assertEqual(response["receipt"]["commit_sequence"], 2)

        _, completed, response = self.request(
            self.claim_request(
                "append-0003",
                claim_id="claim-0003",
                task_id="task-0003",
            )
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(response["receipt"]["commit_sequence"], 3)

        audit = subprocess.run(
            [
                str(BROKER_BIN),
                "audit",
                "--store",
                str(self.store_path),
                "--content-dir",
                str(self.content_dir),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertEqual(audit.returncode, 0, audit.stderr)
        self.assertEqual(json.loads(audit.stdout)["commits"], 3)

    def test_retry_after_commit_before_response_survives_crash(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        context = multiprocessing.get_context("fork")
        ready_read, ready_write = os.pipe()
        committed_read, committed_write = os.pipe()
        process = context.Process(
            target=run_crashing_broker,
            args=(
                str(self.store_path),
                str(self.content_dir),
                str(self.socket_path),
                ready_write,
                committed_write,
            ),
        )
        process.start()
        self.child_processes.append(process)
        os.close(ready_write)
        os.close(committed_write)
        ready, _, _ = select.select([ready_read], [], [], 5)
        self.assertTrue(ready, "crashing broker did not signal readiness")
        self.assertEqual(os.read(ready_read, 1), b"1")
        os.close(ready_read)

        request = self.claim_request("crash-0001")
        _, completed, response = self.request(request)
        committed, _, _ = select.select([committed_read], [], [], 5)
        self.assertTrue(committed, "broker did not signal the durable commit")
        self.assertEqual(os.read(committed_read, 1), b"1")
        os.close(committed_read)
        process.join(timeout=5)
        self.assertEqual(process.exitcode, 86)
        self.child_processes.remove(process)
        self.assertNotEqual(completed.returncode, 0)
        self.assertIsNone(response)
        self.assertEqual(self.table_count("authority_commits"), 1)

        self.start_server()
        _, retried_completed, retried = self.request(request)
        self.assertEqual(retried_completed.returncode, 0, retried_completed.stderr)
        self.assertTrue(retried["idempotent_replay"])
        self.assertEqual(retried["receipt"]["commit_sequence"], 1)
        self.assertEqual(self.table_count("authority_commits"), 1)
        self.assertEqual(self.table_count("projection_outbox"), 1)
        _, snapshot_completed, snapshot = self.request(
            {
                "protocol_version": 1,
                "action": "projection.snapshot",
                "ledger_id": "ledger-test",
            }
        )
        self.assertEqual(snapshot_completed.returncode, 0, snapshot_completed.stderr)
        self.assertEqual(snapshot["snapshot"]["through_commit_sequence"], 1)
        self.assertEqual(snapshot["snapshot"]["record_count"], 2)

    def test_evidence_is_durable_before_atomic_multi_record_commit(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server()
        _, completed, created = self.request(self.claim_request("evidence-base-0001"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        claim_head = self.event_for(created["receipt"], "claim")
        task_head = self.event_for(created["receipt"], "task")

        evidence_source = self.temp_dir / "evidence.txt"
        evidence_source.write_bytes(b"broker-owned evidence\n")
        evidence_hash = hashlib.sha256(evidence_source.read_bytes()).hexdigest()
        request = {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": "evidence-draft-0001",
            "operation": {
                "kind": "evidence.attach_draft",
                "task_id": "task-0001",
                "claim_id": "claim-0001",
                "evidence_id": "evidence-0001",
                "evidence_type": "test_output",
            },
            "expected": [
                {
                    "record_type": "task",
                    "record_id": "task-0001",
                    "version": task_head["version"],
                    "event_hash": task_head["event_hash"],
                },
                {
                    "record_type": "claim",
                    "record_id": "claim-0001",
                    "version": claim_head["version"],
                    "event_hash": claim_head["event_hash"],
                },
                {
                    "record_type": "evidence",
                    "record_id": "evidence-0001",
                    "version": 0,
                    "event_hash": None,
                },
            ],
            "blob": {"sha256": evidence_hash, "size_bytes": evidence_source.stat().st_size},
        }
        _, completed, response = self.request(request, evidence_file=evidence_source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(response["receipt"]["commit_sequence"], 2)
        blob = response["receipt"]["evidence"][0]
        retained = self.content_dir / blob["storage_key"]
        self.assertEqual(retained.read_bytes(), evidence_source.read_bytes())
        self.assertEqual(self.table_count("authority_blobs"), 1)
        self.assertEqual(self.table_count("authority_events"), 5)

        _, retried_completed, retried = self.request(request)
        self.assertEqual(retried_completed.returncode, 0, retried_completed.stderr)
        self.assertTrue(retried["idempotent_replay"])
        self.assertEqual(retried["receipt"], response["receipt"])
        self.assertEqual(self.table_count("authority_commits"), 2)
        self.assertEqual(self.table_count("authority_events"), 5)
        self.assertEqual(self.table_count("authority_blobs"), 1)
        self.assertEqual(self.table_count("commit_blobs"), 1)
        self.assertEqual(self.table_count("projection_outbox"), 2)

        server = self.processes.pop()
        self.stop_process(server)
        self.start_server()
        self.assertEqual(retained.read_bytes(), evidence_source.read_bytes())

        _, snapshot_completed, snapshot = self.request(
            {
                "protocol_version": 1,
                "action": "projection.snapshot",
                "ledger_id": "ledger-test",
            }
        )
        self.assertEqual(snapshot_completed.returncode, 0, snapshot_completed.stderr)
        self.assertEqual(snapshot["snapshot"]["through_commit_sequence"], 2)
        self.assertEqual(len(snapshot["snapshot"]["records"]), 3)
        snapshot_identity = {
            key: value
            for key, value in snapshot["snapshot"].items()
            if key not in {"snapshot_digest", "records", "has_more", "next_after"}
        }
        self.assertEqual(
            snapshot["snapshot"]["snapshot_digest"],
            authority_broker.sha256_text(authority_broker.canonical_json(snapshot_identity)),
        )
        server = self.processes.pop()
        self.stop_process(server)
        conn = sqlite3.connect(self.store_path)
        try:
            for table in authority_broker.APPEND_ONLY_TABLES:
                self.assertGreater(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0)
                with self.assertRaises(sqlite3.IntegrityError, msg=table):
                    conn.execute(f"UPDATE {table} SET rowid = rowid")
                conn.rollback()
                with self.assertRaises(sqlite3.IntegrityError, msg=table):
                    conn.execute(f"DELETE FROM {table}")
                conn.rollback()
        finally:
            conn.close()

    def test_status_evidence_requires_distinct_author_and_uses_real_verifier_peer(self) -> None:
        fake_builder_uid = os.getuid() + 50000
        self.init_store(
            {
                fake_builder_uid: ["builder"],
                os.getuid(): ["verifier"],
            }
        )
        claim_request = authority_broker.normalize_request(
            self.claim_request("fixture-author-0001")
        )
        store = authority_broker.AuthorityStore(self.store_path, self.content_dir)
        receipt, replay = store.commit(
            claim_request,
            authority_broker.PeerCredentials(
                pid=12345,
                uid=fake_builder_uid,
                gid=os.getgid(),
            ),
            authority_broker.digest_request(claim_request),
            [],
        )
        self.assertFalse(replay)
        task_head = self.event_for(receipt, "task")
        claim_head = self.event_for(receipt, "claim")
        evidence_source = self.temp_dir / "verified-evidence.txt"
        evidence_source.write_bytes(b"independent verifier evidence\n")
        evidence_hash = hashlib.sha256(evidence_source.read_bytes()).hexdigest()
        status_request = self.evidence_request(
            "verified-status-0001",
            task_head,
            claim_head,
            evidence_hash,
            evidence_source.stat().st_size,
            kind="evidence.attach_status",
            status="verified",
        )

        self.start_server()
        client_pid, completed, response = self.request(
            status_request,
            evidence_file=evidence_source,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(response["receipt"]["actor"]["pid"], client_pid)
        self.assertEqual(response["receipt"]["actor"]["uid"], os.getuid())
        self.assertEqual(
            {event["record_type"] for event in response["receipt"]["events"]},
            {"task", "claim", "evidence"},
        )
        conn = sqlite3.connect(self.store_path)
        try:
            evidence_payload = json.loads(
                conn.execute(
                    """
                    SELECT payload_json FROM authority_events
                    WHERE record_type = 'evidence' AND record_id = 'evidence-0001'
                    """
                ).fetchone()[0]
            )
            claim_payload = json.loads(
                conn.execute(
                    """
                    SELECT payload_json FROM authority_events
                    WHERE record_type = 'claim' AND record_id = 'claim-0001'
                    ORDER BY version DESC LIMIT 1
                    """
                ).fetchone()[0]
            )
            task_payload = json.loads(
                conn.execute(
                    """
                    SELECT payload_json FROM authority_events
                    WHERE record_type = 'task' AND record_id = 'task-0001'
                    ORDER BY version DESC LIMIT 1
                    """
                ).fetchone()[0]
            )
            status_event_count = conn.execute(
                "SELECT COUNT(*) FROM authority_events WHERE commit_sequence = 2"
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(status_event_count, 3)
        self.assertEqual(evidence_payload["verification_authority"], "uid_isolated")
        self.assertEqual(evidence_payload["policy_authority"], "external_broker")
        self.assertEqual(evidence_payload["verified_by_uid"], os.getuid())
        self.assertEqual(claim_payload["author_uid"], fake_builder_uid)
        self.assertEqual(claim_payload["verification_status"], "verified")
        self.assertEqual(claim_payload["verification_authority"], "uid_isolated")
        self.assertEqual(claim_payload["policy_authority"], "external_broker")
        self.assertIn("claim-0001", task_payload["verified_claim_ids"])
        self.assertEqual(self.table_count("projection_outbox"), 2)

        verified_task_head = self.event_for(response["receipt"], "task")
        verified_claim_head = self.event_for(response["receipt"], "claim")
        transition = {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": "verified-transition-0001",
            "operation": {
                "kind": "task.transition",
                "task_id": "task-0001",
                "status": "verified",
                "claim_id": "claim-0001",
            },
            "expected": [
                {
                    "record_type": "task",
                    "record_id": "task-0001",
                    "version": verified_task_head["version"],
                    "event_hash": verified_task_head["event_hash"],
                }
            ],
        }
        _, completed, transitioned = self.request(transition)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        transitioned_task_head = self.event_for(transitioned["receipt"], "task")

        invalidating_source = self.temp_dir / "invalidating-evidence.txt"
        invalidating_source.write_bytes(b"later verifier quarantine\n")
        invalidating_hash = hashlib.sha256(invalidating_source.read_bytes()).hexdigest()
        invalidation = self.evidence_request(
            "status-invalidation-0001",
            transitioned_task_head,
            verified_claim_head,
            invalidating_hash,
            invalidating_source.stat().st_size,
            kind="evidence.attach_status",
            status="quarantined",
            evidence_id="evidence-0002",
        )
        _, completed, invalidated = self.request(
            invalidation,
            evidence_file=invalidating_source,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        invalidated_task = self.event_for(invalidated["receipt"], "task")
        conn = sqlite3.connect(self.store_path)
        try:
            task_payload = json.loads(
                conn.execute(
                    """
                    SELECT payload_json FROM authority_events
                    WHERE record_type = 'task' AND record_id = 'task-0001'
                    ORDER BY version DESC LIMIT 1
                    """
                ).fetchone()[0]
            )
        finally:
            conn.close()
        self.assertEqual(task_payload["status"], "open")
        self.assertNotIn("transition_claim_id", task_payload)

        complete = {
            "protocol_version": 1,
            "action": "commit",
            "ledger_id": "ledger-test",
            "operation_key": "invalid-complete-0001",
            "operation": {
                "kind": "task.transition",
                "task_id": "task-0001",
                "status": "complete",
            },
            "expected": [
                {
                    "record_type": "task",
                    "record_id": "task-0001",
                    "version": invalidated_task["version"],
                    "event_hash": invalidated_task["event_hash"],
                }
            ],
        }
        _, completed, completion_response = self.request(complete)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(completion_response["error"]["code"], "invalid_transition")
        _, completed, snapshot_response = self.request(
            {
                "protocol_version": 1,
                "action": "projection.snapshot",
                "ledger_id": "ledger-test",
            }
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        claim_record = next(
            record
            for record in snapshot_response["snapshot"]["records"]
            if record["record_type"] == "claim"
        )
        self.assertEqual(claim_record["payload"]["author_uid"], fake_builder_uid)
        self.assertEqual(claim_record["authority"]["actor_uid"], os.getuid())
        self.assertEqual(claim_record["authority"]["policy"]["generation"], 1)

    def test_same_uid_status_and_missing_or_mismatched_evidence_fd_fail_closed(self) -> None:
        self.init_store({os.getuid(): ["builder", "verifier"]})
        self.start_server()
        _, completed, created = self.request(self.claim_request("self-status-base-0001"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        task_head = self.event_for(created["receipt"], "task")
        claim_head = self.event_for(created["receipt"], "claim")
        source = self.temp_dir / "status.txt"
        source.write_bytes(b"status evidence\n")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        status_request = self.evidence_request(
            "self-status-0001",
            task_head,
            claim_head,
            source_hash,
            source.stat().st_size,
            kind="evidence.attach_status",
            status="verified",
        )
        _, completed, response = self.request(status_request, evidence_file=source)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "self_verification")

        draft_request = self.evidence_request(
            "missing-fd-0001",
            task_head,
            claim_head,
            source_hash,
            source.stat().st_size,
        )
        _, completed, response = self.request(draft_request)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "evidence_fd_required")

        draft_request["operation_key"] = "mismatched-fd-0001"
        draft_request["blob"]["sha256"] = "0" * 64
        _, completed, response = self.request(draft_request, evidence_file=source)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "evidence_hash_mismatch")
        self.assertEqual(self.table_count("authority_commits"), 1)
        self.assertEqual(self.table_count("authority_blobs"), 0)

    def test_injected_status_transition_failure_rolls_back_all_authority_metadata(self) -> None:
        fake_builder_uid = os.getuid() + 50000
        self.init_store(
            {
                fake_builder_uid: ["builder"],
                os.getuid(): ["verifier"],
            }
        )
        claim_request = authority_broker.normalize_request(
            self.claim_request("status-failure-base-0001")
        )
        store = authority_broker.AuthorityStore(self.store_path, self.content_dir)
        receipt, _ = store.commit(
            claim_request,
            authority_broker.PeerCredentials(12345, fake_builder_uid, os.getgid()),
            authority_broker.digest_request(claim_request),
            [],
        )
        task_head = self.event_for(receipt, "task")
        claim_head = self.event_for(receipt, "claim")
        source = self.temp_dir / "failing-status.txt"
        source.write_bytes(b"durable but unreferenced after rollback\n")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        request = self.evidence_request(
            "status-failure-0001",
            task_head,
            claim_head,
            source_hash,
            source.stat().st_size,
            kind="evidence.attach_status",
            status="verified",
        )

        self.start_server()
        conn = sqlite3.connect(self.store_path)
        try:
            conn.execute(
                """
                CREATE TRIGGER injected_status_claim_failure
                BEFORE INSERT ON authority_events
                WHEN NEW.operation = 'evidence.attach_status'
                     AND NEW.record_type = 'claim'
                BEGIN
                    SELECT RAISE(ABORT, 'injected status claim failure');
                END
                """
            )
            conn.commit()
        finally:
            conn.close()

        _, completed, response = self.request(request, evidence_file=source)
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "internal_error")
        self.assertEqual(self.table_count("authority_commits"), 1)
        self.assertEqual(self.table_count("authority_events"), 2)
        self.assertEqual(self.table_count("authority_blobs"), 0)
        self.assertEqual(self.table_count("commit_blobs"), 0)
        self.assertEqual(self.table_count("projection_outbox"), 1)

    def test_cas_directory_fsync_failure_prevents_authority_metadata_commit(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        claim_request = authority_broker.normalize_request(
            self.claim_request("cas-fsync-base-0001")
        )
        store = authority_broker.AuthorityStore(self.store_path, self.content_dir)
        peer = authority_broker.PeerCredentials(os.getpid(), os.getuid(), os.getgid())
        receipt, _ = store.commit(
            claim_request,
            peer,
            authority_broker.digest_request(claim_request),
            [],
        )
        task_head = self.event_for(receipt, "task")
        claim_head = self.event_for(receipt, "claim")
        source = self.temp_dir / "fsync-evidence.txt"
        source.write_bytes(b"must not gain metadata before shard fsync\n")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        request = self.evidence_request(
            "cas-fsync-failure-0001",
            task_head,
            claim_head,
            source_hash,
            source.stat().st_size,
        )
        real_fsync_directory = authority_broker.fsync_directory

        def fail_shard_fsync(path: Path) -> None:
            if path.name == source_hash[:2]:
                raise OSError("injected shard directory fsync failure")
            real_fsync_directory(path)

        source_fd = os.open(source, os.O_RDONLY)
        try:
            with mock.patch.object(
                authority_broker,
                "fsync_directory",
                side_effect=fail_shard_fsync,
            ):
                with self.assertRaises(OSError):
                    authority_broker.AuthorityBroker(store).handle(
                        request,
                        peer,
                        source_fd,
                    )
        finally:
            os.close(source_fd)
        self.assertEqual(self.table_count("authority_commits"), 1)
        self.assertEqual(self.table_count("authority_events"), 2)
        self.assertEqual(self.table_count("authority_blobs"), 0)
        self.assertEqual(self.table_count("commit_blobs"), 0)
        self.assertEqual(self.table_count("projection_outbox"), 1)

    def test_cas_file_fsync_failure_prevents_authority_metadata_commit(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        claim_request = authority_broker.normalize_request(
            self.claim_request("cas-file-fsync-base-0001")
        )
        store = authority_broker.AuthorityStore(self.store_path, self.content_dir)
        peer = authority_broker.PeerCredentials(os.getpid(), os.getuid(), os.getgid())
        receipt, _ = store.commit(
            claim_request,
            peer,
            authority_broker.digest_request(claim_request),
            [],
        )
        task_head = self.event_for(receipt, "task")
        claim_head = self.event_for(receipt, "claim")
        source = self.temp_dir / "file-fsync-evidence.txt"
        source.write_bytes(b"must not gain metadata before file fsync\n")
        source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        request = self.evidence_request(
            "cas-file-fsync-failure-0001",
            task_head,
            claim_head,
            source_hash,
            source.stat().st_size,
        )
        real_fsync = authority_broker.os.fsync

        def fail_regular_file_fsync(fd: int) -> None:
            if stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError("injected content file fsync failure")
            real_fsync(fd)

        source_fd = os.open(source, os.O_RDONLY)
        try:
            with mock.patch.object(
                authority_broker.os,
                "fsync",
                side_effect=fail_regular_file_fsync,
            ):
                with self.assertRaises(OSError):
                    authority_broker.AuthorityBroker(store).handle(
                        request,
                        peer,
                        source_fd,
                    )
        finally:
            os.close(source_fd)
        self.assertEqual(self.table_count("authority_commits"), 1)
        self.assertEqual(self.table_count("authority_events"), 2)
        self.assertEqual(self.table_count("authority_blobs"), 0)
        self.assertEqual(self.table_count("commit_blobs"), 0)
        self.assertEqual(self.table_count("projection_outbox"), 1)

    def test_injected_multi_record_failure_rolls_back_authority_commit(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server()
        conn = sqlite3.connect(self.store_path)
        try:
            conn.execute(
                """
                CREATE TRIGGER injected_claim_failure
                BEFORE INSERT ON authority_events
                WHEN NEW.record_type = 'claim'
                BEGIN
                    SELECT RAISE(ABORT, 'injected claim event failure');
                END
                """
            )
            conn.commit()
        finally:
            conn.close()

        _, completed, response = self.request(self.claim_request("atomic-failure-0001"))
        self.assertNotEqual(completed.returncode, 0)
        self.assertEqual(response["error"]["code"], "internal_error")
        self.assertEqual(self.table_count("authority_commits"), 0)
        self.assertEqual(self.table_count("authority_events"), 0)
        self.assertEqual(self.table_count("projection_outbox"), 0)

    def test_concurrent_requests_receive_monotonic_commit_sequences(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server()
        requests = [
            self.claim_request(
                f"concurrent-{index:04d}",
                claim_id=f"claim-{index:04d}",
                task_id=f"task-{index:04d}",
            )
            for index in (1, 2)
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.request, requests))
        responses = []
        for _, completed, response in results:
            self.assertEqual(completed.returncode, 0, completed.stderr)
            responses.append(response)
        self.assertEqual(
            sorted(response["receipt"]["commit_sequence"] for response in responses),
            [1, 2],
        )

    def test_concurrent_requests_against_same_head_commit_once_and_reject_stale(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server()
        _, completed, seeded = self.request(
            self.claim_request(
                "contended-seed-0001",
                claim_id="claim-seed",
                task_id="shared-task",
            )
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        task_head = self.event_for(seeded["receipt"], "task")
        requests = [
            self.claim_request(
                f"contended-{index:04d}",
                claim_id=f"claim-{index:04d}",
                task_id="shared-task",
            )
            for index in (1, 2)
        ]
        for request in requests:
            request["expected"][0]["version"] = task_head["version"]
            request["expected"][0]["event_hash"] = task_head["event_hash"]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(self.request, requests))
        successes = [response for _, completed, response in results if completed.returncode == 0]
        failures = [response for _, completed, response in results if completed.returncode != 0]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0]["error"]["code"], "stale_record")
        self.assertEqual(successes[0]["receipt"]["commit_sequence"], 2)
        self.assertEqual(self.table_count("authority_commits"), 2)
        self.assertEqual(self.table_count("authority_events"), 4)
        self.assertEqual(self.table_count("projection_outbox"), 2)
        conn = sqlite3.connect(self.store_path)
        try:
            latest_task_version = conn.execute(
                """
                SELECT MAX(version) FROM authority_events
                WHERE record_type = 'task' AND record_id = 'shared-task'
                """
            ).fetchone()[0]
        finally:
            conn.close()
        self.assertEqual(latest_task_version, 2)

    def test_projection_snapshot_is_length_framed_paginated_and_sequence_pinned(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        self.start_server()
        for index in range(1, 18):
            _, completed, response = self.request(
                self.claim_request(
                    f"page-seed-{index:04d}",
                    claim_id=f"claim-{index:04d}",
                    task_id=f"task-{index:04d}",
                    text=str(index).zfill(4) + "x" * 4092,
                )
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(response["receipt"]["commit_sequence"], index)

        snapshot_request = {
            "protocol_version": 1,
            "action": "projection.snapshot",
            "ledger_id": "ledger-test",
            "limit": 16,
        }
        _, completed, first = self.request(snapshot_request)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        first_snapshot = first["snapshot"]
        self.assertTrue(first_snapshot["has_more"])
        self.assertEqual(first_snapshot["record_count"], 34)
        self.assertEqual(len(first_snapshot["records"]), 16)
        self.assertGreater(
            len(authority_broker.canonical_json(first).encode("utf-8")),
            65536,
        )

        _, completed, _ = self.request(
            self.claim_request(
                "page-later-0001",
                claim_id="claim-later",
                task_id="task-later",
            )
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        records = list(first_snapshot["records"])
        page = first_snapshot
        while page["has_more"]:
            snapshot_request["through_commit_sequence"] = first_snapshot["through_commit_sequence"]
            snapshot_request["after"] = page["next_after"]
            _, completed, response = self.request(snapshot_request)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            page = response["snapshot"]
            self.assertEqual(page["snapshot_digest"], first_snapshot["snapshot_digest"])
            self.assertEqual(page["records_sha256"], first_snapshot["records_sha256"])
            records.extend(page["records"])

        self.assertEqual(len(records), 34)
        self.assertEqual(
            len({(record["record_type"], record["record_id"]) for record in records}),
            34,
        )
        self.assertNotIn("claim-later", {record["record_id"] for record in records})

    def test_broker_ignores_hostile_worktree_policy_and_local_ledger(self) -> None:
        hostile = self.temp_dir / "hostile-worktree"
        local_operator = hostile / ".operator"
        local_operator.mkdir(parents=True)
        (local_operator / "identity.yaml").write_text(
            "mode: enforced\nuids:\n  999999:\n    name: forged\n    roles: [builder, verifier]\n"
        )
        (local_operator / "ledger.sqlite3").write_bytes(b"not a sqlite database")

        self.init_store({os.getuid(): ["builder"]})
        self.start_server(
            cwd=hostile,
            env={
                "OPERATOR_DIR": str(local_operator),
                "OPERATOR_POLICY_PATH": str(local_operator / "identity.yaml"),
                "OPERATOR_TEST_UID": "999999",
                "OPERATOR_TEST_SENTINEL": "1",
            },
        )
        (local_operator / "identity.yaml").write_text("mode: single_user\nuids: {}\n")
        (local_operator / "ledger.sqlite3").unlink()
        shutil.rmtree(hostile)

        _, completed, response = self.request(
            self.claim_request("hostile-worktree-0001"),
            env={
                "OPERATOR_DIR": str(local_operator),
                "OPERATOR_POLICY_PATH": str(local_operator / "identity.yaml"),
                "OPERATOR_TEST_UID": "999999",
                "OPERATOR_TEST_SENTINEL": "1",
            },
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(response["receipt"]["actor"]["uid"], os.getuid())
        self.assertEqual(self.table_count("authority_commits"), 1)

    def test_corrupt_or_unsupported_store_fails_before_listener_startup(self) -> None:
        self.init_store({os.getuid(): ["builder"]})
        server = self.start_server()
        _, completed, _ = self.request(self.claim_request("corrupt-base-0001"))
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.stop_process(server)
        self.processes.remove(server)

        conn = sqlite3.connect(self.store_path)
        try:
            conn.execute("DROP TRIGGER authority_commits_no_update")
            conn.execute("UPDATE authority_commits SET request_digest = ?", ("0" * 64,))
            conn.execute(
                """
                CREATE TRIGGER authority_commits_no_update
                BEFORE UPDATE ON authority_commits
                BEGIN
                    SELECT RAISE(ABORT, 'authority_commits is append-only by broker contract');
                END
                """
            )
            conn.commit()
        finally:
            conn.close()
        process = subprocess.run(
            [
                str(BROKER_BIN),
                "serve",
                "--store",
                str(self.store_path),
                "--content-dir",
                str(self.content_dir),
                "--socket",
                str(self.socket_path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stderr)["error"]["code"], "store_corrupt")
        self.assertFalse(self.socket_path.exists())

        unsupported_store = self.temp_dir / "unsupported.sqlite3"
        unsupported_content = self.temp_dir / "unsupported-content"
        unsupported_config = self.temp_dir / "unsupported.json"
        self.init_store(
            {os.getuid(): ["builder"]},
            store_path=unsupported_store,
            content_dir=unsupported_content,
            config_path=unsupported_config,
        )
        conn = sqlite3.connect(unsupported_store)
        try:
            conn.execute("PRAGMA user_version = 999")
        finally:
            conn.close()
        audit = subprocess.run(
            [
                str(BROKER_BIN),
                "audit",
                "--store",
                str(unsupported_store),
                "--content-dir",
                str(unsupported_content),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertNotEqual(audit.returncode, 0)
        self.assertEqual(
            json.loads(audit.stderr)["error"]["code"],
            "unsupported_store_schema",
        )


if __name__ == "__main__":
    unittest.main()
