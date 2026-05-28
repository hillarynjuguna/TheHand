import asyncio
from collections.abc import Coroutine
from typing import Any

from .scheduler import default_scheduler

DEFAULT_POSTPROCESSING_ARTIFACTS = ["summary", "chapter_map"]


def default_artifact_types(defaults: list[str] | None = None) -> list[str]:
    return defaults or DEFAULT_POSTPROCESSING_ARTIFACTS.copy()


def enqueue_background_task(
    coro: Coroutine[Any, Any, Any],
    *,
    work_type: str = "background",
    entity_id: str | None = None,
    correlation_id: str | None = None,
    dependencies: list[str] | None = None,
    causation_id: str | None = None,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 1,
) -> asyncio.Task:
    return default_scheduler.enqueue(
        coro,
        work_type=work_type,
        entity_id=entity_id,
        correlation_id=correlation_id,
        dependencies=dependencies,
        causation_id=causation_id,
        payload=payload,
        max_attempts=max_attempts,
    )


def runtime_queue_snapshot() -> dict[str, Any]:
    return default_scheduler.snapshot()
