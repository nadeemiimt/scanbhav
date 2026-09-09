"""Stable API contract for the multi-stock screener UI.

The frontend should consume only these shapes (via /api/ta/screen/*).
Price loading is routed through registered data providers so additional
sources can be added without changing the UI contract.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

CONTRACT_VERSION = "1"

ScreenProviderId = Literal["auto", "yfinance", "nse"]
CapView = Literal["all", "large", "mid", "small"]
SortDir = Literal["asc", "desc"]


class ScreenDataProviderInfo(BaseModel):
    id: ScreenProviderId
    label: str
    description: str
    default: bool = False
    available: bool = True


SCREEN_DATA_PROVIDERS: list[ScreenDataProviderInfo] = [
    ScreenDataProviderInfo(
        id="auto",
        label="Auto (Yahoo → NSE)",
        description="Try Yahoo Finance first, then NSE charting/historical APIs.",
        default=True,
    ),
    ScreenDataProviderInfo(
        id="yfinance",
        label="Yahoo Finance",
        description="Daily OHLCV and corporate actions via Yahoo.",
    ),
    ScreenDataProviderInfo(
        id="nse",
        label="NSE India",
        description="NSE public endpoints (NSE-listed symbols; may fall back to Yahoo).",
    ),
]


class ScreenRowContract(BaseModel):
    """One ranked row in the screener table."""

    rank: Optional[int] = None
    section_rank: Optional[int] = None
    bucket: str
    symbol: str
    price: Optional[float] = None
    as_of: Optional[str] = None
    score: Optional[float] = None
    grade: Optional[str] = None
    stance: Optional[str] = None
    composite_score: Optional[float] = None
    horizon_return_pct: Optional[float] = None
    rsi_14: Optional[float] = None
    atr_14: Optional[float] = None
    atr_pct: Optional[float] = None
    macd_hist: Optional[float] = None
    adx_14: Optional[float] = None
    supertrend_dir: Optional[int] = None
    golden_cross: Optional[bool] = None
    price_vs_sma_200_pct: Optional[float] = None
    quality_score: Optional[float] = None
    quality_ok: Optional[bool] = None
    debt_ok: Optional[bool] = None
    growth_ok: Optional[bool] = None
    pattern_bias: Optional[str] = None
    entry_15d: Optional[float] = None
    exit_15d: Optional[float] = None
    stop_15d: Optional[float] = None
    plan_15d_upside_pct: Optional[float] = None
    plan_target_day: Optional[str] = None
    pivot_s1: Optional[float] = None
    pivot_r1: Optional[float] = None
    pivot_r2: Optional[float] = None
    pivot_pivot: Optional[float] = None
    scan_status: Optional[Literal["scanned", "pending", "failed"]] = None
    scanned_at: Optional[str] = None


class ScreenRunContract(BaseModel):
    """Metadata for the cached screen run backing pagination."""

    universe_size: int = 0
    scored: int = 0
    failed: int = 0
    run_at: Optional[str] = None
    horizon: str = "1m"
    data_provider: ScreenProviderId = "auto"
    elapsed_seconds: Optional[float] = None
    disclaimer: Optional[str] = None
    meta: dict[str, Any] = Field(default_factory=dict)
    stale: bool = False
    expected_universe_size: Optional[int] = None


class ScreenCountsContract(BaseModel):
    universe: int = 0
    scanned: int = 0
    pending: int = 0
    failed: int = 0
    all: int = 0
    large: int = 0
    mid: int = 0
    small: int = 0
    large_scanned: int = 0
    mid_scanned: int = 0
    small_scanned: int = 0


class ScreenPageQueryContract(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=10, le=100)
    cap_view: CapView = "all"
    symbol: str = ""
    grade: str = ""
    stance: str = ""
    min_score: Optional[float] = None
    max_score: Optional[float] = None
    min_rsi: Optional[float] = None
    max_rsi: Optional[float] = None
    quality_ok: Optional[bool] = None
    debt_ok: Optional[bool] = None
    growth_ok: Optional[bool] = None
    min_quality: Optional[float] = None
    pattern_bias: str = ""
    view: Literal["all", "scanned"] = "all"
    sort_key: str = "display_rank"
    sort_dir: SortDir = "asc"
    sort_key2: str = "score"
    sort_dir2: SortDir = "desc"


class ScreenPageContract(BaseModel):
    contract_version: str = CONTRACT_VERSION
    page: int
    page_size: int
    total_rows: int
    total_pages: int
    rows: list[ScreenRowContract]
    counts: ScreenCountsContract
    facets: dict[str, list[str]] = Field(default_factory=dict)
    run: Optional[ScreenRunContract] = None
    query: ScreenPageQueryContract
    plan_context: Optional[dict[str, Any]] = None
    data_providers: list[ScreenDataProviderInfo] = Field(default_factory=lambda: list(SCREEN_DATA_PROVIDERS))


class ScreenProvidersContract(BaseModel):
    contract_version: str = CONTRACT_VERSION
    providers: list[ScreenDataProviderInfo]
    default_provider: ScreenProviderId = "auto"
    live_quote: Optional[dict[str, Any]] = None
    brokers: list[dict[str, Any]] = Field(default_factory=list)


def flatten_screen_rows(cached: dict[str, Any]) -> list[dict[str, Any]]:
    """Merge section tops into one list with bucket tags."""
    if not cached:
        return []
    if cached.get("sections"):
        rows: list[dict[str, Any]] = []
        for key in ("large", "mid", "small"):
            sec = cached["sections"].get(key) or {}
            for row in sec.get("top") or []:
                rows.append({**row, "bucket": row.get("bucket") or key})
        return rows
    return [{**row, "bucket": row.get("bucket") or "large"} for row in (cached.get("top") or [])]


def merge_universe_rows(cached: dict[str, Any]) -> list[dict[str, Any]]:
    """Full Nifty 500 list merged with scored cache rows."""
    from universe import bucket_for_symbol, universe_by_bucket, universe_symbols

    scored_rows = flatten_screen_rows(cached)
    scored_map = {str(r.get("symbol") or "").upper(): r for r in scored_rows}
    run_at = cached.get("run_at")
    failed_set = {str(s).upper() for s in (cached.get("failed_symbols") or [])}

    merged: list[dict[str, Any]] = []
    for sym in universe_symbols(limit=500):
        key = sym.upper()
        bucket = bucket_for_symbol(sym) or "large"
        if key in scored_map:
            row = dict(scored_map[key])
            row["scan_status"] = "scanned"
            row["scanned_at"] = run_at
            row["bucket"] = row.get("bucket") or bucket
            merged.append(row)
        elif key in failed_set:
            merged.append({
                "symbol": sym,
                "bucket": bucket,
                "scan_status": "failed",
                "scanned_at": run_at,
            })
        else:
            merged.append({
                "symbol": sym,
                "bucket": bucket,
                "scan_status": "pending",
                "scanned_at": None,
            })
    return merged


def screen_counts(all_rows: list[dict[str, Any]], cached: Optional[dict[str, Any]] = None) -> ScreenCountsContract:
    from universe import universe_by_bucket

    by_bucket = universe_by_bucket()
    universe_total = len(all_rows) if all_rows else sum(len(v) for v in by_bucket.values())
    scanned = sum(1 for r in all_rows if r.get("scan_status") == "scanned")
    failed = sum(1 for r in all_rows if r.get("scan_status") == "failed")
    pending = max(0, universe_total - scanned - failed)
    cap_scanned = {
        key: sum(1 for r in all_rows if r.get("bucket") == key and r.get("scan_status") == "scanned")
        for key in ("large", "mid", "small")
    }
    return ScreenCountsContract(
        universe=universe_total,
        scanned=scanned,
        pending=pending,
        failed=failed,
        all=universe_total,
        large=len(by_bucket.get("large") or []),
        mid=len(by_bucket.get("mid") or []),
        small=len(by_bucket.get("small") or []),
        large_scanned=cap_scanned["large"],
        mid_scanned=cap_scanned["mid"],
        small_scanned=cap_scanned["small"],
    )


def _display_rank(row: dict[str, Any], cap_view: CapView) -> Optional[int]:
    if cap_view == "all":
        return row.get("rank")
    return row.get("section_rank") if row.get("section_rank") is not None else row.get("rank")


def _sort_value(row: dict[str, Any], sort_key: str, cap_view: CapView) -> Any:
    if sort_key == "display_rank":
        return _display_rank(row, cap_view)
    if sort_key == "bucket":
        return str(row.get("bucket") or "")
    return row.get(sort_key)


def _coerce_sort(row: dict[str, Any], sort_key: str, sort_dir: SortDir, cap_view: CapView) -> tuple:
    if sort_key == "scan_status":
        order = {"scanned": 0, "failed": 1, "pending": 2}
        raw = order.get(str(row.get("scan_status") or "pending"), 3)
        return (0, raw if sort_dir == "asc" else -raw)
    if sort_key == "scanned_at":
        raw = row.get("scanned_at") or ""
        return (0, raw if sort_dir == "asc" else tuple(-ord(c) for c in raw) if raw else (0,))
    raw = _sort_value(row, sort_key, cap_view)
    if sort_key in {"symbol", "grade", "stance", "bucket"}:
        norm = str(raw or "").lower()
        return (0, norm if sort_dir == "asc" else tuple(-ord(c) for c in norm))
    if raw is None:
        return (1, 0)
    try:
        num = float(raw)
        return (0, num if sort_dir == "asc" else -num)
    except (TypeError, ValueError):
        norm = str(raw).lower()
        return (0, norm if sort_dir == "asc" else tuple(-ord(c) for c in norm))


def filter_and_sort_rows(
    rows: list[dict[str, Any]],
    query: ScreenPageQueryContract,
) -> list[dict[str, Any]]:
    cap_view = query.cap_view
    out = list(rows)
    if query.view == "scanned":
        out = [r for r in out if r.get("scan_status") == "scanned"]
    if cap_view != "all":
        out = [r for r in out if r.get("bucket") == cap_view]

    sym_q = query.symbol.strip().upper()
    if sym_q:
        out = [r for r in out if sym_q in str(r.get("symbol") or "").upper()]
    if query.grade:
        out = [r for r in out if r.get("grade") == query.grade]
    if query.stance:
        out = [r for r in out if r.get("stance") == query.stance]
    if query.min_score is not None:
        out = [r for r in out if (r.get("score") if r.get("score") is not None else float("-inf")) >= query.min_score]
    if query.max_score is not None:
        out = [r for r in out if (r.get("score") if r.get("score") is not None else float("inf")) <= query.max_score]
    if query.min_rsi is not None:
        out = [r for r in out if (r.get("rsi_14") if r.get("rsi_14") is not None else float("-inf")) >= query.min_rsi]
    if query.max_rsi is not None:
        out = [r for r in out if (r.get("rsi_14") if r.get("rsi_14") is not None else float("inf")) <= query.max_rsi]
    if query.quality_ok is True:
        out = [r for r in out if r.get("quality_ok") is True]
    if query.debt_ok is True:
        out = [r for r in out if r.get("debt_ok") is True]
    if query.growth_ok is True:
        out = [r for r in out if r.get("growth_ok") is True]
    if query.min_quality is not None:
        out = [r for r in out if (r.get("quality_score") if r.get("quality_score") is not None else float("-inf")) >= query.min_quality]
    if query.pattern_bias:
        out = [r for r in out if str(r.get("pattern_bias") or "").lower() == query.pattern_bias.lower()]

    def row_key(row: dict[str, Any]) -> tuple:
        primary = _coerce_sort(row, query.sort_key, query.sort_dir, cap_view)
        if query.sort_key2 and query.sort_key2 != query.sort_key:
            secondary = _coerce_sort(row, query.sort_key2, query.sort_dir2, cap_view)
            return (primary, secondary)
        return (primary,)

    out.sort(key=row_key)
    return out


def paginate_rows(rows: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], int, int]:
    total = len(rows)
    if total == 0:
        return [], 0, 1
    total_pages = max(1, (total + page_size - 1) // page_size)
    page = min(max(1, page), total_pages)
    start = (page - 1) * page_size
    return rows[start : start + page_size], total, total_pages


def run_from_cache(cached: dict[str, Any], *, stale: bool = False, expected: Optional[int] = None) -> ScreenRunContract:
    provider = cached.get("data_provider") or "auto"
    if provider not in ("auto", "yfinance", "nse"):
        provider = "auto"
    return ScreenRunContract(
        universe_size=int(cached.get("universe_size") or 0),
        scored=int(cached.get("scored") or 0),
        failed=int(cached.get("failed") or 0),
        run_at=cached.get("run_at"),
        horizon=str(cached.get("horizon") or "1m"),
        data_provider=provider,
        elapsed_seconds=cached.get("elapsed_seconds"),
        disclaimer=cached.get("disclaimer"),
        meta=dict(cached.get("meta") or {}),
        stale=stale,
        expected_universe_size=expected,
    )


def screen_facets(all_rows: list[dict[str, Any]], cap_view: CapView) -> dict[str, list[str]]:
    rows = [r for r in all_rows if r.get("scan_status") == "scanned"]
    if cap_view != "all":
        rows = [r for r in rows if r.get("bucket") == cap_view]
    grades = sorted({str(r.get("grade")) for r in rows if r.get("grade")})
    stances = sorted({str(r.get("stance")) for r in rows if r.get("stance")})
    return {"grades": grades, "stances": stances}


def enrich_rows_session_plan(cached: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Recompute session entry/exit at serve time (IST today vs next day)."""
    results = cached.get("results") or []
    by_sym = {str(r.get("symbol") or "").upper(): r for r in results} if results else {}
    from analysis.plan_session import enrich_row_session_plan

    for row in rows:
        if row.get("scan_status") != "scanned":
            continue
        full = by_sym.get(str(row.get("symbol") or "").upper())
        enrich_row_session_plan(row, full)


def enrich_rows_15d_plan(cached: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    enrich_rows_session_plan(cached, rows)


def build_screen_page(
    cached: dict[str, Any],
    query: ScreenPageQueryContract,
    *,
    stale: bool = False,
    expected: Optional[int] = None,
    premerged_rows: Optional[list[dict[str, Any]]] = None,
) -> ScreenPageContract:
    all_rows = premerged_rows if premerged_rows is not None else merge_universe_rows(cached)
    filtered = filter_and_sort_rows(all_rows, query)
    page_rows, total, total_pages = paginate_rows(filtered, query.page, query.page_size)
    enrich_rows_session_plan(cached, page_rows)
    safe_query = query.model_copy(update={"page": min(max(1, query.page), total_pages) if total else 1})
    from analysis.plan_session import session_plan_context

    return ScreenPageContract(
        page=safe_query.page,
        page_size=safe_query.page_size,
        total_rows=total,
        total_pages=total_pages,
        rows=[ScreenRowContract.model_validate(row) for row in page_rows],
        counts=screen_counts(all_rows, cached),
        facets=screen_facets(all_rows, query.cap_view),
        run=run_from_cache(cached, stale=stale, expected=expected),
        query=safe_query,
        plan_context=session_plan_context(),
    )
