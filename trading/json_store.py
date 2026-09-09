"""JSON helpers for trading persistence (sets, frozendict, etc.)."""
from __future__ import annotations

import json
from typing import Any


def to_json_safe(obj: Any) -> Any:
    """Recursively convert non-JSON types (set, frozendict) for persistence."""
    if isinstance(obj, set):
        return sorted(obj)
    if isinstance(obj, frozenset):
        return sorted(obj)
    try:
        from frozendict import frozendict

        if isinstance(obj, frozendict):
            return {k: to_json_safe(v) for k, v in obj.items()}
    except ImportError:
        pass
    if isinstance(obj, dict):
        return {k: to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_json_safe(v) for v in obj]
    return obj


def dumps_pretty(data: Any, *, indent: int = 2) -> str:
    return json.dumps(to_json_safe(data), indent=indent)
