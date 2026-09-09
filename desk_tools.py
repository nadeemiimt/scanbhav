"""Desk helpers: relative strength, position sizing, event watch, sector heat."""
from __future__ import annotations

import math
from typing import Any, Optional


def relative_strength(
    stock_returns: dict[str, Any],
    bench_returns: dict[str, Any],
    *,
    bench_label: str = "NIFTY",
) -> dict[str, Any]:
    """Stock return minus benchmark return for shared horizons."""
    out: dict[str, Any] = {"benchmark": bench_label, "horizons": {}}
    for key in ("1w", "1m", "3m", "6m", "1y"):
        s = stock_returns.get(key)
        b = bench_returns.get(key)
        if isinstance(s, (int, float)) and isinstance(b, (int, float)):
            rs = round(float(s) - float(b), 3)
            out["horizons"][key] = {
                "stock_pct": round(float(s), 3),
                "bench_pct": round(float(b), 3),
                "rs_pct": rs,
                "leading": rs > 0.5,
                "lagging": rs < -0.5,
            }
    # Headline: prefer 1m, else first available
    for key in ("1m", "3m", "1w", "6m", "1y"):
        h = out["horizons"].get(key)
        if h:
            out["headline"] = {
                "horizon": key,
                **h,
                "plain": (
                    f"Leading {bench_label} by {h['rs_pct']:+.1f}% over {key}"
                    if h["leading"]
                    else (
                        f"Lagging {bench_label} by {h['rs_pct']:.1f}% over {key}"
                        if h["lagging"]
                        else f"In line with {bench_label} over {key} ({h['rs_pct']:+.1f}%)"
                    )
                ),
            }
            break
    return out


