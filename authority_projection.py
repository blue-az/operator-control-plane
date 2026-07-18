from __future__ import annotations

import datetime
import hashlib
import json
import os
import sqlite3
import stat
import tempfile
from pathlib import Path

import yaml

from authority_client import AuthorityClient, canonical_json

LEDGER_SCHEMA_VERSION = 1
LEDGER_HASH_FORMAT = "operator-ledger-event-v1"


def ensure_journal(op_dir: str) -> sqlite3.Connection:
    os.makedirs(op_dir, exist_ok=True)
    db_path = os.path.join(op_dir, "client_journal.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute("PRAGMA synchronous = FULL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS journal_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS transaction_journal (
            operation_key TEXT PRIMARY KEY,
            canonical_digest TEXT NOT NULL,
            prepared_request TEXT NOT NULL,
            evidence_path TEXT,
            state TEXT NOT NULL CHECK (state IN ('prepared', 'committed', 'projected')),
            receipt_json TEXT,
            commit_sequence INTEGER,
            projection_snapshot_digest TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """
    )
    columns = {row[1] for row in conn.execute("PRAGMA table_info(transaction_journal)").fetchall()}
    if "evidence_path" not in columns:
        conn.execute("ALTER TABLE transaction_journal ADD COLUMN evidence_path TEXT")
    conn.commit()
    return conn


def prepare_transaction(
    conn: sqlite3.Connection,
    operation_key: str,
    request: dict,
    evidence_path: str | None = None,
) -> None:
    wire_request = dict(request)
    wire_request["protocol_version"] = 1
    prepared_request = canonical_json(wire_request)
    semantic_request = {key: value for key, value in wire_request.items() if key != "operation_key"}
    if semantic_request.get("blob") is None:
        semantic_request.pop("blob", None)
    digest = hashlib.sha256(canonical_json(semantic_request).encode("utf-8")).hexdigest()
    existing = conn.execute(
        """
        SELECT canonical_digest, prepared_request, evidence_path
        FROM transaction_journal WHERE operation_key = ?
        """,
        (operation_key,),
    ).fetchone()
    if existing is not None:
        if (
            existing["canonical_digest"] != digest
            or existing["prepared_request"] != prepared_request
            or existing["evidence_path"] != evidence_path
        ):
            raise RuntimeError(f"operation key {operation_key} is already bound to another request")
        return
    conn.execute(
        """
        INSERT INTO transaction_journal (
            operation_key, canonical_digest, prepared_request, evidence_path, state
        ) VALUES (?, ?, ?, ?, 'prepared')
    """,
        (operation_key, digest, prepared_request, evidence_path),
    )
    conn.commit()


def discard_prepared_transaction(conn: sqlite3.Connection, operation_key: str) -> None:
    conn.execute(
        "DELETE FROM transaction_journal WHERE operation_key = ? AND state = 'prepared'",
        (operation_key,),
    )
    conn.commit()


def commit_transaction(conn: sqlite3.Connection, operation_key: str, receipt: dict) -> None:
    prepared = conn.execute(
        "SELECT canonical_digest FROM transaction_journal WHERE operation_key = ?",
        (operation_key,),
    ).fetchone()
    if prepared is None:
        raise RuntimeError(f"operation key {operation_key} was not prepared")
    if receipt.get("operation_key") != operation_key:
        raise RuntimeError("broker receipt operation key does not match the prepared operation")
    if receipt.get("request_digest") != prepared["canonical_digest"]:
        raise RuntimeError("broker receipt request digest does not match the prepared request")
    receipt_without_hash = dict(receipt)
    receipt_hash = receipt_without_hash.pop("receipt_hash", None)
    expected_receipt_hash = hashlib.sha256(
        canonical_json(receipt_without_hash).encode("utf-8")
    ).hexdigest()
    if receipt_hash != expected_receipt_hash:
        raise RuntimeError("broker receipt hash is invalid")
    conn.execute(
        """
        UPDATE transaction_journal SET
            state = 'committed',
            receipt_json = ?,
            commit_sequence = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE operation_key = ?
    """,
        (canonical_json(receipt), receipt["commit_sequence"], operation_key),
    )
    conn.commit()


def project_transaction(conn: sqlite3.Connection, operation_key: str, snapshot_digest: str) -> None:
    conn.execute(
        """
        UPDATE transaction_journal SET
            state = 'projected',
            projection_snapshot_digest = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE operation_key = ?
    """,
        (snapshot_digest, operation_key),
    )
    conn.commit()


def get_last_applied_sequence(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT value FROM journal_metadata WHERE key = 'last_applied_sequence'"
    ).fetchone()
    return int(row["value"]) if row else 0


def set_last_applied_sequence(conn: sqlite3.Connection, seq: int) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO journal_metadata (key, value) VALUES ('last_applied_sequence', ?)",
        (str(seq),),
    )
    conn.commit()


def get_metadata(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM journal_metadata WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None or row["value"] is None:
        return None
    return str(row["value"])


def set_metadata(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO journal_metadata (key, value) VALUES (?, ?)",
        (key, value),
    )


STORE_INCARNATION_KEY = "store_incarnation_id"


def save_yaml(data: any, filepath: str) -> None:
    parent = os.path.dirname(filepath)
    os.makedirs(parent, exist_ok=True)
    rendered = yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
    existing_stat = os.stat(filepath) if os.path.exists(filepath) else None
    if existing_stat:
        target_mode = stat.S_IMODE(existing_stat.st_mode)
    else:
        current_umask = os.umask(0)
        os.umask(current_umask)
        target_mode = 0o666 & ~current_umask
    fd, temporary = tempfile.mkstemp(prefix=f".{os.path.basename(filepath)}.", dir=parent)
    try:
        if existing_stat:
            try:
                os.fchown(fd, -1, existing_stat.st_gid)
            except PermissionError:
                pass
            try:
                os.fchown(fd, existing_stat.st_uid, -1)
            except PermissionError:
                pass
        os.fchmod(fd, target_mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(rendered)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, filepath)
        directory_fd = os.open(parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def get_local_record_version(
    conn_ledger: sqlite3.Connection, record_type: str, record_id: str
) -> tuple[int, str | None]:
    table = conn_ledger.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'authority_projection_events'"
    ).fetchone()
    if table is None:
        return 0, None
    row = conn_ledger.execute(
        """
        SELECT broker_version, broker_event_hash FROM authority_projection_events
        WHERE record_type = ? AND record_id = ?
        ORDER BY broker_version DESC LIMIT 1
        """,
        (record_type, record_id),
    ).fetchone()
    if row:
        return row[0], row[1]
    return 0, None


def get_projection_local_hash(
    conn_ledger: sqlite3.Connection, record_type: str, record_id: str
) -> str | None:
    row = conn_ledger.execute(
        """
        SELECT local_event_hash FROM authority_projection_events
        WHERE record_type = ? AND record_id = ?
        ORDER BY broker_version DESC LIMIT 1
        """,
        (record_type, record_id),
    ).fetchone()
    return row[0] if row else None


def get_local_event_head(
    conn_ledger: sqlite3.Connection, record_type: str, record_id: str
) -> tuple[int, str | None]:
    row = conn_ledger.execute(
        """
        SELECT version, event_hash FROM ledger_events
        WHERE record_type = ? AND record_id = ?
        ORDER BY version DESC LIMIT 1
        """,
        (record_type, record_id),
    ).fetchone()
    return (row[0], row[1]) if row else (0, None)


def event_hash_for_fields(
    record_type: str,
    record_id: str,
    version: int,
    event_type: str,
    payload_json: str,
    actor_uid: int,
    actor_name: str,
    created_at: str,
    source_command: str,
    previous_event_hash: str | None,
) -> str:
    fields = {
        "hash_format": LEDGER_HASH_FORMAT,
        "record_type": record_type,
        "record_id": record_id,
        "version": version,
        "event_type": event_type,
        "payload_json": payload_json,
        "actor_uid": actor_uid,
        "actor_name": actor_name,
        "created_at": created_at,
        "source_command": source_command,
        "previous_event_hash": previous_event_hash,
    }
    return hashlib.sha256(canonical_json(fields).encode("utf-8")).hexdigest()


def evidence_locator(
    op_dir: str,
    evidence_id: str,
    payload: dict | None = None,
    read_only: bool = False,
) -> str:
    if payload and payload.get("path_or_url"):
        return payload["path_or_url"]
    if read_only:
        evidence_root = Path(op_dir) / "evidence"
        for candidate in evidence_root.glob(f"*/{evidence_id}.yaml"):
            try:
                with candidate.open(encoding="utf-8") as handle:
                    local_evidence = yaml.safe_load(handle) or {}
                if local_evidence.get("path_or_url"):
                    return local_evidence["path_or_url"]
            except (OSError, yaml.YAMLError):
                continue
        return f"broker_evidence://{evidence_id}"
    conn = ensure_journal(op_dir)
    try:
        row = conn.execute(
            "SELECT evidence_path FROM transaction_journal WHERE operation_key = ?",
            (f"op-evidence-attach-{evidence_id}",),
        ).fetchone()
    finally:
        conn.close()
    if row:
        if row[0]:
            return row[0]
    if payload:
        return f"broker_content://{payload['sha256']}"
    return f"broker_evidence://{evidence_id}"


def normalize_record(op_dir: str, record: dict, read_only: bool = False) -> tuple[dict, str, str]:
    record_type = record["record_type"]
    record_id = record["record_id"]
    payload = record["payload"]
    binding = {
        "broker_event_hash": record["event_hash"],
        "policy": record["authority"]["policy"],
    }
    if record_type == "task":
        filepath = os.path.join(op_dir, "tasks", f"{record_id}.yaml")
        existing = {}
        if os.path.isfile(filepath):
            with open(filepath, encoding="utf-8") as handle:
                existing = yaml.safe_load(handle) or {}
        normalized = dict(existing)
        normalized.update(
            {
                "task_id": record_id,
                "status": payload["status"],
                "claims": payload.get("claim_ids", []),
                "evidence": [
                    evidence_locator(op_dir, evidence_id, read_only=read_only)
                    for evidence_id in payload.get("evidence_ids", [])
                ],
                "verified_claim_ids": payload.get("verified_claim_ids", []),
                "policy_authority": "external_broker",
                "authority_binding": binding,
            }
        )
        source_command = "task-transition"
    elif record_type == "claim":
        filepath = os.path.join(op_dir, "claims", f"{record_id}.yaml")
        status = payload["verification_status"]
        normalized = {
            "claim_id": record_id,
            "task_id": payload["task_id"],
            "type": payload["claim_type"],
            "text": payload["text"],
            "verification_status": status == "verified",
            "verification_outcome": None if status == "unverified" else status,
            "verified_by": payload.get("verified_by_uid"),
            "evidence_refs": [
                f"evidence/{payload['task_id']}/{evidence_id}.yaml"
                for evidence_id in payload.get("evidence_ids", [])
            ],
            "required_gate": payload.get("required_gate"),
            "verification_authority": payload.get("verification_authority"),
            "policy_authority": "external_broker",
            "authority_binding": binding,
        }
        source_command = "claim-add"
    elif record_type == "evidence":
        filepath = os.path.join(op_dir, "evidence", payload["task_id"], f"{record_id}.yaml")
        normalized = {
            "evidence_id": record_id,
            "task_id": payload["task_id"],
            "claim_id": payload["claim_id"],
            "path_or_url": evidence_locator(op_dir, record_id, payload, read_only=read_only),
            "evidence_type": payload["evidence_type"],
            "hash": payload["sha256"],
            "fingerprint": {
                "algorithm": "sha256",
                "value": payload["sha256"],
                "size_bytes": payload["size_bytes"],
                "mtime_ns": None,
            },
            "verification_status": payload["verification_status"],
            "verification_authority": payload.get("verification_authority"),
            "policy_authority": "external_broker",
            "authority_binding": binding,
        }
        source_command = "evidence-attach"
    elif record_type == "handoff":
        filepath = os.path.join(op_dir, "handoffs", payload["task_id"], f"{record_id}.yaml")
        normalized = {**payload, "authority_binding": binding}
        source_command = "authority-reconcile"
    else:
        filepath = os.path.join(op_dir, f"{record_type}s", f"{record_id}.yaml")
        normalized = {**payload, "authority_binding": binding}
        source_command = "authority-reconcile"
    return normalized, filepath, source_command


def project_record(
    op_dir: str,
    conn_ledger: sqlite3.Connection,
    record: dict,
    commit_sequence: int,
    write_event: bool = True,
) -> None:
    record_type = record["record_type"]
    record_id = record["record_id"]
    local_record_id = record_id
    if record_type in {"evidence", "handoff"}:
        local_record_id = f"{record['payload']['task_id']}/{record_id}"
    broker_version = record["version"]
    broker_event_hash = record["event_hash"]
    actor_uid = record["authority"]["actor_uid"]
    actor_name = f"uid:{actor_uid}"
    normalized, filepath, source_command = normalize_record(op_dir, record)
    local_version, previous_hash = get_local_event_head(conn_ledger, record_type, local_record_id)
    local_version += 1
    event_type = "record_created" if local_version == 1 else "record_updated"
    payload_json = canonical_json(normalized)
    created_at = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    local_event_hash = event_hash_for_fields(
        record_type,
        local_record_id,
        local_version,
        event_type,
        payload_json,
        actor_uid,
        actor_name,
        created_at,
        source_command,
        previous_hash,
    )

    if write_event:
        conn_ledger.execute(
            """
            INSERT INTO ledger_events (
                event_id, record_type, record_id, version, event_type, payload_json,
                actor_uid, actor_name, created_at, source_command, previous_event_hash,
                event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                local_event_hash,
                record_type,
                local_record_id,
                local_version,
                event_type,
                payload_json,
                actor_uid,
                actor_name,
                created_at,
                source_command,
                previous_hash,
                local_event_hash,
            ),
        )
        conn_ledger.execute(
            """
            INSERT INTO authority_projection_events (
                record_type, record_id, broker_version, broker_event_hash,
                commit_sequence, policy_json, local_event_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_type,
                record_id,
                broker_version,
                broker_event_hash,
                commit_sequence,
                canonical_json(record["authority"]["policy"]),
                local_event_hash,
            ),
        )
    save_yaml(normalized, filepath)


def ensure_ledger_schema(conn_ledger: sqlite3.Connection) -> None:
    conn_ledger.executescript(
        """
        CREATE TABLE IF NOT EXISTS ledger_events (
            event_id TEXT PRIMARY KEY,
            record_type TEXT NOT NULL,
            record_id TEXT NOT NULL,
            version INTEGER NOT NULL CHECK (version > 0),
            event_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            actor_uid INTEGER,
            actor_name TEXT,
            created_at TEXT NOT NULL,
            source_command TEXT,
            previous_event_hash TEXT,
            event_hash TEXT NOT NULL,
            UNIQUE(record_type, record_id, version)
        );
        CREATE INDEX IF NOT EXISTS idx_ledger_events_record
            ON ledger_events(record_type, record_id, version);
        CREATE TRIGGER IF NOT EXISTS ledger_events_no_update
        BEFORE UPDATE ON ledger_events
        BEGIN
            SELECT RAISE(ABORT, 'ledger_events is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS ledger_events_no_delete
        BEFORE DELETE ON ledger_events
        BEGIN
            SELECT RAISE(ABORT, 'ledger_events is append-only');
        END;
        CREATE TABLE IF NOT EXISTS authority_projection_events (
            record_type TEXT NOT NULL,
            record_id TEXT NOT NULL,
            broker_version INTEGER NOT NULL CHECK (broker_version > 0),
            broker_event_hash TEXT NOT NULL,
            commit_sequence INTEGER NOT NULL CHECK (commit_sequence > 0),
            policy_json TEXT NOT NULL,
            local_event_hash TEXT NOT NULL,
            PRIMARY KEY(record_type, record_id, broker_version),
            UNIQUE(local_event_hash)
        );
        CREATE TRIGGER IF NOT EXISTS authority_projection_events_no_update
        BEFORE UPDATE ON authority_projection_events
        BEGIN
            SELECT RAISE(ABORT, 'authority_projection_events is append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS authority_projection_events_no_delete
        BEFORE DELETE ON authority_projection_events
        BEGIN
            SELECT RAISE(ABORT, 'authority_projection_events is append-only');
        END;
    """
    )
    conn_ledger.execute(f"PRAGMA user_version = {LEDGER_SCHEMA_VERSION}")


def project_sequence(
    op_dir: str,
    ledger_id: str,
    seq: int,
    client: AuthorityClient,
    conn_journal: sqlite3.Connection,
) -> str | None:
    # 1. Fetch snapshot from broker through seq using pagination
    records = []
    after = None
    snapshot_digest = None
    while True:
        req = {
            "action": "projection.snapshot",
            "ledger_id": ledger_id,
            "through_commit_sequence": seq,
            "after": after,
            "limit": 16,
        }
        res = client.send_request(req)
        if not res.get("ok"):
            raise RuntimeError(f"Failed to fetch snapshot at seq {seq}: {res.get('error')}")
        snapshot = res["snapshot"]
        snapshot_digest = snapshot["snapshot_digest"]
        records.extend(snapshot["records"])
        if not snapshot.get("has_more") or not snapshot.get("next_after"):
            break
        after = snapshot["next_after"]

    # 3. Connect to local ledger SQLite
    ledger_db = os.path.join(op_dir, "ledger.sqlite3")
    conn_ledger = sqlite3.connect(ledger_db)
    conn_ledger.execute("PRAGMA journal_mode = WAL")
    conn_ledger.execute("PRAGMA synchronous = FULL")
    ensure_ledger_schema(conn_ledger)

    conn_ledger.execute("BEGIN IMMEDIATE")
    try:
        # Append missing authority heads. Existing divergent history is never rewritten.
        for record in records:
            record_type = record["record_type"]
            record_id = record["record_id"]
            version = record["version"]

            local_ver, local_hash = get_local_record_version(conn_ledger, record_type, record_id)
            projected_local_hash = get_projection_local_hash(conn_ledger, record_type, record_id)
            if projected_local_hash is not None:
                local_record_id = record_id
                if record_type in {"evidence", "handoff"}:
                    local_record_id = f"{record['payload']['task_id']}/{record_id}"
                _, current_local_hash = get_local_event_head(
                    conn_ledger, record_type, local_record_id
                )
                if current_local_hash != projected_local_hash:
                    raise RuntimeError(
                        f"local P0 history for {record_type} {record_id} changed after projection"
                    )

            if local_ver > version:
                raise RuntimeError(
                    f"local {record_type} {record_id} version {local_ver} exceeds "
                    f"broker version {version}"
                )
            if local_ver == version and local_hash != record["event_hash"]:
                raise RuntimeError(
                    f"local {record_type} {record_id} version {version} diverges from broker"
                )
            if version > local_ver:
                if version != local_ver + 1:
                    raise RuntimeError(
                        f"local {record_type} {record_id} has a version gap before {version}"
                    )
                project_record(op_dir, conn_ledger, record, seq)
            else:
                project_record(op_dir, conn_ledger, record, seq, write_event=False)
        conn_ledger.commit()
    except Exception:
        conn_ledger.rollback()
        raise
    finally:
        conn_ledger.close()

    # 4. Update journal's last_applied_sequence and set state to projected
    set_last_applied_sequence(conn_journal, seq)
    conn_journal.execute(
        """
        UPDATE transaction_journal SET
            state = 'projected',
            projection_snapshot_digest = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE commit_sequence = ?
        """,
        (snapshot_digest, seq),
    )
    conn_journal.commit()

    return snapshot_digest


def validate_projection_heads(op_dir: str) -> None:
    ledger_db = os.path.join(op_dir, "ledger.sqlite3")
    if not os.path.exists(ledger_db):
        return
    conn = sqlite3.connect(ledger_db)
    try:
        table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'authority_projection_events'"
        ).fetchone()
        if table is None:
            return
        rows = conn.execute(
            """
            SELECT projection.record_type, projection.record_id, projection.local_event_hash
            FROM authority_projection_events AS projection
            WHERE NOT EXISTS (
                SELECT 1 FROM authority_projection_events AS newer
                WHERE newer.record_type = projection.record_type
                  AND newer.record_id = projection.record_id
                  AND newer.broker_version > projection.broker_version
            )
            """
        ).fetchall()
        for record_type, record_id, projected_hash in rows:
            projected_event = conn.execute(
                "SELECT record_id FROM ledger_events WHERE event_hash = ?",
                (projected_hash,),
            ).fetchone()
            local_hash = None
            if projected_event:
                _, local_hash = get_local_event_head(conn, record_type, projected_event[0])
            if local_hash != projected_hash:
                raise RuntimeError(
                    f"local P0 history for {record_type} {record_id} changed after projection"
                )
    finally:
        conn.close()


def reconcile_projections(
    op_dir: str,
    ledger_id: str,
    client: AuthorityClient,
    *,
    acknowledge_store_reset: bool = False,
) -> tuple[str, int]:
    conn_journal = ensure_journal(op_dir)

    # 1. Recover any locally prepared transactions that may have been committed by broker
    # (Checking the broker for idempotent replays or matching sequences)
    # We retrieve the latest sequence from broker first.
    req = {
        "action": "projection.snapshot",
        "ledger_id": ledger_id,
        "through_commit_sequence": None,
        "after": None,
        "limit": 1,
    }
    res = client.send_request(req)
    if not res.get("ok"):
        raise RuntimeError(f"Broker connection failed during reconcile: {res.get('error')}")

    broker_seq = res["snapshot"]["through_commit_sequence"]
    broker_policy = res["snapshot"]["policy"]
    broker_incarnation = res["snapshot"].get("store_incarnation_id")
    if not broker_incarnation:
        conn_journal.close()
        raise RuntimeError(
            "broker projection.snapshot is missing store_incarnation_id "
            "(upgrade the authority broker)"
        )

    local_incarnation = get_metadata(conn_journal, STORE_INCARNATION_KEY)
    if local_incarnation is not None and local_incarnation != broker_incarnation:
        if not acknowledge_store_reset:
            conn_journal.close()
            raise RuntimeError(
                "store incarnation discontinuity: "
                f"local journal remembers {local_incarnation}, "
                f"broker reports {broker_incarnation}. "
                "The authority store appears to have been rebuilt or replaced. "
                "Reconciliation refuses to silently no-op or project across stores. "
                "If this rebuild was intentional, re-run: "
                "operator authority-reconcile --acknowledge-store-reset"
            )
        # Explicit operator acknowledgment: drop sequence progress and adopt the
        # new incarnation before any projection work. Prior projected YAML is
        # treated as untrusted until re-derived from the new store's history.
        set_last_applied_sequence(conn_journal, 0)
        set_metadata(conn_journal, STORE_INCARNATION_KEY, broker_incarnation)
        conn_journal.commit()
        # Discard prepared ops bound to the dead store; they cannot be safely
        # replayed against a new incarnation.
        conn_journal.execute("DELETE FROM transaction_journal WHERE state = 'prepared'")
        conn_journal.commit()
    elif local_incarnation is None and acknowledge_store_reset:
        # No prior binding: treat as adopt-and-continue (first-time upgrade path).
        set_metadata(conn_journal, STORE_INCARNATION_KEY, broker_incarnation)
        conn_journal.commit()

    # 2. Check if we have prepared transactions that have since been committed on the broker
    prepared_rows = conn_journal.execute(
        "SELECT * FROM transaction_journal WHERE state = 'prepared'"
    ).fetchall()
    replay_errors = {}
    for row in prepared_rows:
        op_key = row["operation_key"]
        # Query broker for this operation_key by executing an idempotent commit replay
        # (or looking it up if broker supported it, but replay with the same operation_key is idempotent)
        req_send = json.loads(row["prepared_request"])
        evidence_path = row["evidence_path"]

        try:
            res_check = client.send_request(req_send, evidence_path=evidence_path)
        except Exception as exc:
            # Broker unreachable or the attempt itself failed: we still don't
            # know whether an earlier attempt committed this operation, so
            # leave it 'prepared' for the next reconcile to retry.
            replay_errors[op_key] = str(exc)
            continue

        if res_check.get("ok") and "receipt" in res_check:
            commit_transaction(conn_journal, op_key, res_check["receipt"])
            if res_check["receipt"]["commit_sequence"] > broker_seq:
                broker_seq = res_check["receipt"]["commit_sequence"]
        else:
            # The broker gave a definitive answer: this operation was never
            # committed under this key (rejected, or the key was never seen).
            # Mirror the ok=False handling at the original prepare call sites
            # and discard it instead of wedging the repo forever.
            discard_prepared_transaction(conn_journal, op_key)
            replay_errors[op_key] = res_check.get("error")

    remaining_prepared = conn_journal.execute(
        "SELECT operation_key FROM transaction_journal WHERE state = 'prepared' ORDER BY operation_key"
    ).fetchall()
    if remaining_prepared:
        keys = ", ".join(
            f"{row['operation_key']} ({replay_errors.get(row['operation_key'], 'unresolved')})"
            for row in remaining_prepared
        )
        conn_journal.close()
        raise RuntimeError(f"prepared broker operations remain unresolved: {keys}")

    # 3. Sequential reconciliation
    validate_projection_heads(op_dir)
    last_applied = get_last_applied_sequence(conn_journal)

    if broker_seq < last_applied:
        raise RuntimeError(f"local sequence {last_applied} exceeds broker sequence {broker_seq}")

    if last_applied > 0:
        broker_records = []
        after_ptr = None
        while True:
            chk_req = {
                "action": "projection.snapshot",
                "ledger_id": ledger_id,
                "through_commit_sequence": last_applied,
                "after": after_ptr,
                "limit": 16,
            }
            chk_res = client.send_request(chk_req)
            if not chk_res.get("ok"):
                raise RuntimeError(
                    f"Broker consistency check failed at sequence {last_applied}: {chk_res.get('error')}"
                )
            snap = chk_res["snapshot"]
            broker_records.extend(snap["records"])
            if not snap.get("has_more") or not snap.get("next_after"):
                break
            after_ptr = snap["next_after"]

        ledger_db = os.path.join(op_dir, "ledger.sqlite3")
        if not os.path.exists(ledger_db):
            raise RuntimeError("local ledger database is missing")
        conn_chk = sqlite3.connect(ledger_db)
        try:
            for record in broker_records:
                rtype = record["record_type"]
                rid = record["record_id"]
                rver = record["version"]
                rhash = record["event_hash"]

                local_ver, local_hash = get_local_record_version(conn_chk, rtype, rid)
                if local_ver != rver or local_hash != rhash:
                    raise RuntimeError(
                        f"local {rtype} {rid} version {local_ver} (hash {local_hash}) "
                        f"diverges from broker version {rver} (hash {rhash}) at sequence {last_applied}"
                    )
        finally:
            conn_chk.close()

    last_digest = None
    for seq in range(last_applied + 1, broker_seq + 1):
        last_digest = project_sequence(op_dir, ledger_id, seq, client, conn_journal)

    # 4. Mark any matching committed transactions as projected
    conn_journal.execute(
        """
        UPDATE transaction_journal SET
            state = 'projected',
            updated_at = CURRENT_TIMESTAMP
        WHERE state = 'committed' AND commit_sequence <= ?
        """,
        (broker_seq,),
    )
    set_metadata(conn_journal, "policy_binding", canonical_json(broker_policy))
    set_metadata(conn_journal, STORE_INCARNATION_KEY, broker_incarnation)
    conn_journal.commit()

    conn_journal.close()
    return last_digest or "", broker_seq


def get_expected_item(op_dir: str, record_type: str, record_id: str) -> dict:
    db_path = os.path.join(op_dir, "ledger.sqlite3")
    if not os.path.exists(db_path):
        return {
            "record_type": record_type,
            "record_id": record_id,
            "version": 0,
            "event_hash": None,
        }
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            """
            SELECT broker_version, broker_event_hash FROM authority_projection_events
            WHERE record_type = ? AND record_id = ?
            ORDER BY broker_version DESC LIMIT 1
            """,
            (record_type, record_id),
        ).fetchone()
        conn.close()
        if row:
            return {
                "record_type": record_type,
                "record_id": record_id,
                "version": row[0],
                "event_hash": row[1],
            }
    except Exception:
        pass
    return {"record_type": record_type, "record_id": record_id, "version": 0, "event_hash": None}


def compile_expected(
    op_dir: str,
    kind: str,
    task_id: str,
    claim_id: str | None = None,
    evidence_id: str | None = None,
) -> list[dict]:
    from authority_client import resolve_enrollment

    enrollment = resolve_enrollment()
    if not enrollment:
        raise RuntimeError("Not enrolled")
    ledger_id = enrollment.ledger_id
    socket_path = enrollment.socket_path
    client = AuthorityClient(socket_path)

    # Only these 1-3 keys are ever consulted below; stop paginating the
    # broker snapshot as soon as all of them have been seen instead of
    # always walking the entire ledger.
    wanted_keys = set()
    wanted_keys.add(("task", task_id))
    if kind in ("evidence.attach_draft", "evidence.attach_status") and claim_id:
        wanted_keys.add(("claim", claim_id))

    # Fetch records from broker using pagination, using live broker state
    # (not the local projection cache) so the "expected" preconditions sent
    # with the operation reflect the broker's current authoritative head.
    broker_records = {}
    after = None
    pinned_seq = None
    while True:
        req = {
            "action": "projection.snapshot",
            "ledger_id": ledger_id,
            "through_commit_sequence": pinned_seq,
            "after": after,
            "limit": 16,
        }
        try:
            res = client.send_request(req)
        except Exception as exc:
            raise RuntimeError(
                f"cannot determine expected state: broker unreachable: {exc}"
            ) from exc
        if not res.get("ok"):
            raise RuntimeError(f"cannot determine expected state: {res.get('error')}")
        snapshot = res["snapshot"]
        if pinned_seq is None:
            pinned_seq = snapshot["through_commit_sequence"]
        for rec in snapshot["records"]:
            broker_records[(rec["record_type"], rec["record_id"])] = rec
        if wanted_keys.issubset(broker_records.keys()):
            break
        if not snapshot.get("has_more") or not snapshot.get("next_after"):
            break
        after = snapshot["next_after"]

    def get_expected_from_broker(record_type: str, record_id: str) -> dict:
        rec = broker_records.get((record_type, record_id))
        if rec:
            return {
                "record_type": record_type,
                "record_id": record_id,
                "version": rec["version"],
                "event_hash": rec["event_hash"],
            }
        return {
            "record_type": record_type,
            "record_id": record_id,
            "version": 0,
            "event_hash": None,
        }

    expected = []
    # Always include task if required
    if kind in (
        "claim.create",
        "evidence.attach_draft",
        "evidence.attach_status",
        "task.transition",
    ):
        expected.append(get_expected_from_broker("task", task_id))
    # Include claim if required
    if kind in ("claim.create", "evidence.attach_draft", "evidence.attach_status"):
        if claim_id:
            expected.append(get_expected_from_broker("claim", claim_id))
    # Include evidence if required
    if kind in ("evidence.attach_draft", "evidence.attach_status"):
        if evidence_id:
            expected.append(get_expected_from_broker("evidence", evidence_id))
    return expected
