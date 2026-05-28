from __future__ import annotations

import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from infrastructure.subprocess.runner import AsyncCommandRunner

StepCallback = Callable[[str, str], None]


@dataclass(frozen=True)
class MediaExecutionConfig:
    whisper_bin: str
    whisper_bin_fallback: str
    models_dir: str
    temp_dir: Path
    cache_dir: Path | None = None


class LocalMediaExecutionProvider:
    """Local subprocess-backed media execution provider.

    Runtime orchestration owns the semantic steps; this adapter owns external
    commands and filesystem temp outputs.
    """

    def __init__(self, config: MediaExecutionConfig, runner: AsyncCommandRunner | None = None) -> None:
        self.config = config
        self.runner = runner or AsyncCommandRunner()
        self.config.temp_dir.mkdir(parents=True, exist_ok=True)
        if self.config.cache_dir:
            self.config.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_whisper_bin(self) -> str:
        for candidate in [self.config.whisper_bin, self.config.whisper_bin_fallback]:
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        raise FileNotFoundError(
            "whisper.cpp is not installed or not built on this machine.\n"
            f"Expected: {self.config.whisper_bin}\n"
            f"Fallback: {self.config.whisper_bin_fallback}\n"
            "Build whisper.cpp and download a model, or set WHISPER_BIN and MODELS_DIR."
        )

    def get_ffmpeg_bin(self) -> str:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        try:
            import imageio_ffmpeg

            return imageio_ffmpeg.get_ffmpeg_exe()
        except Exception as exc:
            raise FileNotFoundError(
                "ffmpeg is not installed or available to TheHand.\n"
                "Install ffmpeg on PATH, or install the Python fallback with: "
                ".venv\\Scripts\\python.exe -m pip install imageio-ffmpeg"
            ) from exc

    def build_ytdlp_executable(self) -> list[str]:
        executable = shutil.which("yt-dlp")
        if executable:
            return [executable]
        return [sys.executable, "-m", "yt_dlp"]

    def get_model_path(self, model_name: str) -> str:
        candidates = [
            Path(self.config.models_dir) / f"ggml-{model_name}.bin",
            Path(self.config.models_dir) / f"{model_name}.bin",
            Path(self.config.models_dir) / f"ggml-{model_name}-q5_1.bin",
            Path(self.config.models_dir) / f"ggml-{model_name}-q8_0.bin",
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
        raise FileNotFoundError(
            f"Model '{model_name}' not found in {self.config.models_dir}.\n"
            f"Run: bash models/download-ggml-model.sh {model_name}"
        )

    def list_available_models(self) -> list[str]:
        models_path = Path(self.config.models_dir)
        faster_models = ["tiny", "base", "small", "medium", "large-v3"] if self.has_faster_whisper() else []
        if not models_path.exists():
            return faster_models
        seen: set[str] = set()
        found: list[str] = []
        for model_file in sorted(models_path.glob("ggml-*.bin")):
            name = model_file.stem.replace("ggml-", "").replace("-q5_1", "").replace("-q8_0", "")
            if name not in seen:
                seen.add(name)
                found.append(name)
        for name in faster_models:
            if name not in seen:
                found.append(name)
        return found

    def has_faster_whisper(self) -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except Exception:
            return False

    def detect_platform(self, url: str) -> str:
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

    def build_ytdlp_cmd(self, url: str, out_path: str) -> list[str]:
        platform = self.detect_platform(url)
        command = [
            *self.build_ytdlp_executable(),
            "--no-playlist",
            "--extract-audio",
            "--audio-format", "best",
            "--audio-quality", "0",
            "--no-warnings",
            "--retries", "3",
            "--fragment-retries", "3",
            "-o", out_path,
        ]

        if platform == "tiktok":
            command += [
                "--user-agent",
                "Mozilla/5.0 (Linux; Android 12; SM-G991B) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
                "--add-header", "Referer:https://www.tiktok.com/",
            ]
        elif platform == "instagram":
            command += [
                "--user-agent",
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
                "--add-header", "Referer:https://www.instagram.com/",
            ]
            cookies_file = Path.home() / ".thehand" / "instagram-cookies.txt"
            if cookies_file.exists():
                command += ["--cookies", str(cookies_file)]
        elif platform == "youtube":
            cookies_file = Path.home() / ".thehand" / "youtube-cookies.txt"
            if cookies_file.exists():
                command += ["--cookies", str(cookies_file)]

        command.append(url)
        return command

    async def download_audio(self, url: str, job_id: str, on_step: StepCallback) -> Path:
        out_path = self.config.temp_dir / job_id / "audio.%(ext)s"
        (self.config.temp_dir / job_id).mkdir(parents=True, exist_ok=True)
        on_step("yt-dlp", "running")

        result = await self.runner.run(self.build_ytdlp_cmd(url, str(out_path)))
        if result.returncode != 0:
            error = result.stderr.decode()
            if "login" in error.lower() or "private" in error.lower():
                raise RuntimeError(
                    "This content requires login.\n"
                    "Export your cookies (see README) to ~/.thehand/instagram-cookies.txt\n\n"
                    f"{error}"
                )
            if "unavailable" in error.lower() or "removed" in error.lower():
                raise RuntimeError(f"Content unavailable or removed.\n\n{error}")
            raise RuntimeError(f"yt-dlp failed:\n{error}")

        for media_file in (self.config.temp_dir / job_id).iterdir():
            if media_file.stem == "audio":
                on_step("yt-dlp", "done")
                return media_file
        raise FileNotFoundError("yt-dlp ran but no audio file was produced")

    async def convert_to_wav(self, input_path: Path, job_id: str, on_step: StepCallback) -> Path:
        wav_path = self.config.temp_dir / job_id / "audio.wav"
        on_step("ffmpeg", "running")
        command = [
            self.get_ffmpeg_bin(), "-y",
            "-i", str(input_path),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(wav_path),
        ]
        result = await self.runner.run(command)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed:\n{result.stderr.decode()}")
        on_step("ffmpeg", "done")
        return wav_path

    async def run_whisper(self, wav_path: Path, model: str, language: str, job_id: str, on_step: StepCallback) -> dict:
        on_step("whisper.cpp", "running")
        try:
            whisper_bin = self.get_whisper_bin()
            model_path = self.get_model_path(model)
        except FileNotFoundError:
            return await self.run_faster_whisper(wav_path, model, language, job_id, on_step)

        output_base = str(self.config.temp_dir / job_id / "transcript")
        command = [
            whisper_bin,
            "-m", model_path,
            "-f", str(wav_path),
            "-otxt",
            "-osrt",
            "-ovtt",
            "-oj",
            "-of", output_base,
            "--print-progress",
        ]
        if language and language != "auto":
            command += ["-l", language]

        result = await self.runner.run(command)
        if result.returncode != 0:
            raise RuntimeError(f"whisper failed:\n{result.stderr.decode()}")

        on_step("whisper.cpp", "done")
        transcript = {}
        for extension, key in [(".txt", "text"), (".srt", "srt"), (".vtt", "vtt"), (".json", "json_raw")]:
            output = Path(output_base + extension)
            if output.exists():
                transcript[key] = output.read_text(encoding="utf-8")
        return transcript

    async def run_faster_whisper(self, wav_path: Path, model: str, language: str, job_id: str, on_step: StepCallback) -> dict:
        on_step("whisper.cpp", "running")
        if not self.has_faster_whisper():
            raise FileNotFoundError(
                "No transcription engine is available. Install/build whisper.cpp, or install the Python fallback with: "
                ".venv\\Scripts\\python.exe -m pip install faster-whisper"
            )

        try:
            from faster_whisper import WhisperModel
        except Exception as exc:
            raise RuntimeError(f"faster-whisper could not be imported: {exc}") from exc

        def transcribe() -> tuple[list, object]:
            cache_dir = self.config.cache_dir or (self.config.temp_dir / "models")
            cache_dir.mkdir(parents=True, exist_ok=True)
            whisper_model = WhisperModel(
                model,
                device="cpu",
                compute_type="int8",
                download_root=str(cache_dir),
            )
            return whisper_model.transcribe(
                str(wav_path),
                language=None if language == "auto" else language,
                vad_filter=True,
            )

        segments_iter, info = await asyncio.to_thread(transcribe)
        segments = list(segments_iter)
        text = "\n".join(segment.text.strip() for segment in segments if segment.text.strip())
        transcript = {
            "text": text,
            "srt": self._format_srt(segments),
            "vtt": self._format_vtt(segments),
            "json_raw": self._format_json(segments, info),
        }
        on_step("whisper.cpp", "done")
        return transcript

    def _format_timestamp(self, seconds: float, separator: str) -> str:
        millis = int(round(seconds * 1000))
        hours, remainder = divmod(millis, 3_600_000)
        minutes, remainder = divmod(remainder, 60_000)
        secs, millis = divmod(remainder, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"

    def _format_srt(self, segments: list) -> str:
        blocks = []
        for index, segment in enumerate(segments, start=1):
            blocks.append(
                f"{index}\n"
                f"{self._format_timestamp(segment.start, ',')} --> {self._format_timestamp(segment.end, ',')}\n"
                f"{segment.text.strip()}"
            )
        return "\n\n".join(blocks)

    def _format_vtt(self, segments: list) -> str:
        cues = ["WEBVTT"]
        for segment in segments:
            cues.append(
                f"{self._format_timestamp(segment.start, '.')} --> {self._format_timestamp(segment.end, '.')}\n"
                f"{segment.text.strip()}"
            )
        return "\n\n".join(cues)

    def _format_json(self, segments: list, info: object) -> str:
        import json

        return json.dumps(
            {
                "engine": "faster-whisper",
                "language": getattr(info, "language", None),
                "duration": getattr(info, "duration", None),
                "segments": [
                    {"start": segment.start, "end": segment.end, "text": segment.text}
                    for segment in segments
                ],
            },
            ensure_ascii=False,
        )

    def cleanup_job(self, job_id: str) -> None:
        job_dir = self.config.temp_dir / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir, ignore_errors=True)
