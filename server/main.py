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

import json
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
import hashlib
import logging

from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
from api.routes.frontend import register_frontend_routes
from api.routes.runtime import RuntimeRouteDeps, create_runtime_router
from api.websocket.jobs import register_job_websocket_routes
from runtime import events as runtime_events
from runtime import store as runtime_store
from runtime.generators import generate_artifact_content
from runtime.orchestration import default_artifact_types, enqueue_background_task, runtime_queue_snapshot
from runtime.execution.media import LocalMediaExecutionProvider, MediaExecutionConfig
from runtime.persistence.transcripts import TranscriptArtifactStore
from runtime.repositories import artifacts as artifacts_repo
from runtime.repositories import chunks as chunks_repo
from runtime.repositories import jobs as jobs_repo
from runtime.schema import (
    ENTITY_ARTIFACT,
    ENTITY_JOB,
    EVENT_CATEGORY_ARTIFACT,
    create_event,
    legacy_websocket_message,
    websocket_event,
)
from runtime.state import create_queued_job
from runtime.state import JOB_TERMINAL_STATUSES
from runtime.state_machine import transition_state
from runtime.transport import JobWebSocketTransport
from runtime import recovery as runtime_recovery
from runtime.jobs.registry import SQLiteJobRegistry

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

WHISPER_BIN = os.environ.get(
    "WHISPER_BIN",
    os.environ.get(
        "THEHAND_WHISPER_BIN",
        str(Path.home() / "whisper.cpp" / "build" / "bin" / "whisper-cli"),
    ),
)
WHISPER_BIN_FALLBACK = str(Path.home() / "whisper.cpp" / "build" / "bin" / "main")

MODELS_DIR = os.environ.get(
    "MODELS_DIR",
    os.environ.get(
        "THEHAND_MODELS_DIR",
        str(Path.home() / "whisper.cpp" / "models"),
    ),
)

FRONTEND_DIR = os.environ.get(
    "FRONTEND_DIR",
    str(Path(__file__).parent.parent / "app" / "dist"),
)

TEMP_DIR = Path(tempfile.gettempdir()) / "thehand"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

media_execution = LocalMediaExecutionProvider(
    MediaExecutionConfig(
        whisper_bin=WHISPER_BIN,
        whisper_bin_fallback=WHISPER_BIN_FALLBACK,
        models_dir=MODELS_DIR,
        temp_dir=TEMP_DIR,
        cache_dir=runtime_store.DATA_DIR / "huggingface",
    )
)
transcript_artifact_store = TranscriptArtifactStore(runtime_store.JOB_ARTIFACTS_DIR)

# Persistent storage and artifacts
DATA_DIR = runtime_store.DATA_DIR
FTS_ENABLED = False

job_registry = SQLiteJobRegistry()
# WebSocket transport for pushing real-time job and artifact events
job_transport = JobWebSocketTransport()
RECOVERY_REPORT: dict = {}

# ---------------------------------------------------------------------------
# Persistence helpers
# ---------------------------------------------------------------------------

def _current_timestamp() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + 'Z'


def init_db() -> None:
    global FTS_ENABLED
    FTS_ENABLED = runtime_store.init_schema()
    try:
        runtime_events.init_runtime_events_table()
    except Exception:
        pass

    global RECOVERY_REPORT
    RECOVERY_REPORT = runtime_recovery.recover_interrupted_runtime(_current_timestamp())


def create_chunks_for_job(job_id: str, transcript: dict) -> None:
    chunks_repo.create_chunks_for_job(job_id, transcript, _current_timestamp(), FTS_ENABLED)


def _compute_hash(text: str | None) -> str | None:
    if not text:
        return None
    h = hashlib.sha256()
    h.update(text.encode('utf-8'))
    return h.hexdigest()


def create_db_job(job: dict) -> None:
    jobs_repo.create_job(job, FTS_ENABLED)
    transition_state(
        entity_type=ENTITY_JOB,
        entity_id=job['id'],
        current_state=None,
        next_state=job.get('status') or 'queued',
        reason='job created',
        source='api',
        actor='runtime',
        payload={
            'source_type': job.get('source_type'),
            'model': job.get('model'),
            'language': job.get('language'),
        },
    )