def position_size(
    *,
    price: float,
    atr: Optional[float],
    capital: float = 100_000.0,
    risk_pct: float = 1.0,
    atr_stop_mult: float = 1.5,
    reward_r: float = 2.0,
) -> dict[str, Any]:
    """Educational ATR stop + share count from % risk of capital + R-multiple targets."""
    if price <= 0 or capital <= 0:
        raise ValueError("price and capital must be positive")
    risk_pct = max(0.1, min(5.0, float(risk_pct)))
    atr_stop_mult = max(0.5, min(4.0, float(atr_stop_mult)))
    reward_r = max(0.5, min(5.0, float(reward_r)))
    risk_rupees = capital * (risk_pct / 100.0)
    stop_distance = None
    stop_price = None
    shares = None
    notional = None
    if atr and atr > 0:
        stop_distance = round(atr * atr_stop_mult, 4)
        stop_price = round(price - stop_distance, 4)
        if stop_distance > 0:
            shares = int(risk_rupees // stop_distance)
            notional = round(shares * price, 2) if shares else 0.0
    if shares is None:
        notional_cap = capital * 0.1
        shares = int(notional_cap // price) if price else 0
        notional = round(shares * price, 2)
        stop_distance = round(price * 0.03, 4)
        stop_price = round(price - stop_distance, 4)

    targets = []
    if stop_distance and stop_distance > 0:
        for r in (1.0, reward_r, max(reward_r, 3.0)):
            targets.append({
                "r": r,
                "price": round(price + stop_distance * r, 4),
            })

    heat_pct = round((notional or 0) / capital * 100, 2) if capital else 0

    return {
        "price": round(price, 4),
        "capital": round(capital, 2),
        "risk_pct": risk_pct,
        "risk_rupees": round(risk_rupees, 2),
        "atr": round(atr, 4) if atr else None,
        "atr_stop_mult": atr_stop_mult,
        "stop_distance": stop_distance,
        "stop_price": stop_price,
        "shares": shares or 0,
        "notional": notional or 0.0,
        "position_heat_pct": heat_pct,
        "targets": targets,
        "reward_r": reward_r,
        "plain": (
            f"Risk ₹{risk_rupees:,.0f} ({risk_pct}%) → ~{shares or 0} shares, "
            f"stop ₹{stop_price}, heat {heat_pct}% of capital, "
            f"target ~{reward_r:.0f}R at ₹{targets[1]['price'] if len(targets) > 1 else '—'}."
            if stop_price is not None
            else "Insufficient data for sizing."
        ),
        "disclaimer": "Educational position sizing only — not investment advice.",
    }


def sip_projection(
    *,
    monthly: float,
    years: float = 10,
    expected_annual_return_pct: float = 12.0,
) -> dict[str, Any]:
    """Simple SIP future-value projection (educational)."""
    monthly = max(100.0, float(monthly))
    years = max(0.5, min(40.0, float(years)))
    r_yr = max(-20.0, min(30.0, float(expected_annual_return_pct))) / 100.0
    r_m = (1 + r_yr) ** (1 / 12) - 1
    n = int(round(years * 12))
    invested = monthly * n
    if abs(r_m) < 1e-12:
        fv = invested
    else:
        fv = monthly * (((1 + r_m) ** n - 1) / r_m) * (1 + r_m)
    return {
        "monthly": round(monthly, 2),
        "years": years,
        "expected_annual_return_pct": expected_annual_return_pct,
        "months": n,
        "invested": round(invested, 2),
        "projected_value": round(fv, 2),
        "gain": round(fv - invested, 2),
        "plain": (
            f"₹{monthly:,.0f}/mo for {years:g}y at {expected_annual_return_pct:g}% → "
            f"~₹{fv:,.0f} (invested ₹{invested:,.0f})."
        ),
        "disclaimer": "Illustrative math only — markets do not guarantee returns.",
    }


def portfolio_heat(holdings: list[dict[str, Any]], capital_hint: Optional[float] = None) -> dict[str, Any]:
    """Per-name weight + concentration heat from mark values."""
    rows = []
    total = 0.0
    for h in holdings or []:
        qty = float(h.get("quantity") or 0)
        px = float(h.get("mark_price") or h.get("current_price") or h.get("avg_cost") or 0)
        mv = qty * px
        if mv <= 0:
            continue
        total += mv
        rows.append({
            "symbol": h.get("symbol") or h.get("name") or "?",
            "market_value": round(mv, 2),
        })
    base = capital_hint if capital_hint and capital_hint > 0 else total
    for r in rows:
        r["weight_pct"] = round(r["market_value"] / base * 100, 2) if base else 0
        r["hot"] = r["weight_pct"] >= 25
    rows.sort(key=lambda x: x["weight_pct"], reverse=True)
    top = rows[0]["weight_pct"] if rows else 0
    return {
        "total_value": round(total, 2),
        "positions": rows,
        "top_weight_pct": top,
        "concentrated": top >= 25,
        "plain": (
            f"Top name is {top:.0f}% of book — diversify if above ~25%."
            if rows
            else "No holdings to measure heat."
        ),
    }


def market_breadth(screen_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """% of screened names above SMA200 / positive horizon return as breadth proxies."""
    rows = screen_rows or []
    n = len(rows)
    if not n:
        return {"count": 0, "above_sma200_pct": None, "positive_horizon_pct": None, "plain": "Run Screener to compute breadth."}
    above = 0
    pos = 0
    known_sma = 0
    for r in rows:
        vs = r.get("price_vs_sma_200_pct")
        if isinstance(vs, (int, float)):
            known_sma += 1
            if vs >= 0:
                above += 1
        hr = r.get("horizon_return_pct")
        if isinstance(hr, (int, float)) and hr >= 0:
            pos += 1
    above_pct = round(above / known_sma * 100, 1) if known_sma else None
    pos_pct = round(pos / n * 100, 1)
    return {
        "count": n,
        "above_sma200_pct": above_pct,
        "positive_horizon_pct": pos_pct,
        "plain": (
            f"Breadth: {above_pct}% above SMA200 · {pos_pct}% green on ranked horizon."
            if above_pct is not None
            else f"Breadth: {pos_pct}% green on ranked horizon ({n} names)."
        ),
    }


def session_levels(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Prior-day H/L, gap vs prior close, simple volume profile from chart window."""

    def _f(value: Any, default: float = 0.0) -> float:
        try:
            x = float(value)
        except (TypeError, ValueError):
            return default
        return x if math.isfinite(x) else default

    if not candles or len(candles) < 3:
        return {"available": False}
    last = candles[-1]
    prev = candles[-2]
    prior_high = _f(prev.get("high"))
    prior_low = _f(prev.get("low"))
    prior_close = _f(prev.get("close"))
    open_ = _f(last.get("open") or last.get("close"))
    close = _f(last.get("close"))
    gap_pct = round((open_ / prior_close - 1) * 100, 3) if prior_close else None
    # Volume profile: 12 price buckets over window
    highs = [_f(c.get("high")) for c in candles]
    lows = [_f(c.get("low")) for c in candles]
    positive_lows = [x for x in lows if x > 0]
    if not positive_lows or not highs:
        return {"available": False}
    lo, hi = min(positive_lows), max(highs)
    buckets = []
    if hi > lo:
        steps = 12
        width = (hi - lo) / steps
        vols = [0.0] * steps
        for c in candles:
            mid = (_f(c.get("high")) + _f(c.get("low")) + _f(c.get("close"))) / 3
            vol = _f(c.get("volume"))
            if mid <= 0 or vol <= 0 or not math.isfinite(mid):
                continue
            idx = min(steps - 1, max(0, int((mid - lo) / width)))
            vols[idx] += vol
        vmax = max(vols) or 1
        for i, v in enumerate(vols):
            buckets.append({
                "price_mid": round(lo + (i + 0.5) * width, 2),
                "volume": round(v, 0),
                "intensity": round(v / vmax, 3),
            })
    poc = max(buckets, key=lambda b: b["volume"])["price_mid"] if buckets else None
    return {
        "available": True,
        "prior_high": round(prior_high, 4),
        "prior_low": round(prior_low, 4),
        "prior_close": round(prior_close, 4),
        "last_open": round(open_, 4),
        "last_close": round(close, 4),
        "gap_pct": gap_pct,
        "gap_filled": bool(
            gap_pct is not None and (
                (gap_pct > 0 and close <= prior_close) or (gap_pct < 0 and close >= prior_close)
            )
        ),
        "opening_range_proxy": {
            "note": "Daily bars only — proxy uses prior day range as session reference (not true intraday ORB).",
            "high": round(prior_high, 4),
            "low": round(prior_low, 4),
        },
        "volume_profile": buckets,
        "poc": poc,
        "plain": (
            f"Prior day {prior_low:.0f}–{prior_high:.0f}; gap {gap_pct:+.2f}%; "
            f"POC ~{poc}."
            if gap_pct is not None and poc
            else "Session levels available."
        ),
    }


def scan_watch_alerts(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Evaluate watchlist alert rules against latest technicals snapshots."""
    alerts = []
    for it in items or []:
        sym = it.get("symbol")
        tech = it.get("technicals") or {}
        price = tech.get("price")
        rsi = (tech.get("momentum") or {}).get("rsi_14")
        rules = it.get("rules") or {}
        if price is None:
            continue
        above = rules.get("price_above")
        below = rules.get("price_below")
        rsi_hi = rules.get("rsi_above", 70)
        rsi_lo = rules.get("rsi_below", 30)
        if above is not None and price >= float(above):
            alerts.append({"symbol": sym, "level": "price", "message": f"{sym} ≥ ₹{above} (now {price})"})
        if below is not None and price <= float(below):
            alerts.append({"symbol": sym, "level": "price", "message": f"{sym} ≤ ₹{below} (now {price})"})
        if rsi is not None and rsi >= float(rsi_hi):
            alerts.append({"symbol": sym, "level": "rsi", "message": f"{sym} RSI {rsi} ≥ {rsi_hi} (stretched)"})
        if rsi is not None and rsi <= float(rsi_lo):
            alerts.append({"symbol": sym, "level": "rsi", "message": f"{sym} RSI {rsi} ≤ {rsi_lo} (soft)"})
        st = (tech.get("trend") or {}).get("supertrend_dir")
        if rules.get("supertrend_flip") and st in (1, -1):
            alerts.append({
                "symbol": sym,
                "level": "trend",
                "message": f"{sym} Supertrend {'bullish' if st == 1 else 'bearish'}",
            })
    return {"count": len(alerts), "alerts": alerts}


def event_watch(news: Optional[dict[str, Any]], dossier: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Surface earnings/event-like headlines and dossier red flags as a calendar-lite list."""
    items: list[dict[str, Any]] = []
    for h in (news or {}).get("headlines") or []:
        tag = (h.get("catalyst_tag") or "general").lower()
        if tag in {"earnings", "regulation", "rates", "geopolitics", "supply"} or h.get("high_impact"):
            items.append({
                "kind": "news",
                "tag": tag,
                "label": h.get("catalyst_label") or tag,
                "title": h.get("title") or "",
                "url": h.get("url"),
                "when": h.get("published") or h.get("date") or "",
            })
    for flag in ((dossier or {}).get("signal_radar") or {}).get("red_flags") or []:
        text = flag if isinstance(flag, str) else (flag.get("text") or flag.get("title") or str(flag))
        items.append({"kind": "risk", "tag": "risk", "label": "Risk flag", "title": text, "url": None, "when": ""})
    return {
        "count": len(items),
        "items": items[:12],
        "plain": "Event watch from catalysts + risk flags (not a formal earnings calendar).",
    }


def sector_heat_from_screen(screen: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Bucket screened names by sector when present; else by grade."""
    rows = (screen or {}).get("top") or (screen or {}).get("results") or []
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        sector = row.get("sector") or row.get("industry") or "Universe"
        b = buckets.setdefault(sector, {"sector": sector, "count": 0, "avg_score": 0.0, "up": 0, "down": 0})
        score = float(row.get("score") or 0)
        b["count"] += 1
        b["avg_score"] += score
        ch = row.get("change_pct") or row.get("horizon_return_pct") or 0
        try:
            chf = float(ch)
        except (TypeError, ValueError):
            chf = 0.0
        if chf >= 0:
            b["up"] += 1
        else:
            b["down"] += 1
    out = []
    for b in buckets.values():
        if b["count"]:
            b["avg_score"] = round(b["avg_score"] / b["count"], 2)
        out.append(b)
    out.sort(key=lambda x: x["avg_score"], reverse=True)
    return {"buckets": out[:16], "source": "last universe screen", "count": len(out)}
