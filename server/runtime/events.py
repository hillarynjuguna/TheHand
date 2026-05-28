import json
import uuid
from datetime import datetime, timedelta
from .types import RuntimeEvent
from . import event_store

_LAST_TIMESTAMP: datetime | None = None


def _current_ts() -> str:
    global _LAST_TIMESTAMP
    now = datetime.utcnow()
    if _LAST_TIMESTAMP is not None and now <= _LAST_TIMESTAMP:
        now = _LAST_TIMESTAMP + timedelta(microseconds=1)
    _LAST_TIMESTAMP = now
    return now.isoformat(timespec="microseconds") + 'Z'


def init_runtime_events_table() -> None:
    event_store.init()


def emit_event(event: RuntimeEvent) -> RuntimeEvent:
    """Persist a canonical runtime event and publish it on the bus.

    Returns the persisted event (with event_id, timestamp, sequence filled).
    """
    ev = dict(event)
    ev.setdefault('event_id', str(uuid.uuid4()))
    ev.setdefault('schema_version', 1)
    ev.setdefault('timestamp', _current_ts())
    ev.setdefault('entity_id', ev.get('artifact_id') or ev.get('job_id'))
    ev.setdefault('event_category', (ev.get('payload') or {}).get('event_category'))
    return event_store.append(ev)


def fetch_events(job_id: str | None = None, limit: int = 100):
    return event_store.recent(job_id=job_id, limit=limit)


def fetch_entity_timeline(entity_id: str, limit: int = 200):
    return event_store.query_timeline(entity_id, limit=limit)
