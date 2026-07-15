#!/usr/bin/env python3
"""Standalone P3 authorization broker and external authority store."""

from __future__ import annotations

import argparse
import array
import datetime
import hashlib
import json
import os
import re
import signal
import socket
import sqlite3
import stat
import struct
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

PROTOCOL_VERSION = 1
STORE_SCHEMA_VERSION = 1
STORE_APPLICATION_ID = 0x4F504252
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 16 * 1024 * 1024
MAX_RECORD_BYTES = 512 * 1024
MAX_SNAPSHOT_PAGE_RECORDS = 16
FRAME_HEADER_BYTES = 4
VALID_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
VALID_SHA256 = re.compile(r"[0-9a-f]{64}")
VALID_ROLES = frozenset({"builder", "verifier"})
OPERATION_ROLES = {
    "ledger.enroll": None,
    "claim.create": "builder",
    "evidence.attach_draft": "builder",
    "evidence.attach_status": "verifier",
    "task.transition": "verifier",
}
OPERATION_RECORD_TYPES = {
    "ledger.enroll": frozenset(),
    "claim.create": frozenset({"claim", "task"}),
    "evidence.attach_draft": frozenset({"evidence", "claim", "task"}),
    "evidence.attach_status": frozenset({"evidence", "claim", "task"}),
    "task.transition": frozenset({"task"}),
}
RECORD_TYPE_ORDER = {"task": 0, "claim": 1, "evidence": 2}
APPEND_ONLY_TABLES = (
    "store_meta",
    "policy_snapshots",
    "policy_roles",
    "ledger_policy_events",
    "authority_commits",
    "authority_events",
    "authority_blobs",
    "commit_blobs",
    "projection_outbox",
)
REQUIRED_TABLES = frozenset(APPEND_ONLY_TABLES)


class BrokerError(Exception):
    def __init__(self, code: str, message: str, **details: object) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details

    def response(self) -> dict:
        error = {"code": self.code, "message": self.message}
        if self.details:
            error["details"] = self.details
        return {"ok": False, "error": error}


@dataclass(frozen=True)
class PeerCredentials:
    pid: int
    uid: int
    gid: int


@dataclass(frozen=True)
class BootstrapConfig:
    policy_id: str
    policy_generation: int
    ledgers: tuple[str, ...]
    roles: dict[int, frozenset[str]]
    policy_json: str
    policy_sha256: str


@dataclass(frozen=True)
class StagedBlob:
    sha256: str
    size_bytes: int
    storage_key: str

    def as_dict(self) -> dict:
        return {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "storage_key": self.storage_key,
        }


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


def canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_token(value: object, field: str) -> str:
    if not isinstance(value, str) or not VALID_TOKEN.fullmatch(value):
        raise BrokerError(
            "invalid_request",
            f"{field} must match {VALID_TOKEN.pattern!r}",
            field=field,
        )
    return value


