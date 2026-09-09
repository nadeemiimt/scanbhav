"""Deep stock dossier: applied technicals, competitive edge, conviction ensemble.

Educational research helpers for normal users — not investment advice and not a
guarantee of prediction accuracy. Scores are transparent multi-factor heuristics.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from market_signals import build_critical_signals


def _num(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _pct(value: Optional[float], digits: int = 2) -> Optional[float]:
    if value is None:
        return None
    return round(value, digits)


def _signal(score: int) -> str:
    if score >= 1:
        return "bullish"
    if score <= -1:
        return "bearish"
    return "neutral"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def build_technical_board(tech: dict[str, Any], guide: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Every applied technical parameter with value, signal, and plain-English read."""
    guide = guide or {}
    ma = tech.get("moving_averages") or {}
    mom = tech.get("momentum") or {}
    vol = tech.get("volatility") or {}
    trend = tech.get("trend") or {}
    volume = tech.get("volume") or {}
    levels = tech.get("levels") or {}
    rets = tech.get("returns_pct") or {}
    price = _num(tech.get("price"))

    rows: list[dict[str, Any]] = []

    def add(
        key: str,
        group: str,
        label: str,
        value: Any,
        *,
        unit: str = "",
        score: int = 0,
        applied: str,
        plain: str,
    ) -> None:
        g = guide.get(key) or {}
        rows.append({
            "key": key,
            "group": group,
            "label": g.get("title") or label,
            "value": value,
            "unit": unit,
            "signal": _signal(score),
            "score": score,
            "applied": applied,
            "plain_english": plain,
            "what": g.get("what"),
            "why": g.get("why"),
        })

    # --- Moving averages ---
    for key, label in [
        ("sma_20", "SMA 20"), ("sma_50", "SMA 50"), ("sma_100", "SMA 100"), ("sma_200", "SMA 200"),
        ("ema_9", "EMA 9"), ("ema_21", "EMA 21"), ("ema_50", "EMA 50"), ("ema_200", "EMA 200"),
    ]:
        val = _num(ma.get(key))
        score = 0
        plain = "Not enough history yet."
        applied = f"{label} is part of the trend stack."
        if price is not None and val is not None:
            score = 1 if price >= val else -1
            side = "above" if score > 0 else "below"
            plain = f"Price is {side} {label} ({val:.2f}) — short-hand for {'buyers' if score > 0 else 'sellers'} owning that timeframe."
            applied = f"Applied: compare price {price:.2f} vs {label}."
        add(key, "Moving averages", label, val, score=score, applied=applied, plain=plain)

    for key, label, good in [
        ("golden_cross", "Golden cross", True),
        ("death_cross", "Death cross", False),
        ("ema_stack_bullish", "EMA stack bullish", True),
    ]:
        flag = bool(ma.get(key))
        if key == "death_cross":
            score = -1 if flag else 0
            plain = "SMA50 is below SMA200 (long-term caution)." if flag else "No death cross right now."
        else:
            score = 1 if flag else 0
            plain = f"{label} is active." if flag else f"{label} is not active."
        add(key, "Moving averages", label, 1 if flag else 0, score=score,
            applied=f"Rule flag checked: {label}.", plain=plain)

    # --- Momentum ---
    rsi14 = _num(mom.get("rsi_14"))
    if rsi14 is not None:
        score = 1 if 45 <= rsi14 <= 68 else (-1 if rsi14 >= 72 or rsi14 <= 30 else 0)
        if rsi14 >= 72:
            plain = f"RSI {rsi14:.1f} looks stretched/overbought — rallies can pause."
        elif rsi14 <= 30:
            plain = f"RSI {rsi14:.1f} looks oversold — bounce risk/reward improves, but downtrends can stay weak."
        elif rsi14 >= 50:
            plain = f"RSI {rsi14:.1f} sits in a constructive momentum zone."
        else:
            plain = f"RSI {rsi14:.1f} is soft — momentum not clearly on the buyers’ side."
        add("rsi_14", "Momentum", "RSI 14", rsi14, score=score, applied="14-day RSI applied to closes.", plain=plain)

    rsi7 = _num(mom.get("rsi_7"))
    if rsi7 is not None:
        score = 1 if rsi7 >= 55 else (-1 if rsi7 <= 35 else 0)
        add("rsi_7", "Momentum", "RSI 7", rsi7, score=score,
            applied="Faster RSI for short swings.",
            plain=f"Short-cycle RSI is {rsi7:.1f}.")

    hist = _num(mom.get("macd_hist"))
    if hist is not None:
        score = 1 if hist > 0 else -1
        add("macd_hist", "Momentum", "MACD histogram", hist, score=score,
            applied="MACD 12/26/9 histogram applied.",
            plain="MACD histogram positive — short momentum ahead of signal." if score > 0
            else "MACD histogram negative — short momentum lagging.")

    for key, label, bull_above, bear_below in [
        ("stoch_k", "Stochastic %K", 50, 20),
        ("cci_20", "CCI 20", 0, -100),
        ("mfi_14", "MFI 14", 50, 20),
        ("roc_12", "ROC 12", 0, -5),
    ]:
        val = _num(mom.get(key))
        if val is None:
            continue
        unit = "%" if key == "roc_12" else ""
        score = 1 if val >= bull_above else (-1 if val <= bear_below else 0)
        add(key, "Momentum", label, val, unit=unit, score=score,
            applied=f"{label} oscillator applied.",
            plain=f"{label} reads {val:.2f}{unit}.")

    wr = _num(mom.get("williams_r"))
    if wr is not None:
        score = 1 if wr > -50 else (-1 if wr < -80 else 0)
        add("williams_r", "Momentum", "Williams %R", wr, score=score,
            applied="Williams %R 14 applied.",
            plain=f"Williams %R at {wr:.1f} (near 0 = hot; near -100 = washed out).")

    # --- Trend / volatility / volume ---
    adx = _num(trend.get("adx_14"))
    if adx is not None:
        score = 1 if adx >= 25 else 0
        add("adx_14", "Trend", "ADX 14", adx, score=score,
            applied="ADX measures trend strength (not direction alone).",
            plain=f"ADX {adx:.1f} means {'a strong trend is in force' if adx >= 25 else 'a quieter / range-like tape'}.")

    plus_di, minus_di = _num(trend.get("plus_di")), _num(trend.get("minus_di"))
    if plus_di is not None and minus_di is not None:
        score = 1 if plus_di > minus_di else -1
        add("plus_di", "Trend", "+DI vs −DI", plus_di, score=score,
            applied="Directional movement compared.",
            plain=f"+DI {plus_di:.1f} vs −DI {minus_di:.1f} — {'up-force leads' if score > 0 else 'down-force leads'}.")

    st_dir = trend.get("supertrend_dir")
    if st_dir is not None:
        score = 1 if str(st_dir).lower() in {"1", "up", "bull", "bullish"} or st_dir == 1 else -1
        add("supertrend_dir", "Trend", "Supertrend", st_dir, score=score,
            applied="Supertrend 10,3 direction applied.",
            plain="Supertrend is bullish." if score > 0 else "Supertrend is bearish.")

    atr_pct = _num(vol.get("atr_pct"))
    if atr_pct is not None:
        score = -1 if atr_pct >= 4 else (0 if atr_pct >= 2 else 1)
        add("atr_pct", "Volatility", "ATR %", atr_pct, unit="%", score=score,
            applied="14-day ATR as % of price.",
            plain=f"Typical daily swing ~{atr_pct:.2f}% — {'jumpy' if atr_pct >= 3 else 'relatively calm'} for position sizing.")

    bb = _num(vol.get("bb_pct_b"))
    if bb is not None:
        score = -1 if bb >= 1 else (1 if bb <= 0 else 0)
        add("bb_pct_b", "Volatility", "Bollinger %B", bb, score=score,
            applied="Price location inside Bollinger bands.",
            plain=f"%B {bb:.2f} — {'near/above upper band' if bb >= 0.8 else 'near/below lower band' if bb <= 0.2 else 'mid-band'}.")

    rvol = _num(volume.get("rvol"))
    if rvol is not None:
        score = 1 if rvol >= 1.3 else (-1 if rvol <= 0.7 else 0)
        add("rvol", "Volume", "Relative volume", rvol, score=score,
            applied="Today/latest volume vs 20-day average.",
            plain=f"Relative volume {rvol:.2f}× — {'interest is elevated' if rvol >= 1.3 else 'quiet tape' if rvol < 0.8 else 'normal participation'}.")

    # --- Levels ---
    for key, label in [("pivot", "Pivot"), ("r1", "R1"), ("s1", "S1"), ("r2", "R2"), ("s2", "S2"),
                       ("high_52w", "52w high"), ("low_52w", "52w low")]:
        val = _num(levels.get(key))
        if val is None:
            continue
        score = 0
        plain = f"{label} sits at {val:.2f}."
        if price is not None and key in {"r1", "r2", "high_52w"}:
            score = 1 if price >= val * 0.98 else 0
            plain = f"Price vs {label} ({val:.2f}): {'pressing resistance' if price >= val * 0.99 else 'room below resistance'}."
        if price is not None and key in {"s1", "s2", "low_52w"}:
            score = -1 if price <= val * 1.02 else 0
            plain = f"Price vs {label} ({val:.2f}): {'near support — watch for breaks' if price <= val * 1.02 else 'cushion above support'}."
        add(key, "Levels", label, val, score=score, applied=f"{label} level marked from prior session / range.", plain=plain)

    dist52 = _num(levels.get("dist_from_52w_high_pct"))
    if dist52 is not None:
        score = 1 if dist52 >= -8 else (-1 if dist52 <= -25 else 0)
        add("dist_from_52w_high_pct", "Levels", "Distance from 52w high", dist52, unit="%",
            score=score, applied="How far price sits under the 52-week peak.",
            plain=f"{abs(dist52):.1f}% below the 52-week high." if dist52 < 0 else "At/near 52-week highs.")

    for key, label in [("1d", "1D return"), ("1w", "1W return"), ("1m", "1M return"), ("1y", "1Y return")]:
        val = _num(rets.get(key))
        if val is None:
            continue
        score = 1 if val > 0 else (-1 if val < 0 else 0)
        add(f"ret_{key}", "Returns", label, val, unit="%", score=score,
            applied=f"Horizon return {label} from local candles.",
            plain=f"{label}: {val:+.2f}%.")

    return rows


