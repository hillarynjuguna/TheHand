from typing import Any

JOB_STATUS_QUEUED = "queued"
JOB_STATUS_RUNNING = "running"
JOB_STATUS_DONE = "done"
JOB_STATUS_ERROR = "error"
JOB_TERMINAL_STATUSES = {JOB_STATUS_DONE, JOB_STATUS_ERROR}

ARTIFACT_STATUS_QUEUED = "queued"
ARTIFACT_STATUS_RUNNING = "running"
ARTIFACT_STATUS_PERSISTING = "persisting"
ARTIFACT_STATUS_DONE = "done"
ARTIFACT_STATUS_ERROR = "error"
ARTIFACT_TERMINAL_STATUSES = {ARTIFACT_STATUS_DONE, ARTIFACT_STATUS_ERROR}


def create_queued_job(
    job_id: str,
    *,
    source_type: str,
    source: str | None,
    model: str,
    language: str,
    created_at: str,
    step: str,
    filename: str | None = None,
) -> dict[str, Any]:
    job = {
        "id": job_id,
        "status": JOB_STATUS_QUEUED,
        "step": step,
        "step_status": "pending",
        "progress": 0,
        "source_type": source_type,
        "source": source,
        "model": model,
        "language": language,
        "created_at": created_at,
        "updated_at": created_at,
        "transcript": None,
        "error": None,
    }
    if filename is not None:
        job["filename"] = filename
    return job
