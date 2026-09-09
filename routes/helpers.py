"""Shared helpers for API route handlers."""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException

from config import BASE_DIR
from fetch_stock_data import (
    fetch_daily_auto,
    fetch_nse_daily,
    fetch_yfinance_company_data,
    fetch_yfinance_daily,
    fetch_yfinance_fundamentals,
    fetch_yfinance_news,
    yahoo_symbol,
)
from peers import fetch_peers
from technicals import row_close
from utils.errors import swallow
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Short-lived in-process caches so typing/search and reloads feel snappy.
_SEARCH_CACHE: dict[str, tuple[float, list[dict[str, str]]]] = {}
_SEARCH_TTL_SECONDS = 900  # 15 minutes
_STOCK_CACHE_TTL_SECONDS = 4 * 3600  # reuse saved candles/enrichment for 4 hours

def safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())


def raw_path(symbol: str) -> Path:
    return BASE_DIR / "data" / "raw" / safe_name(symbol) / "daily_adjusted.json"


def rows_from_payload(payload: dict[str, Any], limit: Optional[int] = None) -> list[dict[str, Any]]:
    entries = sorted(payload.get("Time Series (Daily)", {}).items())
    if limit:
        entries = entries[-limit:]
    return [{"date": day, **values} for day, values in entries]


def response_data(payload: dict[str, Any], limit: Optional[int] = None, *, cached: bool = False) -> dict[str, Any]:
    rows = rows_from_payload(payload, limit)
    if not rows:
        raise HTTPException(status_code=404, detail="No price rows were returned for this symbol.")
    latest_idx = next((i for i in range(len(rows) - 1, -1, -1) if row_close(rows[i]) > 0), None)
    if latest_idx is None:
        raise HTTPException(status_code=404, detail="No valid price rows were returned for this symbol.")
    latest = rows[latest_idx]
    previous = rows[latest_idx - 1] if latest_idx > 0 else latest
    close = row_close(latest)
    prev_close = row_close(previous)
    change_pct = ((close / prev_close) - 1) * 100 if prev_close else None
    return {
        "metadata": {**(payload.get("Meta Data", {}) or {}), "cached": cached},
        "company": payload.get("Company Data", {}),
        "fundamentals": payload.get("Fundamentals", {}),
        "peers": payload.get("Peers", []),
        "news": payload.get("News", []),
        "summary": {
            "date": latest["date"], "close": close, "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "open": latest.get("1. open"), "high": latest.get("2. high"), "low": latest.get("3. low"), "volume": latest.get("6. volume"),
        },
        "rows": rows,
    }


def percent_change(new: float, old: float) -> Optional[float]:
    return round((new / old - 1) * 100, 2) if old else None


def annualized_volatility_pct(closes: list[float], window: int = 30) -> Optional[float]:
    """Simple close-to-close annualized volatility over the trailing window."""
    sample = closes[-(window + 1):]
    if len(sample) < 3:
        return None
    returns = [(sample[i] / sample[i - 1]) - 1 for i in range(1, len(sample)) if sample[i - 1]]
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
    return round((variance ** 0.5) * (252 ** 0.5) * 100, 2)


def simple_moving_average(closes: list[float], window: int) -> Optional[float]:
    if len(closes) < window:
        return None
    return round(sum(closes[-window:]) / window, 2)