def build_decoded_facts(
    *,
    symbol: str,
    tech: dict[str, Any],
    ratings: dict[str, Any],
    quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Plain-language 'stock in and out' facts for non-experts."""
    company = (quote or {}).get("company") or {}
    fundamentals = (quote or {}).get("fundamentals") or {}
    summary = (quote or {}).get("summary") or {}
    ma = tech.get("moving_averages") or {}
    levels = tech.get("levels") or {}
    price = _num(tech.get("price")) or _num(summary.get("close")) or _num(company.get("live_price"))

    facts = []
    facts.append({
        "title": "What is this company?",
        "body": (
            f"{company.get('name') or symbol} sits in "
            f"{company.get('sector') or 'an unspecified sector'} / "
            f"{company.get('industry') or 'industry n/a'}. "
            "Use sector context when reading oil, rate, or policy news."
        ),
    })
    if price is not None:
        facts.append({
            "title": "Where is the price?",
            "body": (
                f"Last researched price around {price:,.2f} as of {tech.get('as_of') or summary.get('date') or 'n/a'}. "
                f"Composite technical grade: {ratings.get('composite_grade')} "
                f"({pretty_stance(ratings.get('composite_stance'))})."
            ),
        })
    mcap = _num(company.get("market_cap"))
    if mcap:
        facts.append({
            "title": "How big is it?",
            "body": f"Market cap about {_human_money(mcap)}. Larger caps often move slower; smaller caps can swing harder.",
        })
    pe = _num(company.get("trailing_pe"))
    if pe:
        facts.append({
            "title": "Is it expensive on earnings?",
            "body": (
                f"Trailing P/E ≈ {pe:.1f}. "
                "Lower isn’t always better — compare with peers and growth. High P/E needs growth to justify it."
            ),
        })
    roe = _num(fundamentals.get("roe_pct"))
    if roe is not None:
        facts.append({
            "title": "Does it earn well on equity?",
            "body": f"ROE ≈ {roe:.1f}%. Higher ROE can hint at a stronger business engine — still check debt.",
        })
    de = _num(fundamentals.get("debt_to_equity"))
    if de is not None:
        facts.append({
            "title": "How leveraged is it?",
            "body": (
                f"Debt-to-equity ≈ {de:.2f}. "
                f"{'Balance sheet looks lighter.' if de < 0.5 else 'Leverage is material — rate shocks matter more.' if de > 1.5 else 'Moderate leverage.'}"
            ),
        })
    vs200 = _num(ma.get("price_vs_sma_200_pct"))
    if vs200 is not None:
        facts.append({
            "title": "Long-term trend check",
            "body": (
                f"Price is {vs200:+.1f}% vs the 200-day average — "
                f"{'in a longer-term uptrend zone' if vs200 > 0 else 'below the long-term trend line'}."
            ),
        })
    dist = _num(levels.get("dist_from_52w_high_pct"))
    if dist is not None:
        facts.append({
            "title": "52-week context",
            "body": f"About {abs(dist):.1f}% {'below' if dist < 0 else 'above'} the 52-week high — useful for ‘how extended is this rally/drawdown?’.",
        })
    best = ratings.get("best_horizon")
    if best:
        h = (ratings.get("horizons") or {}).get(best) or {}
        facts.append({
            "title": "Which horizon looks strongest on the tape?",
            "body": (
                f"Model’s best technical horizon: {str(best).upper()} "
                f"(score {h.get('score')}, {pretty_stance(h.get('stance'))}). "
                "Horizons can disagree — that’s normal."
            ),
        })

    return {
        "symbol": symbol.upper(),
        "headline": f"Stock decoded · {company.get('name') or symbol.upper()}",
        "facts": facts,
        "disclaimer": "Plain-English briefing from available data. Educational only — not advice.",
    }


def pretty_stance(stance: Any) -> str:
    return str(stance or "mixed").replace("_", " ")


def _human_money(value: float) -> str:
    abs_v = abs(value)
    if abs_v >= 1e12:
        return f"₹{value/1e12:.2f}T" if value > 1e11 else f"${value/1e12:.2f}T"
    if abs_v >= 1e9:
        return f"{value/1e9:.2f}B"
    if abs_v >= 1e7:
        return f"{value/1e7:.2f} Cr"
    if abs_v >= 1e6:
        return f"{value/1e6:.2f}M"
    return f"{value:,.0f}"


def build_competitive_moat(
    *,
    symbol: str,
    quote: dict[str, Any] | None = None,
    tech: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advantages / disadvantages vs industry peers (transparent heuristics)."""
    company = (quote or {}).get("company") or {}
    fundamentals = (quote or {}).get("fundamentals") or {}
    peers = list((quote or {}).get("peers") or [])
    advantages: list[str] = []
    disadvantages: list[str] = []
    comparisons: list[dict[str, Any]] = []

    my_pe = _num(company.get("trailing_pe"))
    my_pb = _num(company.get("price_to_book"))
    my_mcap = _num(company.get("market_cap"))
    my_dy = _num(company.get("dividend_yield_pct"))
    my_roe = _num(fundamentals.get("roe_pct"))
    my_de = _num(fundamentals.get("debt_to_equity"))
    my_growth = _num(fundamentals.get("revenue_growth_yoy_pct"))
    my_margin = _num(fundamentals.get("net_margin_pct"))
    vs200 = _num((tech or {}).get("moving_averages", {}).get("price_vs_sma_200_pct"))

    peer_pes = [_num(p.get("trailing_pe")) for p in peers]
    peer_pes = [p for p in peer_pes if p and p > 0]
    peer_pbs = [_num(p.get("price_to_book")) for p in peers]
    peer_pbs = [p for p in peer_pbs if p and p > 0]
    peer_mcaps = [_num(p.get("market_cap")) for p in peers]
    peer_mcaps = [p for p in peer_mcaps if p]

    med = lambda xs: sorted(xs)[len(xs) // 2] if xs else None
    pe_med, pb_med, mcap_med = med(peer_pes), med(peer_pbs), med(peer_mcaps)

    if my_pe and pe_med:
        cheaper = my_pe < pe_med * 0.9
        comparisons.append({
            "metric": "Trailing P/E",
            "you": my_pe,
            "peer_median": pe_med,
            "edge": "advantage" if cheaper else ("disadvantage" if my_pe > pe_med * 1.1 else "inline"),
        })
        if cheaper:
            advantages.append(f"Trades at a lower P/E ({my_pe:.1f}) than peer median ({pe_med:.1f}).")
        elif my_pe > pe_med * 1.1:
            disadvantages.append(f"Richer P/E ({my_pe:.1f}) than peer median ({pe_med:.1f}) — growth must keep delivering.")

    if my_pb and pb_med:
        cheaper = my_pb < pb_med * 0.9
        comparisons.append({
            "metric": "Price / Book",
            "you": my_pb,
            "peer_median": pb_med,
            "edge": "advantage" if cheaper else ("disadvantage" if my_pb > pb_med * 1.1 else "inline"),
        })
        if cheaper:
            advantages.append(f"Lower price-to-book ({my_pb:.2f}) vs peers ({pb_med:.2f}).")
        elif my_pb > pb_med * 1.1:
            disadvantages.append(f"Higher price-to-book ({my_pb:.2f}) vs peers ({pb_med:.2f}).")

    if my_mcap and mcap_med:
        comparisons.append({
            "metric": "Market cap",
            "you": my_mcap,
            "peer_median": mcap_med,
            "edge": "advantage" if my_mcap >= mcap_med else "disadvantage",
        })
        if my_mcap >= mcap_med:
            advantages.append("Among the larger names in this peer set — often better liquidity / institutional coverage.")
        else:
            disadvantages.append("Smaller than peer median — can mean higher volatility and thinner research coverage.")

    if my_roe is not None:
        if my_roe >= 15:
            advantages.append(f"ROE {my_roe:.1f}% looks healthy for compounding.")
        elif my_roe < 8:
            disadvantages.append(f"ROE {my_roe:.1f}% is modest — capital efficiency may be a watch item.")

    if my_de is not None:
        if my_de <= 0.5:
            advantages.append(f"Debt-to-equity {my_de:.2f} looks contained.")
        elif my_de >= 1.8:
            disadvantages.append(f"Debt-to-equity {my_de:.2f} is elevated — rate/refinancing risk matters.")

    if my_growth is not None:
        if my_growth >= 12:
            advantages.append(f"Revenue growth ~{my_growth:.1f}% YoY supports a growth narrative.")
        elif my_growth <= 0:
            disadvantages.append(f"Revenue growth ~{my_growth:.1f}% YoY — top-line pressure.")

    if my_margin is not None:
        if my_margin >= 12:
            advantages.append(f"Net margin ~{my_margin:.1f}% suggests pricing power / mix strength.")
        elif my_margin < 5:
            disadvantages.append(f"Net margin ~{my_margin:.1f}% is thin — cost shocks hurt faster.")

    if my_dy and my_dy > 0.02:
        advantages.append(f"Dividend yield ~{my_dy * 100 if my_dy < 1 else my_dy:.2f}% adds cash-return context (verify units).")

    if vs200 is not None:
        if vs200 > 5:
            advantages.append(f"Price {vs200:.1f}% above SMA200 — tape aligns with longer-term strength.")
        elif vs200 < -5:
            disadvantages.append(f"Price {vs200:.1f}% below SMA200 — longer-term trend still healing.")

    if not peers:
        disadvantages.append("Peer set unavailable — competitive read is thinner until industry peers load.")

    # Moat score 0-100
    score = 50
    score += 6 * len(advantages)
    score -= 6 * len(disadvantages)
    score = int(_clamp(score))

    return {
        "symbol": symbol.upper(),
        "industry": company.get("industry"),
        "sector": company.get("sector"),
        "peer_count": len(peers),
        "moat_score": score,
        "moat_label": "wider edge" if score >= 65 else ("contested" if score >= 45 else "challenged"),
        "advantages": advantages[:8],
        "disadvantages": disadvantages[:8],
        "comparisons": comparisons,
        "peers": [
            {
                "symbol": p.get("symbol"),
                "name": p.get("name"),
                "market_cap": p.get("market_cap"),
                "trailing_pe": p.get("trailing_pe"),
                "price_to_book": p.get("price_to_book"),
                "change_pct": p.get("change_pct"),
            }
            for p in peers[:6]
        ],
        "disclaimer": "Competitive edge is a transparent heuristic vs available peers — not a formal moat rating.",
    }


def build_signal_radar(tech: dict[str, Any], ratings: dict[str, Any], moat: dict[str, Any], news: dict[str, Any] | None = None) -> dict[str, Any]:
    greens: list[str] = []
    reds: list[str] = []
    ma = tech.get("moving_averages") or {}
    mom = tech.get("momentum") or {}
    if ma.get("golden_cross"):
        greens.append("Golden cross (SMA50 > SMA200)")
    if ma.get("death_cross"):
        reds.append("Death cross (SMA50 < SMA200)")
    if ma.get("ema_stack_bullish"):
        greens.append("Bullish EMA stack (9>21>50)")
    rsi = _num(mom.get("rsi_14"))
    if rsi is not None and rsi >= 70:
        reds.append(f"RSI {rsi:.0f} overbought zone")
    if rsi is not None and 50 <= rsi < 70:
        greens.append(f"RSI {rsi:.0f} constructive")
    if rsi is not None and rsi <= 30:
        reds.append(f"RSI {rsi:.0f} oversold / weak")
    hist = _num(mom.get("macd_hist"))
    if hist is not None and hist > 0:
        greens.append("MACD histogram positive")
    elif hist is not None:
        reds.append("MACD histogram negative")
    stance = str(ratings.get("composite_stance") or "")
    if stance in {"bullish", "constructive"}:
        greens.append(f"Composite stance {stance}")
    if stance in {"bearish", "cautious"}:
        reds.append(f"Composite stance {stance}")
    for a in (moat.get("advantages") or [])[:3]:
        greens.append(a)
    for d in (moat.get("disadvantages") or [])[:3]:
        reds.append(d)
    hi = (news or {}).get("high_impact_count") or 0
    if hi:
        reds.append(f"{hi} high-impact news tags in latest sweep (read catalysts carefully)")

    critical = (news or {}).get("_critical_signals") if isinstance(news, dict) else None
    if critical:
        dist = critical.get("price_distortion") or {}
        pol = critical.get("government_policy") or {}
        bar = critical.get("psychological_barriers") or {}
        if dist.get("inflation_risk") in {"moderate", "high"}:
            reds.append(f"Artificial inflation risk: {dist['inflation_risk']} — {dist.get('primary_read', '')[:90]}")
        if dist.get("deflation_risk") in {"moderate", "high"}:
            reds.append(f"Artificial deflation risk: {dist['deflation_risk']} — {dist.get('primary_read', '')[:90]}")
        if pol.get("policy_exposure") in {"moderate", "high"}:
            reds.append(f"Government policy exposure: {pol['policy_exposure']} ({pol.get('sector_label', 'sector')})")
        hist = critical.get("price_history") or {}
        if hist.get("pump_and_dump_count_5y", 0) >= 1:
            reds.append(
                f"5y history: {hist['pump_and_dump_count_5y']} pump→dump pair(s) — "
                f"{hist.get('recent_pump_dump_emphasis', '')[:80]}"
            )
        elif hist.get("pump_count_5y", 0) + hist.get("dump_count_5y", 0) >= 2:
            reds.append(
                f"5y distortion history: {hist.get('pump_count_5y', 0)} pumps, {hist.get('dump_count_5y', 0)} dumps"
            )
        if hist.get("repeat_pattern_risk") in {"moderate", "high"}:
            reds.append(f"Repeat artificial move pattern risk: {hist['repeat_pattern_risk']}")
        for ep in (hist.get("recent_episodes") or [])[:1]:
            reds.append(f"Recent: {ep.get('plain_english', ep.get('type', 'episode'))[:100]}")
        found = critical.get("corporate_foundation") or {}
        if found.get("foundation_exposure") in {"moderate", "high"}:
            reds.append(f"Corporate foundation stress: {found['foundation_exposure']}")
        for m in (found.get("associated_company_mentions") or [])[:1]:
            reds.append(f"Group/officer headline: {m[:100]}")
        for tail in (pol.get("policy_tailwinds") or [])[:1]:
            greens.append(tail[:120])
        nearest = bar.get("nearest")
        if nearest:
            note = f"Psych barrier: {nearest['label']} at {nearest['level']} ({nearest['distance_pct']:+.1f}%)"
            reds.append(note) if nearest.get("role") == "resistance" and nearest.get("distance_pct", 0) > -2 else greens.append(note)

    return {
        "green_flags": greens[:12],
        "red_flags": reds[:12],
        "balance": len(greens) - len(reds),
    }


def build_conviction_ensemble(
    *,
    tech: dict[str, Any],
    ratings: dict[str, Any],
    moat: dict[str, Any],
    board: list[dict[str, Any]],
    news: dict[str, Any] | None = None,
    critical: dict[str, Any] | None = None,
    extended: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Multi-factor conviction score with explainable weights (educational forecast band)."""
    bull = sum(1 for r in board if r.get("signal") == "bullish")
    bear = sum(1 for r in board if r.get("signal") == "bearish")
    total = max(bull + bear, 1)
    tech_score = 100 * bull / total

    composite = _num(ratings.get("composite_score"))
    rating_score = _clamp(composite if composite is not None else 50)

    moat_score = _num(moat.get("moat_score")) or 50

    news_score = 55.0
    if news:
        tags = news.get("tag_counts") or {}
        pressure = sum(tags.get(k, 0) for k in (
            "geopolitics_war", "supply_constraints", "rates_macro", "regulation_policy", "government_policy",
        ))
        support = sum(tags.get(k, 0) for k in ("earnings_corporate", "commodity_energy"))
        news_score = _clamp(55 + 4 * support - 5 * pressure)

    if critical:
        dist = critical.get("price_distortion") or {}
        pol = critical.get("government_policy") or {}
        if dist.get("inflation_risk") == "high" or dist.get("deflation_risk") == "high":
            news_score -= 12
        elif dist.get("inflation_risk") == "moderate" or dist.get("deflation_risk") == "moderate":
            news_score -= 6
        if pol.get("policy_exposure") == "high":
            news_score -= 8
        elif pol.get("policy_exposure") == "moderate":
            news_score -= 4
        hist = critical.get("price_history") or {}
        if hist.get("repeat_pattern_risk") == "high":
            news_score -= 10
        elif hist.get("repeat_pattern_risk") == "moderate":
            news_score -= 5
        found = critical.get("corporate_foundation") or {}
        if found.get("foundation_exposure") == "high":
            news_score -= 8
        elif found.get("foundation_exposure") == "moderate":
            news_score -= 4
        news_score = _clamp(news_score)

    # Horizon agreement: how many horizons are constructive+
    horizons = ratings.get("horizons") or {}
    good = 0
    bad = 0
    for h in horizons.values():
        st = str(h.get("stance") or "")
        if st in {"bullish", "constructive"}:
            good += 1
        elif st in {"bearish", "cautious"}:
            bad += 1
    horizon_score = _clamp(50 + 8 * good - 8 * bad)

    extended_score = 50.0
    if extended:
        adj = ((ratings.get("extended_adjustment") or {}).get("delta")) or 0
        extended_score = _clamp(50 + float(adj) * 2)
        fund_q = ((extended.get("fundamentals") or {}).get("quality_scores") or {}).get("composite_quality")
        if fund_q:
            extended_score = _clamp(extended_score * 0.6 + fund_q * 0.4)

    weights = {"technicals": 0.26, "composite": 0.22, "horizons": 0.13, "competitive": 0.18, "news": 0.09, "extended": 0.12}
    try:
        from trading.autopilot import load_calibration
        cal = load_calibration().get("weights") or {}
        if cal:
            weights = {
                "technicals": float(cal.get("technicals", weights["technicals"])),
                "composite": float(cal.get("composite", weights["composite"])),
                "horizons": float(cal.get("horizons", weights["horizons"])),
                "competitive": float(cal.get("competitive", weights["competitive"])),
                "news": float(cal.get("news", weights["news"])),
                "extended": float(cal.get("extended", weights.get("extended", 0.12))),
            }
    except Exception:
        pass

    factors = [
        {"id": "technicals", "label": "Applied technical signals", "weight": weights["technicals"], "score": round(tech_score, 1)},
        {"id": "composite", "label": "Horizon composite grade", "weight": weights["composite"], "score": round(rating_score, 1)},
        {"id": "horizons", "label": "Horizon agreement", "weight": weights["horizons"], "score": round(horizon_score, 1)},
        {"id": "competitive", "label": "Competitive / peer edge", "weight": weights["competitive"], "score": round(moat_score, 1)},
        {"id": "news", "label": "News & macro catalysts", "weight": weights["news"], "score": round(news_score, 1)},
    ]
    if extended:
        factors.append({"id": "extended", "label": "Extended factors (patterns, regime, India, options)", "weight": weights["extended"], "score": round(extended_score, 1)})
    conviction = sum(f["weight"] * f["score"] for f in factors)
    conviction = round(_clamp(conviction), 1)

    # Confidence rises when factors agree and data coverage is decent
    spread = max(f["score"] for f in factors) - min(f["score"] for f in factors)
    coverage = min(100, 40 + len(board) * 1.2 + (moat.get("peer_count") or 0) * 4)
    confidence = round(_clamp(coverage - spread * 0.35), 1)

    if conviction >= 68:
        band = "constructive bias"
        plain = "Factors lean constructive — still verify catalysts and risk size."
    elif conviction <= 38:
        band = "cautious bias"
        plain = "Factors lean cautious — weakness or rich valuation/news pressure may dominate."
    else:
        band = "mixed / wait-and-see"
        plain = "Signals disagree — treat as research in progress, not a clear directional call."

    return {
        "conviction_score": conviction,
        "confidence": confidence,
        "band": band,
        "plain_english": plain,
        "factors": factors,
        "signal_counts": {"bullish": bull, "bearish": bear, "neutral": len(board) - bull - bear},
        "forecast_note": (
            "This is an educational multi-factor conviction meter, not a guaranteed prediction. "
            "Higher confidence means factors agree more — not that the future is known."
        ),
    }


def build_scenario_lab(quote: dict[str, Any] | None, tech: dict[str, Any] | None) -> dict[str, Any]:
    """Sector-aware what-if scenarios (heuristic sensitivity, not a pricing model)."""
    company = (quote or {}).get("company") or {}
    sector = str(company.get("sector") or "").lower()
    industry = str(company.get("industry") or "").lower()
    atr = _num((tech or {}).get("volatility", {}).get("atr_pct")) or 2.0
    blob = f"{sector} {industry}"

    def scenario(title: str, bias: str, impact: str, why: str) -> dict[str, str]:
        return {"title": title, "bias": bias, "impact": impact, "why": why}

    scenarios = [
        scenario(
            "Market risk-on (+ risk appetite)",
            "tailwind",
            f"Could add roughly {atr * 1.2:.1f}%–{atr * 2.5:.1f}% noise in a lively session (order-of-magnitude).",
            "Broad risk-on usually lifts betas; exact move depends on ownership and news.",
        ),
        scenario(
            "Risk-off / sharp selloff",
            "headwind",
            f"Drawdown noise on the order of {atr * 1.5:.1f}%–{atr * 3.5:.1f}% is plausible in stress tapes.",
            "Liquidity gaps can overshoot ATR — use this as a sizing thought experiment only.",
        ),
    ]

    if any(k in blob for k in ("energy", "oil", "gas", "refin")):
        scenarios.append(scenario(
            "Crude oil spike",
            "mixed",
            "Refiners/upstream can diverge — check whether you’re leveraged to cracks or crude.",
            "Energy names often reprice fast on geopolitics and OPEC headlines.",
        ))
        scenarios.append(scenario(
            "Supply chain / freight disruption",
            "headwind",
            "Margins and volumes can compress if feedstock or logistics tighten.",
            "Your news scout tags supply shocks for a reason in this sector.",
        ))
    elif any(k in blob for k in ("bank", "financ", "insur")):
        scenarios.append(scenario(
            "Rate hike cycle",
            "mixed",
            "NII can help banks; mark-to-market / credit costs can hurt.",
            "Financials are rate-sensitive — watch RBI/Fed path and credit quality.",
        ))
    elif any(k in blob for k in ("tech", "software", "semiconductor", "it ")):
        scenarios.append(scenario(
            "Global IT spend slowdown",
            "headwind",
            "Growth multiples compress when deal cycles lengthen.",
            "Tech often trades as a duration asset — rates + growth surprises matter.",
        ))
    elif any(k in blob for k in ("auto", "consumer", "retail")):
        scenarios.append(scenario(
            "Demand soft patch / inflation squeeze",
            "headwind",
            "Volumes and mix can slip; premium brands may hold up better.",
            "Consumer cyclicals feel income and confidence shocks quickly.",
        ))
    else:
        scenarios.append(scenario(
            "Sector policy / regulation surprise",
            "mixed",
            "One headline can reprice the group even if company news is quiet.",
            "Always map the stock to its sector policy calendar.",
        ))

    scenarios.append(scenario(
        "Earnings beat with strong guidance",
        "tailwind",
        "Can reset both fundamentals narrative and technical breakout odds.",
        "Your desk still needs the print — this is a template, not a forecast.",
    ))

    return {
        "atr_pct_context": atr,
        "sector": company.get("sector"),
        "industry": company.get("industry"),
        "scenarios": scenarios,
        "disclaimer": "Scenario lab is educational sensitivity framing using ATR/sector heuristics — not a pricing engine.",
    }


def build_extended_board_rows(extended: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not extended:
        return []
    rows: list[dict[str, Any]] = []
    ind = extended.get("indicators") or {}
    ich = ind.get("ichimoku") or {}
    if ich.get("price_vs_cloud"):
        sig = "bullish" if ich["price_vs_cloud"] == "above" else ("bearish" if ich["price_vs_cloud"] == "below" else "neutral")
        rows.append({"group": "Ichimoku", "label": "Cloud position", "value": ich["price_vs_cloud"], "signal": sig, "note": f"TK cross {ich.get('tenkan_kijun_cross')}"})
    cmf = ind.get("cmf") or {}
    if cmf.get("cmf_20") is not None:
        rows.append({"group": "Volume flow", "label": "CMF(20)", "value": cmf["cmf_20"], "signal": "bullish" if cmf.get("bias") == "accumulation" else ("bearish" if cmf.get("bias") == "distribution" else "neutral")})
    pat = extended.get("patterns") or {}
    for p in (pat.get("candlestick", {}).get("patterns") or [])[:2]:
        rows.append({"group": "Patterns", "label": p.get("name"), "value": p.get("bias"), "signal": p.get("bias") if p.get("bias") != "indecision" else "neutral"})
    div = extended.get("divergence") or {}
    if div.get("composite_signal") not in (None, "none"):
        rows.append({"group": "Divergence", "label": "RSI/MACD", "value": div["composite_signal"], "signal": div["composite_signal"] if div["composite_signal"] != "mixed" else "neutral"})
    fund = extended.get("fundamentals") or {}
    qs = fund.get("quality_scores") or {}
    if qs.get("composite_quality"):
        rows.append({"group": "Fundamentals", "label": "Quality score", "value": qs["composite_quality"], "signal": "bullish" if qs["composite_quality"] >= 65 else ("bearish" if qs["composite_quality"] < 45 else "neutral")})
    opt = extended.get("options") or {}
    if opt.get("pcr_oi"):
        rows.append({"group": "Options", "label": "PCR(OI)", "value": opt["pcr_oi"], "signal": opt.get("pcr_bias", "neutral")})
    reg = ((extended.get("regime") or {}).get("regime") or {}).get("regime")
    if reg:
        rows.append({"group": "Regime", "label": "Market regime", "value": reg, "signal": "bullish" if reg == "bull" else ("bearish" if reg == "bear" else "neutral")})
    return rows


def build_deep_dossier(
    *,
    symbol: str,
    technicals: dict[str, Any],
    ratings: dict[str, Any],
    quote: dict[str, Any] | None = None,
    indicator_guide: dict[str, Any] | None = None,
    news: dict[str, Any] | None = None,
    extended: dict[str, Any] | None = None,
) -> dict[str, Any]:
    board = build_technical_board(technicals, indicator_guide)
    critical = build_critical_signals(
        technicals=technicals,
        ratings=ratings,
        news=news,
        quote=quote,
    )
    board.extend(critical.get("board_rows") or [])
    board.extend(build_extended_board_rows(extended))
    news_for_radar = {**(news or {}), "_critical_signals": critical}
    decoded = build_decoded_facts(symbol=symbol, tech=technicals, ratings=ratings, quote=quote)
    moat = build_competitive_moat(symbol=symbol, quote=quote, tech=technicals)
    radar = build_signal_radar(technicals, ratings, moat, news_for_radar)
    conviction = build_conviction_ensemble(
        tech=technicals, ratings=ratings, moat=moat, board=board, news=news, critical=critical, extended=extended,
    )
    scenarios = build_scenario_lab(quote, technicals)

    applied_groups: dict[str, int] = {}
    for row in board:
        applied_groups[row["group"]] = applied_groups.get(row["group"], 0) + 1

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol.upper(),
        "technical_board": board,
        "technical_groups": applied_groups,
        "parameters_applied": len(board),
        "decoded": decoded,
        "competitive": moat,
        "signal_radar": radar,
        "critical_signals": critical,
        "conviction": conviction,
        "scenario_lab": scenarios,
        "truth_thermometer": {
            "data_coverage_score": int(_clamp(
                35
                + min(40, len(board))
                + (8 if (quote or {}).get("fundamentals") else 0)
                + (8 if (quote or {}).get("peers") else 0)
                + (6 if (quote or {}).get("news") else 0)
                + (10 if extended else 0)
            )),
            "note": "How complete today’s inputs look (price/TA/fundamentals/peers/news) — not accuracy of the future.",
        },
        "extended_analysis": extended,
        "disclaimer": (
            "Deep dossier is educational market research. Conviction and scenarios are transparent heuristics, "
            "not guaranteed predictions or personalized advice."
        ),
    }
