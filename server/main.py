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
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
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

# In-memory job store
jobs: dict[str, dict] = {}

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="TheHand Transcription Server", version="1.0.0")

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

        # Done
        update_job(
            job_id,
            status="done",
            progress=100,
            step="output",
            step_status="done",
            transcript=transcript,
        )

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
    except FileNotFoundError as e:
        whisper_ok = False

    return {
        "status": "ok",
        "whisper_ready": whisper_ok,
        "whisper_bin": WHISPER_BIN,
        "models_dir": MODELS_DIR,
        "available_models": list_available_models(),
    }


@app.get("/api/models")
async def get_models():
    """List available Whisper models."""
    return {"models": list_available_models()}


@app.post("/api/transcribe/url")
async def transcribe_url(
    background_tasks,
    url: str = Form(...),
    model: str = Form("small"),
    language: str = Form("auto"),
):
    """Start a transcription job from a URL. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "yt-dlp",
        "step_status": "pending",
        "progress": 0,
        "url": url,
        "model": model,
        "language": language,
        "transcript": None,
        "error": None,
    }
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

    jobs[job_id] = {
        "id": job_id,
        "status": "queued",
        "step": "ffmpeg",
        "step_status": "pending",
        "progress": 0,
        "filename": file.filename,
        "model": model,
        "language": language,
        "transcript": None,
        "error": None,
    }
    asyncio.create_task(run_transcription_job(job_id, None, upload_path, model, language))
    return {"job_id": job_id}


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    """Poll job status and retrieve transcript when done."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    return jobs[job_id]


@app.get("/api/job/{job_id}/download/{fmt}")
async def download_transcript(job_id: str, fmt: str):
    """Download transcript in a specific format: text, srt, vtt, json."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    job = jobs[job_id]
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
        await websocket.close()


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
