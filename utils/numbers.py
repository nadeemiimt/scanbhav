"""Numeric parsing helpers shared across analysis modules."""
from __future__ import annotations

from typing import Any, Optional


def parse_float(value: Any) -> Optional[float]:
    """Parse a finite float; return None for NaN, inf, or invalid input."""
    try:
        if value is None:
            return None
        x = float(value)
        if x != x:  # NaN
            return None
        if x in (float("inf"), float("-inf")):
            return None
        return x
    except (TypeError, ValueError):
        return None


def parse_int(value: Any, *, default: Optional[int] = None) -> Optional[int]:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def fmt_signed_pct(value: Any, *, digits: int = 2, fallback: str = "—") -> str:
    """Format a percentage with an explicit sign; tolerate string/None inputs."""
    n = parse_float(value)
    if n is None:
        if value is None:
            return fallback
        return str(value)
    return f"{n:+.{digits}f}"