def require_sha256(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise BrokerError("invalid_request", f"{field} must be a SHA-256 string", field=field)
    normalized = value.lower()
    if not VALID_SHA256.fullmatch(normalized):
        raise BrokerError("invalid_request", f"{field} must be 64 lowercase hex characters")
    return normalized


def require_text(value: object, field: str, *, max_length: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise BrokerError(
            "invalid_request",
            f"{field} must be a non-empty string of at most {max_length} characters",
            field=field,
        )
    return value


def require_exact_keys(value: dict, allowed: set[str], context: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        rendered = ", ".join(sorted(unknown))
        raise BrokerError("invalid_request", f"{context} has unknown field(s): {rendered}")


def require_absolute_path(value: str, field: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise BrokerError("invalid_path", f"{field} must be an absolute path", field=field)
    return path


def read_bootstrap_config(path: Path) -> BootstrapConfig:
    try:
        data = path.read_bytes()
        if len(data) > MAX_REQUEST_BYTES:
            raise BrokerError(
                "invalid_bootstrap",
                f"bootstrap config exceeds {MAX_REQUEST_BYTES} bytes",
            )
        raw = decode_json(data)
    except OSError as exc:
        raise BrokerError("invalid_bootstrap", f"could not read bootstrap config: {exc}") from exc
    except BrokerError as exc:
        if exc.code == "invalid_bootstrap":
            raise
        raise BrokerError("invalid_bootstrap", f"invalid bootstrap config: {exc.message}") from exc
    if not isinstance(raw, dict):
        raise BrokerError("invalid_bootstrap", "bootstrap config must contain a JSON object")
    require_exact_keys(raw, {"policy_id", "policy_generation", "ledgers", "roles"}, "config")

    policy_id = require_token(raw.get("policy_id"), "policy_id")
    generation = raw.get("policy_generation")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation < 1:
        raise BrokerError("invalid_bootstrap", "policy_generation must be a positive integer")

    raw_ledgers = raw.get("ledgers")
    if not isinstance(raw_ledgers, list) or not raw_ledgers:
        raise BrokerError("invalid_bootstrap", "ledgers must be a non-empty list")
    ledgers = tuple(sorted(require_token(item, "ledger_id") for item in raw_ledgers))
    if len(set(ledgers)) != len(ledgers):
        raise BrokerError("invalid_bootstrap", "ledgers must not contain duplicates")

    raw_roles = raw.get("roles")
    if not isinstance(raw_roles, dict) or not raw_roles:
        raise BrokerError("invalid_bootstrap", "roles must be a non-empty UID mapping")
    roles: dict[int, frozenset[str]] = {}
    for raw_uid, raw_uid_roles in raw_roles.items():
        if not isinstance(raw_uid, str) or not raw_uid.isdigit():
            raise BrokerError("invalid_bootstrap", f"role UID {raw_uid!r} is not numeric")
        uid = int(raw_uid)
        if not isinstance(raw_uid_roles, list) or not raw_uid_roles:
            raise BrokerError("invalid_bootstrap", f"roles for UID {uid} must be a non-empty list")
        if any(not isinstance(role, str) for role in raw_uid_roles):
            raise BrokerError("invalid_bootstrap", f"roles for UID {uid} must be strings")
        uid_roles = frozenset(raw_uid_roles)
        unknown_roles = uid_roles - VALID_ROLES
        if unknown_roles:
            raise BrokerError(
                "invalid_bootstrap",
                f"UID {uid} has unknown role(s): {', '.join(sorted(unknown_roles))}",
            )
        roles[uid] = uid_roles

    normalized = {
        "policy_id": policy_id,
        "policy_generation": generation,
        "ledgers": list(ledgers),
        "roles": {str(uid): sorted(uid_roles) for uid, uid_roles in sorted(roles.items())},
    }
    policy_json = canonical_json(normalized)
    return BootstrapConfig(
        policy_id=policy_id,
        policy_generation=generation,
        ledgers=ledgers,
        roles=roles,
        policy_json=policy_json,
        policy_sha256=sha256_text(policy_json),
    )


def normalize_expected(raw_expected: object, operation: dict) -> list[dict]:
    if operation["kind"] == "ledger.enroll" and raw_expected == []:
        return []
    if not isinstance(raw_expected, list) or not raw_expected:
        raise BrokerError("invalid_request", "expected must be a non-empty list")
    expected = []
    seen_records = set()
    for index, item in enumerate(raw_expected):
        if not isinstance(item, dict):
            raise BrokerError("invalid_request", f"expected {index} must be an object")
        require_exact_keys(
            item,
            {"record_type", "record_id", "version", "event_hash"},
            f"expected {index}",
        )
        record_type = require_token(item.get("record_type"), "record_type")
        if record_type not in RECORD_TYPE_ORDER:
            raise BrokerError("invalid_request", f"unsupported record_type: {record_type}")
        record_id = require_token(item.get("record_id"), "record_id")
        record_key = (record_type, record_id)
        if record_key in seen_records:
            raise BrokerError(
                "invalid_request", f"duplicate precondition for {record_type} {record_id}"
            )
        seen_records.add(record_key)
        version = item.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 0:
            raise BrokerError("invalid_request", "version must be a non-negative integer")
        event_hash = item.get("event_hash")
        if version == 0:
            if event_hash is not None:
                raise BrokerError("invalid_request", "event_hash must be null for a new record")
        else:
            event_hash = require_sha256(event_hash, "event_hash")
        expected.append(
            {
                "record_type": record_type,
                "record_id": record_id,
                "version": version,
                "event_hash": event_hash,
            }
        )

    kind = operation["kind"]
    record_ids = {
        "task": operation["task_id"],
        "claim": operation.get("claim_id"),
        "evidence": operation.get("evidence_id"),
    }
    required = {
        (record_type, record_ids[record_type]) for record_type in OPERATION_RECORD_TYPES[kind]
    }
    actual = {(item["record_type"], item["record_id"]) for item in expected}
    if actual != required:
        rendered = ", ".join(
            f"{record_type}:{record_id}" for record_type, record_id in sorted(required)
        )
        raise BrokerError("invalid_request", f"{kind} requires preconditions for: {rendered}")
    return sorted(expected, key=lambda item: RECORD_TYPE_ORDER[item["record_type"]])


def normalize_operation(raw_operation: object) -> dict:
    if not isinstance(raw_operation, dict):
        raise BrokerError("invalid_request", "operation must be an object")
    kind = raw_operation.get("kind")
    if kind not in OPERATION_ROLES:
        raise BrokerError("invalid_operation", f"unsupported operation: {kind!r}")

    if kind == "ledger.enroll":
        require_exact_keys(
            raw_operation,
            {
                "kind",
                "repository_identity",
                "anchor_records",
                "legacy_anchor_sha256",
            },
            "operation",
        )
        identity = raw_operation.get("repository_identity")
        if not isinstance(identity, dict):
            raise BrokerError("invalid_request", "repository_identity must be an object")
        require_exact_keys(
            identity,
            {
                "repository_path",
                "repository_device",
                "repository_inode",
                "operator_device",
                "operator_inode",
                "ledger_device",
                "ledger_inode",
            },
            "repository_identity",
        )
        repository_path = identity.get("repository_path")
        if not isinstance(repository_path, str) or not os.path.isabs(repository_path):
            raise BrokerError("invalid_request", "repository_path must be absolute")
        normalized_identity = {"repository_path": repository_path}
        for field in (
            "repository_device",
            "repository_inode",
            "operator_device",
            "operator_inode",
            "ledger_device",
            "ledger_inode",
        ):
            value = identity.get(field)
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise BrokerError("invalid_request", f"{field} must be a positive integer")
            normalized_identity[field] = value

        raw_anchors = raw_operation.get("anchor_records")
        if not isinstance(raw_anchors, list):
            raise BrokerError("invalid_request", "anchor_records must be an array")
        anchors = []
        seen = set()
        for index, raw_anchor in enumerate(raw_anchors):
            if not isinstance(raw_anchor, dict):
                raise BrokerError("invalid_request", f"anchor_records[{index}] must be an object")
            require_exact_keys(
                raw_anchor,
                {"record_type", "record_id", "version", "event_hash"},
                f"anchor_records[{index}]",
            )
            record_type = require_token(raw_anchor.get("record_type"), "record_type")
            record_id = require_token(raw_anchor.get("record_id"), "record_id")
            version = raw_anchor.get("version")
            if not isinstance(version, int) or isinstance(version, bool) or version < 1:
                raise BrokerError("invalid_request", "anchor version must be a positive integer")
            key = (record_type, record_id)
            if key in seen:
                raise BrokerError("invalid_request", "anchor_records contains a duplicate record")
            seen.add(key)
            anchors.append(
                {
                    "record_type": record_type,
                    "record_id": record_id,
                    "version": version,
                    "event_hash": require_sha256(raw_anchor.get("event_hash"), "event_hash"),
                }
            )
        anchors.sort(key=lambda item: (item["record_type"], item["record_id"]))
        anchor_digest = require_sha256(
            raw_operation.get("legacy_anchor_sha256"), "legacy_anchor_sha256"
        )
        if anchor_digest != sha256_text(canonical_json(anchors)):
            raise BrokerError("invalid_request", "legacy anchor digest does not match records")
        return {
            "kind": kind,
            "repository_identity": normalized_identity,
            "anchor_records": anchors,
            "legacy_anchor_sha256": anchor_digest,
        }

    if kind == "claim.create":
        require_exact_keys(
            raw_operation,
            {"kind", "task_id", "claim_id", "claim_type", "text", "required_gate"},
            "operation",
        )
        operation = {
            "kind": kind,
            "task_id": require_token(raw_operation.get("task_id"), "task_id"),
            "claim_id": require_token(raw_operation.get("claim_id"), "claim_id"),
            "claim_type": require_token(raw_operation.get("claim_type"), "claim_type"),
            "text": require_text(raw_operation.get("text"), "text"),
        }
        required_gate = raw_operation.get("required_gate")
        if required_gate is not None:
            operation["required_gate"] = require_text(required_gate, "required_gate")
        return operation

    if kind.startswith("evidence."):
        require_exact_keys(
            raw_operation,
            {
                "kind",
                "task_id",
                "claim_id",
                "evidence_id",
                "evidence_type",
                "verification_status",
            },
            "operation",
        )
        operation = {
            "kind": kind,
            "task_id": require_token(raw_operation.get("task_id"), "task_id"),
            "claim_id": require_token(raw_operation.get("claim_id"), "claim_id"),
            "evidence_id": require_token(raw_operation.get("evidence_id"), "evidence_id"),
            "evidence_type": require_token(raw_operation.get("evidence_type"), "evidence_type"),
        }
        verification_status = raw_operation.get("verification_status")
        if kind == "evidence.attach_draft":
            if verification_status is not None:
                raise BrokerError(
                    "invalid_request",
                    "evidence.attach_draft does not accept verification_status",
                )
        elif verification_status not in {"verified", "false", "quarantined"}:
            raise BrokerError(
                "invalid_request",
                "evidence.attach_status requires verification_status: verified, false, or quarantined",
            )
        else:
            operation["verification_status"] = verification_status
        return operation

    require_exact_keys(raw_operation, {"kind", "task_id", "status", "claim_id"}, "operation")
    status = raw_operation.get("status")
    if status not in {"verified", "complete"}:
        raise BrokerError("invalid_request", "task.transition status must be verified or complete")
    claim_id = raw_operation.get("claim_id")
    if status == "verified":
        claim_id = require_token(claim_id, "claim_id")
    elif claim_id is not None:
        raise BrokerError("invalid_request", "complete transition does not accept claim_id")
    operation = {
        "kind": kind,
        "task_id": require_token(raw_operation.get("task_id"), "task_id"),
        "status": status,
    }
    if claim_id is not None:
        operation["claim_id"] = claim_id
    return operation


def normalize_commit_request(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise BrokerError("invalid_request", "request must contain a JSON object")
    require_exact_keys(
        raw,
        {
            "protocol_version",
            "action",
            "ledger_id",
            "operation_key",
            "operation",
            "expected",
            "blob",
        },
        "request",
    )
    if raw.get("protocol_version") != PROTOCOL_VERSION:
        raise BrokerError("unsupported_protocol", f"protocol_version must be {PROTOCOL_VERSION}")
    if raw.get("action") != "commit":
        raise BrokerError("invalid_request", "action must be 'commit'")
    operation = normalize_operation(raw.get("operation"))
    normalized = {
        "protocol_version": PROTOCOL_VERSION,
        "action": "commit",
        "ledger_id": require_token(raw.get("ledger_id"), "ledger_id"),
        "operation_key": require_token(raw.get("operation_key"), "operation_key"),
        "operation": operation,
        "expected": normalize_expected(raw.get("expected"), operation),
    }
    raw_blob = raw.get("blob")
    if operation["kind"].startswith("evidence."):
        if not isinstance(raw_blob, dict):
            raise BrokerError("invalid_request", f"{operation['kind']} requires blob metadata")
        require_exact_keys(raw_blob, {"sha256", "size_bytes"}, "blob")
        size_bytes = raw_blob.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 0:
            raise BrokerError("invalid_request", "blob size_bytes must be a non-negative integer")
        normalized["blob"] = {
            "sha256": require_sha256(raw_blob.get("sha256"), "blob sha256"),
            "size_bytes": size_bytes,
        }
    elif raw_blob is not None:
        raise BrokerError("invalid_request", f"{operation['kind']} does not accept blob metadata")
    return normalized


def normalize_request(raw: object) -> dict:
    if not isinstance(raw, dict):
        raise BrokerError("invalid_request", "request must contain a JSON object")
    action = raw.get("action")
    if action == "commit":
        return normalize_commit_request(raw)
    if action == "projection.snapshot":
        require_exact_keys(
            raw,
            {
                "protocol_version",
                "action",
                "ledger_id",
                "through_commit_sequence",
                "after",
                "limit",
            },
            "request",
        )
        if raw.get("protocol_version") != PROTOCOL_VERSION:
            raise BrokerError(
                "unsupported_protocol",
                f"protocol_version must be {PROTOCOL_VERSION}",
            )
        through_sequence = raw.get("through_commit_sequence")
        if through_sequence is not None and (
            not isinstance(through_sequence, int)
            or isinstance(through_sequence, bool)
            or through_sequence < 0
        ):
            raise BrokerError(
                "invalid_request",
                "through_commit_sequence must be a non-negative integer",
            )
        after = raw.get("after")
        if after is not None:
            if not isinstance(after, dict):
                raise BrokerError("invalid_request", "after must be an object or null")
            require_exact_keys(after, {"record_type", "record_id"}, "after")
            after = {
                "record_type": require_token(after.get("record_type"), "after record_type"),
                "record_id": require_token(after.get("record_id"), "after record_id"),
            }
            if after["record_type"] not in RECORD_TYPE_ORDER:
                raise BrokerError("invalid_request", "after record_type is not supported")
        limit = raw.get("limit", MAX_SNAPSHOT_PAGE_RECORDS)
        if (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or not 1 <= limit <= MAX_SNAPSHOT_PAGE_RECORDS
        ):
            raise BrokerError(
                "invalid_request",
                f"limit must be between 1 and {MAX_SNAPSHOT_PAGE_RECORDS}",
            )
        return {
            "protocol_version": PROTOCOL_VERSION,
            "action": "projection.snapshot",
            "ledger_id": require_token(raw.get("ledger_id"), "ledger_id"),
            "through_commit_sequence": through_sequence,
            "after": after,
            "limit": limit,
        }
    raise BrokerError("invalid_request", "action must be commit or projection.snapshot")


def digest_request(request: dict) -> str:
    semantic_request = {key: value for key, value in request.items() if key != "operation_key"}
    return sha256_text(canonical_json(semantic_request))


def fsync_directory(path: Path) -> None:
    directory_fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def schema_manifest_sha256(conn: sqlite3.Connection) -> str:
    rows = conn.execute(
        """
        SELECT type, name, sql FROM sqlite_schema
        WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'
        ORDER BY type, name
        """
    )
    manifest = [
        {
            "type": row["type"],
            "name": row["name"],
            "sql": " ".join(row["sql"].split()),
        }
        for row in rows
    ]
    return sha256_text(canonical_json(manifest))


def stage_evidence(content_root: Path, item: dict, source_fd: int) -> StagedBlob:
    content_store = content_root / "sha256"
    if content_store.is_symlink() or not content_store.is_dir():
        raise BrokerError("content_store_corrupt", "content store root is missing or unsafe")
    target_dir = content_store / item["sha256"][:2]
    if target_dir.is_symlink() or (target_dir.exists() and not target_dir.is_dir()):
        raise BrokerError("content_store_corrupt", f"content shard is unsafe: {target_dir}")
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    shard_stat = target_dir.stat()
    if (
        not stat.S_ISDIR(shard_stat.st_mode)
        or shard_stat.st_uid != os.geteuid()
        or stat.S_IMODE(shard_stat.st_mode) & 0o077
    ):
        raise BrokerError("content_store_corrupt", f"content shard is not private: {target_dir}")
    fsync_directory(content_store)
    temp_fd, temp_name = tempfile.mkstemp(prefix=".staged-", dir=target_dir)
    temp_path = Path(temp_name)
    digest = hashlib.sha256()
    size = 0
    try:
        source_stat = os.fstat(source_fd)
        if not stat.S_ISREG(source_stat.st_mode):
            raise BrokerError("evidence_unavailable", "evidence descriptor is not a regular file")
        try:
            os.lseek(source_fd, 0, os.SEEK_SET)
        except OSError as exc:
            raise BrokerError(
                "evidence_unavailable",
                f"evidence descriptor cannot be rewound: {exc}",
            ) from exc
        os.fchmod(temp_fd, 0o600)
        while chunk := os.read(source_fd, 1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
            view = memoryview(chunk)
            while view:
                written = os.write(temp_fd, view)
                if written == 0:
                    raise BrokerError("content_store_error", "short write while staging evidence")
                view = view[written:]
        os.fsync(temp_fd)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        os.close(temp_fd)

    actual_sha256 = digest.hexdigest()
    if actual_sha256 != item["sha256"]:
        temp_path.unlink(missing_ok=True)
        raise BrokerError(
            "evidence_hash_mismatch",
            f"expected {item['sha256']}, got {actual_sha256}",
        )
    if size != item["size_bytes"]:
        temp_path.unlink(missing_ok=True)
        raise BrokerError(
            "evidence_size_mismatch",
            f"expected {item['size_bytes']} bytes, got {size}",
        )

    storage_key = f"sha256/{actual_sha256[:2]}/{actual_sha256}"
    target = content_root / storage_key
    if target.is_symlink():
        temp_path.unlink(missing_ok=True)
        raise BrokerError("content_store_corrupt", f"stored evidence path is a symlink: {target}")
    try:
        os.link(temp_path, target)
    except FileExistsError:
        pass
    finally:
        temp_path.unlink(missing_ok=True)
    fsync_directory(target_dir)

    stored_hash, stored_size = hash_file(target)
    if stored_hash != actual_sha256 or stored_size != size:
        raise BrokerError("content_store_corrupt", f"stored evidence failed verification: {target}")
    return StagedBlob(actual_sha256, size, storage_key)


class AuthorityStore:
    def __init__(self, database_path: Path, content_root: Path) -> None:
        self.database_path = database_path
        self.content_root = content_root

    def connect(self, read_only: bool = False) -> sqlite3.Connection:
        if read_only:
            uri = f"{self.database_path.as_uri()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True, timeout=5)
        else:
            conn = sqlite3.connect(self.database_path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA trusted_schema = OFF")
        conn.execute("PRAGMA busy_timeout = 5000")
        if not read_only:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = FULL")
        return conn

    def initialize(self, config: BootstrapConfig) -> None:
        if self.database_path.is_symlink() or self.content_root.is_symlink():
            raise BrokerError("unsafe_store_path", "authority store paths must not be symlinks")
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.content_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.content_root, 0o700)
        (self.content_root / "sha256").mkdir(parents=True, exist_ok=True)
        os.chmod(self.content_root / "sha256", 0o700)
        conn = self.connect()
        try:
            os.chmod(self.database_path, 0o600)
            current_version = conn.execute("PRAGMA user_version").fetchone()[0]
            application_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if current_version not in {0, STORE_SCHEMA_VERSION}:
                raise BrokerError(
                    "unsupported_store_schema",
                    f"store schema {current_version} is not supported",
                )
            if application_id not in {0, STORE_APPLICATION_ID}:
                raise BrokerError(
                    "unsupported_store",
                    f"store application ID {application_id} is not supported",
                )
            self._create_schema(conn)
            self._seed_bootstrap(conn, config)
        finally:
            conn.close()
        fsync_directory(self.database_path.parent)
        fsync_directory(self.content_root)

    def validate(self) -> None:
        if not self.database_path.is_file():
            raise BrokerError(
                "store_unavailable", f"authority store not found: {self.database_path}"
            )
        if not self.content_root.is_dir():
            raise BrokerError("store_unavailable", f"content store not found: {self.content_root}")
        if self.database_path.is_symlink() or self.content_root.is_symlink():
            raise BrokerError("unsafe_store_path", "authority store paths must not be symlinks")
        for path in (self.database_path, self.content_root):
            path_stat = path.stat()
            if path_stat.st_uid != os.geteuid():
                raise BrokerError(
                    "unsafe_store_owner",
                    f"authority store path is not owned by broker UID {os.geteuid()}: {path}",
                )
            if stat.S_IMODE(path_stat.st_mode) & 0o077:
                raise BrokerError(
                    "unsafe_store_permissions",
                    f"authority store path allows group or other access: {path}",
                )
        conn = self.connect(read_only=True)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version != STORE_SCHEMA_VERSION:
                raise BrokerError(
                    "unsupported_store_schema",
                    f"store schema {version} is not supported; expected {STORE_SCHEMA_VERSION}",
                )
            application_id = conn.execute("PRAGMA application_id").fetchone()[0]
            if application_id != STORE_APPLICATION_ID:
                raise BrokerError(
                    "unsupported_store",
                    f"store application ID {application_id} is not supported",
                )
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise BrokerError("store_corrupt", f"SQLite integrity check failed: {integrity}")
            tables = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_schema WHERE type = 'table'")
            }
            missing_tables = REQUIRED_TABLES - tables
            if missing_tables:
                raise BrokerError(
                    "store_corrupt",
                    f"authority store is missing table(s): {', '.join(sorted(missing_tables))}",
                )
            triggers = {
                row["name"]
                for row in conn.execute("SELECT name FROM sqlite_schema WHERE type = 'trigger'")
            }
            required_triggers = {
                f"{table}_{operation}"
                for table in APPEND_ONLY_TABLES
                for operation in ("no_update", "no_delete")
            }
            missing_triggers = required_triggers - triggers
            if missing_triggers:
                raise BrokerError(
                    "store_corrupt",
                    "authority store is missing append-only trigger(s): "
                    + ", ".join(sorted(missing_triggers)),
                )
            stored_manifest = conn.execute(
                "SELECT value FROM store_meta WHERE key = 'schema_manifest_sha256'"
            ).fetchone()
            actual_manifest = schema_manifest_sha256(conn)
            if not stored_manifest or stored_manifest["value"] != actual_manifest:
                raise BrokerError("store_corrupt", "authority store schema manifest mismatch")
        except sqlite3.Error as exc:
            raise BrokerError(
                "store_corrupt", f"could not validate authority store: {exc}"
            ) from exc
        finally:
            conn.close()

    def _create_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS store_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS policy_snapshots (
                policy_id TEXT NOT NULL,
                generation INTEGER NOT NULL CHECK (generation > 0),
                policy_sha256 TEXT NOT NULL CHECK (length(policy_sha256) = 64),
                policy_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (policy_id, generation)
            );

            CREATE TABLE IF NOT EXISTS policy_roles (
                policy_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                uid INTEGER NOT NULL CHECK (uid >= 0),
                role TEXT NOT NULL CHECK (role IN ('builder', 'verifier')),
                PRIMARY KEY (policy_id, generation, uid, role),
                FOREIGN KEY (policy_id, generation)
                    REFERENCES policy_snapshots(policy_id, generation)
            );

            CREATE TABLE IF NOT EXISTS ledger_policy_events (
                policy_event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                ledger_id TEXT NOT NULL,
                event_type TEXT NOT NULL CHECK (event_type IN ('enroll', 'rotate', 'revoke')),
                policy_id TEXT NOT NULL,
                generation INTEGER NOT NULL,
                policy_sha256 TEXT NOT NULL,
                previous_event_hash TEXT,
                event_body_json TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                UNIQUE (ledger_id, policy_event_sequence),
                FOREIGN KEY (policy_id, generation)
                    REFERENCES policy_snapshots(policy_id, generation)
            );

            CREATE TABLE IF NOT EXISTS authority_commits (
                commit_sequence INTEGER PRIMARY KEY,
                ledger_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                operation_key TEXT NOT NULL UNIQUE,
                request_digest TEXT NOT NULL CHECK (length(request_digest) = 64),
                request_json TEXT NOT NULL,
                actor_pid INTEGER NOT NULL,
                actor_uid INTEGER NOT NULL,
                actor_gid INTEGER NOT NULL,
                policy_id TEXT NOT NULL,
                policy_generation INTEGER NOT NULL,
                policy_sha256 TEXT NOT NULL,
                previous_commit_hash TEXT,
                commit_body_json TEXT NOT NULL,
                commit_hash TEXT NOT NULL UNIQUE,
                receipt_json TEXT NOT NULL,
                receipt_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                FOREIGN KEY (policy_id, policy_generation)
                    REFERENCES policy_snapshots(policy_id, generation)
            );

            CREATE TABLE IF NOT EXISTS authority_events (
                event_id TEXT PRIMARY KEY,
                commit_sequence INTEGER NOT NULL,
                ledger_id TEXT NOT NULL,
                record_type TEXT NOT NULL,
                record_id TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                operation TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                actor_uid INTEGER NOT NULL,
                policy_id TEXT NOT NULL,
                policy_generation INTEGER NOT NULL,
                previous_event_hash TEXT,
                event_body_json TEXT NOT NULL,
                event_hash TEXT NOT NULL UNIQUE,
                UNIQUE (ledger_id, record_type, record_id, version),
                FOREIGN KEY (commit_sequence) REFERENCES authority_commits(commit_sequence)
            );

            CREATE TABLE IF NOT EXISTS authority_blobs (
                sha256 TEXT PRIMARY KEY CHECK (length(sha256) = 64),
                size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
                storage_key TEXT NOT NULL UNIQUE,
                first_commit_sequence INTEGER NOT NULL,
                FOREIGN KEY (first_commit_sequence)
                    REFERENCES authority_commits(commit_sequence)
            );

            CREATE TABLE IF NOT EXISTS commit_blobs (
                commit_sequence INTEGER NOT NULL,
                sha256 TEXT NOT NULL,
                PRIMARY KEY (commit_sequence, sha256),
                FOREIGN KEY (commit_sequence) REFERENCES authority_commits(commit_sequence),
                FOREIGN KEY (sha256) REFERENCES authority_blobs(sha256)
            );

            CREATE TABLE IF NOT EXISTS projection_outbox (
                commit_sequence INTEGER PRIMARY KEY,
                ledger_id TEXT NOT NULL,
                receipt_hash TEXT NOT NULL,
                projection_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (commit_sequence) REFERENCES authority_commits(commit_sequence)
            );
            """
        )
        metadata = {
            "application": "operator-authority-broker",
            "schema_version": str(STORE_SCHEMA_VERSION),
            "hash_format": "sha256-canonical-json-v1",
        }
        for key, value in metadata.items():
            existing = conn.execute("SELECT value FROM store_meta WHERE key = ?", (key,)).fetchone()
            if existing and existing["value"] != value:
                raise BrokerError("store_corrupt", f"store metadata mismatch for {key}")
            if not existing:
                conn.execute("INSERT INTO store_meta(key, value) VALUES (?, ?)", (key, value))
        for table in APPEND_ONLY_TABLES:
            conn.executescript(
                f"""
                CREATE TRIGGER IF NOT EXISTS {table}_no_update
                BEFORE UPDATE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, '{table} is append-only by broker contract');
                END;
                CREATE TRIGGER IF NOT EXISTS {table}_no_delete
                BEFORE DELETE ON {table}
                BEGIN
                    SELECT RAISE(ABORT, '{table} is append-only by broker contract');
                END;
                """
            )
        manifest_sha256 = schema_manifest_sha256(conn)
        existing_manifest = conn.execute(
            "SELECT value FROM store_meta WHERE key = 'schema_manifest_sha256'"
        ).fetchone()
        if existing_manifest and existing_manifest["value"] != manifest_sha256:
            raise BrokerError("store_corrupt", "authority store schema manifest mismatch")
        if not existing_manifest:
            conn.execute(
                "INSERT INTO store_meta(key, value) VALUES ('schema_manifest_sha256', ?)",
                (manifest_sha256,),
            )
        conn.execute(f"PRAGMA application_id = {STORE_APPLICATION_ID}")
        conn.execute(f"PRAGMA user_version = {STORE_SCHEMA_VERSION}")

    def _seed_bootstrap(self, conn: sqlite3.Connection, config: BootstrapConfig) -> None:
        created_at = utc_now()
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = conn.execute(
                """
                SELECT policy_sha256, policy_json
                FROM policy_snapshots
                WHERE policy_id = ? AND generation = ?
                """,
                (config.policy_id, config.policy_generation),
            ).fetchone()
            if existing:
                if (
                    existing["policy_sha256"] != config.policy_sha256
                    or existing["policy_json"] != config.policy_json
                ):
                    raise BrokerError(
                        "bootstrap_conflict",
                        "stored policy generation differs from bootstrap config",
                    )
            else:
                conn.execute(
                    """
                    INSERT INTO policy_snapshots(
                        policy_id, generation, policy_sha256, policy_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        config.policy_id,
                        config.policy_generation,
                        config.policy_sha256,
                        config.policy_json,
                        created_at,
                    ),
                )
                for uid, roles in sorted(config.roles.items()):
                    for role in sorted(roles):
                        conn.execute(
                            """
                            INSERT INTO policy_roles(policy_id, generation, uid, role)
                            VALUES (?, ?, ?, ?)
                            """,
                            (config.policy_id, config.policy_generation, uid, role),
                        )
            stored_roles = {
                (row["uid"], row["role"])
                for row in conn.execute(
                    """
                    SELECT uid, role FROM policy_roles
                    WHERE policy_id = ? AND generation = ?
                    """,
                    (config.policy_id, config.policy_generation),
                )
            }
            expected_roles = {(uid, role) for uid, roles in config.roles.items() for role in roles}
            if stored_roles != expected_roles:
                raise BrokerError("bootstrap_conflict", "stored policy roles differ from config")

            for ledger_id in config.ledgers:
                current = self._current_policy_event(conn, ledger_id)
                if current:
                    if (
                        current["event_type"] != "enroll"
                        or current["policy_id"] != config.policy_id
                        or current["generation"] != config.policy_generation
                        or current["policy_sha256"] != config.policy_sha256
                    ):
                        raise BrokerError(
                            "bootstrap_conflict",
                            f"ledger {ledger_id} is already bound to another policy",
                        )
                    continue
                event_body = {
                    "ledger_id": ledger_id,
                    "event_type": "enroll",
                    "policy_id": config.policy_id,
                    "generation": config.policy_generation,
                    "policy_sha256": config.policy_sha256,
                    "previous_event_hash": None,
                }
                event_body_json = canonical_json(event_body)
                conn.execute(
                    """
                    INSERT INTO ledger_policy_events(
                        ledger_id, event_type, policy_id, generation, policy_sha256,
                        previous_event_hash, event_body_json, event_hash, created_at
                    ) VALUES (?, 'enroll', ?, ?, ?, NULL, ?, ?, ?)
                    """,
                    (
                        ledger_id,
                        config.policy_id,
                        config.policy_generation,
                        config.policy_sha256,
                        event_body_json,
                        sha256_text(event_body_json),
                        created_at,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    @staticmethod
    def _current_policy_event(conn: sqlite3.Connection, ledger_id: str) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT * FROM ledger_policy_events
            WHERE ledger_id = ?
            ORDER BY policy_event_sequence DESC
            LIMIT 1
            """,
            (ledger_id,),
        ).fetchone()

    @staticmethod
    def _existing_operation(conn: sqlite3.Connection, operation_key: str) -> sqlite3.Row | None:
        return conn.execute(
            "SELECT * FROM authority_commits WHERE operation_key = ?",
            (operation_key,),
        ).fetchone()

    @staticmethod
    def _idempotent_result(
        existing: sqlite3.Row,
        ledger_id: str,
        actor_uid: int,
        request_digest: str,
    ) -> dict:
        if existing["ledger_id"] != ledger_id or existing["actor_uid"] != actor_uid:
            raise BrokerError(
                "operation_key_scope_conflict",
                "operation_key is already bound to another ledger or peer UID",
            )
        if existing["request_digest"] != request_digest:
            raise BrokerError(
                "operation_key_conflict",
                "operation_key was already committed with a different request digest",
            )
        return json.loads(existing["receipt_json"])

    def lookup_idempotent(
        self,
        request: dict,
        peer: PeerCredentials,
        request_digest: str,
    ) -> dict | None:
        conn = self.connect(read_only=True)
        try:
            existing = self._existing_operation(conn, request["operation_key"])
            if not existing:
                return None
            return self._idempotent_result(
                existing,
                request["ledger_id"],
                peer.uid,
                request_digest,
            )
        finally:
            conn.close()

    def projection_snapshot(self, request: dict, peer: PeerCredentials) -> dict:
        ledger_id = request["ledger_id"]
        conn = self.connect(read_only=True)
        conn.execute("BEGIN")
        try:
            policy = self._current_policy_event(conn, ledger_id)
            if not policy:
                raise BrokerError("unknown_ledger", f"ledger is not enrolled: {ledger_id}")
            if policy["event_type"] == "revoke":
                raise BrokerError("policy_revoked", f"ledger policy is revoked: {ledger_id}")
            roles = [
                row["role"]
                for row in conn.execute(
                    """
                    SELECT role FROM policy_roles
                    WHERE policy_id = ? AND generation = ? AND uid = ?
                    ORDER BY role
                    """,
                    (policy["policy_id"], policy["generation"], peer.uid),
                )
            ]
            if not roles:
                raise BrokerError(
                    "unknown_peer_uid",
                    f"peer UID {peer.uid} is not registered for ledger {ledger_id}",
                    peer_uid=peer.uid,
                )
            current_sequence = conn.execute(
                """
                SELECT COALESCE(MAX(commit_sequence), 0)
                FROM authority_commits WHERE ledger_id = ?
                """,
                (ledger_id,),
            ).fetchone()[0]
            through_sequence = request["through_commit_sequence"]
            if through_sequence is None:
                through_sequence = current_sequence
            elif through_sequence > current_sequence:
                raise BrokerError(
                    "snapshot_sequence_unavailable",
                    f"ledger has no state through commit sequence {through_sequence}",
                    current_commit_sequence=current_sequence,
                )

            records_hash = hashlib.sha256()
            page_records = []
            record_count = 0
            has_more = False
            after = request["after"]
            after_key = (after["record_type"], after["record_id"]) if after is not None else None
            for row in conn.execute(
                """
                SELECT event.record_type, event.record_id, event.version,
                       event.event_hash, event.payload_json, event.actor_uid,
                       event.policy_id, event.policy_generation,
                       authority_commit.policy_sha256
                FROM authority_events AS event
                JOIN authority_commits AS authority_commit
                  ON authority_commit.commit_sequence = event.commit_sequence
                WHERE event.ledger_id = ?
                  AND event.commit_sequence <= ?
                  AND NOT EXISTS (
                      SELECT 1 FROM authority_events AS newer
                      WHERE newer.ledger_id = event.ledger_id
                        AND newer.record_type = event.record_type
                        AND newer.record_id = event.record_id
                        AND newer.commit_sequence <= ?
                        AND newer.version > event.version
                  )
                ORDER BY event.record_type, event.record_id
                """,
                (ledger_id, through_sequence, through_sequence),
            ):
                record = {
                    "record_type": row["record_type"],
                    "record_id": row["record_id"],
                    "version": row["version"],
                    "event_hash": row["event_hash"],
                    "payload": json.loads(row["payload_json"]),
                    "authority": {
                        "actor_uid": row["actor_uid"],
                        "policy": {
                            "id": row["policy_id"],
                            "generation": row["policy_generation"],
                            "sha256": row["policy_sha256"],
                        },
                    },
                }
                encoded_record = canonical_json(record).encode("utf-8")
                records_hash.update(struct.pack("!I", len(encoded_record)))
                records_hash.update(encoded_record)
                record_count += 1
                record_key = (record["record_type"], record["record_id"])
                if after_key is not None and record_key <= after_key:
                    continue
                if len(page_records) < request["limit"]:
                    page_records.append(record)
                else:
                    has_more = True

            snapshot_identity = {
                "ledger_id": ledger_id,
                "through_commit_sequence": through_sequence,
                "policy": {
                    "id": policy["policy_id"],
                    "generation": policy["generation"],
                    "sha256": policy["policy_sha256"],
                },
                "record_count": record_count,
                "records_sha256": records_hash.hexdigest(),
            }
            return {
                **snapshot_identity,
                "snapshot_digest": sha256_text(canonical_json(snapshot_identity)),
                "records": page_records,
                "has_more": has_more,
                "next_after": (
                    {
                        "record_type": page_records[-1]["record_type"],
                        "record_id": page_records[-1]["record_id"],
                    }
                    if has_more and page_records
                    else None
                ),
            }
        finally:
            conn.rollback()
            conn.close()

    def preflight(self, request: dict, peer: PeerCredentials) -> None:
        conn = self.connect(read_only=True)
        try:
            self._authorize_and_validate_state(conn, request, peer)
        finally:
            conn.close()

    def _authorize_and_validate_state(
        self,
        conn: sqlite3.Connection,
        request: dict,
        peer: PeerCredentials,
    ) -> tuple[sqlite3.Row, list[dict]]:
        policy = self._current_policy_event(conn, request["ledger_id"])
        if not policy:
            raise BrokerError("unknown_ledger", f"ledger is not enrolled: {request['ledger_id']}")
        if policy["event_type"] == "revoke":
            raise BrokerError("policy_revoked", f"ledger policy is revoked: {request['ledger_id']}")
        operation = request["operation"]
        operation_kind = operation["kind"]
        if operation_kind == "ledger.enroll":
            if peer.uid != 0:
                raise BrokerError(
                    "root_required",
                    "ledger enrollment requires a root SO_PEERCRED identity",
                    peer_uid=peer.uid,
                )
            existing_commits = conn.execute(
                "SELECT COUNT(*) FROM authority_commits",
            ).fetchone()[0]
            if existing_commits:
                raise BrokerError(
                    "ledger_already_active",
                    "ledger enrollment must be the authority store's first broker commit",
                )
            return policy, []

        roles = {
            row["role"]
            for row in conn.execute(
                """
                SELECT role FROM policy_roles
                WHERE policy_id = ? AND generation = ? AND uid = ?
                """,
                (policy["policy_id"], policy["generation"], peer.uid),
            )
        }
        if not roles:
            raise BrokerError(
                "unknown_peer_uid",
                f"peer UID {peer.uid} is not registered for ledger {request['ledger_id']}",
                peer_uid=peer.uid,
            )
        required_role = OPERATION_ROLES[operation_kind]
        if required_role not in roles:
            raise BrokerError(
                "missing_role",
                f"peer UID {peer.uid} lacks required role {required_role}",
                peer_uid=peer.uid,
                required_role=required_role,
            )

        heads = {}
        for expected in request["expected"]:
            head = conn.execute(
                """
                SELECT version, event_hash, payload_json, actor_uid FROM authority_events
                WHERE ledger_id = ? AND record_type = ? AND record_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (request["ledger_id"], expected["record_type"], expected["record_id"]),
            ).fetchone()
            expected_version = expected["version"]
            if expected_version == 0:
                if head:
                    raise BrokerError(
                        "stale_record",
                        f"{expected['record_type']} {expected['record_id']} already exists",
                    )
            elif not head:
                raise BrokerError(
                    "stale_record",
                    f"{expected['record_type']} {expected['record_id']} does not exist",
                )
            elif (
                head["version"] != expected_version or head["event_hash"] != expected["event_hash"]
            ):
                raise BrokerError(
                    "stale_record",
                    f"precondition failed for {expected['record_type']} {expected['record_id']}",
                    current_version=head["version"],
                    current_event_hash=head["event_hash"],
                )
            heads[expected["record_type"]] = head

        if operation_kind == "evidence.attach_status":
            author = conn.execute(
                """
                SELECT actor_uid FROM authority_events
                WHERE ledger_id = ? AND record_type = 'claim' AND record_id = ?
                ORDER BY version ASC LIMIT 1
                """,
                (request["ledger_id"], operation["claim_id"]),
            ).fetchone()
            if not author:
                raise BrokerError(
                    "unknown_claim",
                    f"claim is not authoritative: {operation['claim_id']}",
                )
            if author["actor_uid"] == peer.uid:
                raise BrokerError(
                    "self_verification",
                    f"verifier UID {peer.uid} matches claim author UID",
                    author_uid=author["actor_uid"],
                    verifier_uid=peer.uid,
                )
        mutations = self._build_mutations(request, peer, heads, conn)
        for mutation in mutations:
            payload_size = len(canonical_json(mutation["payload"]).encode("utf-8"))
            if payload_size > MAX_RECORD_BYTES:
                raise BrokerError(
                    "record_too_large",
                    f"{mutation['record_type']} {mutation['record_id']} exceeds "
                    f"{MAX_RECORD_BYTES} canonical bytes",
                )
        return policy, mutations

    @staticmethod
    def _mutation(expected: dict, payload: dict) -> dict:
        return {
            "record_type": expected["record_type"],
            "record_id": expected["record_id"],
            "expected_version": expected["version"],
            "expected_event_hash": expected["event_hash"],
            "payload": payload,
        }

    def _build_mutations(
        self,
        request: dict,
        peer: PeerCredentials,
        heads: dict[str, sqlite3.Row | None],
        conn: sqlite3.Connection,
    ) -> list[dict]:
        operation = request["operation"]
        kind = operation["kind"]
        expected = {item["record_type"]: item for item in request["expected"]}

        if kind == "claim.create":
            task = (
                json.loads(heads["task"]["payload_json"])
                if heads["task"]
                else {
                    "task_id": operation["task_id"],
                    "claim_ids": [],
                    "evidence_ids": [],
                    "verified_claim_ids": [],
                    "status": "open",
                }
            )
            if task.get("task_id") != operation["task_id"]:
                raise BrokerError(
                    "store_corrupt", "task payload identity does not match its record"
                )
            if operation["claim_id"] in task.get("claim_ids", []):
                raise BrokerError("store_corrupt", "new claim is already listed by its task")
            task["claim_ids"] = [*task.get("claim_ids", []), operation["claim_id"]]
            claim = {
                "claim_id": operation["claim_id"],
                "task_id": operation["task_id"],
                "claim_type": operation["claim_type"],
                "text": operation["text"],
                "required_gate": operation.get("required_gate"),
                "evidence_ids": [],
                "verification_status": "unverified",
                "author_uid": peer.uid,
            }
            return [
                self._mutation(expected["task"], task),
                self._mutation(expected["claim"], claim),
            ]

        if kind.startswith("evidence."):
            if not heads["task"]:
                raise BrokerError(
                    "unknown_task", f"task is not authoritative: {operation['task_id']}"
                )
            if not heads["claim"]:
                raise BrokerError(
                    "unknown_claim", f"claim is not authoritative: {operation['claim_id']}"
                )
            task = json.loads(heads["task"]["payload_json"])
            claim = json.loads(heads["claim"]["payload_json"])
            if task.get("task_id") != operation["task_id"]:
                raise BrokerError(
                    "store_corrupt", "task payload identity does not match its record"
                )
            if (
                claim.get("claim_id") != operation["claim_id"]
                or claim.get("task_id") != operation["task_id"]
                or operation["claim_id"] not in task.get("claim_ids", [])
            ):
                raise BrokerError(
                    "invalid_relationship", "claim does not belong to the requested task"
                )
            evidence_id = operation["evidence_id"]
            if evidence_id in claim.get("evidence_ids", []) or evidence_id in task.get(
                "evidence_ids", []
            ):
                raise BrokerError(
                    "store_corrupt", "new evidence is already listed by authority state"
                )
            claim["evidence_ids"] = [*claim.get("evidence_ids", []), evidence_id]
            task["evidence_ids"] = [*task.get("evidence_ids", []), evidence_id]
            status = operation.get("verification_status", "draft")
            evidence = {
                "evidence_id": evidence_id,
                "task_id": operation["task_id"],
                "claim_id": operation["claim_id"],
                "evidence_type": operation["evidence_type"],
                "sha256": request["blob"]["sha256"],
                "size_bytes": request["blob"]["size_bytes"],
                "verification_status": status,
                "policy_authority": "external_broker",
                "attached_by_uid": peer.uid,
            }
            if kind == "evidence.attach_status":
                evidence["verification_authority"] = "uid_isolated"
                evidence["verified_by_uid"] = peer.uid
                claim["verification_status"] = status
                claim["verified_by_uid"] = peer.uid
                claim["verification_authority"] = "uid_isolated"
                claim["policy_authority"] = "external_broker"
                verified_claims = list(task.get("verified_claim_ids", []))
                if status == "verified" and operation["claim_id"] not in verified_claims:
                    verified_claims.append(operation["claim_id"])
                elif status != "verified":
                    verified_claims = [
                        claim_id
                        for claim_id in verified_claims
                        if claim_id != operation["claim_id"]
                    ]
                    if task.get("transition_claim_id") == operation["claim_id"]:
                        task["status"] = "open"
                        task.pop("transition_claim_id", None)
                        task.pop("transition_claim_event_hash", None)
                        task.pop("transitioned_by_uid", None)
                task["verified_claim_ids"] = verified_claims
            return [
                self._mutation(expected["task"], task),
                self._mutation(expected["claim"], claim),
                self._mutation(expected["evidence"], evidence),
            ]

        if not heads["task"]:
            raise BrokerError("unknown_task", f"task is not authoritative: {operation['task_id']}")
        task = json.loads(heads["task"]["payload_json"])
        if task.get("task_id") != operation["task_id"]:
            raise BrokerError("store_corrupt", "task payload identity does not match its record")
        if operation["status"] == "verified":
            if task.get("status") != "open":
                raise BrokerError(
                    "invalid_transition",
                    "verified transition requires open task state",
                )
            claim = conn.execute(
                """
                SELECT payload_json, event_hash FROM authority_events
                WHERE ledger_id = ? AND record_type = 'claim' AND record_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (request["ledger_id"], operation["claim_id"]),
            ).fetchone()
            if not claim:
                raise BrokerError(
                    "unknown_claim", f"claim is not authoritative: {operation['claim_id']}"
                )
            claim_payload = json.loads(claim["payload_json"])
            if (
                claim_payload.get("task_id") != operation["task_id"]
                or claim_payload.get("verification_status") != "verified"
                or claim_payload.get("verification_authority") != "uid_isolated"
                or claim_payload.get("policy_authority") != "external_broker"
            ):
                raise BrokerError(
                    "unverified_claim", "verified transition requires a verified claim for the task"
                )
            task["status"] = "verified"
            task["transition_claim_id"] = operation["claim_id"]
            task["transition_claim_event_hash"] = claim["event_hash"]
        else:
            if task.get("status") != "verified":
                raise BrokerError(
                    "invalid_transition", "complete transition requires verified task state"
                )
            transition_claim_id = task.get("transition_claim_id")
            claim = conn.execute(
                """
                SELECT payload_json FROM authority_events
                WHERE ledger_id = ? AND record_type = 'claim' AND record_id = ?
                ORDER BY version DESC LIMIT 1
                """,
                (request["ledger_id"], transition_claim_id),
            ).fetchone()
            claim_payload = json.loads(claim["payload_json"]) if claim else {}
            if (
                claim_payload.get("verification_status") != "verified"
                or claim_payload.get("verification_authority") != "uid_isolated"
                or claim_payload.get("policy_authority") != "external_broker"
            ):
                raise BrokerError(
                    "invalid_transition",
                    "complete transition requires its authoritative claim to remain verified",
                )
            task["status"] = "complete"
        task["transitioned_by_uid"] = peer.uid
        return [self._mutation(expected["task"], task)]

    def commit(
        self,
        request: dict,
        peer: PeerCredentials,
        request_digest: str,
        staged_blobs: list[StagedBlob],
    ) -> tuple[dict, bool]:
        conn = self.connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            existing = self._existing_operation(conn, request["operation_key"])
            if existing:
                receipt = self._idempotent_result(
                    existing,
                    request["ledger_id"],
                    peer.uid,
                    request_digest,
                )
                conn.rollback()
                return receipt, True

            policy, mutations = self._authorize_and_validate_state(conn, request, peer)
            operation_kind = request["operation"]["kind"]
            commit_sequence = conn.execute(
                "SELECT COALESCE(MAX(commit_sequence), 0) + 1 FROM authority_commits"
            ).fetchone()[0]
            previous_commit = conn.execute(
                """
                SELECT commit_hash FROM authority_commits
                ORDER BY commit_sequence DESC LIMIT 1
                """
            ).fetchone()
            previous_commit_hash = previous_commit["commit_hash"] if previous_commit else None

            event_rows = []
            event_summaries = []
            for mutation in mutations:
                version = mutation["expected_version"] + 1
                previous_event_hash = mutation["expected_event_hash"]
                payload_json = canonical_json(mutation["payload"])
                event_body = {
                    "commit_sequence": commit_sequence,
                    "ledger_id": request["ledger_id"],
                    "record_type": mutation["record_type"],
                    "record_id": mutation["record_id"],
                    "version": version,
                    "operation": operation_kind,
                    "payload": mutation["payload"],
                    "actor_uid": peer.uid,
                    "policy_id": policy["policy_id"],
                    "policy_generation": policy["generation"],
                    "previous_event_hash": previous_event_hash,
                }
                event_body_json = canonical_json(event_body)
                event_hash = sha256_text(event_body_json)
                event_id = f"evt-{event_hash[:32]}"
                event_rows.append(
                    (
                        event_id,
                        commit_sequence,
                        request["ledger_id"],
                        mutation["record_type"],
                        mutation["record_id"],
                        version,
                        operation_kind,
                        payload_json,
                        peer.uid,
                        policy["policy_id"],
                        policy["generation"],
                        previous_event_hash,
                        event_body_json,
                        event_hash,
                    )
                )
                event_summaries.append(
                    {
                        "event_id": event_id,
                        "record_type": mutation["record_type"],
                        "record_id": mutation["record_id"],
                        "version": version,
                        "event_hash": event_hash,
                    }
                )

            blob_summaries = [
                blob.as_dict() for blob in sorted(staged_blobs, key=lambda b: b.sha256)
            ]
            created_at = utc_now()
            commit_body = {
                "commit_sequence": commit_sequence,
                "ledger_id": request["ledger_id"],
                "operation": operation_kind,
                "operation_key": request["operation_key"],
                "request_digest": request_digest,
                "actor": {"pid": peer.pid, "uid": peer.uid, "gid": peer.gid},
                "policy": {
                    "id": policy["policy_id"],
                    "generation": policy["generation"],
                    "sha256": policy["policy_sha256"],
                },
                "events": event_summaries,
                "evidence": blob_summaries,
                "previous_commit_hash": previous_commit_hash,
            }
            commit_body_json = canonical_json(commit_body)
            commit_hash = sha256_text(commit_body_json)
            receipt_without_hash = {
                "protocol_version": PROTOCOL_VERSION,
                "status": "committed",
                "projection_status": "pending",
                **commit_body,
                "commit_hash": commit_hash,
            }
            receipt_hash = sha256_text(canonical_json(receipt_without_hash))
            receipt = {**receipt_without_hash, "receipt_hash": receipt_hash}
            receipt_json = canonical_json(receipt)

            conn.execute(
                """
                INSERT INTO authority_commits(
                    commit_sequence, ledger_id, operation, operation_key, request_digest,
                    request_json, actor_pid, actor_uid, actor_gid, policy_id,
                    policy_generation, policy_sha256, previous_commit_hash, commit_body_json,
                    commit_hash, receipt_json, receipt_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    commit_sequence,
                    request["ledger_id"],
                    operation_kind,
                    request["operation_key"],
                    request_digest,
                    canonical_json(request),
                    peer.pid,
                    peer.uid,
                    peer.gid,
                    policy["policy_id"],
                    policy["generation"],
                    policy["policy_sha256"],
                    previous_commit_hash,
                    commit_body_json,
                    commit_hash,
                    receipt_json,
                    receipt_hash,
                    created_at,
                ),
            )
            conn.executemany(
                """
                INSERT INTO authority_events(
                    event_id, commit_sequence, ledger_id, record_type, record_id, version,
                    operation, payload_json, actor_uid, policy_id, policy_generation,
                    previous_event_hash, event_body_json, event_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                event_rows,
            )
            for blob in staged_blobs:
                existing_blob = conn.execute(
                    "SELECT size_bytes, storage_key FROM authority_blobs WHERE sha256 = ?",
                    (blob.sha256,),
                ).fetchone()
                if existing_blob:
                    if (
                        existing_blob["size_bytes"] != blob.size_bytes
                        or existing_blob["storage_key"] != blob.storage_key
                    ):
                        raise BrokerError(
                            "content_store_corrupt",
                            f"stored blob metadata disagrees for {blob.sha256}",
                        )
                else:
                    conn.execute(
                        """
                        INSERT INTO authority_blobs(
                            sha256, size_bytes, storage_key, first_commit_sequence
                        ) VALUES (?, ?, ?, ?)
                        """,
                        (blob.sha256, blob.size_bytes, blob.storage_key, commit_sequence),
                    )
                conn.execute(
                    "INSERT INTO commit_blobs(commit_sequence, sha256) VALUES (?, ?)",
                    (commit_sequence, blob.sha256),
                )

            projection = {
                "commit_sequence": commit_sequence,
                "ledger_id": request["ledger_id"],
                "events": [
                    {
                        **summary,
                        "payload": mutation["payload"],
                    }
                    for summary, mutation in zip(event_summaries, mutations, strict=True)
                ],
                "evidence": blob_summaries,
                "receipt": receipt,
            }
            conn.execute(
                """
                INSERT INTO projection_outbox(
                    commit_sequence, ledger_id, receipt_hash, projection_json, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    commit_sequence,
                    request["ledger_id"],
                    receipt_hash,
                    canonical_json(projection),
                    created_at,
                ),
            )
            conn.commit()
            return receipt, False
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


class AuthorityBroker:
    def __init__(self, store: AuthorityStore) -> None:
        self.store = store

    def handle(
        self,
        raw_request: object,
        peer: PeerCredentials,
        evidence_fd: int | None = None,
    ) -> tuple[dict, bool]:
        request = normalize_request(raw_request)
        if request["action"] == "projection.snapshot":
            if evidence_fd is not None:
                raise BrokerError(
                    "unexpected_evidence_fd",
                    "projection.snapshot does not accept a file descriptor",
                )
            return {
                "ok": True,
                "snapshot": self.store.projection_snapshot(request, peer),
            }, False
        request_digest = digest_request(request)
        existing = self.store.lookup_idempotent(request, peer, request_digest)
        if existing is not None:
            return {"ok": True, "idempotent_replay": True, "receipt": existing}, False

        self.store.preflight(request, peer)
        staged_blobs = []
        if "blob" in request:
            if evidence_fd is None:
                raise BrokerError(
                    "evidence_fd_required", "evidence operation requires one file descriptor"
                )
            staged_blobs.append(
                stage_evidence(self.store.content_root, request["blob"], evidence_fd)
            )
        elif evidence_fd is not None:
            raise BrokerError(
                "unexpected_evidence_fd", "operation does not accept a file descriptor"
            )
        receipt, replay = self.store.commit(request, peer, request_digest, staged_blobs)
        return {"ok": True, "idempotent_replay": replay, "receipt": receipt}, not replay


def peer_credentials(connection: socket.socket) -> PeerCredentials:
    if not hasattr(socket, "SO_PEERCRED"):
        raise BrokerError("unsupported_platform", "SO_PEERCRED is required")
    size = struct.calcsize("3i")
    raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, size)
    pid, uid, gid = struct.unpack("3i", raw)
    return PeerCredentials(pid=pid, uid=uid, gid=gid)


def strict_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise BrokerError("invalid_json", f"duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_json_constant(value: str) -> object:
    raise BrokerError("invalid_json", f"non-finite JSON number is not allowed: {value}")


def validate_json_value(value: object, depth: int = 0) -> None:
    if depth > 32:
        raise BrokerError("invalid_json", "JSON nesting exceeds 32 levels")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        raise BrokerError("invalid_json", "floating-point JSON values are not supported")
    if isinstance(value, list):
        for item in value:
            validate_json_value(item, depth + 1)
        return
    if isinstance(value, dict):
        for item in value.values():
            validate_json_value(item, depth + 1)
        return
    raise BrokerError("invalid_json", f"unsupported JSON value: {type(value).__name__}")


def decode_json(data: bytes) -> object:
    try:
        value = json.loads(
            data,
            object_pairs_hook=strict_json_object,
            parse_constant=reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError("invalid_json", f"request is not valid JSON: {exc}") from exc
    validate_json_value(value)
    return value


def close_fds(file_descriptors: list[int]) -> None:
    for file_descriptor in file_descriptors:
        try:
            os.close(file_descriptor)
        except OSError:
            pass


def receive_frame(
    connection: socket.socket,
    *,
    max_bytes: int,
) -> tuple[object, int | None]:
    descriptor_size = array.array("i").itemsize
    receive_flags = getattr(socket, "MSG_CMSG_CLOEXEC", 0)
    first_chunk, ancillary, flags, _ = connection.recvmsg(
        min(65536, max_bytes + FRAME_HEADER_BYTES),
        socket.CMSG_SPACE(descriptor_size * 2),
        receive_flags,
    )
    received_fds = []
    try:
        if not first_chunk:
            raise BrokerError("invalid_request", "connection closed before a frame was received")
        for level, kind, payload in ancillary:
            if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
                raise BrokerError("invalid_ancillary_data", "unexpected ancillary socket data")
            descriptors = array.array("i")
            descriptors.frombytes(payload[: len(payload) - (len(payload) % descriptor_size)])
            received_fds.extend(descriptors)
        if flags & getattr(socket, "MSG_CTRUNC", 0):
            raise BrokerError("invalid_ancillary_data", "ancillary socket data was truncated")
        if len(received_fds) > 1:
            raise BrokerError("invalid_evidence_fd", "at most one evidence descriptor is allowed")
        framed = bytearray(first_chunk)
        while len(framed) < FRAME_HEADER_BYTES:
            chunk = connection.recv(FRAME_HEADER_BYTES - len(framed))
            if not chunk:
                raise BrokerError("invalid_request", "connection closed during frame header")
            framed.extend(chunk)
        payload_size = struct.unpack("!I", framed[:FRAME_HEADER_BYTES])[0]
        if payload_size == 0:
            raise BrokerError("invalid_request", "JSON frame is empty")
        if payload_size > max_bytes:
            raise BrokerError("frame_too_large", f"frame exceeds {max_bytes} bytes")
        frame_size = FRAME_HEADER_BYTES + payload_size
        if len(framed) > frame_size:
            raise BrokerError("invalid_request", "connection sent bytes after the first frame")
        while len(framed) < frame_size:
            chunk = connection.recv(min(65536, frame_size - len(framed)))
            if not chunk:
                raise BrokerError("invalid_request", "connection closed during JSON frame")
            framed.extend(chunk)
        return (
            decode_json(bytes(framed[FRAME_HEADER_BYTES:])),
            received_fds[0] if received_fds else None,
        )
    except Exception:
        close_fds(received_fds)
        raise


def send_frame(
    connection: socket.socket,
    value: object,
    evidence_fd: int | None = None,
    *,
    max_bytes: int,
) -> None:
    data = canonical_json(value).encode("utf-8")
    if len(data) > max_bytes:
        raise BrokerError("frame_too_large", f"frame exceeds {max_bytes} bytes")
    frame = struct.pack("!I", len(data)) + data
    ancillary = []
    if evidence_fd is not None:
        descriptors = array.array("i", [evidence_fd])
        ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, descriptors))
    sent = connection.sendmsg([frame], ancillary)
    if sent == 0:
        raise BrokerError("short_socket_write", "could not send the protocol frame")
    if sent < len(frame):
        connection.sendall(frame[sent:])


class BrokerServer:
    def __init__(
        self,
        broker: AuthorityBroker,
        socket_path: Path,
        *,
        after_commit: Callable[[dict], None] | None = None,
        ready_fd: int | None = None,
    ) -> None:
        self.broker = broker
        self.socket_path = socket_path
        self.after_commit = after_commit
        self.ready_fd = ready_fd
        self.stop_event = threading.Event()
        self.listener: socket.socket | None = None
        self.socket_identity: tuple[int, int] | None = None

    def stop(self) -> None:
        self.stop_event.set()
        if self.listener:
            try:
                self.listener.close()
            except OSError:
                pass

    def serve_forever(self) -> None:
        if not hasattr(socket, "SO_PEERCRED"):
            raise BrokerError("unsupported_platform", "Linux SO_PEERCRED is required")
        if os.geteuid() == 0:
            raise BrokerError("root_broker_forbidden", "the authority broker must not run as root")
        audit = audit_store(self.broker.store)
        if not audit["ok"]:
            raise BrokerError("store_corrupt", "; ".join(audit["issues"]))
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        if self.socket_path.exists() or self.socket_path.is_symlink():
            existing = self.socket_path.lstat()
            if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != os.getuid():
                raise BrokerError(
                    "socket_path_unsafe",
                    f"refusing to replace socket path: {self.socket_path}",
                )
            self.socket_path.unlink()

        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener = listener
        listener.bind(str(self.socket_path))
        os.chmod(self.socket_path, 0o600)
        listener.listen(32)
        listener.settimeout(0.25)
        bound_stat = self.socket_path.lstat()
        self.socket_identity = (bound_stat.st_dev, bound_stat.st_ino)
        if self.ready_fd is not None:
            os.write(self.ready_fd, b"1")
            os.close(self.ready_fd)
            self.ready_fd = None

        try:
            while not self.stop_event.is_set():
                try:
                    connection, _ = listener.accept()
                except TimeoutError:
                    continue
                except OSError:
                    if self.stop_event.is_set():
                        break
                    raise
                with connection:
                    connection.settimeout(5)
                    committed = False
                    evidence_fd = None
                    try:
                        peer = peer_credentials(connection)
                        raw_request, evidence_fd = receive_frame(
                            connection,
                            max_bytes=MAX_REQUEST_BYTES,
                        )
                        response, committed = self.broker.handle(
                            raw_request,
                            peer,
                            evidence_fd,
                        )
                    except BrokerError as exc:
                        response = exc.response()
                    except Exception:
                        traceback.print_exc(file=sys.stderr)
                        response = BrokerError(
                            "internal_error",
                            "broker failed while processing the request",
                        ).response()
                    finally:
                        if evidence_fd is not None:
                            close_fds([evidence_fd])
                    if committed and self.after_commit:
                        self.after_commit(response["receipt"])
                    try:
                        send_frame(
                            connection,
                            response,
                            max_bytes=MAX_RESPONSE_BYTES,
                        )
                    except BrokerError as exc:
                        try:
                            send_frame(
                                connection,
                                exc.response(),
                                max_bytes=MAX_RESPONSE_BYTES,
                            )
                        except (BrokerError, OSError, TimeoutError):
                            pass
                    except (OSError, TimeoutError):
                        pass
        finally:
            try:
                listener.close()
            finally:
                self._remove_own_socket()

    def _remove_own_socket(self) -> None:
        if self.socket_identity is None:
            return
        try:
            current = self.socket_path.lstat()
        except FileNotFoundError:
            return
        if (current.st_dev, current.st_ino) == self.socket_identity:
            self.socket_path.unlink()


def send_request(
    socket_path: Path,
    request: object,
    timeout: float = 5,
    evidence_fd: int | None = None,
) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(timeout)
        client.connect(str(socket_path))
        send_frame(
            client,
            request,
            evidence_fd,
            max_bytes=MAX_REQUEST_BYTES,
        )
        response, response_fd = receive_frame(
            client,
            max_bytes=MAX_RESPONSE_BYTES,
        )
    if response_fd is not None:
        close_fds([response_fd])
        raise BrokerError("invalid_response", "broker response included an unexpected descriptor")
    if not isinstance(response, dict):
        raise BrokerError("invalid_response", "broker response is not an object")
    return response


def load_stored_json(value: str, label: str, issues: list[str]) -> object | None:
    try:
        parsed = decode_json(value.encode("utf-8"))
    except BrokerError as exc:
        issues.append(f"{label} is invalid: {exc.message}")
        return None
    try:
        if canonical_json(parsed) != value:
            issues.append(f"{label} is not canonical JSON")
    except (TypeError, ValueError) as exc:
        issues.append(f"{label} cannot be canonicalized: {exc}")
        return None
    return parsed


def audit_store(store: AuthorityStore) -> dict:
    issues: list[str] = []
    commits: list[sqlite3.Row] = []
    events: list[sqlite3.Row] = []
    blobs: list[sqlite3.Row] = []
    store.validate()
    conn = store.connect(read_only=True)
    conn.execute("BEGIN")
    try:
        metadata = {
            row["key"]: row["value"]
            for row in conn.execute("SELECT key, value FROM store_meta ORDER BY key")
        }
        expected_metadata = {
            "application": "operator-authority-broker",
            "schema_version": str(STORE_SCHEMA_VERSION),
            "hash_format": "sha256-canonical-json-v1",
            "schema_manifest_sha256": schema_manifest_sha256(conn),
        }
        if metadata != expected_metadata:
            issues.append("store metadata does not match schema version 1")

        foreign_key_issues = conn.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_issues:
            issues.append(f"foreign-key check reported {len(foreign_key_issues)} violation(s)")

        policies = conn.execute(
            "SELECT * FROM policy_snapshots ORDER BY policy_id, generation"
        ).fetchall()
        policy_keys = set()
        for policy in policies:
            label = f"policy {policy['policy_id']} generation {policy['generation']}"
            policy_keys.add((policy["policy_id"], policy["generation"], policy["policy_sha256"]))
            policy_json = load_stored_json(policy["policy_json"], label, issues)
            if sha256_text(policy["policy_json"]) != policy["policy_sha256"]:
                issues.append(f"{label} digest mismatch")
            if not isinstance(policy_json, dict):
                continue
            if (
                policy_json.get("policy_id") != policy["policy_id"]
                or policy_json.get("policy_generation") != policy["generation"]
            ):
                issues.append(f"{label} identity mismatch")
            raw_roles = policy_json.get("roles")
            if not isinstance(raw_roles, dict):
                issues.append(f"{label} roles are malformed")
                continue
            expected_roles = set()
            roles_are_valid = True
            for uid, roles in raw_roles.items():
                if (
                    not isinstance(uid, str)
                    or not uid.isdigit()
                    or not isinstance(roles, list)
                    or any(not isinstance(role, str) for role in roles)
                ):
                    roles_are_valid = False
                    continue
                expected_roles.update((int(uid), role) for role in roles)
            if not roles_are_valid:
                issues.append(f"{label} roles are malformed")
            stored_roles = {
                (row["uid"], row["role"])
                for row in conn.execute(
                    """
                    SELECT uid, role FROM policy_roles
                    WHERE policy_id = ? AND generation = ?
                    """,
                    (policy["policy_id"], policy["generation"]),
                )
            }
            if stored_roles != expected_roles:
                issues.append(f"{label} role rows mismatch")

        policy_event_heads: dict[str, str] = {}
        expected_policy_sequence = 1
        policy_events = conn.execute(
            "SELECT * FROM ledger_policy_events ORDER BY policy_event_sequence"
        ).fetchall()
        for event in policy_events:
            sequence = event["policy_event_sequence"]
            if sequence != expected_policy_sequence:
                issues.append(
                    f"policy event sequence gap: expected {expected_policy_sequence}, got {sequence}"
                )
            expected_policy_sequence += 1
            previous_hash = policy_event_heads.get(event["ledger_id"])
            if event["previous_event_hash"] != previous_hash:
                issues.append(f"policy event {sequence} previous hash mismatch")
            body = load_stored_json(
                event["event_body_json"],
                f"policy event {sequence} body",
                issues,
            )
            expected_body = {
                "ledger_id": event["ledger_id"],
                "event_type": event["event_type"],
                "policy_id": event["policy_id"],
                "generation": event["generation"],
                "policy_sha256": event["policy_sha256"],
                "previous_event_hash": event["previous_event_hash"],
            }
            if body != expected_body:
                issues.append(f"policy event {sequence} body mismatch")
            if sha256_text(event["event_body_json"]) != event["event_hash"]:
                issues.append(f"policy event {sequence} hash mismatch")
            if (
                event["policy_id"],
                event["generation"],
                event["policy_sha256"],
            ) not in policy_keys:
                issues.append(f"policy event {sequence} references an unknown policy snapshot")
            policy_event_heads[event["ledger_id"]] = event["event_hash"]

        previous_commit_hash = None
        expected_sequence = 1
        commit_bodies: dict[int, dict] = {}
        commit_receipts: dict[int, dict] = {}
        commits = conn.execute(
            "SELECT * FROM authority_commits ORDER BY commit_sequence"
        ).fetchall()
        for commit in commits:
            sequence = commit["commit_sequence"]
            label = f"commit {sequence}"
            if sequence != expected_sequence:
                issues.append(f"commit sequence gap: expected {expected_sequence}, got {sequence}")
            expected_sequence += 1
            if commit["previous_commit_hash"] != previous_commit_hash:
                issues.append(f"{label} previous hash mismatch")
            request = load_stored_json(commit["request_json"], f"{label} request", issues)
            if not isinstance(request, dict):
                issues.append(f"{label} request is not an object")
            else:
                if digest_request(request) != commit["request_digest"]:
                    issues.append(f"{label} request digest mismatch")
                if (
                    request.get("ledger_id") != commit["ledger_id"]
                    or request.get("operation_key") != commit["operation_key"]
                    or not isinstance(request.get("operation"), dict)
                    or request["operation"].get("kind") != commit["operation"]
                ):
                    issues.append(f"{label} request binding mismatch")

            body = load_stored_json(commit["commit_body_json"], f"{label} body", issues)
            if sha256_text(commit["commit_body_json"]) != commit["commit_hash"]:
                issues.append(f"{label} hash mismatch")
            if isinstance(body, dict):
                expected_bindings = {
                    "commit_sequence": sequence,
                    "ledger_id": commit["ledger_id"],
                    "operation": commit["operation"],
                    "operation_key": commit["operation_key"],
                    "request_digest": commit["request_digest"],
                    "actor": {
                        "pid": commit["actor_pid"],
                        "uid": commit["actor_uid"],
                        "gid": commit["actor_gid"],
                    },
                    "policy": {
                        "id": commit["policy_id"],
                        "generation": commit["policy_generation"],
                        "sha256": commit["policy_sha256"],
                    },
                    "previous_commit_hash": commit["previous_commit_hash"],
                }
                if any(body.get(key) != value for key, value in expected_bindings.items()):
                    issues.append(f"{label} body binding mismatch")
                commit_bodies[sequence] = body

            receipt = load_stored_json(commit["receipt_json"], f"{label} receipt", issues)
            if isinstance(receipt, dict):
                stored_receipt_hash = receipt.get("receipt_hash")
                receipt_without_hash = {
                    key: value for key, value in receipt.items() if key != "receipt_hash"
                }
                if (
                    stored_receipt_hash != commit["receipt_hash"]
                    or sha256_text(canonical_json(receipt_without_hash)) != commit["receipt_hash"]
                ):
                    issues.append(f"{label} receipt hash mismatch")
                if isinstance(body, dict):
                    expected_receipt = {
                        "protocol_version": PROTOCOL_VERSION,
                        "status": "committed",
                        "projection_status": "pending",
                        **body,
                        "commit_hash": commit["commit_hash"],
                        "receipt_hash": commit["receipt_hash"],
                    }
                    if receipt != expected_receipt:
                        issues.append(f"{label} receipt body mismatch")
                commit_receipts[sequence] = receipt
            previous_commit_hash = commit["commit_hash"]

        event_heads: dict[tuple[str, str, str], tuple[int, str]] = {}
        commits_by_sequence = {row["commit_sequence"]: row for row in commits}
        events_by_commit: dict[int, list[tuple[dict, dict]]] = {}
        events = conn.execute(
            """
            SELECT * FROM authority_events
            ORDER BY commit_sequence, event_id
            """
        ).fetchall()
        for event in events:
            key = (event["ledger_id"], event["record_type"], event["record_id"])
            previous = event_heads.get(key)
            expected_version = previous[0] + 1 if previous else 1
            expected_hash = previous[1] if previous else None
            label = f"event {'/'.join(key)} v{event['version']}"
            if event["version"] != expected_version:
                issues.append(f"{label} version gap")
            if event["previous_event_hash"] != expected_hash:
                issues.append(f"{label} previous hash mismatch")
            payload = load_stored_json(event["payload_json"], f"{label} payload", issues)
            body = load_stored_json(event["event_body_json"], f"{label} body", issues)
            expected_body = {
                "commit_sequence": event["commit_sequence"],
                "ledger_id": event["ledger_id"],
                "record_type": event["record_type"],
                "record_id": event["record_id"],
                "version": event["version"],
                "operation": event["operation"],
                "payload": payload,
                "actor_uid": event["actor_uid"],
                "policy_id": event["policy_id"],
                "policy_generation": event["policy_generation"],
                "previous_event_hash": event["previous_event_hash"],
            }
            if body != expected_body:
                issues.append(f"{label} body mismatch")
            if sha256_text(event["event_body_json"]) != event["event_hash"]:
                issues.append(f"{label} hash mismatch")
            commit = commits_by_sequence.get(event["commit_sequence"])
            if not commit or (
                event["ledger_id"] != commit["ledger_id"]
                or event["operation"] != commit["operation"]
                or event["actor_uid"] != commit["actor_uid"]
                or event["policy_id"] != commit["policy_id"]
                or event["policy_generation"] != commit["policy_generation"]
            ):
                issues.append(f"{label} commit binding mismatch")
            summary = {
                "event_id": event["event_id"],
                "record_type": event["record_type"],
                "record_id": event["record_id"],
                "version": event["version"],
                "event_hash": event["event_hash"],
            }
            events_by_commit.setdefault(event["commit_sequence"], []).append((summary, payload))
            event_heads[key] = (event["version"], event["event_hash"])

        blobs = conn.execute("SELECT * FROM authority_blobs ORDER BY sha256").fetchall()
        blob_by_hash = {blob["sha256"]: blob for blob in blobs}
        content_store = store.content_root / "sha256"
        if content_store.is_symlink() or not content_store.is_dir():
            issues.append("content store root is missing or unsafe")
        for blob in blobs:
            expected_key = f"sha256/{blob['sha256'][:2]}/{blob['sha256']}"
            if blob["storage_key"] != expected_key:
                issues.append(f"blob storage key mismatch: {blob['sha256']}")
            shard_path = content_store / blob["sha256"][:2]
            if shard_path.is_symlink() or not shard_path.is_dir():
                issues.append(f"blob shard missing or unsafe: {blob['sha256']}")
                continue
            shard_stat = shard_path.stat()
            if shard_stat.st_uid != os.geteuid() or stat.S_IMODE(shard_stat.st_mode) & 0o077:
                issues.append(f"blob shard is not private: {blob['sha256']}")
                continue
            blob_path = store.content_root / blob["storage_key"]
            if blob_path.is_symlink() or not blob_path.is_file():
                issues.append(f"blob missing or unsafe: {blob['sha256']}")
                continue
            actual_hash, actual_size = hash_file(blob_path)
            if actual_hash != blob["sha256"] or actual_size != blob["size_bytes"]:
                issues.append(f"blob mismatch: {blob['sha256']}")

        commit_blob_rows = conn.execute(
            "SELECT commit_sequence, sha256 FROM commit_blobs ORDER BY commit_sequence, sha256"
        ).fetchall()
        blobs_by_commit: dict[int, list[dict]] = {}
        first_commit_by_blob: dict[str, int] = {}
        for row in commit_blob_rows:
            first_commit_by_blob.setdefault(row["sha256"], row["commit_sequence"])
            blob = blob_by_hash.get(row["sha256"])
            if blob:
                blobs_by_commit.setdefault(row["commit_sequence"], []).append(
                    {
                        "sha256": blob["sha256"],
                        "size_bytes": blob["size_bytes"],
                        "storage_key": blob["storage_key"],
                    }
                )
        for blob in blobs:
            if first_commit_by_blob.get(blob["sha256"]) != blob["first_commit_sequence"]:
                issues.append(f"blob first commit mismatch: {blob['sha256']}")

        outbox_rows = {
            row["commit_sequence"]: row
            for row in conn.execute("SELECT * FROM projection_outbox ORDER BY commit_sequence")
        }
        for commit in commits:
            sequence = commit["commit_sequence"]
            body = commit_bodies.get(sequence)
            commit_events = sorted(
                events_by_commit.get(sequence, []),
                key=lambda item: RECORD_TYPE_ORDER[item[0]["record_type"]],
            )
            summaries = [item[0] for item in commit_events]
            evidence = blobs_by_commit.get(sequence, [])
            if body and body.get("events") != summaries:
                issues.append(f"commit {sequence} event summary mismatch")
            if body and body.get("evidence") != evidence:
                issues.append(f"commit {sequence} evidence summary mismatch")
            outbox = outbox_rows.get(sequence)
            if not outbox:
                issues.append(f"commit {sequence} has no projection outbox entry")
                continue
            if (
                outbox["ledger_id"] != commit["ledger_id"]
                or outbox["receipt_hash"] != commit["receipt_hash"]
            ):
                issues.append(f"commit {sequence} outbox binding mismatch")
            projection = load_stored_json(
                outbox["projection_json"],
                f"commit {sequence} projection",
                issues,
            )
            expected_projection = {
                "commit_sequence": sequence,
                "ledger_id": commit["ledger_id"],
                "events": [{**summary, "payload": payload} for summary, payload in commit_events],
                "evidence": evidence,
                "receipt": commit_receipts.get(sequence),
            }
            if projection != expected_projection:
                issues.append(f"commit {sequence} projection mismatch")
        if len(outbox_rows) != len(commits):
            issues.append(
                f"projection outbox count {len(outbox_rows)} != commit count {len(commits)}"
            )
    finally:
        conn.rollback()
        conn.close()
    return {
        "ok": not issues,
        "issues": issues,
        "commits": len(commits),
        "events": len(events),
        "blobs": len(blobs),
    }


def read_json_input(path: str) -> object:
    try:
        if path == "-":
            data = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
            if len(data) > MAX_REQUEST_BYTES:
                raise BrokerError("request_too_large", f"request exceeds {MAX_REQUEST_BYTES} bytes")
            return decode_json(data)
        data = Path(path).read_bytes()
        if len(data) > MAX_REQUEST_BYTES:
            raise BrokerError("request_too_large", f"request exceeds {MAX_REQUEST_BYTES} bytes")
        return decode_json(data)
    except OSError as exc:
        raise BrokerError("invalid_json", f"could not read request JSON: {exc}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Standalone Operator P3 authority broker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "bootstrap-fixture",
        help="Initialize a non-production standalone authority fixture",
    )
    init_parser.add_argument("--store", required=True)
    init_parser.add_argument("--content-dir", required=True)
    init_parser.add_argument("--bootstrap-config", required=True)

    serve_parser = subparsers.add_parser("serve", help="Serve broker requests on a Unix socket")
    serve_parser.add_argument("--store", required=True)
    serve_parser.add_argument("--content-dir", required=True)
    serve_parser.add_argument("--socket", required=True)
    serve_parser.add_argument("--ready-fd", type=int, default=None, help=argparse.SUPPRESS)

    request_parser = subparsers.add_parser("request", help="Send one raw broker request")
    request_parser.add_argument("--socket", required=True)
    request_parser.add_argument("--json", required=True, help="Request JSON path or '-' for stdin")
    request_parser.add_argument("--timeout", type=float, default=5)
    request_parser.add_argument(
        "--evidence-file",
        help="Client-side file to pass to the broker as one SCM_RIGHTS descriptor",
    )

    audit_parser = subparsers.add_parser("audit", help="Audit standalone authority history")
    audit_parser.add_argument("--store", required=True)
    audit_parser.add_argument("--content-dir", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "bootstrap-fixture":
            store_path = require_absolute_path(args.store, "store")
            content_root = require_absolute_path(args.content_dir, "content-dir")
            config_path = require_absolute_path(args.bootstrap_config, "bootstrap-config")
            config = read_bootstrap_config(config_path)
            store = AuthorityStore(store_path, content_root)
            store.initialize(config)
            print(
                canonical_json(
                    {
                        "ok": True,
                        "policy_id": config.policy_id,
                        "policy_generation": config.policy_generation,
                        "policy_sha256": config.policy_sha256,
                        "ledgers": list(config.ledgers),
                    }
                )
            )
            return 0

        if args.command == "serve":
            store_path = require_absolute_path(args.store, "store")
            content_root = require_absolute_path(args.content_dir, "content-dir")
            socket_path = require_absolute_path(args.socket, "socket")
            store = AuthorityStore(store_path, content_root)
            server = BrokerServer(
                AuthorityBroker(store),
                socket_path,
                ready_fd=args.ready_fd,
            )

            def stop_server(_signum: int, _frame: object) -> None:
                server.stop()

            signal.signal(signal.SIGTERM, stop_server)
            signal.signal(signal.SIGINT, stop_server)
            server.serve_forever()
            return 0

        if args.command == "request":
            socket_path = require_absolute_path(args.socket, "socket")
            evidence_fd = None
            try:
                if args.evidence_file:
                    flags = os.O_RDONLY
                    if hasattr(os, "O_NOFOLLOW"):
                        flags |= os.O_NOFOLLOW
                    evidence_fd = os.open(args.evidence_file, flags)
                response = send_request(
                    socket_path,
                    read_json_input(args.json),
                    args.timeout,
                    evidence_fd,
                )
            finally:
                if evidence_fd is not None:
                    os.close(evidence_fd)
            print(canonical_json(response))
            return 0 if response.get("ok") else 1

        if args.command == "audit":
            store_path = require_absolute_path(args.store, "store")
            content_root = require_absolute_path(args.content_dir, "content-dir")
            result = audit_store(AuthorityStore(store_path, content_root))
            print(canonical_json(result))
            return 0 if result["ok"] else 1
    except BrokerError as exc:
        print(canonical_json(exc.response()), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
