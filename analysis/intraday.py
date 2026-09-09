"""Intraday technical snapshot — Yahoo with NSE charting fallback."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from analysis._helpers import extract_ohlcv
from technicals import compute_technicals, rsi


def _yahoo_intraday_rows(symbol: str, interval: str = "1h", period: str = "5d") -> list[dict[str, Any]]:
    try:
        import yfinance as yf
        from fetch_stock_data import yahoo_symbol
    except ImportError:
        return []
    sym = yahoo_symbol(symbol)
    try:
        hist = yf.Ticker(sym).history(period=period, interval=interval, auto_adjust=True)
    except Exception:
        return []
    if hist is None or hist.empty:
        return []
    rows: list[dict[str, Any]] = []
    for idx, row in hist.iterrows():
        rows.append({
            "date": str(idx.date()) if hasattr(idx, "date") else str(idx),
            "1. open": float(row["Open"]),
            "2. high": float(row["High"]),
            "3. low": float(row["Low"]),
            "4. close": float(row["Close"]),
            "6. volume": float(row.get("Volume") or 0),
        })
    return rows


def _nse_intraday_rows(symbol: str, *, interval_minutes: int = 60, days: int = 10) -> list[dict[str, Any]]:
    from fetch_stock_data import fetch_nse_charting_intraday

    bars = fetch_nse_charting_intraday(symbol, interval_minutes=interval_minutes, days=days)
    rows: list[dict[str, Any]] = []
    for bar in bars:
        ts_ms = bar.get("time")
        if ts_ms is None:
            continue
        dt = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc)
        rows.append({
            "date": dt.date().isoformat(),
            "datetime": dt.isoformat(),
            "1. open": float(bar.get("open") or 0),
            "2. high": float(bar.get("high") or 0),
            "3. low": float(bar.get("low") or 0),
            "4. close": float(bar.get("close") or 0),
            "6. volume": float(bar.get("volume") or 0),
        })
    return rows


def _intraday_rows(symbol: str) -> tuple[list[dict[str, Any]], str]:
    rows = _yahoo_intraday_rows(symbol, interval="1h", period="10d")
    if len(rows) >= 20:
        return rows, "yfinance_1h"
    yahoo_note = "no Yahoo 1h bars"
    nse_rows: list[dict[str, Any]] = []
    nse_failed = False
    try:
        nse_rows = _nse_intraday_rows(symbol, interval_minutes=60, days=10)
        if len(nse_rows) >= 20:
            from fetch_stock_data import log_fetch_fallback_success

            log_fetch_fallback_success(
                symbol,
                yahoo_error=yahoo_note,
                source="NSE charting 60m",
                rows=len(nse_rows),
                data_kind="intraday",
            )
            return nse_rows, "nse_charting_60m"
    except Exception as exc:
        nse_failed = True
        if len(rows) < 20:
            from fetch_stock_data import log_fetch_total_failure

            log_fetch_total_failure(
                symbol,
                data_kind="intraday",
                detail=f"Yahoo: {yahoo_note}; NSE: {exc}",
            )
    if not nse_failed and len(rows) < 20 and len(nse_rows) < 20:
        from fetch_stock_data import log_fetch_total_failure

        log_fetch_total_failure(
            symbol,
            data_kind="intraday",
            detail=f"Yahoo: {yahoo_note}; NSE: insufficient bars ({len(nse_rows)})",
        )
    if rows:
        return rows, "yfinance_1h"
    return [], "unavailable"


def compute_intraday_ta(symbol: str) -> dict[str, Any]:
    rows, source = _intraday_rows(symbol)
    if len(rows) < 20:
        return {"status": "unavailable", "source": source, "bars": len(rows)}
    _, _, _, closes, volumes = extract_ohlcv(rows)
    tech = compute_technicals(rows)
    rsi_s = rsi(closes, 14)
    last_rsi = rsi_s[-1] if rsi_s else None
    vwap_num = vwap_den = 0.0
    for row in rows[-40:]:
        h = float(row.get("2. high") or 0)
        l = float(row.get("3. low") or 0)
        c = float(row.get("4. close") or 0)
        v = float(row.get("6. volume") or 0)
        if v > 0:
            vwap_num += ((h + l + c) / 3) * v
            vwap_den += v
    vwap = vwap_num / vwap_den if vwap_den else None
    last = closes[-1]
    note = (
        "Intraday read uses delayed 1h Yahoo bars — not exchange tick data."
        if source.startswith("yfinance")
        else "Intraday read uses NSE charting 60m bars — delayed, not tick data."
    )
    return {
        "status": "ok",
        "source": source,
        "bars": len(rows),
        "interval": "1h",
        "price": round(last, 4),
        "rsi_14": round(last_rsi, 2) if last_rsi else None,
        "vwap_session": round(vwap, 4) if vwap else None,
        "price_vs_vwap": "above" if vwap and last > vwap else ("below" if vwap else None),
        "trend": (tech.get("trend") or {}).get("supertrend_dir"),
        "momentum_bias": "bullish" if last_rsi and last_rsi > 55 else ("bearish" if last_rsi and last_rsi < 45 else "neutral"),
        "note": note,
    }
