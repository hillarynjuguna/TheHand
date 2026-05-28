from typing import Optional

from runtime import store


def _upsert_search_index(conn, job: dict, fts_enabled: bool) -> None:
    if not fts_enabled:
        return
    conn.execute(
        "INSERT OR REPLACE INTO jobs_fts(job_id, source, filename, status, model, language, transcript_text) VALUES (?, ?, ?, ?, ?, ?, ?);",
        (
            job.get('job_id'),
            job.get('source') or '',
            job.get('filename') or '',
            job.get('status') or '',
            job.get('model') or '',
            job.get('language') or '',
            job.get('transcript_text') or '',
        ),
    )


def db_record_to_job(row) -> dict:
    job = store.row_to_dict(row)
    job['transcript'] = {
        'text': job.pop('transcript_text', '') or '',
        'srt': job.pop('transcript_srt', '') or '',
        'vtt': job.pop('transcript_vtt', '') or '',
        'json_raw': job.pop('transcript_json', '') or '',
    }
    return job


def create_job(job: dict, fts_enabled: bool) -> None:
    with store.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO jobs (job_id, source_type, source, filename, status, step, step_status, progress, model, language, created_at, updated_at, transcript_text, transcript_srt, transcript_vtt, transcript_json, error, duration) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
            (
                job['id'],
                job.get('source_type'),
                job.get('source'),
                job.get('filename'),
                job.get('status'),
                job.get('step'),
                job.get('step_status'),
                job.get('progress', 0),
                job.get('model'),
                job.get('language'),
                job.get('created_at'),
                job.get('updated_at'),
                None,
                None,
                None,
                None,
                None,
                job.get('duration'),
            ),
        )
        _upsert_search_index(conn, {
            'job_id': job['id'],
            'source': job.get('source'),
            'filename': job.get('filename'),
            'status': job.get('status'),
            'model': job.get('model'),
            'language': job.get('language'),
            'transcript_text': None,
        }, fts_enabled)


def update_job(job_id: str, updates: dict, fts_enabled: bool) -> None:
    if not updates:
        return
    keys = ', '.join([f"{key} = ?" for key in updates.keys()])
    params = list(updates.values()) + [job_id]
    with store.transaction() as conn:
        conn.execute(f"UPDATE jobs SET {keys} WHERE job_id = ?;", params)
        job = conn.execute("SELECT * FROM jobs WHERE job_id = ?;", (job_id,)).fetchone()
        if job:
            _upsert_search_index(conn, store.row_to_dict(job), fts_enabled)


def fetch_job(job_id: str) -> Optional[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?;", (job_id,)).fetchone()
        if not row:
            return None
        return db_record_to_job(row)


def list_jobs(search: Optional[str], status: Optional[str], source_type: Optional[str], model: Optional[str], limit: int, offset: int, fts_enabled: bool) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        where_clauses = []
        params = []

        if search:
            if fts_enabled:
                where_clauses.append("job_id IN (SELECT job_id FROM jobs_fts WHERE jobs_fts MATCH ?)")
                params.append(' '.join(search.strip().split()))
            else:
                term = f"%{search}%"
                where_clauses.append("(source LIKE ? OR filename LIKE ? OR status LIKE ? OR model LIKE ? OR language LIKE ? OR transcript_text LIKE ?)")
                params.extend([term] * 6)

        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if source_type:
            where_clauses.append("source_type = ?")
            params.append(source_type)
        if model:
            where_clauses.append("model = ?")
            params.append(model)

        where_clause = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ''
        query = (
            "SELECT j.job_id, j.source_type, j.source, j.filename, j.status, j.step, j.step_status, j.progress, j.model, j.language, j.created_at, j.updated_at, j.error, j.duration, substr(j.transcript_text, 1, 250) AS preview, "
            "COALESCE(c.chunk_count, 0) AS chunk_count "
            "FROM jobs j "
            "LEFT JOIN (SELECT job_id, COUNT(*) AS chunk_count FROM chunks GROUP BY job_id) c ON c.job_id = j.job_id "
            f"{where_clause} "
            "ORDER BY j.updated_at DESC LIMIT ? OFFSET ?;"
        )
        params.extend([limit, offset])
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def queued_or_running_jobs() -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        rows = conn.execute("SELECT job_id, status FROM jobs WHERE status IN ('queued', 'running');").fetchall()
        return [dict(row) for row in rows]
