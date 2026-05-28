"""
TheHand — Local Transcription Server
FastAPI backend for the TheHand UI.

Runs in Termux (Android) or any Python 3.10+ environment.
Serves the built frontend and handles all transcription API calls.

Setup (Termux):
  pip install fastapi uvicorn python-multipart yt-dlp websockets
  uvicorn main:app --host 0.0.0.0 --port 8080

Directory layout expected:
  transcribe-local/
  ├── main.py          ← this file
  └── dist/            ← built frontend (copy from TheHand/dist after npm run build)

whisper.cpp should be compiled at ~/whisper.cpp/build/bin/whisper-cli
This server persists completed jobs in server/data/thehand.db and stores per-job artifacts under server/data/jobs/.
"""

import asyncio
import json
import math
import os
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib
import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, BackgroundTasks

from semantic import build_embedding, chunk_transcript, cosine_similarity
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from runtime import events as runtime_events
from runtime import bus as runtime_bus
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WHISPER_BIN = os.environ.get(
    "WHISPER_BIN",
    str(Path.home() / "whisper.cpp" / "build" / "bin" / "whisper-cli"),
)
WHISPER_BIN_FALLBACK = str(Path.home() / "whisper.cpp" / "build" / "bin" / "main")

MODELS_DIR = os.environ.get(
    "MODELS_DIR",
    str(Path.home() / "whisper.cpp" / "models"),
)

FRONTEND_DIR = os.environ.get(
    "FRONTEND_DIR",
    str(Path(__file__).parent / "dist"),
)

TEMP_DIR = Path(tempfile.gettempdir()) / "thehand"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

# Persistent storage and artifacts
DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "thehand.db"
JOB_ARTIFACTS_DIR = DATA_DIR / "jobs"
JOB_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
DB_LOCK = threading.Lock()
FTS_ENABLED = False

# In-memory job store
jobs: dict[str, dict] = {}
# WebSocket connections per job_id for pushing real-time events
WS_CONNECTIONS: dict[str, list[WebSocket]] = {}

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _row_to_dict(row: sqlite3.Row) -> dict:
    return {key: row[key] for key in row.keys()}


