import json
from typing import Optional

from runtime import store
from semantic import build_embedding, chunk_transcript, cosine_similarity


def _upsert_chunk_search_index(conn, chunk: dict, job: dict, fts_enabled: bool) -> None:
    if not fts_enabled:
        return
    conn.execute(
        "INSERT OR REPLACE INTO chunks_fts(chunk_id, job_id, source, filename, text) VALUES (?, ?, ?, ?, ?);",
        (
            chunk.get('chunk_id'),
            job.get('job_id'),
            job.get('source') or '',
            job.get('filename') or '',
            chunk.get('text') or '',
        ),
    )


def create_chunks_for_job(job_id: str, transcript: dict, created_at: str, fts_enabled: bool) -> None:
    if not transcript:
        return
    chunks = chunk_transcript(transcript.get('text', ''), transcript.get('json_raw', None))
    if not chunks:
        return

    with store.transaction() as conn:
        job_row = conn.execute("SELECT source, filename FROM jobs WHERE job_id = ?;", (job_id,)).fetchone()
        source = job_row['source'] if job_row else None
        filename = job_row['filename'] if job_row else None
        conn.execute("DELETE FROM chunks WHERE job_id = ?;", (job_id,))
        for index, chunk in enumerate(chunks):
            embedding = build_embedding(chunk['text'])
            cursor = conn.execute(
                "INSERT INTO chunks (job_id, chunk_index, start_ts, end_ts, text, embedding_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?);",
                (
                    job_id,
                    index,
                    chunk.get('start_ts'),
                    chunk.get('end_ts'),
                    chunk['text'],
                    json.dumps(embedding),
                    created_at,
                    created_at,
                ),
            )
            _upsert_chunk_search_index(conn, {
                'chunk_id': cursor.lastrowid,
                'text': chunk['text'],
            }, {'job_id': job_id, 'source': source, 'filename': filename}, fts_enabled)


def list_chunks(job_id: Optional[str], search: Optional[str], status: Optional[str], top_k: int, offset: int, fts_enabled: bool) -> list[dict]:
    with store.DB_LOCK, store.get_connection() as conn:
        where_clauses = ["1=1"]
        params: list[Optional[object]] = []
        if job_id:
            where_clauses.append("c.job_id = ?")
            params.append(job_id)
        if status:
            where_clauses.append("j.status = ?")
            params.append(status)
        if search and fts_enabled:
            where_clauses.append("c.chunk_id IN (SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?)")
            params.append(' '.join(search.strip().split()))
        elif search:
            term = f"%{search}%"
            where_clauses.append("(c.text LIKE ? OR j.source LIKE ? OR j.filename LIKE ?)")
            params.extend([term, term, term])

        query = (
            "SELECT c.chunk_id, c.job_id, c.chunk_index, c.start_ts, c.end_ts, c.text, c.embedding_json, j.source_type, j.source, j.filename, j.status AS job_status, j.model, j.language, j.updated_at AS job_updated_at "
            "FROM chunks c "
            "JOIN jobs j ON j.job_id = c.job_id "
            f"WHERE {' AND '.join(where_clauses)} "
            "ORDER BY j.updated_at DESC, c.chunk_index ASC LIMIT ? OFFSET ?;"
        )
        params.extend([top_k, offset])
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def search_chunks(query: str, job_id: Optional[str], status: Optional[str], top_k: int, fts_enabled: bool) -> list[dict]:
    candidates = list_chunks(job_id=job_id, search=query, status=status, top_k=max(100, top_k * 5), offset=0, fts_enabled=fts_enabled)
    query_embedding = build_embedding(query)
    scored = []
    for row in candidates:
        embedding = []
        if row.get('embedding_json'):
            try:
                embedding = json.loads(row['embedding_json'])
            except Exception:
                embedding = []
        scored.append((cosine_similarity(query_embedding, embedding) if embedding else 0.0, row))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [
        {
            'chunk_id': row['chunk_id'],
            'job_id': row['job_id'],
            'chunk_index': row['chunk_index'],
            'start_ts': row['start_ts'],
            'end_ts': row['end_ts'],
            'text': row['text'],
            'score': score,
            'source_type': row['source_type'],
            'source': row['source'],
            'filename': row['filename'],
            'job_status': row['job_status'],
            'model': row['model'],
            'language': row['language'],
            'job_updated_at': row['job_updated_at'],
        }
        for score, row in scored[:top_k]
    ]
