import json
import re
from collections.abc import Awaitable, Callable
from typing import Any

ProgressCallback = Callable[[int, str], Awaitable[None]]
GeneratorResult = tuple[str, dict[str, Any]]


async def _summary_generator(
    transcript: dict,
    chunks: list[dict],
    progress: ProgressCallback,
) -> GeneratorResult:
    if chunks:
        await progress(40, "assembling summary from chunks")
        summary = "\n\n".join([chunk["text"] for chunk in chunks[:3]])
        return summary.strip(), {"method": "heuristic", "source": "chunks"}

    return (transcript.get("text") or "")[:1600].strip(), {
        "method": "heuristic",
        "source": "transcript",
    }


async def _chapter_map_generator(
    transcript: dict,
    chunks: list[dict],
    progress: ProgressCallback,
) -> GeneratorResult:
    chapters = []
    if chunks:
        await progress(35, "clustering chunks for chapters")
        chunk_group = 5
        for index in range(0, len(chunks), chunk_group):
            group = chunks[index:index + chunk_group]
            title = group[0]["text"][:80].strip()
            start = group[0].get("start_ts")
            end = group[-1].get("end_ts")
            chapters.append({"title": title, "start_ts": start, "end_ts": end})

    return json.dumps({"chapters": chapters}, ensure_ascii=False), {
        "method": "chunk_grouping",
        "group_size": 5,
    }


async def _entities_generator(
    transcript: dict,
    chunks: list[dict],
    progress: ProgressCallback,
) -> GeneratorResult:
    text = "\n".join([chunk["text"] for chunk in chunks]) if chunks else (transcript.get("text") or "")
    await progress(30, "scanning for entities")
    words = re.findall(r"\b([A-Z][a-z]{2,})\b", text)
    frequency: dict[str, int] = {}
    for word in words:
        frequency[word] = frequency.get(word, 0) + 1
    entities = sorted(
        [{"entity": key, "count": value} for key, value in frequency.items()],
        key=lambda item: -item["count"],
    )[:60]
    return json.dumps({"entities": entities}, ensure_ascii=False), {
        "method": "heuristic-capitalized-words",
    }


async def _topics_generator(
    transcript: dict,
    chunks: list[dict],
    progress: ProgressCallback,
) -> GeneratorResult:
    text = "\n".join([chunk["text"] for chunk in chunks]) if chunks else (transcript.get("text") or "")
    await progress(30, "extracting topic words")
    stopwords = {
        "the", "and", "for", "with", "that", "this", "have", "from", "are",
        "was", "were", "what", "which", "when", "where", "you", "your",
        "will", "shall", "but", "not", "can", "has",
    }
    words = [word.lower() for word in re.findall(r"\b([A-Za-z]{3,})\b", text)]
    frequency: dict[str, int] = {}
    for word in words:
        if word in stopwords:
            continue
        frequency[word] = frequency.get(word, 0) + 1
    topics = sorted(
        [{"topic": key, "count": value} for key, value in frequency.items()],
        key=lambda item: -item["count"],
    )[:40]
    return json.dumps({"topics": topics}, ensure_ascii=False), {
        "method": "heuristic-top-words",
    }


async def _quotes_generator(
    transcript: dict,
    chunks: list[dict],
    progress: ProgressCallback,
) -> GeneratorResult:
    text = "\n".join([chunk["text"] for chunk in chunks]) if chunks else (transcript.get("text") or "")
    await progress(30, "finding quotes")
    quotes = re.findall(r'"([^"]{20,200})"', text)[:80]
    return json.dumps({"quotes": quotes}, ensure_ascii=False), {
        "method": "heuristic-quote-extract",
    }


GENERATOR_REGISTRY = {
    "summary": _summary_generator,
    "chapter_map": _chapter_map_generator,
    "entities": _entities_generator,
    "topics": _topics_generator,
    "quotes": _quotes_generator,
}


async def generate_artifact_content(
    artifact_type: str,
    transcript: dict,
    chunks: list[dict],
    progress: ProgressCallback,
) -> GeneratorResult:
    generator = GENERATOR_REGISTRY.get(artifact_type)
    if not generator:
        return f"Unsupported artifact type: {artifact_type}", {"method": "none"}
    return await generator(transcript, chunks, progress)
