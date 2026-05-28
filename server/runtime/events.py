import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock
from .types import RuntimeEvent
from . import bus

DB_PATH = Path(__file__).parent.parent / 'data' / 'thehand.db'
_LOCK = Lock()


def _current_ts() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def init_runtime_events_table() -> None:
    with _LOCK, sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
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
                schema_version INTEGER
            );
            """
        )
        conn.commit()


def _next_sequence(job_id: str | None) -> int:
    with _LOCK, sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        cur = conn.execute("SELECT COALESCE(MAX(sequence), 0) FROM runtime_events WHERE job_id = ?;", (job_id,))
        row = cur.fetchone()
        return (row[0] or 0) + 1


def emit_event(event: RuntimeEvent) -> RuntimeEvent:
    """Persist a canonical runtime event and publish it on the bus.

    Returns the persisted event (with event_id, timestamp, sequence filled).
    """
    ev = dict(event)
    ev.setdefault('event_id', str(uuid.uuid4()))
    ev.setdefault('schema_version', 1)
    ev.setdefault('timestamp', _current_ts())
    job_id = ev.get('job_id')
    ev['sequence'] = _next_sequence(job_id)

    payload_json = json.dumps(ev.get('payload') or {})

    with _LOCK, sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        conn.execute(
            "INSERT INTO runtime_events (event_id, sequence, timestamp, job_id, artifact_id, entity_type, event_type, source, state_from, state_to, correlation_id, causation_id, payload_json, schema_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (
                ev['event_id'],
                ev['sequence'],
                ev['timestamp'],
                ev.get('job_id'),
                ev.get('artifact_id'),
                ev.get('entity_type'),
                ev.get('event_type'),
                ev.get('source'),
                ev.get('state_from'),
                ev.get('state_to'),
                ev.get('correlation_id'),
                ev.get('causation_id'),
                payload_json,
                ev.get('schema_version', 1),
            ),
        )
        conn.commit()

    # publish to in-process bus
    try:
        bus.publish(ev)
    except Exception:
        pass

    return ev


def fetch_events(job_id: str | None = None, limit: int = 100):
    with _LOCK, sqlite3.connect(DB_PATH, check_same_thread=False) as conn:
        if job_id:
            rows = conn.execute("SELECT * FROM runtime_events WHERE job_id = ? ORDER BY sequence DESC LIMIT ?;", (job_id, limit)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM runtime_events ORDER BY sequence DESC LIMIT ?;", (limit,)).fetchall()
        result = []
        for r in rows:
            result.append({
                'event_id': r[0], 'sequence': r[1], 'timestamp': r[2], 'job_id': r[3], 'artifact_id': r[4], 'entity_type': r[5], 'event_type': r[6], 'source': r[7], 'state_from': r[8], 'state_to': r[9], 'correlation_id': r[10], 'causation_id': r[11], 'payload': json.loads(r[12] or '{}'), 'schema_version': r[13]
            })
        return result
