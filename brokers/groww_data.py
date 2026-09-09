"""Groww Trade API — historical OHLCV for symbols missing on Yahoo/NSE."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from brokers.groww_auth import groww_data_available, resolve_groww_access_token
from brokers.sdk_loader import groww_api
from brokers.symbols import base_symbol, exchange_for, groww_symbol

# Groww limits 1-day candles to 180 days per request.
_GROWW_DAY_CHUNK_DAYS = 170


def _groww_exchange_const(groww, symbol: str) -> str:
    return groww.EXCHANGE_BSE if exchange_for(symbol) == "BSE" else groww.EXCHANGE_NSE


def _candles_to_daily_series(candles: list[list[Any]]) -> dict[str, dict[str, str]]:
    series: dict[str, dict[str, str]] = {}
    for candle in candles or []:
        if not candle or len(candle) < 5:
            continue
        ts_raw = str(candle[0])
        day = ts_raw[:10]
        if len(day) != 10:
            continue
        open_p, high_p, low_p, close_p = candle[1:5]
        volume = candle[5] if len(candle) > 5 else 0
        series[day] = {
            "1. open": str(open_p),
            "2. high": str(high_p),
            "3. low": str(low_p),
            "4. close": str(close_p),
            "5. adjusted close": str(close_p),
            "6. volume": str(volume or 0),
        }
    return series


def fetch_groww_daily(symbol: str, years: int) -> dict[str, Any]:
    """Fetch daily OHLCV via Groww backtesting API (data only — not for orders)."""
    if not groww_data_available():
        raise RuntimeError(
            "Groww data unavailable. Set GROWW_API_KEY + GROWW_API_SECRET (or GROWW_ACCESS_TOKEN) "
            "and install growwapi."
        )

    token = resolve_groww_access_token()
    if not token:
        raise RuntimeError("Groww access token missing.")

    groww = groww_api(token)
    gsym = groww_symbol(symbol)
    exchange = _groww_exchange_const(groww, symbol)
    end = datetime.now()
    start = end - timedelta(days=max(365, 365 * years))
    merged: dict[str, dict[str, str]] = {}
    cursor = start

    while cursor < end:
        chunk_end = min(cursor + timedelta(days=_GROWW_DAY_CHUNK_DAYS), end)
        try:
            response = groww.get_historical_candles(
                exchange=exchange,
                segment=groww.SEGMENT_CASH,
                groww_symbol=gsym,
                start_time=cursor.strftime("%Y-%m-%d 00:00:00"),
                end_time=chunk_end.strftime("%Y-%m-%d 23:59:59"),
                candle_interval=groww.CANDLE_INTERVAL_DAY,
            )
        except Exception as exc:
            msg = str(exc)
            if "access forbidden" in msg.lower():
                raise RuntimeError(
                    f"Groww market-data API denied for {gsym} — whitelist this host's public IP "
                    f"in the Groww developer portal (or use BROKER_GATEWAY_URL on a static-IP VM)."
                ) from exc
            raise
        merged.update(_candles_to_daily_series(response.get("candles") or []))
        cursor = chunk_end + timedelta(seconds=1)

    cutoff = (date.today() - timedelta(days=365 * years)).isoformat()
    series = {day: row for day, row in merged.items() if day >= cutoff}
    if not series:
        raise RuntimeError(f"No Groww daily history was returned for {gsym}.")

    return {
        "Meta Data": {
            "source": "Groww Trade API",
            "symbol": gsym,
            "app_symbol": symbol.upper(),
        },
        "Time Series (Daily)": series,
    }