def analysis_input(symbol: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Build a transparent agent input from stored market data; no figures are invented."""
    rows = rows_from_payload(payload)
    closes = [float(row.get("5. adjusted close") or row.get("4. close") or 0) for row in rows]
    closes = [value for value in closes if value > 0]
    if len(closes) < 2:
        raise ValueError("At least two daily closing prices are required for AI insights.")
    company = payload.get("Company Data", {})
    fundamentals = payload.get("Fundamentals", {})
    peers = payload.get("Peers", [])
    latest = company.get("live_price") or closes[-1]
    sma_50 = simple_moving_average(closes, 50)
    sma_200 = simple_moving_average(closes, 200)
    return {
        "ticker": symbol.upper(),
        "company_name": company.get("name") or symbol.upper(),
        "sector": company.get("sector") or "unknown",
        "industry": company.get("industry") or "unknown",
        "price": latest,
        "market_cap": company.get("market_cap"),
        "data_as_of": rows[-1]["date"],
        "peers": [
            {
                "symbol": peer.get("symbol"),
                "name": peer.get("name"),
                "market_cap": peer.get("market_cap"),
                "trailing_pe": peer.get("trailing_pe"),
                "forward_pe": peer.get("forward_pe"),
                "price_to_book": peer.get("price_to_book"),
                "dividend_yield_pct": peer.get("dividend_yield_pct"),
            }
            for peer in peers
        ],
        "recent_news": [
            {"title": item.get("title"), "summary": item.get("summary"), "published_at": item.get("published_at"), "publisher": item.get("publisher")}
            for item in payload.get("News", [])
        ],
        "financials": {
            "eps": fundamentals.get("eps") or company.get("eps_ttm"),
            "revenue_growth_yoy_pct": fundamentals.get("revenue_growth_yoy_pct"),
            "gross_margin_pct": fundamentals.get("gross_margin_pct"),
            "operating_margin_pct": fundamentals.get("operating_margin_pct"),
            "net_margin_pct": fundamentals.get("net_margin_pct"),
            "free_cash_flow": fundamentals.get("free_cash_flow"),
            "operating_cash_flow": fundamentals.get("operating_cash_flow"),
            "debt_to_equity": fundamentals.get("debt_to_equity"),
            "current_ratio": fundamentals.get("current_ratio"),
            "roe_pct": fundamentals.get("roe_pct"),
        },
        "valuation": {
            "pe_ratio": company.get("trailing_pe"),
            "forward_pe_ratio": company.get("forward_pe"),
            "peg_ratio": company.get("peg_ratio"),
            "price_to_book": company.get("price_to_book"),
            "enterprise_to_ebitda": company.get("enterprise_to_ebitda"),
            "dividend_yield_pct": company.get("dividend_yield_pct"),
            "price_to_sales": round(company["market_cap"] / fundamentals["revenue"], 2) if company.get("market_cap") and fundamentals.get("revenue") else None,
        },
        "price_performance": {
            "one_month_pct": percent_change(latest, closes[max(0, len(closes) - 22)]),
            "six_month_pct": percent_change(latest, closes[max(0, len(closes) - 127)]),
            "one_year_pct": percent_change(latest, closes[max(0, len(closes) - 253)]),
            "distance_from_52_week_high_pct": percent_change(latest, max(closes[-252:])),
            "beta": company.get("beta"),
            "annualized_volatility_30d_pct": annualized_volatility_pct(closes, 30),
            "sma_50": sma_50,
            "sma_200": sma_200,
            "price_vs_sma_50_pct": percent_change(latest, sma_50) if sma_50 else None,
            "price_vs_sma_200_pct": percent_change(latest, sma_200) if sma_200 else None,
        },
        "notes": [
            "Price performance was calculated from locally saved daily candles.",
            "Missing fundamental values are intentionally null and must be treated as missing by the agent.",
        ],
    }



def _cache_is_fresh(path: Path, ttl_seconds: int = _STOCK_CACHE_TTL_SECONDS) -> bool:
    if not path.exists():
        return False
    age = time.time() - path.stat().st_mtime
    return age <= ttl_seconds


def fetch_prices(symbol: str, provider: str, *, force_refresh: bool = False) -> dict[str, Any]:
    path = raw_path(symbol)
    if not force_refresh and _cache_is_fresh(path):
        return json.loads(path.read_text(encoding="utf-8"))

    if provider == "yfinance":
        payload = fetch_yfinance_daily(symbol, 5)
    elif provider == "nse":
        # The NSE public endpoint intermittently returns 503 and does not serve
        # BSE listings. Keep the UI responsive by using Yahoo's NSE/BSE listing
        # when NSE rejects a request.
        if symbol.upper().endswith(".BSE"):
            payload = fetch_yfinance_daily(symbol, 5)
        else:
            try:
                payload = fetch_nse_daily(symbol, 5)
            except Exception:
                payload = fetch_yfinance_daily(symbol, 5)
    else:
        payload = fetch_daily_auto(symbol, 5)

    source = payload.get("Meta Data", {}).get("source", "")
    if source == "Yahoo Finance":
        # Run enrichment calls in parallel — sequential Yahoo round-trips are the
        # main reason Load stock feels slow.
        def _company() -> dict[str, Any]:
            try:
                return fetch_yfinance_company_data(symbol)
            except Exception:
                return {}

        def _fundamentals() -> dict[str, Any]:
            try:
                return fetch_yfinance_fundamentals(symbol)
            except Exception:
                return {}

        def _news() -> list[dict[str, Any]]:
            try:
                return fetch_yfinance_news(symbol)
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=3) as pool:
            company_f = pool.submit(_company)
            fundamentals_f = pool.submit(_fundamentals)
            news_f = pool.submit(_news)
            payload["Company Data"] = company_f.result()
            payload["Fundamentals"] = fundamentals_f.result()
            payload["News"] = news_f.result()
        try:
            industry = payload["Company Data"].get("industry")
            payload["Peers"] = fetch_peers(yahoo_symbol(symbol), industry)
        except Exception:
            payload["Peers"] = []

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _display_symbol(symbol: str) -> str:
    """Map Yahoo Indian suffixes to the project's BSE/NSE spelling."""
    upper = symbol.upper().strip()
    if upper.endswith(".NS"):
        return f"{upper[:-3]}.NSE"
    if upper.endswith(".BO"):
        return f"{upper[:-3]}.BSE"
    return upper


def _is_transient_fetch_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "503",
            "429",
            "502",
            "504",
            "service unavailable",
            "too many requests",
            "rate limit",
            "timed out",
            "timeout",
            "connection reset",
            "temporarily unavailable",
        )
    )


