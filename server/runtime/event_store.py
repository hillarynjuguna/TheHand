import json
import sqlite3

from . import bus, store
from .schema import stable_payload_json

EVENT_COLUMNS = "event_id, sequence, timestamp, job_id, artifact_id, entity_type, event_type, source, state_from, state_to, correlation_id, causation_id, payload_json, schema_version, event_category, entity_id, actor, reason"


def init() -> None:
    with store.transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runtime_events (
                event_id TEXT PRIMARY KEY,
                sequence INTEGER,
                timestamp TEXT,
                job_id TEXT,
                artifact_id TEXT,
                entity_type TEXT,
                event_type TEXT,
                source TEXT,
                state_from TEXT,
                state_to TEXT,
                correlation_id TEXT,
                causation_id TEXT,
                payload_json TEXT,
                schema_version INTEGER,
                event_category TEXT,
                entity_id TEXT,
                actor TEXT,
                reason TEXT
            );
            """
        )
        for column, definition in [
            ("event_category", "TEXT"),
            ("entity_id", "TEXT"),
            ("actor", "TEXT"),
            ("reason", "TEXT"),
        ]:
            store.ensure_column(conn, "runtime_events", column, definition)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_category ON runtime_events(event_category, timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_entity ON runtime_events(entity_id, timestamp);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_job ON runtime_events(job_id, sequence);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runtime_events_correlation ON runtime_events(correlation_id, causation_id);")


def next_sequence(conn, job_id: str | None) -> int:
    if job_id is None:
        row = conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM runtime_events WHERE job_id IS NULL;").fetchone()
    else:
        row = conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM runtime_events WHERE job_id = ?;", (job_id,)).fetchone()
    return (row[0] or 0) + 1


def append(event: dict) -> dict:
    ev = dict(event)
    ev.setdefault("entity_id", ev.get("artifact_id") or ev.get("job_id"))
    with store.transaction() as conn:
        ev["sequence"] = next_sequence(conn, ev.get("job_id"))
        conn.execute(
            f"INSERT OR IGNORE INTO runtime_events ({EVENT_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (
                ev.get("event_id"),
                ev.get("sequence"),
                ev.get("timestamp"),
                ev.get("job_id"),
                ev.get("artifact_id"),
                ev.get("entity_type"),
                ev.get("event_type"),
                ev.get("source"),
                ev.get("state_from"),
                ev.get("state_to"),
                ev.get("correlation_id"),
                ev.get("causation_id"),
                stable_payload_json(ev.get("payload") or {}),
                ev.get("schema_version", 1),
                ev.get("event_category"),
                ev.get("entity_id"),
                ev.get("actor"),
                ev.get("reason"),
            ),
        )
    try:
        bus.publish(ev)
    except Exception:
        pass
    return ev


def _row_to_event(row) -> dict:
    return {
        'event_id': row[0], 'sequence': row[1], 'timestamp': row[2], 'job_id': row[3],
        'artifact_id': row[4], 'entity_type': row[5], 'event_type': row[6], 'source': row[7],
        'state_from': row[8], 'state_to': row[9], 'correlation_id': row[10],
        'causation_id': row[11], 'payload': json.loads(row[12] or '{}'),
        'schema_version': row[13], 'event_category': row[14], 'entity_id': row[15],
        'actor': row[16], 'reason': row[17],
    }


def replay(entity_id: str, limit: int = 1000) -> list[dict]:
    return query_timeline(entity_id, limit=limit)


def replay_category(event_category: str, limit: int = 1000) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {EVENT_COLUMNS} FROM runtime_events WHERE event_category = ? ORDER BY timestamp ASC, sequence ASC LIMIT ?;",
            (event_category, limit),
        ).fetchall()
        return [_row_to_event(row) for row in rows]


def query_timeline(entity_id: str, limit: int = 200) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {EVENT_COLUMNS} FROM runtime_events WHERE entity_id = ? OR job_id = ? OR artifact_id = ? ORDER BY timestamp ASC, sequence ASC LIMIT ?;",
            (entity_id, entity_id, entity_id, limit),
        ).fetchall()
        return [_row_to_event(row) for row in rows]


def query_correlated(correlation_id: str, limit: int = 200) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            f"SELECT {EVENT_COLUMNS} FROM runtime_events WHERE correlation_id = ? OR causation_id = ? ORDER BY timestamp ASC, sequence ASC LIMIT ?;",
            (correlation_id, correlation_id, limit),
        ).fetchall()
        return [_row_to_event(row) for row in rows]


def recent(job_id: str | None = None, limit: int = 100) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        if job_id:
            rows = conn.execute(
                f"SELECT {EVENT_COLUMNS} FROM runtime_events WHERE job_id = ? ORDER BY sequence DESC LIMIT ?;",
                (job_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT {EVENT_COLUMNS} FROM runtime_events ORDER BY timestamp DESC, sequence DESC LIMIT ?;",
                (limit,),
            ).fetchall()
        return [_row_to_event(row) for row in rows]
