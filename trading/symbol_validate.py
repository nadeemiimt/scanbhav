"""App symbol normalization and validation (.NSE / .BSE required)."""
from __future__ import annotations

import re

_APP_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&.-]{0,22}\.(NSE|BSE)$")
_BARE_TICKER = re.compile(r"^[A-Z0-9][A-Z0-9&.-]{0,22}$")

CURATED_SYMBOLS_MAX = 20


def normalize_app_symbol(symbol: str, *, default_exchange: str = "NSE") -> str:
    """Return canonical app symbol; bare tickers get .NSE/.BSE appended."""
    raw = (symbol or "").strip().upper()
    if not raw:
        raise ValueError("Symbol is empty.")
    if raw.endswith(".NS"):
        raw = f"{raw[:-3]}.NSE"
    elif raw.endswith(".BO"):
        raw = f"{raw[:-3]}.BSE"
    elif not raw.endswith((".NSE", ".BSE")):
        if not _BARE_TICKER.fullmatch(raw):
            raise ValueError(f"Invalid symbol: {symbol}")
        ex = default_exchange.upper()
        if ex not in {"NSE", "BSE"}:
            ex = "NSE"
        raw = f"{raw}.{ex}"
    if not _APP_SYMBOL.fullmatch(raw):
        raise ValueError(f"Invalid symbol format: {symbol}")
    return raw


def normalize_symbol_list(
    symbols: list[str] | None,
    *,
    max_count: int = CURATED_SYMBOLS_MAX,
    min_count: int = 0,
) -> list[str]:
    """Normalize, dedupe, and enforce list size limits."""
    if not symbols:
        if min_count > 0:
            raise ValueError(f"Select at least {min_count} stock(s).")
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in symbols:
        if not item or not str(item).strip():
            continue
        norm = normalize_app_symbol(str(item))
        if norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    if len(out) < min_count:
        raise ValueError(f"Select at least {min_count} stock(s).")
    if len(out) > max_count:
        raise ValueError(f"Maximum {max_count} stocks allowed.")
    return out
