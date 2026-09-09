"""Fetch auditable Alpha Vantage data and save raw provider responses locally."""
from __future__ import annotations

import argparse
import json
import re
import time as time_mod
from datetime import date, datetime, timedelta, time
from pathlib import Path
from typing import Any

from alpha_vantage import AlphaVantageClient
from alpha_vantage import AlphaVantageError
from config import BASE_DIR


def _fetch_logger():
    from utils.logging_config import get_logger

    return get_logger(__name__)


def log_fetch_fallback_success(
    symbol: str,
    *,
    yahoo_error: str,
    source: str,
    rows: int,
    data_kind: str = "daily",
) -> None:
    """WARN when Yahoo missed data but a fallback provider succeeded."""
    _fetch_logger().warning(
        "Yahoo had no %s data for %s (%s) — loaded from %s (%s rows)",
        data_kind,
        symbol.upper(),
        yahoo_error[:120],
        source,
        rows,
    )


def log_fetch_total_failure(symbol: str, *, data_kind: str, detail: str) -> None:
    """ERROR when every provider in the chain failed."""
    _fetch_logger().error(
        "Failed to fetch %s data for %s: %s",
        data_kind,
        symbol.upper(),
        detail[:400],
    )


def safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())


def save(directory: Path, name: str, payload: dict[str, Any]) -> None:
    (directory / f"{name}.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def yahoo_symbol(symbol: str) -> str:
    """Map app exchange suffix to Yahoo Finance ticker.

    App uses Alpha Vantage-style suffixes; Yahoo uses its own:
      RELIANCE.NSE  -> RELIANCE.NS   (NSE — finance.yahoo.com/quote/RELIANCE.NS)
      RELIANCE.BSE  -> RELIANCE.BO   (BSE — finance.yahoo.com/quote/RELIANCE.BO)
    """
    upper = symbol.upper()
    if upper.endswith(".BSE"):
        return f"{upper[:-4]}.BO"
    if upper.endswith(".NSE"):
        return f"{upper[:-4]}.NS"
    return upper


def fetch_yfinance_daily(symbol: str, years: int) -> dict[str, Any]:
    """Return Yahoo daily history in the same shape consumed by build_stock_input.py."""
    import yfinance as yf

    history = yf.Ticker(yahoo_symbol(symbol)).history(period=f"{years}y", auto_adjust=False)
    if history.empty:
        raise RuntimeError(f"No Yahoo Finance daily history was returned for {yahoo_symbol(symbol)}.")
    series = {}
    for timestamp, row in history.iterrows():
        day = timestamp.strftime("%Y-%m-%d")
        series[day] = {
            "1. open": str(row["Open"]), "2. high": str(row["High"]),
            "3. low": str(row["Low"]), "4. close": str(row["Close"]),
            "5. adjusted close": str(row.get("Adj Close", row["Close"])),
            "6. volume": str(row["Volume"]),
        }
    return {"Meta Data": {"source": "Yahoo Finance", "symbol": yahoo_symbol(symbol)}, "Time Series (Daily)": series}


def fetch_yfinance_daily_batch(symbols: list[str], years: int = 5) -> dict[str, dict[str, Any]]:
    """Download many symbols in one Yahoo call for faster multi-stock screens."""
    import yfinance as yf

    yahoo_map = {yahoo_symbol(symbol): symbol for symbol in symbols}
    tickers = " ".join(yahoo_map.keys())
    period = f"{years}y"
    raw = yf.download(
        tickers=tickers,
        period=period,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )
    out: dict[str, dict[str, Any]] = {}
    if raw is None or raw.empty:
        return out

    # Single-ticker download has flat columns; multi has MultiIndex.
    if len(yahoo_map) == 1:
        yahoo = next(iter(yahoo_map))
        frame = raw
        series = {}
        for timestamp, row in frame.iterrows():
            day = timestamp.strftime("%Y-%m-%d")
            series[day] = {
                "1. open": str(row["Open"]), "2. high": str(row["High"]),
                "3. low": str(row["Low"]), "4. close": str(row["Close"]),
                "5. adjusted close": str(row.get("Adj Close", row["Close"])),
                "6. volume": str(row["Volume"]),
            }
        out[yahoo_map[yahoo]] = {"Meta Data": {"source": "Yahoo Finance", "symbol": yahoo}, "Time Series (Daily)": series}
        return out

    for yahoo, original in yahoo_map.items():
        try:
            frame = raw[yahoo].dropna(how="all")
        except Exception:
            continue
        if frame.empty:
            continue
        series = {}
        for timestamp, row in frame.iterrows():
            if row.get("Close") != row.get("Close"):
                continue
            day = timestamp.strftime("%Y-%m-%d")
            series[day] = {
                "1. open": str(row["Open"]), "2. high": str(row["High"]),
                "3. low": str(row["Low"]), "4. close": str(row["Close"]),
                "5. adjusted close": str(row.get("Adj Close", row["Close"])),
                "6. volume": str(row.get("Volume", 0)),
            }
        if series:
            out[original] = {"Meta Data": {"source": "Yahoo Finance", "symbol": yahoo}, "Time Series (Daily)": series}
    return out


def fetch_yfinance_company_data(symbol: str) -> dict[str, Any]:
    """Fetch quote and profile fields separately from the end-of-day candles.

    Prefer ``fast_info`` for price fields (much cheaper); only hit the heavy
    ``info`` payload when name/sector/industry are still missing.
    """
    import yfinance as yf

    ticker = yf.Ticker(yahoo_symbol(symbol))
    try:
        fast = dict(ticker.fast_info)
    except Exception:
        fast = {}

    info: dict[str, Any] = {}
    need_profile = True
    # Try a lighter path first when available.
    try:
        get_info = getattr(ticker, "get_info", None)
        if callable(get_info):
            info = get_info() or {}
            need_profile = False
        else:
            info = ticker.info or {}
            need_profile = False
    except Exception:
        if need_profile:
            try:
                info = ticker.info or {}
            except Exception:
                info = {}

    def value(*names: str) -> Any:
        for name in names:
            candidate = fast.get(name, info.get(name))
            if candidate is not None:
                try:
                    return float(candidate)
                except (TypeError, ValueError):
                    return candidate
        return None

    officers_raw = info.get("companyOfficers") or []
    officers: list[dict[str, Any]] = []
    for o in officers_raw[:10]:
        if not isinstance(o, dict):
            continue
        officers.append({
            "name": o.get("name"),
            "title": o.get("title"),
            "age": o.get("age"),
            "yearBorn": o.get("yearBorn"),
        })
    ceo = None
    for o in officers:
        title = str(o.get("title") or "").lower()
        if "chief executive" in title or title.strip() == "ceo" or "managing director" in title:
            ceo = o
            break
    if not ceo and officers:
        ceo = officers[0]

    return {
        "name": info.get("longName") or info.get("shortName") or fast.get("shortName"),
        "symbol": yahoo_symbol(symbol),
        "currency": info.get("currency") or fast.get("currency"),
        "live_price": value("lastPrice", "regularMarketPrice", "currentPrice"),
        "previous_close": value("previousClose", "regularMarketPreviousClose"),
        "day_open": value("open", "regularMarketOpen"),
        "day_high": value("dayHigh", "regularMarketDayHigh"),
        "day_low": value("dayLow", "regularMarketDayLow"),
        "volume": value("lastVolume", "regularMarketVolume"),
        "average_volume": value("threeMonthAverageVolume", "averageVolume"),
        "fifty_two_week_high": value("yearHigh", "fiftyTwoWeekHigh"),
        "fifty_two_week_low": value("yearLow", "fiftyTwoWeekLow"),
        "market_cap": value("marketCap"),
        "trailing_pe": value("trailingPE"),
        "forward_pe": value("forwardPE"),
        "eps_ttm": value("trailingEps"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "website": info.get("website"),
        "dividend_yield_pct": value("dividendYield"),
        "peg_ratio": value("pegRatio"),
        "beta": value("beta"),
        "enterprise_to_ebitda": value("enterpriseToEbitda"),
        "price_to_book": value("priceToBook"),
        "full_time_employees": info.get("fullTimeEmployees"),
        "officers": officers,
        "ceo": ceo,
        "data_note": "Quote/profile fields can be live, delayed, or unavailable; chart values are end-of-day candles.",
    }



def fetch_yfinance_fundamentals(symbol: str) -> dict[str, Any]:
    """Calculate analysis-ready fields from Yahoo's annual financial statements."""
    import yfinance as yf

    ticker = yf.Ticker(yahoo_symbol(symbol))

    def pair(frame: Any, row_name: str) -> tuple[Any, Any]:
        try:
            values = frame.loc[row_name].dropna().tolist()
            current = float(values[0]) if values else None
            previous = float(values[1]) if len(values) > 1 else None
            return current, previous
        except (AttributeError, KeyError, TypeError, ValueError):
            return None, None

    try:
        income = ticker.income_stmt
        balance = ticker.balance_sheet
        cashflow = ticker.cashflow
    except Exception:
        return {}
    revenue, prior_revenue = pair(income, "Total Revenue")
    gross_profit, _ = pair(income, "Gross Profit")
    operating_income, _ = pair(income, "Operating Income")
    net_income, _ = pair(income, "Net Income")
    eps, _ = pair(income, "Diluted EPS")
    total_debt, _ = pair(balance, "Total Debt")
    equity, _ = pair(balance, "Stockholders Equity")
    current_assets, _ = pair(balance, "Current Assets")
    current_liabilities, _ = pair(balance, "Current Liabilities")
    free_cash_flow, _ = pair(cashflow, "Free Cash Flow")
    operating_cash_flow, _ = pair(cashflow, "Operating Cash Flow")

    def ratio(numerator: Any, denominator: Any) -> Any:
        return round(numerator / denominator * 100, 2) if numerator is not None and denominator not in (None, 0) else None

    return {
        "revenue": revenue,
        "revenue_growth_yoy_pct": ratio(revenue - prior_revenue if revenue is not None and prior_revenue is not None else None, prior_revenue),
        "gross_margin_pct": ratio(gross_profit, revenue),
        "operating_margin_pct": ratio(operating_income, revenue),
        "net_margin_pct": ratio(net_income, revenue),
        "free_cash_flow": free_cash_flow,
        "operating_cash_flow": operating_cash_flow,
        "debt_to_equity": round(total_debt / equity, 3) if total_debt is not None and equity not in (None, 0) else None,
        "current_ratio": round(current_assets / current_liabilities, 2) if current_assets is not None and current_liabilities not in (None, 0) else None,
        "roe_pct": ratio(net_income, equity),
        "eps": eps,
        "source": "Yahoo Finance annual financial statements",
        "note": "Ratios use the latest annual statement values made available by Yahoo Finance."
    }



def fetch_yfinance_news(symbol: str, limit: int = 8) -> list[dict[str, Any]]:
    """Return recent headlines for the symbol from Yahoo Finance's news feed.

    Only fields provided by Yahoo are kept (title, publisher, link, published date,
    and a short summary if present). Returns an empty list if news is unavailable.
    """
    import yfinance as yf

    try:
        raw_items = yf.Ticker(yahoo_symbol(symbol)).news or []
    except Exception:
        return []

    items: list[dict[str, Any]] = []
    for raw in raw_items[:limit]:
        content = raw.get("content", raw)
        provider = content.get("provider") or {}
        link = content.get("clickThroughUrl") or content.get("canonicalUrl") or {}
        title = content.get("title")
        if not title:
            continue
        items.append({
            "title": title,
            "summary": content.get("summary") or content.get("description") or None,
            "publisher": provider.get("displayName"),
            "published_at": content.get("pubDate") or content.get("displayTime"),
            "url": link.get("url"),
        })
    return items


def nse_symbol(symbol: str) -> str:
    """NSE uses its bare security symbol, e.g. RELIANCE rather than RELIANCE.NSE."""
    upper = symbol.upper()
    return upper.removesuffix(".NSE").removesuffix(".BSE")


def parse_nse_date(value: str) -> str:
    for pattern in ("%d-%b-%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized NSE date: {value}")


_CHARTING_BASE = "https://charting.nseindia.com"
_CHARTING_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _charting_session():
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": _CHARTING_UA,
        "Accept": "application/json, text/plain, */*",
        "Referer": f"{_CHARTING_BASE}/",
    })
    session.get(f"{_CHARTING_BASE}/", timeout=30)
    return session


