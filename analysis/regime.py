"""Market regime: VIX percentile, yield curve proxy, bull/bear/sideways, FII flow input."""
from __future__ import annotations

from typing import Any, Optional

from analysis._helpers import clamp, num
from analysis.india_data import fetch_fii_dii_flows
from fetch_stock_data import fetch_yfinance_daily
from technicals import compute_technicals


def _rows_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entries = sorted(payload.get("Time Series (Daily)", {}).items())
    return [{"date": day, **values} for day, values in entries]


def _vix_context() -> dict[str, Any]:
    try:
        payload = fetch_yfinance_daily("^INDIAVIX", years=2)
        rows = _rows_from_payload(payload)
        tech = compute_technicals(rows)
        closes = [float(r.get("4. close") or r.get("5. adjusted close") or 0) for r in rows if float(r.get("4. close") or 0) > 0]
        if len(closes) < 30:
            return {"status": "unavailable"}
        last = closes[-1]
        hist = closes[-252:] if len(closes) >= 252 else closes
        below = sum(1 for x in hist if x <= last)
        percentile = round(100 * below / len(hist), 1)
        label = "elevated_fear" if percentile >= 75 else ("complacent" if percentile <= 25 else "normal")
        return {
            "status": "ok",
            "vix": round(last, 2),
            "percentile_1y": percentile,
            "label": label,
        }
    except Exception:
        return {"status": "unavailable"}


def _yield_curve_proxy() -> dict[str, Any]:
    try:
        y10 = fetch_yfinance_daily("^TNX", years=1)
        y2 = fetch_yfinance_daily("^IRX", years=1)
        r10 = _rows_from_payload(y10)
        r2 = _rows_from_payload(y2)
        t10 = compute_technicals(r10)
        t2 = compute_technicals(r2)
        spread = (t10.get("price") or 0) - (t2.get("price") or 0)
        inverted = spread < 0
        return {"status": "ok", "us_10y": t10.get("price"), "us_3m_proxy": t2.get("price"), "spread_bps_proxy": round(spread * 100, 1), "inverted": inverted}
    except Exception:
        return {"status": "unavailable", "note": "India G-Sec curve needs RBI feed."}


def classify_regime(vix: dict[str, Any], fii: dict[str, Any], tech: dict[str, Any]) -> dict[str, Any]:
    ma = tech.get("moving_averages") or {}
    vs200 = num(ma.get("price_vs_sma_200_pct")) or 0
    vix_pct = num(vix.get("percentile_1y")) or 50
    score = 50.0
    if vs200 > 5:
        score += 15
    elif vs200 < -5:
        score -= 15
    if vix_pct >= 70:
        score -= 10
    elif vix_pct <= 30:
        score += 5
    flows = fii.get("flows") if isinstance(fii.get("flows"), list) else []
    fii_net = None
    if flows:
        try:
            fii_net = num(flows[0].get("fiiNet")) or num(flows[0].get("fii_net"))
        except Exception:
            pass
    if fii_net is not None:
        score += 5 if fii_net > 0 else -5
    score = clamp(score)
    if score >= 65:
        regime = "bull"
    elif score <= 35:
        regime = "bear"
    else:
        regime = "sideways"
    return {
        "regime": regime,
        "regime_score": round(score, 1),
        "drivers": {
            "price_vs_sma200_pct": vs200,
            "vix_percentile": vix_pct,
            "fii_net_latest": fii_net,
        },
    }


def commodity_sector_beta(sector: Optional[str]) -> dict[str, Any]:
    betas = {
        "Energy": {"crude": 0.7, "inr": -0.3},
        "Metal": {"crude": 0.2, "usd_inr": 0.4},
        "FMCG": {"crude": -0.1, "inr": 0.1},
        "IT": {"usd_inr": 0.5},
    }
    if not sector:
        return {"betas": {}}
    for key, b in betas.items():
        if key.lower() in sector.lower():
            return {"sector": sector, "commodity_betas": b}
    return {"sector": sector, "commodity_betas": {}}


def compute_regime(tech: dict[str, Any], quote: dict[str, Any] | None = None) -> dict[str, Any]:
    vix = _vix_context()
    fii = fetch_fii_dii_flows()
    regime = classify_regime(vix, fii, tech)
    sector = ((quote or {}).get("company") or {}).get("sector")
    return {
        "vix": vix,
        "yield_curve": _yield_curve_proxy(),
        "fii_dii_flows": fii,
        "regime": regime,
        "commodity_betas": commodity_sector_beta(sector),
    }