def _current_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def init_db() -> None:
    global FTS_ENABLED
    with DB_LOCK:
        conn = get_db_connection()
        try:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    source_type TEXT,
                    source TEXT,
                    filename TEXT,
                    status TEXT,
                    step TEXT,
                    step_status TEXT,
                    progress INTEGER,
                    model TEXT,
                    language TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    transcript_text TEXT,
                    transcript_srt TEXT,
                    transcript_vtt TEXT,
                    transcript_json TEXT,
                    error TEXT,
                    duration REAL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT,
                    chunk_index INTEGER,
                    start_ts REAL,
                    end_ts REAL,
                    text TEXT,
                    embedding_json TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    job_id TEXT,
                    artifact_type TEXT,
                    title TEXT,
                    content TEXT,
                    metadata_json TEXT,
                    embedding_json TEXT,
                    generation_model TEXT,
                    generation_status TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    FOREIGN KEY(job_id) REFERENCES jobs(job_id)
                );
                CREATE TABLE IF NOT EXISTS artifact_versions (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artifact_id TEXT,
                    version_number INTEGER,
                    content TEXT,
                    metadata_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id)
                );
                CREATE TABLE IF NOT EXISTS artifact_events (
                    event_id TEXT PRIMARY KEY,
                    artifact_id TEXT,
                    job_id TEXT,
                    event_type TEXT,
                    status TEXT,
                    detail_json TEXT,
                    created_at TEXT,
                    FOREIGN KEY(artifact_id) REFERENCES artifacts(artifact_id)
                );
                """
            )
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS jobs_fts USING fts5(job_id UNINDEXED, source, filename, status, model, language, transcript_text);"
            )
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, job_id UNINDEXED, source, filename, text);"
            )
            FTS_ENABLED = True
        except sqlite3.OperationalError:
            FTS_ENABLED = False
        # Ensure artifact schema has recommended columns for dependency, attempts, and errors
        try:
            conn.execute("ALTER TABLE artifacts ADD COLUMN depends_on TEXT;")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE artifacts ADD COLUMN input_hash TEXT;")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE artifacts ADD COLUMN generation_attempts INTEGER DEFAULT 0;")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE artifacts ADD COLUMN generation_error TEXT;")
        except Exception:
            pass
        conn.execute(
            "UPDATE jobs SET status = 'error', error = 'Server restarted while job was pending.', updated_at = ? WHERE status IN ('queued', 'running');",
            (_current_timestamp(),),
        )
        conn.commit()
        conn.close()
    # ensure runtime events table exists
    try:
        runtime_events.init_runtime_events_table()
    except Exception:
        pass


def _upsert_search_index(conn: sqlite3.Connection, job: dict) -> None:
    if not FTS_ENABLED:
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


def _upsert_chunk_search_index(conn: sqlite3.Connection, chunk: dict, job: dict) -> None:
    if not FTS_ENABLED:
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


def create_chunks_for_job(job_id: str, transcript: dict) -> None:
    if not transcript:
        return

    chunks = chunk_transcript(transcript.get('text', ''), transcript.get('json_raw', None))
    if not chunks:
        return

    created_at = _current_timestamp()
    with DB_LOCK, get_db_connection() as conn:
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
            chunk_id = cursor.lastrowid
            _upsert_chunk_search_index(conn, {
                'chunk_id': chunk_id,
                'text': chunk['text'],
            }, {'job_id': job_id, 'source': source, 'filename': filename})
        conn.commit()


def _compute_hash(text: str | None) -> str | None:
    if not text:
        return None
    h = hashlib.sha256()
    h.update(text.encode('utf-8'))
    return h.hexdigest()


def _db_record_to_job(row: sqlite3.Row) -> dict:
    job = _row_to_dict(row)
    job['transcript'] = {
        'text': job.pop('transcript_text', '') or '',
        'srt': job.pop('transcript_srt', '') or '',
        'vtt': job.pop('transcript_vtt', '') or '',
        'json_raw': job.pop('transcript_json', '') or '',
    }
    return job


def create_db_job(job: dict) -> None:
    with DB_LOCK, get_db_connection() as conn:
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
        })
        conn.commit()


def update_db_job(job_id: str, updates: dict) -> None:
    if not updates:
        return
    updates['updated_at'] = _current_timestamp()
    keys = ', '.join([f"{k} = ?" for k in updates.keys()])
    params = list(updates.values()) + [job_id]
    with DB_LOCK, get_db_connection() as conn:
        conn.execute(f"UPDATE jobs SET {keys} WHERE job_id = ?;", params)
        job = conn.execute("SELECT * FROM jobs WHERE job_id = ?;", (job_id,)).fetchone()
        if job:
            _upsert_search_index(conn, _row_to_dict(job))
        conn.commit()


def fetch_db_job(job_id: str) -> Optional[dict]:
    with DB_LOCK, get_db_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?;", (job_id,)).fetchone()
        if not row:
            return None
        return _db_record_to_job(row)


def list_db_jobs(search: Optional[str] = None, status: Optional[str] = None, source_type: Optional[str] = None, model: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    with DB_LOCK, get_db_connection() as conn:
        where_clauses = []
        params = []

        if search:
            if FTS_ENABLED:
                search_query = ' '.join(search.strip().split())
                where_clauses.append("job_id IN (SELECT job_id FROM jobs_fts WHERE jobs_fts MATCH ?)")
                params.append(search_query)
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


def list_chunks(job_id: Optional[str] = None, search: Optional[str] = None, status: Optional[str] = None, top_k: int = 50, offset: int = 0) -> list[dict]:
    with DB_LOCK, get_db_connection() as conn:
        where_clauses = ["1=1"]
        params: list[Optional[object]] = []

        if job_id:
            where_clauses.append("c.job_id = ?")
            params.append(job_id)
        if status:
            where_clauses.append("j.status = ?")
            params.append(status)

        if search and FTS_ENABLED:
            where_clauses.append("c.chunk_id IN (SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ?)")
            params.append(' '.join(search.strip().split()))
        elif search:
            term = f"%{search}%"
            where_clauses.append("(c.text LIKE ? OR j.source LIKE ? OR j.filename LIKE ?)")
            params.extend([term, term, term])

        where_clause = " AND ".join(where_clauses)
        query = (
            "SELECT c.chunk_id, c.job_id, c.chunk_index, c.start_ts, c.end_ts, c.text, c.embedding_json, j.source_type, j.source, j.filename, j.status AS job_status, j.model, j.language, j.updated_at AS job_updated_at "
            "FROM chunks c "
            "JOIN jobs j ON j.job_id = c.job_id "
            f"WHERE {where_clause} "
            "ORDER BY j.updated_at DESC, c.chunk_index ASC LIMIT ? OFFSET ?;"
        )
        params.extend([top_k, offset])
        rows = conn.execute(query, tuple(params)).fetchall()
        return [dict(row) for row in rows]


def search_chunks(query: str, job_id: Optional[str] = None, status: Optional[str] = None, top_k: int = 20) -> list[dict]:
    candidates = list_chunks(job_id=job_id, search=query, status=status, top_k=max(100, top_k * 5))
    query_embedding = build_embedding(query)
    scored = []

    for row in candidates:
        embedding = []
        if row.get('embedding_json'):
            try:
                embedding = json.loads(row['embedding_json'])
            except Exception:
                embedding = []
        similarity = cosine_similarity(query_embedding, embedding) if embedding else 0.0
        scored.append((similarity, row))

    scored.sort(key=lambda item: item[0], reverse=True)
    results = []
    for score, row in scored[:top_k]:
        results.append({
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
        })
    return results


def persist_job_artifacts(job_id: str, transcript: dict) -> None:
    job_dir = JOB_ARTIFACTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    for ext, key in [('.txt', 'text'), ('.srt', 'srt'), ('.vtt', 'vtt'), ('.json', 'json_raw')]:
        content = transcript.get(key)
        if content:
            (job_dir / f"transcript{ext}").write_text(content, encoding='utf-8')


def _artifact_dir_for(job_id: str) -> Path:
    path = JOB_ARTIFACTS_DIR / job_id / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_artifact_record(job_id: str, artifact_type: str, title: str | None, content: str | None, metadata: dict | None, generation_model: str | None, generation_status: str = 'queued') -> str:
    artifact_id = str(uuid.uuid4())
    ts = _current_timestamp()
    with DB_LOCK, get_db_connection() as conn:
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
                ts,
                ts,
                None,
                metadata.get('source_transcript_hash') if metadata else None,
                0,
                None,
            ),
        )
        conn.commit()
    return artifact_id


def record_artifact_event(artifact_id: str, job_id: str, event_type: str, status: str, detail: dict | None = None) -> None:
    event_id = str(uuid.uuid4())
    ts = _current_timestamp()
    with DB_LOCK, get_db_connection() as conn:
        conn.execute(
            "INSERT INTO artifact_events (event_id, artifact_id, job_id, event_type, status, detail_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?);",
            (event_id, artifact_id, job_id, event_type, status, json.dumps(detail or {}), ts),
        )
        conn.commit()
    # emit a canonical runtime event as well
    try:
        runtime_events.emit_event({
            'job_id': job_id,
            'artifact_id': artifact_id,
            'entity_type': 'artifact',
            'event_type': event_type,
            'source': 'artifact_projection',
            'state_from': None,
            'state_to': status,
            'correlation_id': None,
            'causation_id': None,
            'payload': detail or {},
        })
    except Exception:
        pass


async def broadcast_to_job(job_id: str, message: dict) -> None:
    """Send a JSON message to all connected websockets for a job."""
    conns = WS_CONNECTIONS.get(job_id, [])
    if not conns:
        return
    to_remove: list[WebSocket] = []
    for ws in list(conns):
        try:
            await ws.send_json(message)
        except Exception:
            to_remove.append(ws)
    # cleanup closed sockets
    if to_remove:
        WS_CONNECTIONS[job_id] = [w for w in conns if w not in to_remove]


def update_artifact_record(artifact_id: str, updates: dict) -> None:
    if not updates:
        return
    updates['updated_at'] = _current_timestamp()
    keys = ', '.join([f"{k} = ?" for k in updates.keys()])
    params = list(updates.values()) + [artifact_id]
    with DB_LOCK, get_db_connection() as conn:
        conn.execute(f"UPDATE artifacts SET {keys} WHERE artifact_id = ?;", params)
        conn.commit()


def fetch_artifact_record(artifact_id: str) -> Optional[dict]:
    with DB_LOCK, get_db_connection() as conn:
        row = conn.execute("SELECT * FROM artifacts WHERE artifact_id = ?;", (artifact_id,)).fetchone()
        if not row:
            return None
        result = _row_to_dict(row)
        try:
            result['metadata'] = json.loads(result.get('metadata_json') or '{}')
        except Exception:
            result['metadata'] = {}
        return result


def list_job_artifacts(job_id: str) -> list[dict]:
    with DB_LOCK, get_db_connection() as conn:
        rows = conn.execute("SELECT artifact_id, job_id, artifact_type, title, generation_status, created_at, updated_at FROM artifacts WHERE job_id = ? ORDER BY updated_at DESC;", (job_id,)).fetchall()
        return [dict(r) for r in rows]


def persist_artifact_content(job_id: str, artifact_id: str, content: str, metadata: dict | None = None) -> None:
    art_dir = _artifact_dir_for(job_id)
    path = art_dir / f"{artifact_id}.json"
    payload = {
        'artifact_id': artifact_id,
        'job_id': job_id,
        'content': content,
        'metadata': metadata or {},
        'created_at': _current_timestamp(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')

app = FastAPI(title="TheHand Transcription Server", version="1.0.0")

init_db()


@app.on_event("startup")
async def resume_queued_artifacts():
    """On startup, resume artifact generation for queued or running artifacts."""
    logging.info("Startup: scanning for queued artifacts to resume")
    with DB_LOCK, get_db_connection() as conn:
        rows = conn.execute("SELECT artifact_id, job_id, artifact_type, generation_status FROM artifacts WHERE generation_status IN ('queued', 'running');").fetchall()
        for r in rows:
            rec = dict(r)
            try:
                logging.info(f"Resuming artifact {rec['artifact_id']} (status={rec['generation_status']})")
                asyncio.create_task(generate_artifact_job(rec['artifact_id'], rec['job_id'], rec['artifact_type'], None))
            except Exception:
                logging.exception(f"Failed to resume artifact {rec['artifact_id']}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_whisper_bin() -> str:
    for candidate in [WHISPER_BIN, WHISPER_BIN_FALLBACK]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    raise FileNotFoundError(
        f"whisper-cli not found at {WHISPER_BIN}.\n"
        "Run inside whisper.cpp: cmake --build build -j$(nproc)"
    )


def get_model_path(model_name: str) -> str:
    candidates = [
        Path(MODELS_DIR) / f"ggml-{model_name}.bin",
        Path(MODELS_DIR) / f"{model_name}.bin",
        Path(MODELS_DIR) / f"ggml-{model_name}-q5_1.bin",
        Path(MODELS_DIR) / f"ggml-{model_name}-q8_0.bin",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    raise FileNotFoundError(
        f"Model '{model_name}' not found in {MODELS_DIR}.\n"
        f"Run: bash models/download-ggml-model.sh {model_name}"
    )


def list_available_models() -> list[str]:
    models_path = Path(MODELS_DIR)
    if not models_path.exists():
        return []
    seen = set()
    found = []
    for f in sorted(models_path.glob("ggml-*.bin")):
        name = f.stem.replace("ggml-", "").replace("-q5_1", "").replace("-q8_0", "")
        if name not in seen:
            seen.add(name)
            found.append(name)
    return found


def update_job(job_id: str, **kwargs):
    if job_id in jobs:
        jobs[job_id].update(kwargs)

    db_updates: dict[str, object] = {}
    for key, value in kwargs.items():
        if key == 'transcript' and isinstance(value, dict):
            db_updates['transcript_text'] = value.get('text')
            db_updates['transcript_srt'] = value.get('srt')
            db_updates['transcript_vtt'] = value.get('vtt')
            db_updates['transcript_json'] = value.get('json_raw')
            continue
        db_updates[key] = value

    if db_updates:
        update_db_job(job_id, db_updates)


async def run_postprocessing_pipeline(job_id: str, defaults: list[str] | None = None):
    """Orchestrator for post-transcription artifact generation.

    Creates artifact records (if missing) and schedules background generation tasks.
    """
    logging.info(f"Postprocessing pipeline start for job {job_id}")
    defaults = defaults or ['summary', 'chapter_map']
    job = fetch_db_job(job_id)
    if not job:
        logging.warning(f"Postprocessing: job {job_id} not found")
        return

    transcript_hash = _compute_hash(job.get('transcript', {}).get('text'))
    for art_type in defaults:
        # create artifact record
        title = f"{art_type} for {job_id}"
        artifact_id = create_artifact_record(job_id, art_type, title, '', {'source_transcript_hash': transcript_hash}, generation_model=None, generation_status='queued')
        logging.info(f"Created artifact {artifact_id} ({art_type}) for job {job_id}")
        # schedule generation
        asyncio.create_task(generate_artifact_job(artifact_id, job_id, art_type, None))

    logging.info(f"Postprocessing pipeline scheduled for job {job_id}")

# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def detect_platform(url: str) -> str:
    """Identify the platform from a URL for platform-specific handling."""
    url_lower = url.lower()
    if "tiktok.com" in url_lower:
        return "tiktok"
    if "instagram.com" in url_lower:
        return "instagram"
    if "youtube.com" in url_lower or "youtu.be" in url_lower:
        return "youtube"
    if "twitter.com" in url_lower or "x.com" in url_lower:
        return "twitter"
    return "generic"


def build_ytdlp_cmd(url: str, out_path: str) -> list[str]:
    """Build yt-dlp command with platform-specific options."""
    platform = detect_platform(url)

    base_cmd = [
        "yt-dlp",
        "--no-playlist",
        "--extract-audio",
        "--audio-format", "best",
        "--audio-quality", "0",
        "--no-warnings",
        "--retries", "3",
        "--fragment-retries", "3",
        "-o", out_path,
    ]

    # TikTok: mobile user-agent works best; avoid rate limits
    if platform == "tiktok":
        base_cmd += [
            "--user-agent",
            "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
            "--add-header", "Referer:https://www.tiktok.com/",
        ]

    # Instagram: needs a browser-style referer; optional cookies file
    elif platform == "instagram":
        base_cmd += [
            "--user-agent",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
            "--add-header", "Referer:https://www.instagram.com/",
        ]
        # If user has exported Instagram cookies (see README), use them
        cookies_file = Path.home() / ".thehand" / "instagram-cookies.txt"
        if cookies_file.exists():
            base_cmd += ["--cookies", str(cookies_file)]

    # YouTube: cookies from browser help with age-gated content
    elif platform == "youtube":
        cookies_file = Path.home() / ".thehand" / "youtube-cookies.txt"
        if cookies_file.exists():
            base_cmd += ["--cookies", str(cookies_file)]

    base_cmd.append(url)
    return base_cmd


async def download_audio(url: str, job_id: str) -> Path:
    """Use yt-dlp to download audio from a URL."""
    out_path = TEMP_DIR / job_id / "audio.%(ext)s"
    (TEMP_DIR / job_id).mkdir(parents=True, exist_ok=True)

    update_job(job_id, step="yt-dlp", step_status="running")

    cmd = build_ytdlp_cmd(url, str(out_path))

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        err = stderr.decode()
        # Surface helpful hints for common failures
        if "login" in err.lower() or "private" in err.lower():
            raise RuntimeError(
                f"This content requires login.\n"
                f"Export your cookies (see README) to ~/.thehand/instagram-cookies.txt\n\n{err}"
            )
        if "unavailable" in err.lower() or "removed" in err.lower():
            raise RuntimeError(f"Content unavailable or removed.\n\n{err}")
        raise RuntimeError(f"yt-dlp failed:\n{err}")

    # Find the downloaded file (extension varies)
    for f in (TEMP_DIR / job_id).iterdir():
        if f.stem == "audio":
            update_job(job_id, step="yt-dlp", step_status="done")
            return f

    raise FileNotFoundError("yt-dlp ran but no audio file was produced")


async def convert_to_wav(input_path: Path, job_id: str) -> Path:
    """Convert any audio file to 16kHz mono WAV for whisper."""
    wav_path = TEMP_DIR / job_id / "audio.wav"
    update_job(job_id, step="ffmpeg", step_status="running")

    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(wav_path),
    ]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{stderr.decode()}")

    update_job(job_id, step="ffmpeg", step_status="done")
    return wav_path


async def run_whisper(wav_path: Path, model: str, language: str, job_id: str) -> dict:
    """Run whisper-cli and return transcript in multiple formats."""
    update_job(job_id, step="whisper.cpp", step_status="running")

    whisper_bin = get_whisper_bin()
    model_path = get_model_path(model)
    output_base = str(TEMP_DIR / job_id / "transcript")

    cmd = [
        whisper_bin,
        "-m", model_path,
        "-f", str(wav_path),
        "-otxt",          # plain text
        "-osrt",          # SRT subtitles
        "-ovtt",          # VTT web captions
        "-oj",            # JSON with word timestamps
        "-of", output_base,
        "--print-progress",
    ]

    if language and language != "auto":
        cmd += ["-l", language]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    if proc.returncode != 0:
        raise RuntimeError(f"whisper failed:\n{stderr.decode()}")

    update_job(job_id, step="whisper.cpp", step_status="done")

    # Read all output formats
    result = {}
    for ext, key in [(".txt", "text"), (".srt", "srt"), (".vtt", "vtt"), (".json", "json_raw")]:
        p = Path(output_base + ext)
        if p.exists():
            result[key] = p.read_text(encoding="utf-8")

    return result


def cleanup_job(job_id: str):
    job_dir = TEMP_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)

# ---------------------------------------------------------------------------
# Background task runner
# ---------------------------------------------------------------------------

async def run_transcription_job(job_id: str, url: Optional[str], file_path: Optional[Path],
                                 model: str, language: str):
    """Full pipeline: download (if URL) → ffmpeg → whisper → store result."""
    try:
        update_job(job_id, status="running", progress=0)

        # Step 1 — get audio
        if url:
            audio_path = await download_audio(url, job_id)
        else:
            audio_path = file_path

        update_job(job_id, progress=30)

        # Step 2 — convert to WAV
        wav_path = await convert_to_wav(audio_path, job_id)
        update_job(job_id, progress=55)

        # Step 3 — transcribe
        transcript = await run_whisper(wav_path, model, language, job_id)
        update_job(job_id, progress=95)

        # Persist artifacts, create semantic chunks, and finish
        persist_job_artifacts(job_id, transcript)
        create_chunks_for_job(job_id, transcript)
        # compute transcript hash and persist
        transcript_text = transcript.get('text') if isinstance(transcript, dict) else None
        transcript_hash = _compute_hash(transcript_text)
        update_job(
            job_id,
            status="done",
            progress=100,
            step="output",
            step_status="done",
            transcript=transcript,
            transcript_hash=transcript_hash,
        )
        # kick off autonomous postprocessing pipeline (summary, chapter_map)
        try:
            asyncio.create_task(run_postprocessing_pipeline(job_id))
        except Exception as e:
            logging.exception(f"Failed to start postprocessing for {job_id}: {e}")

    except Exception as exc:
        update_job(job_id, status="error", error=str(exc))
    finally:
        # Clean up temp files (keep job metadata)
        cleanup_job(job_id)


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    """Health check — also validates whisper and model availability."""
    try:
        whisper_ok = bool(get_whisper_bin())
    except FileNotFoundError:
        whisper_ok = False

    return {
        "status": "ok",
        "whisper_ready": whisper_ok,
        "whisper_bin": WHISPER_BIN,
        "models_dir": MODELS_DIR,
        "available_models": list_available_models(),
    }


@app.get("/api/jobs")
async def list_jobs(
    q: Optional[str] = None,
    status: Optional[str] = None,
    source_type: Optional[str] = None,
    model: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List saved jobs and search transcripts."""
    jobs = list_db_jobs(search=q, status=status, source_type=source_type, model=model, limit=limit, offset=offset)
    return {"jobs": jobs}


