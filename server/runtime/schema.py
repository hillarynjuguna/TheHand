import json
import uuid
from datetime import datetime
from typing import Any

SCHEMA_VERSION = 1

EVENT_CATEGORY_TRANSITION = "transition"
EVENT_CATEGORY_PROGRESS = "progress"
EVENT_CATEGORY_ARTIFACT = "artifact"
EVENT_CATEGORY_WEBSOCKET = "websocket"
EVENT_CATEGORY_RECOVERY = "recovery"

ENTITY_JOB = "job"
ENTITY_ARTIFACT = "artifact"


def utc_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


def stable_payload_json(payload: dict[str, Any] | None) -> str:
    return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def create_event(
    *,
    event_type: str,
    event_category: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    job_id: str | None = None,
    artifact_id: str | None = None,
    source: str | None = None,
    state_from: str | None = None,
    state_to: str | None = None,
    reason: str | None = None,
    actor: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_entity_id = entity_id or artifact_id or job_id
    resolved_job_id = job_id if entity_type != ENTITY_JOB else (job_id or entity_id)
    resolved_artifact_id = artifact_id if entity_type != ENTITY_ARTIFACT else (artifact_id or entity_id)
    enriched_payload = dict(payload or {})
    if reason is not None:
        enriched_payload.setdefault("reason", reason)
    if actor is not None:
        enriched_payload.setdefault("actor", actor)

    return {
        "event_id": str(uuid.uuid4()),
        "schema_version": SCHEMA_VERSION,
        "timestamp": utc_timestamp(),
        "job_id": resolved_job_id,
        "artifact_id": resolved_artifact_id,
        "entity_type": entity_type,
        "entity_id": resolved_entity_id,
        "event_type": event_type,
        "event_category": event_category,
        "source": source,
        "state_from": state_from,
        "state_to": state_to,
        "reason": reason,
        "actor": actor,
        "correlation_id": correlation_id,
        "causation_id": causation_id,
        "payload": enriched_payload,
    }


def transition_event(
    *,
    entity_type: str,
    entity_id: str,
    current_state: str | None,
    next_state: str,
    reason: str,
    source: str,
    actor: str | None = None,
    correlation_id: str | None = None,
    causation_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_payload = dict(payload or {})
    return create_event(
        event_type=f"{entity_type}.transition",
        event_category=EVENT_CATEGORY_TRANSITION,
        entity_type=entity_type,
        entity_id=entity_id,
        job_id=entity_id if entity_type == ENTITY_JOB else event_payload.get("job_id"),
        artifact_id=entity_id if entity_type == ENTITY_ARTIFACT else None,
        source=source,
        state_from=current_state,
        state_to=next_state,
        reason=reason,
        actor=actor,
        correlation_id=correlation_id,
        causation_id=causation_id,
        payload=event_payload,
    )


def websocket_event(job_id: str, message: dict[str, Any]) -> dict[str, Any]:
    artifact_id = message.get("artifact_id")
    artifact_type = message.get("artifact_type")
    event_type = message.get("type") or "job_update"
    entity_type = ENTITY_ARTIFACT if artifact_id else ENTITY_JOB
    entity_id = artifact_id or job_id
    state_to = message.get("status")
    payload = dict(message)
    if artifact_type:
        payload.setdefault("artifact_type", artifact_type)

    return create_event(
        event_type=event_type,
        event_category=EVENT_CATEGORY_WEBSOCKET,
        entity_type=entity_type,
        entity_id=entity_id,
        job_id=job_id,
        artifact_id=artifact_id,
        source="websocket_projection",
        state_to=state_to,
        payload=payload,
    )


def legacy_websocket_message(event: dict[str, Any], fallback: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = dict(event.get("payload") or {})
    if fallback:
        payload = {**fallback, **payload}
    payload.setdefault("type", event.get("event_type"))
    if event.get("artifact_id"):
        payload.setdefault("artifact_id", event.get("artifact_id"))
    if event.get("state_to") and "status" not in payload:
        payload["status"] = event.get("state_to")
    return payload