def _resolve_charting_instrument(session, base_sym: str) -> tuple[str, str]:
    """Return (chart_symbol, scripcode token) from charting.nseindia.com."""
    response = session.get(
        f"{_CHARTING_BASE}/v1/exchanges/symbolsDynamic",
        params={"symbol": base_sym, "segment": ""},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise RuntimeError(f"No NSE charting symbol info for {base_sym}.")

    upper = base_sym.upper()
    preferred = [upper, f"{upper}-EQ", f"{upper}-ST", f"{upper}-BE", f"{upper}-SM"]
    for candidate in preferred:
        for row in rows:
            if str(row.get("symbol", "")).upper() == candidate:
                token = row.get("scripcode") or row.get("token")
                if token is not None:
                    return str(row["symbol"]), str(token)

    row = rows[0]
    token = row.get("scripcode") or row.get("token")
    if token is None:
        raise RuntimeError(f"No scripcode for NSE charting symbol {base_sym}.")
    return str(row["symbol"]), str(token)


def _chart_bars_to_daily_series(bars: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    from datetime import timezone

    series: dict[str, dict[str, str]] = {}
    for bar in bars or []:
        ts_ms = bar.get("time")
        if ts_ms is None:
            continue
        day = datetime.fromtimestamp(float(ts_ms) / 1000.0, tz=timezone.utc).date().isoformat()
        close = bar.get("close")
        series[day] = {
            "1. open": str(bar.get("open", "")),
            "2. high": str(bar.get("high", "")),
            "3. low": str(bar.get("low", "")),
            "4. close": str(close),
            "5. adjusted close": str(close),
            "6. volume": str(bar.get("volume") or 0),
        }
    return series


def _fetch_charting_bars(
    session,
    chart_symbol: str,
    token: str,
    *,
    days: int,
    chart_type: str,
    interval_minutes: str | int,
) -> list[dict[str, Any]]:
    end = date.today()
    start = end - timedelta(days=max(1, days))
    from_ts = int(datetime.combine(start, time.min).timestamp())
    to_ts = int(datetime.combine(end, time.max).timestamp())
    response = session.get(
        f"{_CHARTING_BASE}/v1/charts/symbolHistoricalData",
        params={
            "fromDate": from_ts,
            "toDate": to_ts,
            "symbol": chart_symbol,
            "token": token,
            "symbolType": "Equity",
            "chartType": chart_type,
            "timeInterval": str(interval_minutes),
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    bars = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(bars, list):
        return []
    return bars


def fetch_nse_charting_intraday(
    symbol: str,
    *,
    interval_minutes: int = 60,
    days: int = 10,
) -> list[dict[str, Any]]:
    """Intraday OHLCV from NSE charting (5/15/60 minute bars)."""
    if symbol.upper().endswith(".BSE"):
        raise RuntimeError("NSE charting does not serve BSE symbols.")
    base_sym = nse_symbol(symbol)
    session = _charting_session()
    chart_symbol, token = _resolve_charting_instrument(session, base_sym)
    bars = _fetch_charting_bars(
        session,
        chart_symbol,
        token,
        days=days,
        chart_type="I",
        interval_minutes=interval_minutes,
    )
    if not bars:
        raise RuntimeError(f"No NSE intraday bars for {chart_symbol} ({interval_minutes}m).")
    time_mod.sleep(0.25)
    return bars


def fetch_nse_ltp(symbol: str) -> float:
    """Latest traded price from NSE charting 5-minute bars (NSE-listed only)."""
    bars = fetch_nse_charting_intraday(symbol, interval_minutes=5, days=2)
    last = bars[-1].get("close")
    price = float(last) if last is not None else 0.0
    if price <= 0:
        raise RuntimeError(f"No NSE LTP for {nse_symbol(symbol)}.")
    return price


def fetch_nse_charting_daily(symbol: str, years: int) -> dict[str, Any]:
    """Daily OHLCV via charting.nseindia.com (works when /api/historical/cm/equity 503s)."""
    base_sym = nse_symbol(symbol)
    session = _charting_session()
    chart_symbol, token = _resolve_charting_instrument(session, base_sym)
    end = date.today()
    start = end - timedelta(days=365 * years)
    from_ts = int(datetime.combine(start, time.min).timestamp())
    to_ts = int(datetime.combine(end, time.max).timestamp())
    response = session.get(
        f"{_CHARTING_BASE}/v1/charts/symbolHistoricalData",
        params={
            "fromDate": from_ts,
            "toDate": to_ts,
            "symbol": chart_symbol,
            "token": token,
            "symbolType": "Equity",
            "chartType": "D",
            "timeInterval": "1",
        },
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    bars = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(bars, list) or not bars:
        raise RuntimeError(f"No NSE charting daily bars for {chart_symbol}.")
    cutoff = (date.today() - timedelta(days=365 * years)).isoformat()
    series = {day: row for day, row in _chart_bars_to_daily_series(bars).items() if day >= cutoff}
    if not series:
        raise RuntimeError(f"No NSE charting daily rows in range for {chart_symbol}.")
    time_mod.sleep(0.35)
    return {
        "Meta Data": {
            "source": "NSE charting API",
            "symbol": base_sym,
            "chart_symbol": chart_symbol,
            "token": token,
        },
        "Time Series (Daily)": series,
    }


def fetch_nse_historical_cm_daily(symbol: str, years: int) -> dict[str, Any]:
    """Download NSE equity history through the legacy public endpoint."""
    import requests

    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.nseindia.com/",
    })
    session.get("https://www.nseindia.com/", timeout=30)
    end = date.today()
    start = end - timedelta(days=365 * years)
    rows: dict[str, dict[str, str]] = {}
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=360), end)
        response = session.get(
            "https://www.nseindia.com/api/historical/cm/equity",
            params={
                "symbol": nse_symbol(symbol),
                "series": '["EQ"]',
                "from": cursor.strftime("%d-%m-%Y"),
                "to": chunk_end.strftime("%d-%m-%Y"),
            },
            timeout=45,
        )
        response.raise_for_status()
        payload = response.json()
        for row in payload.get("data", []):
            raw_day = row.get("CH_TIMESTAMP") or row.get("mTIMESTAMP")
            if not raw_day:
                continue
            day = parse_nse_date(raw_day)
            rows[day] = {
                "1. open": str(row.get("CH_OPENING_PRICE", "")),
                "2. high": str(row.get("CH_TRADE_HIGH_PRICE", "")),
                "3. low": str(row.get("CH_TRADE_LOW_PRICE", "")),
                "4. close": str(row.get("CH_CLOSING_PRICE", "")),
                # NSE history is as-traded; adjusted close is unavailable here.
                "5. adjusted close": str(row.get("CH_CLOSING_PRICE", "")),
                "6. volume": str(row.get("CH_TOT_TRADED_QTY", "")),
            }
        cursor = chunk_end + timedelta(days=1)
        time_mod.sleep(0.6)
    if not rows:
        raise RuntimeError(f"No NSE equity history was returned for {nse_symbol(symbol)}.")
    return {"Meta Data": {"source": "NSE public historical endpoint", "symbol": nse_symbol(symbol)}, "Time Series (Daily)": rows}


def fetch_nse_daily(symbol: str, years: int) -> dict[str, Any]:
    """NSE daily OHLCV — charting API first, legacy historical endpoint as backup."""
    if symbol.upper().endswith(".BSE"):
        raise RuntimeError("NSE endpoints do not serve BSE symbols.")
    errors: list[str] = []
    try:
        return fetch_nse_charting_daily(symbol, years)
    except Exception as exc:
        errors.append(f"charting: {exc}")
    try:
        return fetch_nse_historical_cm_daily(symbol, years)
    except Exception as exc:
        errors.append(f"historical: {exc}")
    raise RuntimeError("; ".join(errors))


def groww_data_enabled() -> bool:
    from config import setting

    return setting("GROWW_DATA_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def fetch_daily_auto(
    symbol: str,
    years: int,
    *,
    allow_nse_fallback: bool = True,
    allow_groww_fallback: bool | None = None,
) -> dict[str, Any]:
    """Yahoo → NSE chain for daily OHLCV (Groww optional via GROWW_DATA_ENABLED)."""
    if allow_groww_fallback is None:
        allow_groww_fallback = groww_data_enabled()
    errors: list[str] = []
    yahoo_error: str | None = None
    try:
        return fetch_yfinance_daily(symbol, years)
    except Exception as exc:
        yahoo_error = str(exc)
        errors.append(f"Yahoo: {exc}")

    if allow_nse_fallback and not symbol.upper().endswith(".BSE"):
        try:
            payload = fetch_nse_daily(symbol, years)
            if yahoo_error:
                source = str(payload.get("Meta Data", {}).get("source") or "NSE")
                row_count = len(payload.get("Time Series (Daily)", {}))
                log_fetch_fallback_success(
                    symbol,
                    yahoo_error=yahoo_error,
                    source=source,
                    rows=row_count,
                    data_kind="daily",
                )
            return payload
        except Exception as exc:
            errors.append(f"NSE: {exc}")

    if allow_groww_fallback:
        try:
            from brokers.groww_data import fetch_groww_daily, groww_data_available

            if groww_data_available():
                payload = fetch_groww_daily(symbol, years)
                if yahoo_error:
                    source = str(payload.get("Meta Data", {}).get("source") or "Groww")
                    row_count = len(payload.get("Time Series (Daily)", {}))
                    log_fetch_fallback_success(
                        symbol,
                        yahoo_error=yahoo_error,
                        source=source,
                        rows=row_count,
                        data_kind="daily",
                    )
                return payload
            errors.append("Groww: credentials or SDK not configured")
        except Exception as exc:
            errors.append(f"Groww: {exc}")

    detail = "; ".join(errors)
    log_fetch_total_failure(symbol, data_kind="daily", detail=detail)
    raise RuntimeError(detail)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Alpha Vantage market data to local JSON files.")
    parser.add_argument("symbol", help="Provider symbol, e.g. RELIANCE.BSE or IBM")
    parser.add_argument("--years", type=int, default=5, help="daily history retained in the local file")
    parser.add_argument("--provider", choices=("auto", "alpha", "yfinance", "nse", "groww"), default="auto", help="price-history provider; auto tries Yahoo → NSE")
    parser.add_argument("--fundamentals", action="store_true", help="also fetch overview, statements, cash flow, and earnings")
    parser.add_argument("--news", action="store_true", help="also fetch recent news sentiment")
    args = parser.parse_args()
    if args.years < 1:
        raise SystemExit("--years must be at least 1")

    target = BASE_DIR / "data" / "raw" / safe_name(args.symbol)
    target.mkdir(parents=True, exist_ok=True)

    client = None
    if args.provider == "alpha":
        client = AlphaVantageClient()
        daily = client.query("TIME_SERIES_DAILY_ADJUSTED", symbol=args.symbol, outputsize="full")
        provider = "Alpha Vantage"
    elif args.provider == "nse":
        daily = fetch_nse_daily(args.symbol, args.years)
        provider = daily.get("Meta Data", {}).get("source", "NSE")
    elif args.provider == "yfinance":
        daily = fetch_yfinance_daily(args.symbol, args.years)
        provider = "Yahoo Finance"
    elif args.provider == "groww":
        from brokers.groww_data import fetch_groww_daily

        daily = fetch_groww_daily(args.symbol, args.years)
        provider = "Groww Trade API"
    else:
        daily = fetch_daily_auto(args.symbol, args.years)
        provider = daily.get("Meta Data", {}).get("source", "auto")
    series = daily.get("Time Series (Daily)", {})
    cutoff = (date.today() - timedelta(days=365 * args.years)).isoformat()
    daily["Time Series (Daily)"] = {day: row for day, row in series.items() if day >= cutoff}
    if not daily["Time Series (Daily)"]:
        raise SystemExit("No daily rows were returned for the selected date range and symbol.")
    save(target, "daily_adjusted", daily)
    print(f"Saved {len(daily['Time Series (Daily)'])} daily rows from {provider} to {target}")

    if args.fundamentals:
        client = client or AlphaVantageClient()
        for function, filename in (
            ("OVERVIEW", "overview"),
            ("INCOME_STATEMENT", "income_statement"),
            ("BALANCE_SHEET", "balance_sheet"),
            ("CASH_FLOW", "cash_flow"),
            ("EARNINGS", "earnings"),
        ):
            try:
                save(target, filename, client.query(function, symbol=args.symbol))
                print(f"Saved {filename}.json")
            except AlphaVantageError as exc:
                print(f"Skipped {filename}: {exc}")
    if args.news:
        client = client or AlphaVantageClient()
        try:
            save(target, "news_sentiment", client.query("NEWS_SENTIMENT", tickers=args.symbol, limit="50"))
            print("Saved news_sentiment.json")
        except AlphaVantageError as exc:
            print(f"Skipped news_sentiment: {exc}")


if __name__ == "__main__":
    main()
