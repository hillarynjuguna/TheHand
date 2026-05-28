from typing import Any

from . import events, store
from .schema import ENTITY_ARTIFACT, ENTITY_JOB
from .state import ARTIFACT_STATUS_RUNNING
from .state_machine import transition_state
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


def recover_interrupted_runtime(timestamp: str) -> dict[str, Any]:
    """Apply startup recovery for interrupted runtime work.

    This keeps the recovery policy in the runtime layer while preserving the
    existing behavior: queued/running jobs are marked error and running
    artifacts are reported for caller-managed resume.
    """
    try:
        with store.transaction() as conn:
            orphaned_jobs = conn.execute(
                "SELECT job_id, status FROM jobs WHERE status IN ('queued', 'running');"
            ).fetchall()
            stale_artifacts = conn.execute(
                "SELECT artifact_id, job_id, generation_status FROM artifacts WHERE generation_status = ?;",
                (ARTIFACT_STATUS_RUNNING,),
            ).fetchall()
            for row in orphaned_jobs:
                transition_state(
                    entity_type=ENTITY_JOB,
                    entity_id=row["job_id"],
                    current_state=row["status"],
                    next_state="error",
                    reason="server restarted while job was pending",
                    source="startup_recovery",
                    actor="runtime",
                )
            conn.execute(
                "UPDATE jobs SET status = 'error', error = 'Server restarted while job was pending.', updated_at = ? WHERE status IN ('queued', 'running');",
                (timestamp,),
            )
        return {
            "timestamp": timestamp,
            "orphaned_jobs": [dict(row) for row in orphaned_jobs],
            "stale_artifacts": [dict(row) for row in stale_artifacts],
            "actions": ["marked queued/running jobs as error"],
            "replayed_state_count": len(replay_runtime_state(events.fetch_events(limit=1000))),
        }
    except Exception as exc:
        return {"error": str(exc)}
