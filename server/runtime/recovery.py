from typing import Any

from .schema import ENTITY_ARTIFACT, ENTITY_JOB
from .state import ARTIFACT_STATUS_RUNNING
from .state_machine import replay_states


def replay_runtime_state(runtime_events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return replay_states(runtime_events)


def reconcile_runtime_storage(conn, timestamp: str) -> dict[str, Any]:
    orphaned_jobs = conn.execute(
        "SELECT job_id, status FROM jobs WHERE status IN ('queued', 'running');"
    ).fetchall()
    stale_artifacts = conn.execute(
        "SELECT artifact_id, job_id, generation_status FROM artifacts WHERE generation_status = ?;",
        (ARTIFACT_STATUS_RUNNING,),
    ).fetchall()

    return {
        "timestamp": timestamp,
        "orphaned_jobs": [dict(row) for row in orphaned_jobs],
        "stale_artifacts": [dict(row) for row in stale_artifacts],
        "actions": [
            "reported queued/running jobs for caller-managed transition",
            "reported running artifacts for caller-managed resume",
        ],
    }
