import uuid
from datetime import datetime, timedelta

from . import store
from .schema import utc_timestamp


def _future_timestamp(seconds: int) -> str:
    return (datetime.utcnow() + timedelta(seconds=seconds)).isoformat(timespec="microseconds") + "Z"


def acquire(execution_id: str, owner: str = "local", ttl_seconds: int = 60) -> str:
    lease_id = str(uuid.uuid4())
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO leases (lease_id, execution_id, owner, acquired_at, heartbeat_at, expires_at, status) VALUES (?, ?, ?, ?, ?, ?, ?);",
            (lease_id, execution_id, owner, ts, ts, _future_timestamp(ttl_seconds), 'active'),
        )
    return lease_id


def heartbeat(lease_id: str, ttl_seconds: int = 60) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute(
            "UPDATE leases SET heartbeat_at = ?, expires_at = ? WHERE lease_id = ? AND status = 'active';",
            (ts, _future_timestamp(ttl_seconds), lease_id),
        )


def release(lease_id: str) -> None:
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute("UPDATE leases SET released_at = ?, status = 'released' WHERE lease_id = ?;", (ts, lease_id))


def stale_leases(now: str | None = None) -> list[dict]:
    timestamp = now or utc_timestamp()
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute("SELECT * FROM leases WHERE status = 'active' AND expires_at < ?;", (timestamp,)).fetchall()
        return [dict(row) for row in rows]
