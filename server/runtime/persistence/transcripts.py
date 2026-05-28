from __future__ import annotations

from pathlib import Path


class TranscriptArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def persist_transcript_formats(self, job_id: str, transcript: dict) -> None:
        job_dir = self.root / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        for extension, key in [('.txt', 'text'), ('.srt', 'srt'), ('.vtt', 'vtt'), ('.json', 'json_raw')]:
            content = transcript.get(key)
            if content:
                (job_dir / f'transcript{extension}').write_text(content, encoding='utf-8')
