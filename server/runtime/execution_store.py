import json
from typing import Any

from . import store
from .schema import utc_timestamp


def create_execution(execution_id: str, work_type: str, entity_id: str | None, correlation_id: str | None, causation_id: str | None, payload: dict[str, Any] | None = None, max_attempts: int = 1) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO executions (execution_id, work_type, entity_id, status, attempts, max_attempts, queued_at, updated_at, correlation_id, causation_id, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (execution_id, work_type, entity_id, 'queued', 0, max_attempts, ts, ts, correlation_id, causation_id, json.dumps(payload or {}, sort_keys=True)),
        )


def mark_running(execution_id: str, lease_id: str) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute(
            "UPDATE executions SET status = 'running', attempts = attempts + 1, lease_id = ?, heartbeat_at = ?, started_at = COALESCE(started_at, ?), updated_at = ? WHERE execution_id = ?;",
            (lease_id, ts, ts, ts, execution_id),
        )


def heartbeat(execution_id: str) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute("UPDATE executions SET heartbeat_at = ?, updated_at = ? WHERE execution_id = ?;", (ts, ts, execution_id))


def mark_completed(execution_id: str) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute("UPDATE executions SET status = 'done', completed_at = ?, updated_at = ? WHERE execution_id = ?;", (ts, ts, execution_id))


def mark_failed(execution_id: str, error: str) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute("UPDATE executions SET status = 'error', error = ?, completed_at = ?, updated_at = ? WHERE execution_id = ?;", (error, ts, ts, execution_id))


def reclaim_interrupted() -> list[dict]:
    ts = utc_timestamp()
    with store.transaction() as conn:
        rows = conn.execute("SELECT execution_id, work_type, entity_id, attempts, max_attempts FROM executions WHERE status IN ('queued', 'running');").fetchall()
        conn.execute("UPDATE executions SET status = 'stale', updated_at = ? WHERE status = 'running';", (ts,))
        return [dict(row) for row in rows]


def snapshot() -> dict[str, Any]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS count FROM executions GROUP BY status;").fetchall()
        return {"executions": {row["status"]: row["count"] for row in rows}}
