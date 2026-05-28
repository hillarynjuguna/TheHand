import json
import uuid
from typing import Any

from . import event_store, store
from .schema import utc_timestamp
from .state_machine import replay_states


def create_snapshot(entity_id: str, entity_type: str | None = None) -> dict[str, Any]:
    events = event_store.query_timeline(entity_id, limit=1000)
    states = replay_states(events)
    state = states.get(f"{entity_type}:{entity_id}") if entity_type else None
    if state is None and states:
        state = next(reversed(states.values()))
    high_watermark = events[-1] if events else {}
    snapshot_id = str(uuid.uuid4())
    ts = utc_timestamp()
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO runtime_snapshots (snapshot_id, entity_id, entity_type, state_json, high_watermark_event_id, high_watermark_timestamp, created_at) VALUES (?, ?, ?, ?, ?, ?, ?);",
            (
                snapshot_id,
                entity_id,
                entity_type or (state or {}).get("entity_type"),
                json.dumps(state or {}, sort_keys=True),
                high_watermark.get("event_id"),
                high_watermark.get("timestamp"),
                ts,
            ),
        )
    return {
        "snapshot_id": snapshot_id,
        "entity_id": entity_id,
        "entity_type": entity_type or (state or {}).get("entity_type"),
        "state": state or {},
        "created_at": ts,
    }


def latest_snapshot(entity_id: str) -> dict[str, Any] | None:
    with store.DB_LOCK, store.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM runtime_snapshots WHERE entity_id = ? ORDER BY created_at DESC LIMIT 1;",
            (entity_id,),
        ).fetchone()
        if not row:
            return None
        result = dict(row)
        result["state"] = json.loads(result.pop("state_json") or "{}")
        return result


def replay_from_snapshot(entity_id: str) -> dict[str, Any]:
    snapshot = latest_snapshot(entity_id)
    events = event_store.query_timeline(entity_id, limit=1000)
    if not snapshot:
        return {"snapshot": None, "events": events}
    watermark = snapshot.get("high_watermark_timestamp")
    replay_tail = [event for event in events if not watermark or event.get("timestamp", "") > watermark]
    return {"snapshot": snapshot, "events": replay_tail}
