"""Options chain context: PCR, OI, max pain, IV (NSE when available)."""
from __future__ import annotations

import time
from typing import Any, Optional

import requests

from fetch_stock_data import nse_symbol


def fetch_option_chain(symbol: str) -> dict[str, Any]:
    sym = nse_symbol(symbol)
    try:
        session = requests.Session()
        session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        })
        session.get("https://www.nseindia.com/", timeout=15)
        time.sleep(0.3)
        r = session.get(
            "https://www.nseindia.com/api/option-chain-equities",
            params={"symbol": sym},
            timeout=25,
        )
        if r.status_code != 200:
            return {"status": "unavailable", "symbol": sym}
        data = r.json()
        records = data.get("records") or {}
        data_rows = records.get("data") or []
        if not data_rows:
            return {"status": "empty", "symbol": sym}
        ce_oi = pe_oi = 0
        strikes: dict[float, dict[str, float]] = {}
        for row in data_rows:
            strike = row.get("strikePrice")
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            ce_o = float(ce.get("openInterest") or 0)
            pe_o = float(pe.get("openInterest") or 0)
            ce_oi += ce_o
            pe_oi += pe_o
            if strike is not None:
                strikes[float(strike)] = {"ce_oi": ce_o, "pe_oi": pe_o}
        pcr = round(pe_oi / ce_oi, 3) if ce_oi else None
        max_pain = _max_pain(strikes, records.get("underlyingValue"))
        iv = _avg_iv(data_rows)
        return {
            "status": "ok",
            "source": "NSE",
            "symbol": sym,
            "pcr_oi": pcr,
            "total_ce_oi": int(ce_oi),
            "total_pe_oi": int(pe_oi),
            "max_pain": max_pain,
            "avg_iv_pct": iv,
            "underlying": records.get("underlyingValue"),
            "expiry": records.get("expiryDates", [None])[0] if records.get("expiryDates") else None,
        }
    except Exception as exc:
        return {"status": "error", "symbol": sym, "error": str(exc)[:120]}


def _max_pain(strikes: dict[float, dict[str, float]], spot: Optional[float]) -> Optional[float]:
    if not strikes:
        return spot
    best_strike = min(strikes.keys(), key=lambda s: _pain_at(strikes, s))
    return round(best_strike, 2)


def _pain_at(strikes: dict[float, dict[str, float]], at: float) -> float:
    pain = 0.0
    for strike, oi in strikes.items():
        ce, pe = oi.get("ce_oi", 0), oi.get("pe_oi", 0)
        pain += max(0, at - strike) * ce + max(0, strike - at) * pe
    return pain


def _avg_iv(rows: list[dict[str, Any]]) -> Optional[float]:
    ivs = []
    for row in rows:
        for side in ("CE", "PE"):
            iv = (row.get(side) or {}).get("impliedVolatility")
            if iv:
                try:
                    ivs.append(float(iv))
                except (TypeError, ValueError):
                    pass
    return round(sum(ivs) / len(ivs), 2) if ivs else None


def compute_options_context(symbol: str) -> dict[str, Any]:
    chain = fetch_option_chain(symbol)
    bias = "neutral"
    if chain.get("pcr_oi"):
        pcr = chain["pcr_oi"]
        bias = "bullish" if pcr > 1.2 else ("bearish" if pcr < 0.8 else "neutral")
    chain["pcr_bias"] = bias
    return chain
