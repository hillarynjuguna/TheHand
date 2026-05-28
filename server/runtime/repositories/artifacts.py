import json
import uuid
from pathlib import Path
from typing import Optional

from runtime import store


def artifact_dir_for(job_id: str) -> Path:
    path = store.JOB_ARTIFACTS_DIR / job_id / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_artifact(job_id: str, artifact_type: str, title: str | None, content: str | None, metadata: dict | None, generation_model: str | None, generation_status: str, created_at: str) -> str:
    artifact_id = str(uuid.uuid4())
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO artifacts (artifact_id, job_id, artifact_type, title, content, metadata_json, embedding_json, generation_model, generation_status, created_at, updated_at, depends_on, input_hash, generation_attempts, generation_error) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (
                artifact_id,
                job_id,
                artifact_type,
                title or '',
                content or '',
                json.dumps(metadata or {}),
                json.dumps(None),
                generation_model or '',
                generation_status,
                created_at,
                created_at,
                None,
                metadata.get('source_transcript_hash') if metadata else None,
                0,
                None,
            ),
        )
    return artifact_id


def update_artifact(artifact_id: str, updates: dict) -> None:
    if not updates:
        return
    keys = ', '.join([f"{key} = ?" for key in updates.keys()])
    params = list(updates.values()) + [artifact_id]
    with store.transaction() as conn:
        conn.execute(f"UPDATE artifacts SET {keys} WHERE artifact_id = ?;", params)


def fetch_artifact(artifact_id: str) -> Optional[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?;", (artifact_id,)).fetchone()
        if not row:
            return None
        result = store.row_to_dict(row)
        try:
            result['metadata'] = json.loads(result.get('metadata_json') or '{}')
        except Exception:
            result['metadata'] = {}
        return result


def list_job_artifacts(job_id: str) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            "SELECT artifact_id, job_id, artifact_type, title, generation_status, created_at, updated_at FROM artifacts WHERE job_id = ? ORDER BY updated_at DESC;",
            (job_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def persist_artifact_content(job_id: str, artifact_id: str, content: str, metadata: dict | None, created_at: str) -> None:
    path = artifact_dir_for(job_id) / f"{artifact_id}.json"
    payload = {
        'artifact_id': artifact_id,
        'job_id': job_id,
        'content': content,
        'metadata': metadata or {},
        'created_at': created_at,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def add_artifact_version(artifact_id: str, content: str, metadata: dict, created_at: str) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT INTO artifact_versions (artifact_id, version_number, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?);",
            (artifact_id, 1, content, json.dumps(metadata), created_at),
        )
        conn.execute("UPDATE artifacts SET generation_attempts = generation_attempts + 1 WHERE artifact_id = ?;", (artifact_id,))


def generation_status(artifact_id: str) -> Optional[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        row = conn.execute(
            "SELECT artifact_id, job_id, generation_status FROM artifacts WHERE artifact_id = ?;",
            (artifact_id,),
        ).fetchone()
        return dict(row) if row else None


def artifacts_for_resume() -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            "SELECT artifact_id, job_id, artifact_type, generation_status FROM artifacts WHERE generation_status IN ('queued', 'running');"
        ).fetchall()
        return [dict(row) for row in rows]


def chunks_for_artifact_generation(job_id: str, limit: int = 20) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            "SELECT chunk_index, start_ts, end_ts, text FROM chunks WHERE job_id = ? ORDER BY chunk_index ASC LIMIT ?;",
            (job_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def running_artifacts() -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute(
            "SELECT artifact_id, job_id, generation_status FROM artifacts WHERE generation_status = 'running';"
        ).fetchall()
        return [dict(row) for row in rows]