def update_db_job(job_id: str, updates: dict) -> None:
    if not updates:
        return
    updates['updated_at'] = _current_timestamp()
    jobs_repo.update_job(job_id, updates, FTS_ENABLED)


def fetch_db_job(job_id: str) -> Optional[dict]:
    return jobs_repo.fetch_job(job_id)


def list_db_jobs(search: Optional[str] = None, status: Optional[str] = None, source_type: Optional[str] = None, model: Optional[str] = None, limit: int = 50, offset: int = 0) -> list[dict]:
    return jobs_repo.list_jobs(search, status, source_type, model, limit, offset, FTS_ENABLED)


def list_chunks(job_id: Optional[str] = None, search: Optional[str] = None, status: Optional[str] = None, top_k: int = 50, offset: int = 0) -> list[dict]:
    return chunks_repo.list_chunks(job_id, search, status, top_k, offset, FTS_ENABLED)


def search_chunks(query: str, job_id: Optional[str] = None, status: Optional[str] = None, top_k: int = 20) -> list[dict]:
    return chunks_repo.search_chunks(query, job_id, status, top_k, FTS_ENABLED)
def persist_job_artifacts(job_id: str, transcript: dict) -> None:
    transcript_artifact_store.persist_transcript_formats(job_id, transcript)


def create_artifact_record(job_id: str, artifact_type: str, title: str | None, content: str | None, metadata: dict | None, generation_model: str | None, generation_status: str = 'queued') -> str:
    ts = _current_timestamp()
    artifact_id = artifacts_repo.create_artifact(
        job_id,
        artifact_type,
        title,
        content,
        metadata,
        generation_model,
        generation_status,
        ts,
    )
    transition_state(
        entity_type=ENTITY_ARTIFACT,
        entity_id=artifact_id,
        current_state=None,
        next_state=generation_status,
        reason='artifact created',
        source='api',
        actor='runtime',
        payload={'job_id': job_id, 'artifact_type': artifact_type},
    )
    return artifact_id


def record_artifact_event(artifact_id: str, job_id: str, event_type: str, status: str, detail: dict | None = None) -> dict | None:
    event_id = str(uuid.uuid4())
    ts = _current_timestamp()
    artifacts_repo.record_artifact_event(event_id, artifact_id, job_id, event_type, status, detail, ts)
    # emit a canonical runtime event as well
    try:
        return runtime_events.emit_event(create_event(
            job_id=job_id,
            artifact_id=artifact_id,
            entity_type=ENTITY_ARTIFACT,
            entity_id=artifact_id,
            event_type=event_type,
            event_category=EVENT_CATEGORY_ARTIFACT,
            source='artifact_projection',
            state_to=status,
            payload=detail or {},
        ))
    except Exception:
        pass
    return None


async def broadcast_to_job(job_id: str, message: dict) -> None:
    """Send a JSON message to all connected websockets for a job."""
    event = runtime_events.emit_event(websocket_event(job_id, message))
    await job_transport.broadcast(job_id, legacy_websocket_message(event, message))


def update_artifact_record(artifact_id: str, updates: dict) -> None:
    if not updates:
        return
    updates = dict(updates)
    transition_reason = updates.pop('_transition_reason', 'artifact status update')
    transition_source = updates.pop('_transition_source', 'runtime')
    transition_actor = updates.pop('_transition_actor', 'runtime')
    if not updates:
        return
    updates['updated_at'] = _current_timestamp()
    if 'generation_status' in updates:
        row = artifacts_repo.generation_status(artifact_id)
        if row:
            transition_state(
                entity_type=ENTITY_ARTIFACT,
                entity_id=artifact_id,
                current_state=row['generation_status'],
                next_state=updates['generation_status'],
                reason=transition_reason,
                source=transition_source,
                actor=transition_actor,
                payload={'job_id': row['job_id']},
            )
    artifacts_repo.update_artifact(artifact_id, updates)


def fetch_artifact_record(artifact_id: str) -> Optional[dict]:
    return artifacts_repo.fetch_artifact(artifact_id)


def list_job_artifacts(job_id: str) -> list[dict]:
    return artifacts_repo.list_job_artifacts(job_id)


def persist_artifact_content(job_id: str, artifact_id: str, content: str, metadata: dict | None = None) -> None:
    artifacts_repo.persist_artifact_content(job_id, artifact_id, content, metadata, _current_timestamp())


