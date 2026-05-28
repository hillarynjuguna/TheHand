import asyncio
from collections import deque
from collections.abc import Coroutine
from typing import Any

from . import execution_store, leases


class RuntimeExecutor:
    def __init__(self, max_concurrency: int = 2, failure_limit: int = 25) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._active: dict[str, asyncio.Task] = {}
        self._recent_failures: deque[dict[str, Any]] = deque(maxlen=failure_limit)

    async def run(self, work_id: str, coro: Coroutine[Any, Any, Any]) -> Any:
        lease_id = leases.acquire(work_id)
        execution_store.mark_running(work_id, lease_id)
        async with self._semaphore:
            try:
                result = await coro
                execution_store.mark_completed(work_id)
                return result
            except Exception as exc:
                self._recent_failures.append({"work_id": work_id, "error": str(exc)})
                execution_store.mark_failed(work_id, str(exc))
                raise
            finally:
                leases.release(lease_id)
                self._active.pop(work_id, None)

    def track(self, work_id: str, task: asyncio.Task) -> None:
        self._active[work_id] = task

    def cancel(self, work_id: str) -> bool:
        task = self._active.get(work_id)
        if not task:
            return False
        task.cancel()
        return True

    def snapshot(self) -> dict[str, Any]:
        return {
            "active_tasks": list(self._active.keys()),
            "active_count": len(self._active),
            "recent_failures": list(self._recent_failures),
            **execution_store.snapshot(),
        }
