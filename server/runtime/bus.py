import asyncio
from typing import Callable, Dict, List

# Simple in-memory publish/subscribe bus. Subscribers receive events (dict).
_subs: Dict[str, List[Callable]] = {}


def subscribe(key: str, callback: Callable) -> None:
    """Subscribe to a key (job_id or '*' for all)."""
    _subs.setdefault(key, []).append(callback)


def unsubscribe(key: str, callback: Callable) -> None:
    lst = _subs.get(key) or []
    if callback in lst:
        lst.remove(callback)
        _subs[key] = lst


def publish(event: dict) -> None:
    """Publish an event to subscribers for event['job_id'] and '*' subscribers."""
    job_id = event.get('job_id') or '*'
    targets = list(_subs.get(job_id, [])) + list(_subs.get('*', []))
    for cb in targets:
        try:
            res = cb(event)
            if asyncio.iscoroutine(res):
                asyncio.create_task(res)
        except Exception:
            # swallow subscriber exceptions to avoid breaking publisher
            pass
