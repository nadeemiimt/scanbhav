"""Nifty 500 universe with Large / Mid / Small buckets (Yahoo .NS → app .NSE)."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional

from config import BASE_DIR

BUCKETS_PATH = BASE_DIR / "data" / "universe" / "nifty500_buckets.json"

CAP_SECTIONS: list[dict[str, str]] = [
    {"id": "large", "label": "Large Cap", "blurb": "≈ Nifty 100"},
    {"id": "mid", "label": "Mid Cap", "blurb": "≈ Nifty Midcap 150"},
    {"id": "small", "label": "Small Cap", "blurb": "≈ Nifty Smallcap 250"},
]


@lru_cache(maxsize=1)
def _load_buckets() -> dict[str, Any]:
    if not BUCKETS_PATH.exists():
        raise FileNotFoundError(
            f"Missing {BUCKETS_PATH}. Run: python scripts/refresh_nifty_universe.py"
        )
    data = json.loads(BUCKETS_PATH.read_text(encoding="utf-8"))
    for key in ("large", "mid", "small"):
        if key not in data or not isinstance(data[key], list):
            raise ValueError(f"Universe file missing '{key}' list")
    return data


def reload_universe() -> None:
    """Clear cached buckets after refreshing NSE CSVs on disk."""
    _load_buckets.cache_clear()


def bucket_for_symbol(symbol: str) -> Optional[str]:
    """Return large|mid|small for a symbol, if known."""
    data = _load_buckets()
    sym = symbol.upper().strip()
    for key in ("large", "mid", "small"):
        if sym in {s.upper() for s in data[key]}:
            return key
    return None


def universe_by_bucket() -> dict[str, list[str]]:
    """Deduped symbol lists keyed by large / mid / small."""
    data = _load_buckets()
    seen: set[str] = set()
    out: dict[str, list[str]] = {"large": [], "mid": [], "small": []}
    for key in ("large", "mid", "small"):
        for symbol in data[key]:
            sym = str(symbol).upper().strip()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            out[key].append(sym)
    return out


def universe_symbols(limit: int | None = None, bucket: str | None = None) -> list[str]:
    """
    Return unique universe symbols.

    - bucket: large | mid | small | None (all, Large→Mid→Small order)
    - limit: truncate the selected list (None = full Nifty 500)
    """
    by_bucket = universe_by_bucket()
    if bucket:
        key = bucket.lower().strip()
        if key not in by_bucket:
            raise ValueError(f"Unknown bucket '{bucket}'. Use large, mid, or small.")
        out = list(by_bucket[key])
    else:
        out = by_bucket["large"] + by_bucket["mid"] + by_bucket["small"]
    if limit is not None:
        return out[: max(1, min(int(limit), len(out)))]
    return out


def round_robin_batches(
    *,
    batch_size: int = 50,
    bucket: str | None = None,
    limit: int | None = None,
) -> list[list[str]]:
    """Build batches rotating large → mid → small (batch_size symbols each round)."""
    by_bucket = universe_by_bucket()
    if bucket:
        key = bucket.lower().strip()
        if key not in by_bucket:
            raise ValueError(f"Unknown bucket '{bucket}'. Use large, mid, or small.")
        symbols = list(by_bucket[key])
        if limit is not None:
            symbols = symbols[: max(1, min(int(limit), len(symbols)))]
        size = max(1, batch_size)
        return [symbols[i : i + size] for i in range(0, len(symbols), size)]

    keys = ["large", "mid", "small"]
    indices = {k: 0 for k in keys}
    batches: list[list[str]] = []
    total = 0
    cap = limit if limit is not None else sum(len(by_bucket[k]) for k in keys)
    size = max(1, batch_size)

    while total < cap:
        progressed = False
        for key in keys:
            lst = by_bucket[key]
            idx = indices[key]
            if idx >= len(lst):
                continue
            take = min(size, len(lst) - idx, cap - total)
            if take <= 0:
                continue
            batches.append(lst[idx : idx + take])
            indices[key] = idx + take
            total += take
            progressed = True
            if total >= cap:
                break
        if not progressed:
            break
    return batches


def round_robin_batches_from_symbols(symbols: list[str], *, batch_size: int = 50) -> list[list[str]]:
    """Round-robin retry batches for an arbitrary symbol list (e.g. failed fetches)."""
    if not symbols:
        return []
    grouped: dict[str, list[str]] = {"large": [], "mid": [], "small": []}
    for sym in symbols:
        bucket = bucket_for_symbol(sym) or "small"
        grouped.setdefault(bucket, []).append(sym)
    keys = [k for k in ("large", "mid", "small") if grouped.get(k)]
    if len(keys) <= 1:
        size = max(1, batch_size)
        return [symbols[i : i + size] for i in range(0, len(symbols), size)]

    indices = {k: 0 for k in keys}
    batches: list[list[str]] = []
    size = max(1, batch_size)
    remaining = len(symbols)

    while remaining > 0:
        progressed = False
        for key in keys:
            lst = grouped[key]
            idx = indices[key]
            if idx >= len(lst):
                continue
            take = min(size, len(lst) - idx)
            batches.append(lst[idx : idx + take])
            indices[key] = idx + take
            remaining -= take
            progressed = True
            if remaining <= 0:
                break
        if not progressed:
            break
    return batches


def universe_meta() -> dict[str, Any]:
    data = _load_buckets()
    by_bucket = universe_by_bucket()
    return {
        "as_of": data.get("as_of"),
        "source": data.get("source"),
        "urls": data.get("urls"),
        "total": sum(len(v) for v in by_bucket.values()),
        "counts": {k: len(v) for k, v in by_bucket.items()},
        "sections": CAP_SECTIONS,
    }


HORIZONS: list[dict] = [
    {"id": "1d", "label": "1 Day", "bars": 1},
    {"id": "1w", "label": "1 Week", "bars": 5},
    {"id": "1m", "label": "1 Month", "bars": 21},
    {"id": "3m", "label": "3 Months", "bars": 63},
    {"id": "6m", "label": "6 Months", "bars": 126},
    {"id": "9m", "label": "9 Months", "bars": 189},
    {"id": "1y", "label": "1 Year", "bars": 252},
    {"id": "2y", "label": "2 Years", "bars": 504},
    {"id": "3y", "label": "3 Years", "bars": 756},
    {"id": "5y", "label": "5 Years", "bars": 1260},
]
