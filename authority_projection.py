from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from pathlib import Path
import yaml

from authority_client import AuthorityClient, canonical_json

LEDGER_SCHEMA_VERSION = 1


def ensure_journal(op_dir: str) -> sqlite3.Connection:
    os.makedirs(op_dir, exist_ok=True)
    db_path = os.path.join(op_dir, "client_journal.sqlite3")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = FULL")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS journal_metadata (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS transaction_journal (
            operation_key TEXT PRIMARY KEY,
            canonical_digest TEXT NOT NULL,
            prepared_request TEXT NOT NULL,
            state TEXT NOT NULL CHECK (state IN ('prepared', 'committed', 'projected')),
            receipt_json TEXT,
            commit_sequence INTEGER,
            projection_snapshot_digest TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
    """)
    conn.commit()
    return conn


def prepare_transaction(conn: sqlite3.Connection, operation_key: str, request: dict) -> None:
    digest = hashlib.sha256(canonical_json(request).encode("utf-8")).hexdigest()
    conn.execute("""
        INSERT OR REPLACE INTO transaction_journal (
            operation_key, canonical_digest, prepared_request, state
        ) VALUES (?, ?, ?, 'prepared')
    """, (operation_key, digest, canonical_json(request)))
    conn.commit()


def commit_transaction(conn: sqlite3.Connection, operation_key: str, receipt: dict) -> None:
    conn.execute("""
        UPDATE transaction_journal SET
            state = 'committed',
            receipt_json = ?,
            commit_sequence = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE operation_key = ?
    """, (canonical_json(receipt), receipt["commit_sequence"], operation_key))
    conn.commit()


def project_transaction(conn: sqlite3.Connection, operation_key: str, snapshot_digest: str) -> None:
    conn.execute("""
        UPDATE transaction_journal SET
            state = 'projected',
            projection_snapshot_digest = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE operation_key = ?
    """, (snapshot_digest, operation_key))
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


def save_yaml(data: any, filepath: str) -> None:
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    rendered = yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
    with open(filepath, "w") as f:
        f.write(rendered)


def get_local_record_version(conn_ledger: sqlite3.Connection, record_type: str, record_id: str) -> tuple[int, str | None]:
    row = conn_ledger.execute(
        """
        SELECT version, event_hash FROM ledger_events
        WHERE record_type = ? AND record_id = ?
        ORDER BY version DESC LIMIT 1
        """,
        (record_type, record_id),
    ).fetchone()
    if row:
        return row[0], row[1]
    return 0, None


def load_identity_map(op_dir: str) -> dict[int, str]:
    identity_path = os.path.join(op_dir, "identity.yaml")
    if not os.path.exists(identity_path):
        return {}
    try:
        with open(identity_path, "r") as f:
            data = yaml.safe_load(f) or {}
            uids = data.get("uids", {})
            return {int(k): v.get("name", "unknown") for k, v in uids.items()}
    except Exception:
        return {}


def project_record(
    op_dir: str,
    conn_ledger: sqlite3.Connection,
    record: dict,
    identity_map: dict[int, str],
) -> None:
    record_type = record["record_type"]
    record_id = record["record_id"]
    version = record["version"]
    payload = record["payload"]
    event_hash = record["event_hash"]
    actor_uid = record["authority"]["actor_uid"]
    actor_name = identity_map.get(actor_uid, "unknown")

    # 1. Determine event type and source command
    if record_type == "task":
        event_type = "create" if version == 1 else "transition"
        source_cmd = "task-create" if version == 1 else "task-transition"
        filepath = os.path.join(op_dir, "tasks", f"{record_id}.yaml")
    elif record_type == "claim":
        event_type = "create"
        source_cmd = "claim-add"
        filepath = os.path.join(op_dir, "claims", f"{record_id}.yaml")
    elif record_type == "evidence":
        event_type = "attach_draft" if "verification_outcome" not in payload else "attach_status"
        source_cmd = "evidence-attach"
        task_id = payload["task_id"]
        filepath = os.path.join(op_dir, "evidence", task_id, f"{record_id}.yaml")
    elif record_type == "handoff":
        event_type = "create"
        source_cmd = "handoff-add"
        task_id = payload["task_id"]
        filepath = os.path.join(op_dir, "handoffs", task_id, f"{record_id}.yaml")
    else:
        event_type = "commit"
        source_cmd = None
        filepath = os.path.join(op_dir, f"{record_type}s", f"{record_id}.yaml")

    # 2. Get previous event hash from local ledger db
    _, prev_hash = get_local_record_version(conn_ledger, record_type, record_id)

    # 3. Write event to database
    payload_json = canonical_json(payload)
    event_id = f"evt-{event_hash[:32]}"
    
    conn_ledger.execute(
        """
        INSERT OR REPLACE INTO ledger_events (
            event_id, record_type, record_id, version, event_type, payload_json,
            actor_uid, actor_name, created_at, source_command, previous_event_hash,
            event_hash
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
        """,
        (
            event_id,
            record_type,
            record_id,
            version,
            event_type,
            payload_json,
            actor_uid,
            actor_name,
            source_cmd,
            prev_hash,
            event_hash,
        ),
    )

    # 4. Write YAML file
    yaml_payload = payload
    if record_type == "evidence":
        path_or_url = payload.get("path_or_url")
        if not path_or_url:
            # Query local transaction_journal for original path_or_url
            conn_journal = ensure_journal(op_dir)
            row = conn_journal.execute(
                "SELECT prepared_request FROM transaction_journal WHERE operation_key = ?",
                (f"op-evidence-attach-{record_id}",)
            ).fetchone()
            conn_journal.close()
            if row:
                try:
                    req_obj = json.loads(row[0])
                    path_or_url = req_obj.get("path_or_url")
                except Exception:
                    pass
        if not path_or_url:
            path_or_url = f"broker_content://{payload['sha256']}"

        yaml_payload = {
            "evidence_id": payload["evidence_id"],
            "task_id": payload["task_id"],
            "claim_id": payload["claim_id"],
            "type": payload["evidence_type"],
            "path_or_url": path_or_url,
            "hash": payload["sha256"],
            "size": payload["size_bytes"],
            "verification_status": payload["verification_status"],
            "policy_authority": payload.get("policy_authority", "external_broker"),
            "verification_authority": payload.get("verification_authority"),
        }
    elif record_type == "claim":
        yaml_payload = {
            "claim_id": payload["claim_id"],
            "task_id": payload["task_id"],
            "type": payload["claim_type"],
            "text": payload["text"],
            "required_gate": payload.get("required_gate"),
            "evidence_ids": payload.get("evidence_ids", []),
            "verification_status": payload["verification_status"],
            "policy_authority": payload.get("policy_authority", "external_broker"),
            "verification_authority": payload.get("verification_authority"),
        }
    elif record_type == "task":
        yaml_payload = {
            "task_id": payload["task_id"],
            "objective": payload.get("objective", ""),
            "status": payload["status"],
            "claim_ids": payload.get("claim_ids", []),
            "evidence_ids": payload.get("evidence_ids", []),
            "verified_claim_ids": payload.get("verified_claim_ids", []),
            "policy_authority": payload.get("policy_authority", "external_broker"),
            "verification_authority": payload.get("verification_authority"),
        }
    save_yaml(yaml_payload, filepath)


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


    # 2. Load identity map
    identity_map = load_identity_map(op_dir)

    # 3. Connect to local ledger SQLite
    ledger_db = os.path.join(op_dir, "ledger.sqlite3")
    conn_ledger = sqlite3.connect(ledger_db)
    conn_ledger.execute("PRAGMA journal_mode = WAL")
    conn_ledger.execute("PRAGMA synchronous = FULL")
    
    # Ensure ledger table schema is initialized
    conn_ledger.executescript("""
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
    """)

    conn_ledger.execute("BEGIN IMMEDIATE")
    try:
        # Find which records are new or have updated version
        for record in records:
            record_type = record["record_type"]
            record_id = record["record_id"]
            version = record["version"]

            local_ver, local_hash = get_local_record_version(conn_ledger, record_type, record_id)
            if version > local_ver or (version == local_ver and local_hash != record["event_hash"]):
                project_record(op_dir, conn_ledger, record, identity_map)

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


def reconcile_projections(op_dir: str, ledger_id: str, client: AuthorityClient) -> tuple[str, int]:
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

    # 2. Check if we have prepared transactions that have since been committed on the broker
    prepared_rows = conn_journal.execute(
        "SELECT * FROM transaction_journal WHERE state = 'prepared'"
    ).fetchall()
    for row in prepared_rows:
        op_key = row["operation_key"]
        # Query broker for this operation_key by executing an idempotent commit replay
        # (or looking it up if broker supported it, but replay with the same operation_key is idempotent)
        req_check = json.loads(row["prepared_request"])
        try:
            res_check = client.send_request(req_check)
            if res_check.get("ok") and "receipt" in res_check:
                commit_transaction(conn_journal, op_key, res_check["receipt"])
                if res_check["receipt"]["commit_sequence"] > broker_seq:
                    broker_seq = res_check["receipt"]["commit_sequence"]
        except Exception:
            pass  # If broker is unreachable or rejects, we fail closed later

    # 3. Sequential reconciliation
    last_applied = get_last_applied_sequence(conn_journal)
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
    conn_journal.commit()

    conn_journal.close()
    return last_digest or "", broker_seq


def get_expected_item(op_dir: str, record_type: str, record_id: str) -> dict:
    db_path = os.path.join(op_dir, "ledger.sqlite3")
    if not os.path.exists(db_path):
        return {"record_type": record_type, "record_id": record_id, "version": 0, "event_hash": None}
    try:
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            """
            SELECT version, event_hash FROM ledger_events
            WHERE record_type = ? AND record_id = ?
            ORDER BY version DESC LIMIT 1
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
    ledger_id, socket_path = enrollment
    client = AuthorityClient(socket_path)

    # Fetch all records from broker using pagination
    broker_records = {}
    after = None
    while True:
        try:
            req = {
                "action": "projection.snapshot",
                "ledger_id": ledger_id,
                "through_commit_sequence": None,
                "after": after,
                "limit": 16,
            }
            res = client.send_request(req)
            if res.get("ok"):
                snapshot = res["snapshot"]
                for rec in snapshot["records"]:
                    broker_records[(rec["record_type"], rec["record_id"])] = rec
                if not snapshot.get("has_more") or not snapshot.get("next_after"):
                    break
                after = snapshot["next_after"]
            else:
                break
        except Exception:
            break

    def get_expected_from_broker(record_type: str, record_id: str) -> dict:
        rec = broker_records.get((record_type, record_id))
        if rec:
            return {
                "record_type": record_type,
                "record_id": record_id,
                "version": rec["version"],
                "event_hash": rec["event_hash"],
            }
        return {"record_type": record_type, "record_id": record_id, "version": 0, "event_hash": None}

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

