"""Market context: sector RS, breadth, beta usage, sector board."""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from analysis._helpers import num
from analysis._ttl_cache import get_ttl_cached
from config import BASE_DIR
from fetch_stock_data import fetch_yfinance_daily
from desk_tools import relative_strength
from technicals import compute_technicals

_SECTOR_BOARD_TTL = 900.0


def _safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())


def _raw_path(symbol: str) -> Path:
    return BASE_DIR / "data" / "raw" / _safe_name(symbol) / "daily_adjusted.json"


def _rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = sorted(payload.get("Time Series (Daily)", {}).items())
    return [{"date": day, **values} for day, values in entries]


def _load_index_payload(index_sym: str, *, cache_only: bool = False) -> dict[str, Any]:
    path = _raw_path(index_sym)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    if cache_only:
        raise FileNotFoundError(f"No cached bars for {index_sym}")
    return fetch_yfinance_daily(index_sym, years=3)

SECTOR_INDEX_MAP = {
    "Financial Services": "^NSEBANK",
    "Banking": "^NSEBANK",
    "Information Technology": "^CNXIT",
    "IT": "^CNXIT",
    "Energy": "^CNXENERGY",
    "Healthcare": "^CNXPHARMA",
    "Pharma": "^CNXPHARMA",
    "Automobile": "^CNXAUTO",
    "Auto": "^CNXAUTO",
    "FMCG": "^CNXFMCG",
    "Metal": "^CNXMETAL",
    "Real Estate": "^CNXREALTY",
}


def sector_index_for(sector: Optional[str]) -> Optional[str]:
    if not sector:
        return None
    for key, idx in SECTOR_INDEX_MAP.items():
        if key.lower() in sector.lower():
            return idx
    return None


def stock_vs_sector_rs(symbol: str, tech: dict[str, Any], sector: Optional[str]) -> dict[str, Any]:
    idx = sector_index_for(sector)
    if not idx:
        return {"status": "no_sector_index", "sector": sector}
    try:
        payload = _load_index_payload(idx, cache_only=True)
        bench_tech = compute_technicals(_rows_from_payload(payload))
        rs = relative_strength(tech.get("returns_pct") or {}, bench_tech.get("returns_pct") or {}, bench_label=idx)
        return {"status": "ok", "sector_index": idx, "sector": sector, **rs}
    except Exception as exc:
        return {"status": "error", "sector": sector, "error": str(exc)[:80]}


def advance_decline_breadth() -> dict[str, Any]:
    """Approximate breadth from cached Nifty 500 screen if available."""
    cache = BASE_DIR / "data" / "screen_cache" / "last_screen.json"
    if not cache.exists():
        return {"status": "unavailable", "note": "Run screener first for breadth proxy."}
    try:
        data = json.loads(cache.read_text(encoding="utf-8"))
        rows = data.get("all") or data.get("rows") or []
        adv = dec = unch = 0
        for row in rows:
            chg = num(((row.get("technicals") or {}).get("returns_pct") or {}).get("1d"))
            if chg is None:
                chg = num(row.get("horizon_return_pct"))
            if chg is None:
                continue
            if chg > 0.1:
                adv += 1
            elif chg < -0.1:
                dec += 1
            else:
                unch += 1
        ratio = round(adv / max(dec, 1), 2)
        return {
            "status": "ok",
            "source": "screener_cache",
            "advances": adv,
            "declines": dec,
            "unchanged": unch,
            "advance_decline_ratio": ratio,
            "label": "bullish breadth" if ratio > 1.3 else ("bearish breadth" if ratio < 0.7 else "mixed"),
        }
    except Exception:
        return {"status": "error"}


def beta_scoring_context(tech: dict[str, Any], quote: dict[str, Any] | None) -> dict[str, Any]:
    company = (quote or {}).get("company") or {}
    beta = num(company.get("beta"))
    vol_pct = num((tech.get("volatility") or {}).get("atr_pct"))
    score_adj = 0
    note = "Beta unused in base TA score — now feeds risk context."
    if beta is not None:
        if beta > 1.4:
            score_adj = -3
            note = f"High beta ({beta:.2f}) — wider swings vs market."
        elif beta < 0.8:
            score_adj = 2
            note = f"Defensive beta ({beta:.2f}) — lower market sensitivity."
    return {"beta": beta, "atr_pct": vol_pct, "score_adjustment": score_adj, "note": note}


def sector_performance_board(*, cache_only: bool = False) -> dict[str, Any]:
    def _build() -> dict[str, Any]:
        unique: dict[str, str] = {}
        for sector, idx in SECTOR_INDEX_MAP.items():
            if sector != sector.title() and sector in ("IT", "Auto", "Pharma", "Banking"):
                continue
            unique.setdefault(idx, sector)

        def _one(sector: str, idx: str) -> Optional[dict[str, Any]]:
            try:
                payload = _load_index_payload(idx, cache_only=cache_only)
                rows = _rows_from_payload(payload)
                t = compute_technicals(rows)
                return {
                    "sector": sector,
                    "index": idx,
                    "return_1m_pct": (t.get("returns_pct") or {}).get("1m"),
                    "return_3m_pct": (t.get("returns_pct") or {}).get("3m"),
                    "rsi_14": (t.get("momentum") or {}).get("rsi_14"),
                }
            except Exception:
                return None

        board: list[dict[str, Any]] = []
        pairs = list(unique.items())
        if len(pairs) <= 1:
            for idx, sector in pairs:
                row = _one(sector, idx)
                if row:
                    board.append(row)
        else:
            with ThreadPoolExecutor(max_workers=min(6, len(pairs))) as pool:
                futures = [pool.submit(_one, sector, idx) for idx, sector in pairs]
                for fut in futures:
                    row = fut.result()
                    if row:
                        board.append(row)
        board.sort(key=lambda x: num(x.get("return_1m_pct")) or -999, reverse=True)
        return {"sectors": board[:8], "leader": board[0]["sector"] if board else None}

    if cache_only:
        return _build()
    return get_ttl_cached("market.sector_performance_board", _SECTOR_BOARD_TTL, _build)


def compute_market_context(symbol: str, tech: dict[str, Any], quote: dict[str, Any] | None) -> dict[str, Any]:
    sector = ((quote or {}).get("company") or {}).get("sector")
    return {
        "sector_relative_strength": stock_vs_sector_rs(symbol, tech, sector),
        "breadth": advance_decline_breadth(),
        "beta_context": beta_scoring_context(tech, quote),
        "sector_board": sector_performance_board(),
    }