def _read_cached_payload(path: Path, *, min_rows: int = 30) -> Optional[dict[str, Any]]:
    """Return cached OHLCV if the file has enough daily bars."""
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if len(rows_from_payload(payload)) >= min_rows:
            return payload
    except Exception:
        pass
    return None


def _stale_cache_fallback(path: Path, exc: Exception, *, min_rows: int = 30) -> Optional[dict[str, Any]]:
    stale = _read_cached_payload(path, min_rows=min_rows)
    if not stale:
        return None
    out = json.loads(json.dumps(stale))
    meta = dict(out.get("Meta Data") or {})
    meta["stale_cache_used"] = True
    meta["fetch_error"] = str(exc)[:240]
    out["Meta Data"] = meta
    return out


def warm_price_cache_batched(
    symbols: list[str],
    *,
    force_refresh: bool = False,
    years: int = 5,
    chunk_size: int = 50,
    pause_seconds: float = 4.0,
    ttl_seconds: int = 24 * 3600,
    batch_strategy: str = "round_robin",
) -> dict[str, int]:
    """Pre-warm OHLCV caches in Yahoo batches with pauses to reduce rate limits."""
    from fetch_stock_data import fetch_yfinance_daily_batch
    from universe import round_robin_batches_from_symbols

    missing: list[str] = []
    for symbol in symbols:
        path = raw_path(symbol)
        if force_refresh or not _cache_is_fresh(path, ttl_seconds=ttl_seconds):
            missing.append(symbol)
    warmed = 0
    warmed_symbols: set[str] = set()
    size = max(1, chunk_size)
    if batch_strategy == "round_robin":
        chunks = round_robin_batches_from_symbols(missing, batch_size=size)
    else:
        chunks = [missing[i : i + size] for i in range(0, len(missing), size)]
    for i, chunk in enumerate(chunks):
        try:
            batch = fetch_yfinance_daily_batch(chunk, years=years)
            for symbol, payload in batch.items():
                path = raw_path(symbol)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                warmed += 1
                warmed_symbols.add(symbol.upper())
        except Exception as exc:
            swallow("Yahoo batch warm failed", exc)
        if i + 1 < len(chunks) and pause_seconds > 0:
            time.sleep(pause_seconds)

    # Symbols missing from batch responses get a paced single-symbol Yahoo retry.
    for symbol in missing:
        if symbol.upper() in warmed_symbols:
            continue
        try:
            payload = fetch_yfinance_daily(symbol, years)
            path = raw_path(symbol)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            warmed += 1
            warmed_symbols.add(symbol.upper())
        except Exception as exc:
            swallow(f"Yahoo single warm failed for {symbol}", exc)
            try:
                from fetch_stock_data import fetch_daily_auto

                payload = fetch_daily_auto(symbol, years, allow_nse_fallback=True)
                path = raw_path(symbol)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                warmed += 1
                warmed_symbols.add(symbol.upper())
            except Exception as fallback_exc:
                swallow(f"Yahoo/Groww/NSE warm failed for {symbol}", fallback_exc)
        time.sleep(0.35)

    return {"requested": len(missing), "warmed": warmed, "chunks": len(chunks) or 0}