async def generate_artifact_job(
    artifact_id: str,
    job_id: str,
    artifact_type: str,
    generation_model: Optional[str] = None,
) -> None:
    try:
        update_artifact_record(
            artifact_id,
            {
                "generation_status": "running",
                "generation_model": generation_model,
                "generation_started_at": _current_timestamp(),
                "_transition_reason": "artifact generation started",
                "_transition_source": "artifact_generator",
            },
        )
        await broadcast_to_job(
            job_id,
            {
                "type": "artifact_update",
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "status": "running",
                "progress": 10,
            },
        )
        record_artifact_event(artifact_id, job_id, "artifact_started", "running", {"artifact_type": artifact_type})

        job = fetch_db_job(job_id)
        if not job:
            raise RuntimeError(f"Job {job_id} not found")
        transcript = job.get("transcript") or {}
        chunks = chunks_repo.list_chunks(
            job_id=job_id,
            search=None,
            status=None,
            top_k=500,
            offset=0,
            fts_enabled=FTS_ENABLED,
        )

        async def emit_progress(progress: int, note: str) -> None:
            await broadcast_to_job(
                job_id,
                {
                    "type": "artifact_update",
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "status": "running",
                    "progress": progress,
                },
            )
            record_artifact_event(artifact_id, job_id, "artifact_progress", str(progress), {"note": note})

        content, metadata = await generate_artifact_content(artifact_type, transcript, chunks, emit_progress)
        update_artifact_record(
            artifact_id,
            {
                "generation_status": "persisting",
                "_transition_reason": "persisting artifact content",
                "_transition_source": "artifact_generator",
            },
        )
        await broadcast_to_job(
            job_id,
            {
                "type": "artifact_update",
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "status": "persisting",
                "progress": 90,
            },
        )
        persist_artifact_content(job_id, artifact_id, content, metadata)
        update_artifact_record(
            artifact_id,
            {
                "content": content,
                "metadata_json": json.dumps(metadata or {}, ensure_ascii=False),
                "generation_status": "done",
                "generation_completed_at": _current_timestamp(),
                "_transition_reason": "artifact generation completed",
                "_transition_source": "artifact_generator",
            },
        )
        record_artifact_event(artifact_id, job_id, "artifact_completed", "done", {"artifact_type": artifact_type})
        await broadcast_to_job(
            job_id,
            {
                "type": "artifact_update",
                "artifact_id": artifact_id,
                "artifact_type": artifact_type,
                "status": "done",
                "progress": 100,
            },
        )
    except Exception as exc:
        logging.exception("Artifact generation failed for %s", artifact_id)
        try:
            update_artifact_record(
                artifact_id,
                {
                    "generation_status": "error",
                    "generation_error": str(exc),
                    "generation_completed_at": _current_timestamp(),
                    "_transition_reason": "artifact generation failed",
                    "_transition_source": "artifact_generator",
                },
            )
            record_artifact_event(artifact_id, job_id, "artifact_failed", "error", {"error": str(exc)})
            await broadcast_to_job(
                job_id,
                {
                    "type": "artifact_update",
                    "artifact_id": artifact_id,
                    "artifact_type": artifact_type,
                    "status": "error",
                    "error": str(exc),
                },
            )
        except Exception:
            logging.exception("Failed to persist artifact error for %s", artifact_id)


app = FastAPI(title="TheHand Transcription Server", version="1.0.0")

init_db()