@app.get("/api/chunks")
async def get_chunks(
    q: Optional[str] = None,
    job_id: Optional[str] = None,
    status: Optional[str] = None,
    top_k: int = 20,
    offset: int = 0,
):
    """Search transcript chunks and return semantic results."""
    if q:
        chunks = search_chunks(q, job_id=job_id, status=status, top_k=top_k)
    else:
        rows = list_chunks(job_id=job_id, status=status, top_k=top_k, offset=offset)
        chunks = [
            {
                'chunk_id': row['chunk_id'],
                'job_id': row['job_id'],
                'chunk_index': row['chunk_index'],
                'start_ts': row['start_ts'],
                'end_ts': row['end_ts'],
                'text': row['text'],
                'score': None,
                'source_type': row['source_type'],
                'source': row['source'],
                'filename': row['filename'],
                'job_status': row['job_status'],
                'model': row['model'],
                'language': row['language'],
                'job_updated_at': row['job_updated_at'],
            }
            for row in rows
        ]
    return {"chunks": chunks}


@app.get("/api/models")
async def get_models():
    """List available Whisper models."""
    return {"models": list_available_models()}


@app.post("/api/transcribe/url")
async def transcribe_url(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    model: str = Form("small"),
    language: str = Form("auto"),
):
    """Start a transcription job from a URL. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    created_at = _current_timestamp()
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "yt-dlp",
        "step_status": "pending",
        "progress": 0,
        "source_type": "url",
        "source": url,
        "model": model,
        "language": language,
        "created_at": created_at,
        "updated_at": created_at,
        "transcript": None,
        "error": None,
    }
    create_db_job(jobs[job_id])
    asyncio.create_task(run_transcription_job(job_id, url, None, model, language))
    return {"job_id": job_id}


@app.post("/api/transcribe/file")
async def transcribe_file(
    file: UploadFile = File(...),
    model: str = Form("small"),
    language: str = Form("auto"),
):
    """Start a transcription job from an uploaded file."""
    job_id = str(uuid.uuid4())
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "audio").suffix or ".audio"
    upload_path = job_dir / f"upload{suffix}"
    with open(upload_path, "wb") as f:
        content = await file.read()
        f.write(content)

    created_at = _current_timestamp()
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "ffmpeg",
        "step_status": "pending",
        "progress": 0,
        "source_type": "file",
        "source": file.filename,
        "filename": file.filename,
        "model": model,
        "language": language,
        "created_at": created_at,
        "updated_at": created_at,
        "transcript": None,
        "error": None,
    }
    create_db_job(jobs[job_id])
    asyncio.create_task(run_transcription_job(job_id, None, upload_path, model, language))
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    """Poll job status and retrieve transcript when done."""
    if job_id in jobs:
        return jobs[job_id]

    saved = fetch_db_job(job_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Job not found")
    return saved


@app.get("/api/job/{job_id}/artifacts")
async def api_list_job_artifacts(job_id: str):
    """List artifacts derived from a job."""
    # validate job exists
    saved = fetch_db_job(job_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Job not found")
    arts = list_job_artifacts(job_id)
    return {"artifacts": arts}


@app.get("/api/runtime/events")
async def api_runtime_events(job_id: Optional[str] = None, limit: int = 200):
    """Fetch canonical runtime events (append-only)."""
    rows = runtime_events.fetch_events(job_id=job_id, limit=limit)
    return {"events": rows}


@app.get("/api/artifact/{artifact_id}/events")
async def api_artifact_events(artifact_id: str, limit: int = 200):
    with DB_LOCK, get_db_connection() as conn:
        rows = conn.execute("SELECT event_id, artifact_id, job_id, event_type, status, detail_json, created_at FROM artifact_events WHERE artifact_id = ? ORDER BY created_at DESC LIMIT ?;", (artifact_id, limit)).fetchall()
        return {"events": [dict(r) for r in rows]}


@app.get("/api/artifact/{artifact_id}")
async def api_get_artifact(artifact_id: str):
    rec = fetch_artifact_record(artifact_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Artifact not found")
    # try to load persisted content file
    job_id = rec.get('job_id')
    art_path = _artifact_dir_for(job_id) / f"{artifact_id}.json"
    content = None
    if art_path.exists():
        try:
            content = json.loads(art_path.read_text(encoding='utf-8'))
        except Exception:
            content = None
    rec['persisted'] = content
    return rec


async def generate_artifact_job(artifact_id: str, job_id: str, artifact_type: str, generation_model: str | None = None):
    """Background generator — mocked heuristics that produce artifact content and persist it."""
    try:
        update_artifact_record(artifact_id, {'generation_status': 'running', 'generation_attempts': 1, 'generation_started_at': _current_timestamp()})
        # emit queued -> running event
        record_artifact_event(artifact_id, job_id, 'artifact_update', 'running', {'stage': 'start'})
        await broadcast_to_job(job_id, {
            'type': 'artifact_update',
            'artifact_id': artifact_id,
            'artifact_type': artifact_type,
            'status': 'running',
            'progress': 10,
        })

        # load transcript and chunks
        job = fetch_db_job(job_id)
        if not job:
            update_artifact_record(artifact_id, {'generation_status': 'error', 'content': ''})
            return

        transcript = job.get('transcript', {})
        # naive summary: first N characters or stitched first 3 chunks
        chunks_rows = []
        with DB_LOCK, get_db_connection() as conn:
            rows = conn.execute("SELECT chunk_index, start_ts, end_ts, text FROM chunks WHERE job_id = ? ORDER BY chunk_index ASC LIMIT 20;", (job_id,)).fetchall()
            chunks_rows = [dict(r) for r in rows]

        if artifact_type == 'summary':
            if chunks_rows:
                # simulate progress
                await broadcast_to_job(job_id, {'type': 'artifact_update','artifact_id': artifact_id,'artifact_type': artifact_type,'status': 'running','progress': 40})
                record_artifact_event(artifact_id, job_id, 'artifact_progress', '40', {'note': 'assembling summary from chunks'})
                summary = '\n\n'.join([c['text'] for c in chunks_rows[:3]])
            else:
                summary = (transcript.get('text') or '')[:1600]
            content = summary.strip()
            metadata = {'method': 'heuristic', 'source': 'chunks' if chunks_rows else 'transcript'}

        elif artifact_type == 'chapter_map':
            chapters = []
            if chunks_rows:
                # simulate progress
                await broadcast_to_job(job_id, {'type': 'artifact_update','artifact_id': artifact_id,'artifact_type': artifact_type,'status': 'running','progress': 35})
                record_artifact_event(artifact_id, job_id, 'artifact_progress', '35', {'note': 'clustering chunks for chapters'})
                # group by every ~5 chunks as simple chapter heuristic
                chunk_group = 5
                for i in range(0, len(chunks_rows), chunk_group):
                    group = chunks_rows[i:i+chunk_group]
                    title = group[0]['text'][:80].strip()
                    start = group[0].get('start_ts')
                    end = group[-1].get('end_ts')
                    chapters.append({'title': title, 'start_ts': start, 'end_ts': end})
            content = json.dumps({'chapters': chapters}, ensure_ascii=False)
            metadata = {'method': 'chunk_grouping', 'group_size': 5}

        elif artifact_type == 'entities':
            text = '\n'.join([c['text'] for c in chunks_rows]) if chunks_rows else (transcript.get('text') or '')
            await broadcast_to_job(job_id, {'type': 'artifact_update','artifact_id': artifact_id,'artifact_type': artifact_type,'status': 'running','progress': 30})
            record_artifact_event(artifact_id, job_id, 'artifact_progress', '30', {'note': 'scanning for entities'})
            # naive entity extraction: capitalized words frequency
            import re
            words = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
            freq = {}
            for w in words:
                freq[w] = freq.get(w, 0) + 1
            entities = sorted([{'entity': k, 'count': v} for k, v in freq.items()], key=lambda x: -x['count'])[:60]
            content = json.dumps({'entities': entities}, ensure_ascii=False)
            metadata = {'method': 'heuristic-capitalized-words'}

        elif artifact_type == 'topics':
            text = '\n'.join([c['text'] for c in chunks_rows]) if chunks_rows else (transcript.get('text') or '')
            await broadcast_to_job(job_id, {'type': 'artifact_update','artifact_id': artifact_id,'artifact_type': artifact_type,'status': 'running','progress': 30})
            record_artifact_event(artifact_id, job_id, 'artifact_progress', '30', {'note': 'extracting topic words'})
            # naive topic extraction: top words excluding stopwords
            stop = set(['the','and','for','with','that','this','have','from','are','was','were','what','which','when','where','you','your','will','shall','but','not','can','have','has'])
            import re
            words = [w.lower() for w in re.findall(r"\b([A-Za-z]{3,})\b", text)]
            freq = {}
            for w in words:
                if w in stop: continue
                freq[w] = freq.get(w, 0) + 1
            topics = sorted([{'topic': k, 'count': v} for k, v in freq.items()], key=lambda x: -x['count'])[:40]
            content = json.dumps({'topics': topics}, ensure_ascii=False)
            metadata = {'method': 'heuristic-top-words'}

        elif artifact_type == 'quotes':
            text = '\n'.join([c['text'] for c in chunks_rows]) if chunks_rows else (transcript.get('text') or '')
            await broadcast_to_job(job_id, {'type': 'artifact_update','artifact_id': artifact_id,'artifact_type': artifact_type,'status': 'running','progress': 30})
            record_artifact_event(artifact_id, job_id, 'artifact_progress', '30', {'note': 'finding quotes'})
            import re
            quotes = re.findall(r'"([^"]{20,200})"', text)
            quotes = quotes[:80]
            content = json.dumps({'quotes': quotes}, ensure_ascii=False)
            metadata = {'method': 'heuristic-quote-extract'}

        else:
            content = f"Unsupported artifact type: {artifact_type}"
            metadata = {'method': 'none'}

        # persist (simulate finalizing)
        await broadcast_to_job(job_id, {'type': 'artifact_update','artifact_id': artifact_id,'artifact_type': artifact_type,'status': 'persisting','progress': 90})
        record_artifact_event(artifact_id, job_id, 'artifact_progress', '90', {'note': 'persisting artifact'})
        start_ts = datetime.utcnow()
        persist_artifact_content(job_id, artifact_id, content, metadata)
        # update artifact record and add a version
        update_artifact_record(artifact_id, {'generation_status': 'done', 'content': content, 'metadata_json': json.dumps(metadata), 'generation_completed_at': _current_timestamp()})
        duration_ms = int((datetime.utcnow() - start_ts).total_seconds() * 1000)
        with DB_LOCK, get_db_connection() as conn:
            conn.execute("INSERT INTO artifact_versions (artifact_id, version_number, content, metadata_json, created_at) VALUES (?, ?, ?, ?, ?);", (artifact_id, 1, content, json.dumps(metadata), _current_timestamp()))
            conn.execute("UPDATE artifacts SET generation_attempts = generation_attempts + 1 WHERE artifact_id = ?;", (artifact_id,))
            conn.commit()
        logging.info(f"Artifact {artifact_id} generated in {duration_ms}ms")
        # broadcast completion
        record_artifact_event(artifact_id, job_id, 'artifact_complete', 'done', {'duration_ms': duration_ms})
        await broadcast_to_job(job_id, {'type': 'artifact_complete','artifact_id': artifact_id,'artifact_type': artifact_type,'status': 'done','progress': 100})

    except Exception as exc:
        update_artifact_record(artifact_id, {'generation_status': 'error', 'generation_error': str(exc), 'content': ''})
        logging.exception(f"Artifact generation failed for {artifact_id}: {exc}")


@app.post("/api/job/{job_id}/generate/{artifact_type}")
async def api_generate_artifact(job_id: str, artifact_type: str, generation_model: Optional[str] = None):
    """Trigger generation of an artifact for a job. Returns artifact_id immediately."""
    saved = fetch_db_job(job_id)
    if not saved:
        raise HTTPException(status_code=404, detail="Job not found")
    # create artifact record
    title = f"{artifact_type} for {job_id}" 
    artifact_id = create_artifact_record(job_id, artifact_type, title, '', None, generation_model, generation_status='queued')
    # start background task
    asyncio.create_task(generate_artifact_job(artifact_id, job_id, artifact_type, generation_model))
    return {"artifact_id": artifact_id}


@app.get("/api/job/{job_id}/download/{fmt}")
async def download_transcript(job_id: str, fmt: str):
    """Download transcript in a specific format: text, srt, vtt, json."""
    if job_id in jobs:
        job = jobs[job_id]
    else:
        job = fetch_db_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "done":
        raise HTTPException(status_code=400, detail="Job not complete yet")

    transcript = job.get("transcript", {})
    format_map = {
        "text": ("text", "transcript.txt", "text/plain"),
        "srt": ("srt", "transcript.srt", "text/plain"),
        "vtt": ("vtt", "transcript.vtt", "text/vtt"),
        "json": ("json_raw", "transcript.json", "application/json"),
    }

    if fmt not in format_map:
        raise HTTPException(status_code=400, detail=f"Unknown format '{fmt}'. Use: text, srt, vtt, json")

    key, filename, media_type = format_map[fmt]
    content = transcript.get(key, "")
    if not content:
        raise HTTPException(status_code=404, detail=f"Format '{fmt}' not available for this job")

    return PlainTextResponse(content, media_type=media_type, headers={
        "Content-Disposition": f'attachment; filename="{filename}"'
    })

# ---------------------------------------------------------------------------
# WebSocket — real-time progress streaming
# ---------------------------------------------------------------------------

@app.websocket("/ws/job/{job_id}")
async def job_progress_ws(websocket: WebSocket, job_id: str):
    """
    Connect to get real-time job updates pushed over WebSocket.
    Sends JSON messages: {"status", "step", "progress", "transcript", "error"}
    Closes automatically when job is done or errors.
    """
    await websocket.accept()
    # register websocket
    WS_CONNECTIONS.setdefault(job_id, []).append(websocket)
    try:
        while True:
            if job_id not in jobs:
                await websocket.send_json({"error": "job not found"})
                break

            job = jobs[job_id]
            await websocket.send_json({
                "id": job["id"],
                "status": job["status"],
                "step": job.get("step"),
                "step_status": job.get("step_status"),
                "progress": job.get("progress", 0),
                "error": job.get("error"),
                "transcript": job.get("transcript") if job["status"] == "done" else None,
            })

            if job["status"] in ("done", "error"):
                break

            await asyncio.sleep(0.5)

    except WebSocketDisconnect:
        pass
    finally:
        # remove websocket from registry
        try:
            WS_CONNECTIONS[job_id] = [w for w in WS_CONNECTIONS.get(job_id, []) if w is not websocket]
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Serve built frontend (must be last — catch-all SPA routing)
# ---------------------------------------------------------------------------

frontend_path = Path(FRONTEND_DIR)

if frontend_path.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_path / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # For API routes that fell through (shouldn't happen, but safeguard)
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404)
        index = frontend_path / "index.html"
        if index.exists():
            return FileResponse(str(index))
        return JSONResponse(
            {"message": "TheHand server is running. Build the frontend and place dist/ next to main.py."},
            status_code=200,
        )
else:
    @app.get("/")
    async def no_frontend():
        return JSONResponse({
            "message": "TheHand API is running. Frontend not found.",
            "hint": "Run `npm run build` in the TheHand repo and copy dist/ next to main.py",
            "api_docs": "/docs",
        })


# ---------------------------------------------------------------------------
# Entry point (for running directly: python main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
