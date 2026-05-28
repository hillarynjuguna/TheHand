from typing import TypedDict, Optional, Any, Dict


class RuntimeEvent(TypedDict, total=False):
    event_id: str
    schema_version: int
    sequence: int
    timestamp: str
    job_id: Optional[str]
    artifact_id: Optional[str]
    entity_type: Optional[str]
    event_type: str
    source: Optional[str]
    state_from: Optional[str]
    state_to: Optional[str]
    correlation_id: Optional[str]
    causation_id: Optional[str]
    payload: Dict[str, Any]
