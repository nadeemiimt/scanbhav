"""Simple process-local TTL cache for shared market snapshots."""
from __future__ import annotations

import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")

_store: dict[str, tuple[float, Any]] = {}


def get_ttl_cached(key: str, ttl_seconds: float, factory: Callable[[], T]) -> T:
    now = time.monotonic()
    hit = _store.get(key)
    if hit is not None and now - hit[0] < ttl_seconds:
        return hit[1]
    value = factory()
    _store[key] = (now, value)
    return value
