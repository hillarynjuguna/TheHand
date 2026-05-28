from typing import Any

from . import store
from .schema import utc_timestamp


def register_artifact_lineage(
    artifact_id: str,
    *,
    job_id: str,
    artifact_type: str,
    upstream_type: str = "transcript",
    upstream_id: str | None = None,
    upstream_hash: str | None = None,
) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO artifact_lineage (artifact_id, job_id, artifact_type, upstream_type, upstream_id, upstream_hash, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT status FROM artifact_lineage WHERE artifact_id = ?), 'fresh'), ?, ?);",
            (artifact_id, job_id, artifact_type, upstream_type, upstream_id or job_id, upstream_hash, artifact_id, ts, ts),
        )


def get_upstream(artifact_id: str) -> list[dict[str, Any]]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            "SELECT upstream_type, upstream_id, upstream_hash, status FROM artifact_lineage WHERE artifact_id = ?;",
            (artifact_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_downstream(upstream_id: str) -> list[dict[str, Any]]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            "SELECT artifact_id, job_id, artifact_type, status FROM artifact_lineage WHERE upstream_id = ? OR job_id = ?;",
            (upstream_id, upstream_id),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_stale(upstream_id: str, reason: str = "upstream changed") -> list[str]:
    ts = utc_timestamp()
    downstream = get_downstream(upstream_id)
    with store.transaction() as conn:
        conn.execute(
            "UPDATE artifact_lineage SET status = 'stale', updated_at = ? WHERE upstream_id = ? OR job_id = ?;",
            (ts, upstream_id, upstream_id),
        )
    return [row["artifact_id"] for row in downstream]


def mark_fresh(artifact_id: str) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute("UPDATE artifact_lineage SET status = 'fresh', updated_at = ? WHERE artifact_id = ?;", (ts, artifact_id))


def plan_regeneration(upstream_id: str) -> list[dict[str, Any]]:
    return [
        {"artifact_id": row["artifact_id"], "job_id": row["job_id"], "artifact_type": row["artifact_type"]}
        for row in get_downstream(upstream_id)
        if row.get("status") == "stale"
    ]
