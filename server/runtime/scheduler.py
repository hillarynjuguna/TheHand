import asyncio
import uuid
from collections import deque
from collections.abc import Coroutine
from typing import Any

from .executor import RuntimeExecutor
from . import execution_store


class RuntimeScheduler:
    def __init__(self, executor: RuntimeExecutor | None = None) -> None:
        self.executor = executor or RuntimeExecutor()
        self._queued: deque[dict[str, Any]] = deque()
        self._tasks: dict[str, asyncio.Task] = {}

    def enqueue(
        self,
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
        work_id = correlation_id or str(uuid.uuid4())
        execution_store.create_execution(
            work_id,
            work_type,
            entity_id,
            correlation_id,
            causation_id,
            payload=payload,
            max_attempts=max_attempts,
        )
        record = {
            "work_id": work_id,
            "work_type": work_type,
            "entity_id": entity_id,
            "dependencies": dependencies or [],
        }
        self._queued.append(record)
        task = asyncio.create_task(self._run_record(record, coro))
        self._tasks[work_id] = task
        self.executor.track(work_id, task)
        return task

    async def _run_record(self, record: dict[str, Any], coro: Coroutine[Any, Any, Any]) -> Any:
        try:
            if record in self._queued:
                self._queued.remove(record)
            return await self.executor.run(record["work_id"], coro)
        finally:
            self._tasks.pop(record["work_id"], None)

    def cancel(self, work_id: str) -> bool:
        return self.executor.cancel(work_id)

    def snapshot(self) -> dict[str, Any]:
        executor_snapshot = self.executor.snapshot()
        return {
            "queue_depth": len(self._queued),
            "queued": list(self._queued),
            "tasks": list(self._tasks.keys()),
            **executor_snapshot,
        }


default_scheduler = RuntimeScheduler()
