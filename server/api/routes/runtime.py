from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import PlainTextResponse


@dataclass(frozen=True)
class RuntimeRouteDeps:
    whisper_bin: str
    models_dir: str
    get_whisper_bin: Callable[[], str]
    runtime_diagnostics: Callable[[], dict]
    list_available_models: Callable[[], list[str]]
    list_db_jobs: Callable[..., list[dict]]
    search_chunks: Callable[..., list[dict]]
    list_chunks: Callable[..., list[dict]]
    start_url_transcription: Callable[[str, str, str], dict]
    start_file_transcription: Callable[[str | None, bytes, str, str], dict]
    get_job: Callable[[str], dict | None]
    list_job_artifacts: Callable[[str], list[dict]]
    fetch_runtime_events: Callable[..., list[dict]]
    runtime_queue_snapshot: Callable[[], dict]
    recovery_report: Callable[[], dict]
    fetch_entity_timeline: Callable[[str, int], list[dict]]
    list_artifact_events: Callable[[str, int], list[dict]]
    get_artifact: Callable[[str], dict | None]
    generate_artifact: Callable[[str, str, Optional[str]], str | None]
    download_transcript_payload: Callable[[str, str], tuple[str, str, str] | None]


def create_runtime_router(deps: RuntimeRouteDeps) -> APIRouter:
    router = APIRouter()

    @router.get("/api/health")
    async def health():
        try:
            whisper_ok = bool(deps.get_whisper_bin())
        except FileNotFoundError:
            whisper_ok = False

        return {
            "status": "ok",
            "whisper_ready": whisper_ok,
            "whisper_bin": deps.whisper_bin,
            "models_dir": deps.models_dir,
            "available_models": deps.list_available_models(),
            "runtime": deps.runtime_diagnostics(),
        }

    @router.get("/api/jobs")
    async def list_jobs(
        q: Optional[str] = None,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        model: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ):
        jobs = deps.list_db_jobs(search=q, status=status, source_type=source_type, model=model, limit=limit, offset=offset)
        return {"jobs": jobs}

    @router.get("/api/chunks")
    async def get_chunks(
        q: Optional[str] = None,
        job_id: Optional[str] = None,
        status: Optional[str] = None,
        top_k: int = 20,
        offset: int = 0,
    ):
        if q:
            chunks = deps.search_chunks(q, job_id=job_id, status=status, top_k=top_k)
        else:
            rows = deps.list_chunks(job_id=job_id, status=status, top_k=top_k, offset=offset)
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

    @router.get("/api/models")
    async def get_models():
        return {"models": deps.list_available_models()}

    @router.post("/api/transcribe/url")
    async def transcribe_url(
        background_tasks: BackgroundTasks,
        url: str = Form(...),
        model: str = Form("small"),
        language: str = Form("auto"),
    ):
        return deps.start_url_transcription(url, model, language)

    @router.post("/api/transcribe/file")
    async def transcribe_file(
        file: UploadFile = File(...),
        model: str = Form("small"),
        language: str = Form("auto"),
    ):
        content = await file.read()
        return deps.start_file_transcription(file.filename, content, model, language)

    @router.get("/api/job/{job_id}")
    async def get_job_status(job_id: str):
        job = deps.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @router.get("/api/job/{job_id}/artifacts")
    async def api_list_job_artifacts(job_id: str):
        if not deps.get_job(job_id):
            raise HTTPException(status_code=404, detail="Job not found")
        return {"artifacts": deps.list_job_artifacts(job_id)}

    @router.get("/api/runtime/events")
    async def api_runtime_events(job_id: Optional[str] = None, limit: int = 200):
        return {"events": deps.fetch_runtime_events(job_id=job_id, limit=limit)}

    @router.get("/api/runtime/status")
    async def api_runtime_status():
        queue = deps.runtime_queue_snapshot()
        return {
            "status": "ok",
            "queue_depth": queue.get("queue_depth", 0),
            "active_tasks": queue.get("active_tasks", []),
            "active_count": queue.get("active_count", 0),
            "recent_failures": queue.get("recent_failures", []),
            "recovery": deps.recovery_report(),
        }

    @router.get("/api/runtime/queues")
    async def api_runtime_queues():
        return deps.runtime_queue_snapshot()

    @router.get("/api/runtime/events/recent")
    async def api_runtime_events_recent(limit: int = 100):
        return {"events": deps.fetch_runtime_events(limit=limit)}

    @router.get("/api/runtime/entity/{entity_id}/timeline")
    async def api_runtime_entity_timeline(entity_id: str, limit: int = 200):
        return {"events": deps.fetch_entity_timeline(entity_id, limit=limit)}

    @router.get("/api/artifact/{artifact_id}/events")
    async def api_artifact_events(artifact_id: str, limit: int = 200):
        return {"events": deps.list_artifact_events(artifact_id, limit)}

    @router.get("/api/artifact/{artifact_id}")
    async def api_get_artifact(artifact_id: str):
        artifact = deps.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(status_code=404, detail="Artifact not found")
        return artifact

    @router.post("/api/job/{job_id}/generate/{artifact_type}")
    async def api_generate_artifact(job_id: str, artifact_type: str, generation_model: Optional[str] = None):
        artifact_id = deps.generate_artifact(job_id, artifact_type, generation_model)
        if not artifact_id:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"artifact_id": artifact_id}

    @router.get("/api/job/{job_id}/download/{fmt}")
    async def download_transcript(job_id: str, fmt: str):
        if fmt not in {"text", "srt", "vtt", "json"}:
            raise HTTPException(status_code=400, detail=f"Unknown format '{fmt}'. Use: text, srt, vtt, json")
        payload = deps.download_transcript_payload(job_id, fmt)
        if not payload:
            job = deps.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            if job.get("status") != "done":
                raise HTTPException(status_code=400, detail="Job not complete yet")
            raise HTTPException(status_code=404, detail=f"Format '{fmt}' not available for this job")
        content, filename, media_type = payload
        return PlainTextResponse(content, media_type=media_type, headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        })

    return router
