from collections.abc import Callable
from typing import Any

from . import events
from .schema import ENTITY_ARTIFACT, ENTITY_JOB, transition_event
from .state import (
    ARTIFACT_STATUS_DONE,
    ARTIFACT_STATUS_ERROR,
    ARTIFACT_STATUS_PERSISTING,
    ARTIFACT_STATUS_QUEUED,
    ARTIFACT_STATUS_RUNNING,
    JOB_STATUS_DONE,
    JOB_STATUS_ERROR,
    JOB_STATUS_QUEUED,
    JOB_STATUS_RUNNING,
)

TransitionHook = Callable[[dict[str, Any]], None]

VALID_TRANSITIONS: dict[str, dict[str | None, set[str]]] = {
    ENTITY_JOB: {
        None: {JOB_STATUS_QUEUED},
        JOB_STATUS_QUEUED: {JOB_STATUS_RUNNING, JOB_STATUS_ERROR},
        JOB_STATUS_RUNNING: {JOB_STATUS_DONE, JOB_STATUS_ERROR},
        JOB_STATUS_DONE: set(),
        JOB_STATUS_ERROR: set(),
    },
    ENTITY_ARTIFACT: {
        None: {ARTIFACT_STATUS_QUEUED},
        ARTIFACT_STATUS_QUEUED: {ARTIFACT_STATUS_RUNNING, ARTIFACT_STATUS_ERROR},
        ARTIFACT_STATUS_RUNNING: {
            ARTIFACT_STATUS_PERSISTING,
            ARTIFACT_STATUS_DONE,
            ARTIFACT_STATUS_ERROR,
        },
        ARTIFACT_STATUS_PERSISTING: {ARTIFACT_STATUS_DONE, ARTIFACT_STATUS_ERROR},
        ARTIFACT_STATUS_DONE: set(),
        ARTIFACT_STATUS_ERROR: set(),
    },
}

_transition_hooks: list[TransitionHook] = []


class InvalidTransitionError(ValueError):
    pass


def register_transition_hook(callback: TransitionHook) -> None:
    _transition_hooks.append(callback)


def validate_transition(entity_type: str, current_state: str | None, next_state: str) -> None:
    allowed = VALID_TRANSITIONS.get(entity_type, {}).get(current_state)
    if allowed is None or next_state not in allowed:
        raise InvalidTransitionError(
            f"Invalid {entity_type} transition: {current_state!r} -> {next_state!r}"
        )


def transition_state(
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
) -> dict[str, Any] | None:
    if current_state == next_state:
        return None

    validate_transition(entity_type, current_state, next_state)
    event = events.emit_event(
        transition_event(
            entity_type=entity_type,
            entity_id=entity_id,
            current_state=current_state,
            next_state=next_state,
            reason=reason,
            source=source,
            actor=actor,
            correlation_id=correlation_id,
            causation_id=causation_id,
            payload=payload,
        )
    )

    for hook in list(_transition_hooks):
        try:
            hook(event)
        except Exception:
            pass
    return event


def replay_states(runtime_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    states: dict[str, dict[str, Any]] = {}
    ordered = sorted(runtime_events, key=lambda event: (event.get("timestamp") or "", event.get("sequence") or 0))
    for event in ordered:
        if event.get("event_category") != "transition":
            continue
        entity_id = event.get("entity_id") or event.get("artifact_id") or event.get("job_id")
        entity_type = event.get("entity_type")
        if not entity_id or not entity_type:
            continue
        key = f"{entity_type}:{entity_id}"
        states[key] = {
            "entity_id": entity_id,
            "entity_type": entity_type,
            "state": event.get("state_to"),
            "updated_at": event.get("timestamp"),
            "last_event_id": event.get("event_id"),
        }
    return states