async def resume_queued_artifacts():
    """On startup, resume artifact generation for queued or running artifacts."""
    logging.info("Startup: scanning for queued artifacts to resume")
    for rec in artifacts_repo.artifacts_for_resume():
        try:
            logging.info(f"Resuming artifact {rec['artifact_id']} (status={rec['generation_status']})")
            enqueue_background_task(generate_artifact_job(rec['artifact_id'], rec['job_id'], rec['artifact_type'], None))
        except Exception:
            logging.exception(f"Failed to resume artifact {rec['artifact_id']}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.router.add_event_handler("startup", resume_queued_artifacts)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_whisper_bin() -> str:
    return media_execution.get_whisper_bin()


def get_model_path(model_name: str) -> str:
    return media_execution.get_model_path(model_name)


def list_available_models() -> list[str]:
    return media_execution.list_available_models()


def runtime_diagnostics() -> dict:
    diagnostics: dict = {
        "yt_dlp_ready": False,
        "yt_dlp_command": None,
        "ffmpeg_ready": False,
        "ffmpeg_bin": None,
        "whisper_ready": False,
        "faster_whisper_ready": media_execution.has_faster_whisper(),
        "whisper_error": None,
        "models_ready": False,
        "available_models": [],
    }
    try:
        diagnostics["yt_dlp_command"] = media_execution.build_ytdlp_executable()
        diagnostics["yt_dlp_ready"] = True
    except Exception as exc:
        diagnostics["yt_dlp_error"] = str(exc)
    try:
        diagnostics["ffmpeg_bin"] = media_execution.get_ffmpeg_bin()
        diagnostics["ffmpeg_ready"] = True
    except Exception as exc:
        diagnostics["ffmpeg_error"] = str(exc)
    try:
        diagnostics["whisper_bin"] = media_execution.get_whisper_bin()
        diagnostics["whisper_ready"] = True
    except Exception as exc:
        diagnostics["whisper_error"] = str(exc)
        diagnostics["whisper_engine"] = "faster-whisper" if diagnostics["faster_whisper_ready"] else "unavailable"
    else:
        diagnostics["whisper_engine"] = "whisper.cpp"
    models = media_execution.list_available_models()
    diagnostics["available_models"] = models
    diagnostics["models_ready"] = bool(models)
    return diagnostics


def update_job(job_id: str, **kwargs):
    transition_reason = kwargs.pop('_transition_reason', 'job status update')
    transition_source = kwargs.pop('_transition_source', 'runtime')
    transition_actor = kwargs.pop('_transition_actor', 'runtime')
    if 'status' in kwargs:
        current_state = None
        active = job_registry.get_active_snapshot(job_id)
        if active:
            current_state = active.get('status')
        else:
            saved = fetch_db_job(job_id)
            if saved:
                current_state = saved.get('status')
        transition_state(
            entity_type=ENTITY_JOB,
            entity_id=job_id,
            current_state=current_state,
            next_state=kwargs['status'],
            reason=transition_reason,
            source=transition_source,
            actor=transition_actor,
            payload={'updated_fields': sorted(kwargs.keys())},
        )

    updated_snapshot = job_registry.update_job(job_id, kwargs)
    if kwargs.get("status") in JOB_TERMINAL_STATUSES and updated_snapshot:
        job_registry.mark_terminal(job_id)

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
    defaults = default_artifact_types(defaults)
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
        enqueue_background_task(generate_artifact_job(artifact_id, job_id, art_type, None))

    logging.info(f"Postprocessing pipeline scheduled for job {job_id}")

# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

def detect_platform(url: str) -> str:
    return media_execution.detect_platform(url)


def build_ytdlp_cmd(url: str, out_path: str) -> list[str]:
    return media_execution.build_ytdlp_cmd(url, out_path)


async def download_audio(url: str, job_id: str) -> Path:
    return await media_execution.download_audio(
        url,
        job_id,
        lambda step, status: update_job(job_id, step=step, step_status=status),
    )


async def convert_to_wav(input_path: Path, job_id: str) -> Path:
    return await media_execution.convert_to_wav(
        input_path,
        job_id,
        lambda step, status: update_job(job_id, step=step, step_status=status),
    )


async def run_whisper(wav_path: Path, model: str, language: str, job_id: str) -> dict:
    return await media_execution.run_whisper(
        wav_path,
        model,
        language,
        job_id,
        lambda step, status: update_job(job_id, step=step, step_status=status),
    )


def cleanup_job(job_id: str):
    media_execution.cleanup_job(job_id)

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
            enqueue_background_task(run_postprocessing_pipeline(job_id))
        except Exception as e:
            logging.exception(f"Failed to start postprocessing for {job_id}: {e}")

    except Exception as exc:
        current = job_registry.get_active_snapshot(job_id) or fetch_db_job(job_id) or {}
        if current.get("status") in JOB_TERMINAL_STATUSES:
            logging.exception("Post-terminal job error for %s: %s", job_id, exc)
        else:
            update_job(job_id, status="error", error=str(exc))
    finally:
        # Clean up temp files (keep job metadata)
        cleanup_job(job_id)


# ---------------------------------------------------------------------------
# API adapter service functions
# ---------------------------------------------------------------------------


def start_url_transcription(url: str, model: str, language: str) -> dict:
    job_id = str(uuid.uuid4())
    created_at = _current_timestamp()
    job = create_queued_job(
        job_id,
        source_type="url",
        source=url,
        model=model,
        language=language,
        created_at=created_at,
        step="yt-dlp",
    )
    job_registry.create_job(job)
    create_db_job(job)
    enqueue_background_task(run_transcription_job(job_id, url, None, model, language))
    return {"job_id": job_id}


def start_file_transcription(filename: str | None, content: bytes, model: str, language: str) -> dict:
    job_id = str(uuid.uuid4())
    job_dir = TEMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(filename or "audio").suffix or ".audio"
    upload_path = job_dir / f"upload{suffix}"
    upload_path.write_bytes(content)

    created_at = _current_timestamp()
    job = create_queued_job(
        job_id,
        source_type="file",
        source=filename,
        filename=filename,
        model=model,
        language=language,
        created_at=created_at,
        step="ffmpeg",
    )
    job_registry.create_job(job)
    create_db_job(job)
    enqueue_background_task(run_transcription_job(job_id, None, upload_path, model, language))
    return {"job_id": job_id}


def get_job_for_api(job_id: str) -> dict | None:
    return job_registry.get_active_snapshot(job_id) or fetch_db_job(job_id)


def get_artifact_for_api(artifact_id: str) -> dict | None:
    artifact = fetch_artifact_record(artifact_id)
    if not artifact:
        return None
    job_id = artifact.get('job_id')
    artifact['persisted'] = artifacts_repo.load_persisted_artifact(job_id, artifact_id)
    return artifact


def generate_artifact_for_api(job_id: str, artifact_type: str, generation_model: Optional[str] = None) -> str | None:
    if not fetch_db_job(job_id):
        return None
    title = f"{artifact_type} for {job_id}"
    artifact_id = create_artifact_record(job_id, artifact_type, title, '', None, generation_model, generation_status='queued')
    enqueue_background_task(generate_artifact_job(artifact_id, job_id, artifact_type, generation_model))
    return artifact_id


def download_transcript_payload(job_id: str, fmt: str) -> tuple[str, str, str] | None:
    job = get_job_for_api(job_id)
    if not job or job.get("status") != "done":
        return None

    transcript = job.get("transcript", {})
    format_map = {
        "text": ("text", "transcript.txt", "text/plain"),
        "srt": ("srt", "transcript.srt", "text/plain"),
        "vtt": ("vtt", "transcript.vtt", "text/vtt"),
        "json": ("json_raw", "transcript.json", "application/json"),
    }
    key, filename, media_type = format_map[fmt]
    content = transcript.get(key, "")
    if not content:
        return None
    return content, filename, media_type


app.include_router(create_runtime_router(RuntimeRouteDeps(
    whisper_bin=WHISPER_BIN,
    models_dir=MODELS_DIR,
    get_whisper_bin=get_whisper_bin,
    runtime_diagnostics=runtime_diagnostics,
    list_available_models=list_available_models,
    list_db_jobs=list_db_jobs,
    search_chunks=search_chunks,
    list_chunks=list_chunks,
    start_url_transcription=start_url_transcription,
    start_file_transcription=start_file_transcription,
    get_job=get_job_for_api,
    list_job_artifacts=list_job_artifacts,
    fetch_runtime_events=runtime_events.fetch_events,
    runtime_queue_snapshot=runtime_queue_snapshot,
    recovery_report=lambda: RECOVERY_REPORT,
    fetch_entity_timeline=runtime_events.fetch_entity_timeline,
    list_artifact_events=artifacts_repo.list_artifact_events,
    get_artifact=get_artifact_for_api,
    generate_artifact=generate_artifact_for_api,
    download_transcript_payload=download_transcript_payload,
)))

register_job_websocket_routes(app, job_registry, job_transport)
register_frontend_routes(app, FRONTEND_DIR)


# ---------------------------------------------------------------------------
# Entry point (for running directly: python main.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8080, reload=False)