def fetch_prices_light(
    symbol: str,
    *,
    force_refresh: bool = False,
    years: int = 5,
    provider: str = "auto",
    retries: int = 3,
    retry_delay: float = 2.0,
    allow_nse_fallback: bool = True,
    min_rows: int = 30,
) -> dict[str, Any]:
    """Daily candles only — used by the multi-stock technical screener."""
    path = raw_path(symbol)
    if not force_refresh and _cache_is_fresh(path, ttl_seconds=24 * 3600):
        cached = _read_cached_payload(path, min_rows=min_rows)
        if cached:
            return cached

    def _fetch_once() -> dict[str, Any]:
        if provider == "yfinance":
            return fetch_yfinance_daily(symbol, years)
        if provider == "nse":
            if symbol.upper().endswith(".BSE"):
                return fetch_yfinance_daily(symbol, years)
            try:
                return fetch_nse_daily(symbol, years)
            except Exception:
                return fetch_yfinance_daily(symbol, years)
        try:
            return fetch_daily_auto(symbol, years, allow_nse_fallback=allow_nse_fallback)
        except Exception:
            if allow_nse_fallback:
                return fetch_nse_daily(symbol, years)
            raise

    last_exc: Exception | None = None
    attempts = max(1, retries)
    payload: dict[str, Any] | None = None
    for attempt in range(attempts):
        try:
            payload = _fetch_once()
            break
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1 and _is_transient_fetch_error(exc):
                time.sleep(retry_delay * (attempt + 1))
                continue
            stale = _stale_cache_fallback(path, exc, min_rows=min_rows)
            if stale:
                return stale
            raise
    else:
        stale = _stale_cache_fallback(path, last_exc or RuntimeError(f"fetch failed for {symbol}"), min_rows=min_rows)
        if stale:
            return stale
        raise last_exc or RuntimeError(f"fetch failed for {symbol}")

    if payload is None:
        stale = _stale_cache_fallback(path, RuntimeError(f"fetch failed for {symbol}"), min_rows=min_rows)
        if stale:
            return stale
        raise RuntimeError(f"fetch failed for {symbol}")

    # Preserve any previously saved enrichment if present.
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            for key in ("Company Data", "Fundamentals", "Peers", "News"):
                if key in old and key not in payload:
                    payload[key] = old[key]
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def _ensure_loaded(symbol: str, provider: str) -> dict[str, Any]:
    """Return saved payload, fetching first when the symbol is not cached locally."""
    path = raw_path(symbol)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return fetch_prices(symbol, provider)

def _fetch_intraday_rows(symbol: str, provider: str = "auto") -> tuple[list[dict[str, Any]], Optional[float], str]:
    """Fetch 15m bars (5–10d) via Yahoo, NSE charting fallback; return rows, prior close, note."""
    note = ""
    prior_close = None
    rows: list[dict[str, Any]] = []
    try:
        import yfinance as yf
        from fetch_stock_data import yahoo_symbol

        try:
            daily_payload = _ensure_loaded(symbol, provider)
            daily_rows = rows_from_payload(daily_payload)
            if len(daily_rows) >= 2:
                prev = daily_rows[-2]
                prior_close = float(prev.get("5. adjusted close") or prev.get("4. close") or 0) or None
        except Exception:
            pass

        hist = yf.Ticker(yahoo_symbol(symbol)).history(period="10d", interval="15m", auto_adjust=False)
        if hist is not None and not hist.empty:
            for ts, row in hist.iterrows():
                rows.append({
                    "datetime": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row.get("Volume") or 0),
                })
            note = "15m bars from Yahoo Finance."
        if not rows and not symbol.upper().endswith(".BSE"):
            from datetime import datetime, timezone
            from fetch_stock_data import fetch_nse_charting_intraday, log_fetch_fallback_success

            try:
                bars = fetch_nse_charting_intraday(symbol, interval_minutes=15, days=10)
                for bar in bars:
                    ts_ms = bar.get("time")
                    if ts_ms is None:
                        continue
                    dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
                    rows.append({
                        "datetime": dt.isoformat(),
                        "open": float(bar.get("open") or 0),
                        "high": float(bar.get("high") or 0),
                        "low": float(bar.get("low") or 0),
                        "close": float(bar.get("close") or 0),
                        "volume": float(bar.get("volume") or 0),
                    })
                if rows:
                    log_fetch_fallback_success(
                        symbol,
                        yahoo_error="no Yahoo 15m bars",
                        source="NSE charting 15m",
                        rows=len(rows),
                        data_kind="intraday",
                    )
                    note = "15m bars from NSE charting (Yahoo unavailable)."
            except Exception as exc:
                if not rows:
                    from fetch_stock_data import log_fetch_total_failure

                    log_fetch_total_failure(
                        symbol,
                        data_kind="intraday",
                        detail=f"Yahoo: no 15m bars; NSE: {exc}",
                    )
        if not rows:
            note = "No intraday history returned from Yahoo or NSE."
    except Exception as exc:
        note = f"Intraday fetch failed: {exc}"
    return rows, prior_close, note

def _latest_price(symbol: str, provider: str = "auto") -> float:
    payload = fetch_prices(symbol, provider, force_refresh=False)
    rows = rows_from_payload(payload)
    if not rows:
        raise ValueError(f"No price for {symbol}")
    return float(rows[-1].get("5. adjusted close") or rows[-1].get("4. close") or 0)
