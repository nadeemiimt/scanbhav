"""Fast serve path for /api/ta/screen/page — memory + disk cache keyed by screen mtime."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from screener import SCREEN_CACHE

PAGE_CACHE_DIR = BASE_DIR / "data" / "screen_cache" / "pages"
DEFAULT_PAGE_NAME = "default_p1_all.json"

_MERGED_BY_MTIME: dict[float, list[dict[str, Any]]] = {}
_PAYLOAD_BY_KEY: dict[str, tuple[float, dict[str, Any]]] = {}


def _screen_mtime() -> float:
    if not SCREEN_CACHE.exists():
        return 0.0
    try:
        return SCREEN_CACHE.stat().st_mtime
    except OSError:
        return 0.0


def _query_fingerprint(query: Any) -> str:
    raw = json.dumps(query.model_dump(), sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def merged_universe_rows_cached(cached: dict[str, Any]) -> list[dict[str, Any]]:
    from screen_contract import merge_universe_rows

    mtime = _screen_mtime()
    if mtime in _MERGED_BY_MTIME:
        return _MERGED_BY_MTIME[mtime]
    rows = merge_universe_rows(cached)
    _MERGED_BY_MTIME.clear()
    _MERGED_BY_MTIME[mtime] = rows
    return rows


def _default_page_path() -> Path:
    return PAGE_CACHE_DIR / DEFAULT_PAGE_NAME


def load_precomputed_default_page(*, expected_mtime: float | None = None) -> Optional[dict[str, Any]]:
    path = _default_page_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if expected_mtime is not None and float(payload.get("screen_mtime") or 0) != float(expected_mtime):
        return None
    return payload.get("page")


def save_precomputed_default_page(page: dict[str, Any], *, screen_mtime: float) -> None:
    PAGE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _default_page_path().write_text(
        json.dumps({"screen_mtime": screen_mtime, "page": page}, indent=2),
        encoding="utf-8",
    )


def is_default_screen_query(query: Any) -> bool:
    d = query.model_dump()
    return (
        d.get("page") == 1
        and d.get("page_size") == 50
        and d.get("cap_view") == "all"
        and d.get("view") == "all"
        and not (d.get("symbol") or "").strip()
        and not d.get("grade")
        and not d.get("stance")
        and d.get("min_score") is None
        and d.get("max_score") is None
        and d.get("min_rsi") is None
        and d.get("max_rsi") is None
        and d.get("quality_ok") is not True
        and d.get("debt_ok") is not True
        and d.get("growth_ok") is not True
        and d.get("min_quality") is None
        and not (d.get("pattern_bias") or "")
        and d.get("sort_key") == "display_rank"
        and d.get("sort_dir") == "asc"
        and d.get("sort_key2") == "score"
        and d.get("sort_dir2") == "desc"
    )


def resolve_screen_page(
    cached: dict[str, Any],
    query: Any,
    *,
    stale: bool = False,
    expected: Optional[int] = None,
) -> dict[str, Any]:
    """Build or return cached screen page payload."""
    mtime = _screen_mtime()
    fp = _query_fingerprint(query)
    mem_key = f"{mtime}:{fp}"

    hit = _PAYLOAD_BY_KEY.get(mem_key)
    if hit and hit[0] == mtime:
        return hit[1]

    if is_default_screen_query(query):
        pre = load_precomputed_default_page(expected_mtime=mtime)
        if pre:
            _PAYLOAD_BY_KEY[mem_key] = (mtime, pre)
            return pre

    from screen_contract import build_screen_page

    premerged = merged_universe_rows_cached(cached)
    payload = build_screen_page(
        cached,
        query,
        stale=stale,
        expected=expected,
        premerged_rows=premerged,
    ).model_dump()
    _PAYLOAD_BY_KEY[mem_key] = (mtime, payload)

    if is_default_screen_query(query):
        save_precomputed_default_page(payload, screen_mtime=mtime)

    if len(_PAYLOAD_BY_KEY) > 48:
        _PAYLOAD_BY_KEY.clear()

    return payload


def warm_default_screen_page(cached: dict[str, Any], *, stale: bool = False, expected: Optional[int] = None) -> None:
    """Precompute default first page after a screen run completes."""
    from screen_contract import ScreenPageQueryContract

    query = ScreenPageQueryContract(
        page=1,
        page_size=50,
        cap_view="all",
        view="all",
        sort_key="display_rank",
        sort_dir="asc",
        sort_key2="score",
        sort_dir2="desc",
    )
    try:
        resolve_screen_page(cached, query, stale=stale, expected=expected)
    except Exception:
        pass


def invalidate_screen_page_cache() -> None:
    _MERGED_BY_MTIME.clear()
    _PAYLOAD_BY_KEY.clear()
