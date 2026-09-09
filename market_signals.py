"""Critical market signals: price distortion, psychological barriers, government policy.

Educational heuristics from price/volume/news — not manipulation accusations or advice.
"""
from __future__ import annotations

import math
from typing import Any, Optional

from corporate_structure import analyze_corporate_foundation
from price_history_signals import scan_price_history
from utils.numbers import parse_float as _num


def _near_pct(price: float, level: float, band_pct: float = 1.5) -> bool:
    if not level or level <= 0:
        return False
    return abs(price - level) / level * 100 <= band_pct


def _round_levels(price: float) -> list[float]:
    """Nearby round-number levels traders often react to."""
    if price <= 0:
        return []
    if price < 50:
        step = 5
    elif price < 200:
        step = 10
    elif price < 1000:
        step = 25
    else:
        step = 50
    base = math.floor(price / step) * step
    return sorted({max(step, base - step), base, base + step, base + 2 * step})


def detect_psychological_barriers(
    technicals: dict[str, Any],
    quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Price levels where crowd hesitation, anchoring, or breakout battles often show up."""
    price = _num(technicals.get("price"))
    if price is None:
        summary = ((quote or {}).get("summary") or {})
        price = _num(summary.get("close")) or _num(((quote or {}).get("company") or {}).get("live_price"))
    if price is None:
        return {"barriers": [], "headline": "Insufficient price data for barrier scan.", "plain_english": "No barrier scan."}

    ma = technicals.get("moving_averages") or {}
    levels = technicals.get("levels") or {}
    barriers: list[dict[str, Any]] = []

    def add(level: Optional[float], kind: str, label: str, note: str, *, role: str) -> None:
        if level is None or level <= 0:
            return
        dist = (price - level) / level * 100
        if abs(dist) > 8:
            return
        barriers.append({
            "kind": kind,
            "label": label,
            "level": round(level, 4),
            "distance_pct": round(dist, 2),
            "role": role,
            "note": note,
        })

    for lvl in _round_levels(price):
        side = "resistance" if lvl >= price else "support"
        add(lvl, "round_number", f"Round {lvl:g}", f"Whole-number {side} — orders often cluster here.", role=side)

    add(_num(levels.get("high_52w")), "52w_high", "52-week high", "Breakout zone — hesitation or FOMO often peaks here.", role="resistance")
    add(_num(levels.get("low_52w")), "52w_low", "52-week low", "Capitulation / value anchoring zone.", role="support")
    add(_num(ma.get("sma_50")), "sma", "SMA 50", "Intermediate trend wall — dip buyers vs sellers debate.", role="resistance" if price < (_num(ma.get("sma_50")) or price) else "support")
    add(_num(ma.get("sma_200")), "sma", "SMA 200", "Institutional long-term anchor — reclaim/fail matters.", role="resistance" if price < (_num(ma.get("sma_200")) or price) else "support")
    add(_num(levels.get("r1")), "pivot", "Pivot R1", "Short-term overhead supply.", role="resistance")
    add(_num(levels.get("r2")), "pivot", "Pivot R2", "Stronger overhead supply.", role="resistance")
    add(_num(levels.get("s1")), "pivot", "Pivot S1", "First support shelf.", role="support")
    add(_num(levels.get("s2")), "pivot", "Pivot S2", "Deeper support shelf.", role="support")

    barriers.sort(key=lambda b: abs(b["distance_pct"]))
    nearest = barriers[0] if barriers else None
    headline = (
        f"Nearest psychological barrier: {nearest['label']} at {nearest['level']} "
        f"({nearest['distance_pct']:+.1f}% away) — {nearest['note']}"
        if nearest
        else "No major psychological barrier within ~8% of price."
    )
    return {
        "barriers": barriers[:8],
        "nearest": nearest,
        "headline": headline,
        "plain_english": headline,
        "disclaimer": "Barrier levels are crowd-psychology heuristics — not guaranteed support/resistance.",
    }


def detect_price_distortion(
    technicals: dict[str, Any],
    news: dict[str, Any] | None = None,
    quote: dict[str, Any] | None = None,
    history: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Heuristic flags for price moves that look artificially pumped or deflated vs volume/news."""
    mom = technicals.get("momentum") or {}
    ma = technicals.get("moving_averages") or {}
    vol = technicals.get("volatility") or {}
    volume = technicals.get("volume") or {}
    rets = technicals.get("returns_pct") or {}
    levels = technicals.get("levels") or {}

    rsi = _num(mom.get("rsi_14"))
    stoch = _num(mom.get("stoch_k"))
    bb = _num(vol.get("bb_pct_b"))
    atr_pct = _num(vol.get("atr_pct"))
    rvol = _num(volume.get("rvol"))
    ret1d = _num(rets.get("1d"))
    vs200 = _num(ma.get("price_vs_sma_200_pct"))
    dist_high = _num(levels.get("dist_from_52w_high_pct"))

    news = news or {}
    tags = news.get("tag_counts") or {}
    has_catalyst = (
        (news.get("high_impact_count") or 0) > 0
        or tags.get("earnings_corporate", 0) > 0
        or tags.get("regulation_policy", 0) > 0
    )

    inflate_signals: list[dict[str, Any]] = []
    deflate_signals: list[dict[str, Any]] = []

    def flag(direction: str, label: str, severity: str, plain: str, score: int) -> None:
        item = {"direction": direction, "label": label, "severity": severity, "plain_english": plain, "score": score}
        (inflate_signals if direction == "inflate" else deflate_signals).append(item)

    if rvol is not None and ret1d is not None:
        if rvol >= 1.7 and ret1d >= 3.0 and not has_catalyst:
            flag("inflate", "Volume spike without clear catalyst",
                 "elevated" if ret1d >= 5 else "moderate",
                 f"Price up {ret1d:+.1f}% on {rvol:.1f}× volume with no tagged earnings/policy headline — "
                 "move may be sentiment-driven or thin-float chasing (verify independently).",
                 -1 if ret1d >= 5 else 0)
        if rvol >= 1.7 and ret1d <= -3.0 and not has_catalyst:
            flag("deflate", "Heavy sell volume without clear catalyst",
                 "elevated" if ret1d <= -5 else "moderate",
                 f"Price down {ret1d:+.1f}% on {rvol:.1f}× volume without a tagged catalyst — "
                 "could reflect forced selling, stop cascades, or rumor-driven exits.",
                 -1 if ret1d <= -5 else 0)

    if rsi is not None and bb is not None and vs200 is not None:
        if rsi >= 72 and bb >= 0.95 and vs200 > 12:
            flag("inflate", "Overextended rally profile",
                 "elevated",
                 f"RSI {rsi:.0f}, Bollinger %B {bb:.2f}, and {vs200:+.1f}% above SMA200 — "
                 "price may be running ahead of fundamentals; pullback risk rises.",
                 -1)
        if rsi <= 28 and bb <= 0.05 and vs200 < -10:
            flag("deflate", "Capitulation / washout profile",
                 "elevated",
                 f"RSI {rsi:.0f}, %B {bb:.2f}, and {vs200:+.1f}% vs SMA200 — "
                 "panic selling or artificial deflation via stop hunts is possible.",
                 -1)

    if stoch is not None and ret1d is not None and rvol is not None:
        if stoch >= 85 and ret1d >= 4 and rvol >= 1.5:
            flag("inflate", "Parabolic short-term burst",
                 "moderate",
                 f"Stochastic {stoch:.0f} with {ret1d:+.1f}% day move on elevated volume — "
                 "late buyers may be inflating the tape temporarily.",
                 -1)
        if stoch <= 15 and ret1d <= -4 and rvol >= 1.5:
            flag("deflate", "Sharp momentum flush",
                 "moderate",
                 f"Stochastic {stoch:.0f} with {ret1d:+.1f}% day move — "
                 "air-pocket decline may overshoot fair value before stabilising.",
                 -1)

    if dist_high is not None and dist_high > -1.5 and rvol is not None and rvol >= 1.4:
        flag("inflate", "Breakout chase zone",
             "moderate",
             "Price pressing 52-week highs on elevated volume — breakout or bull-trap risk both rise.",
             0)

    pe = _num(((quote or {}).get("company") or {}).get("trailing_pe"))
    if pe and pe > 45 and vs200 is not None and vs200 > 15 and rsi is not None and rsi >= 65:
        flag("inflate", "Rich valuation + extended tape",
             "moderate",
             f"Trailing P/E ~{pe:.0f} with price {vs200:+.1f}% above SMA200 — "
             "multiple expansion may be inflating perceived value vs earnings.",
             -1)

    inflate_score = sum(2 if s["severity"] == "elevated" else 1 for s in inflate_signals)
    deflate_score = sum(2 if s["severity"] == "elevated" else 1 for s in deflate_signals)

    def band(score: int) -> str:
        if score >= 3:
            return "high"
        if score >= 1:
            return "moderate"
        return "low"

    inflation_risk = band(inflate_score)
    deflation_risk = band(deflate_score)

    if inflation_risk == "high":
        primary = "Tape shows elevated artificial-inflation risk — verify whether volume is backed by fundamentals or news."
    elif deflation_risk == "high":
        primary = "Tape shows elevated deflation/washout risk — moves may overshoot before stabilising."
    elif inflation_risk == "moderate":
        primary = "Some signs of an extended or sentiment-driven rally — watch for exhaustion."
    elif deflation_risk == "moderate":
        primary = "Some signs of heavy reactive selling — watch for capitulation then stabilisation."
    else:
        primary = "No strong artificial inflation/deflation pattern detected from volume, momentum, and news tags."

    if atr_pct is not None and atr_pct > 4:
        primary += f" ATR ~{atr_pct:.1f}% — wide swings amplify distortion risk."

    history = history or {}
    if history.get("episodes"):
        primary += f" 5-year history: {history.get('pump_count_5y', 0)} pumps, {history.get('dump_count_5y', 0)} dumps, {history.get('pump_and_dump_count_5y', 0)} pump→dump pairs."
        if history.get("repeat_pattern_risk") in {"moderate", "high"}:
            primary += f" Repeat pattern risk: {history['repeat_pattern_risk']}."
        if history.get("recent_pump_dump_emphasis"):
            primary += f" {history['recent_pump_dump_emphasis']}"

    return {
        "inflation_risk": inflation_risk,
        "deflation_risk": deflation_risk,
        "inflate_signals": inflate_signals,
        "deflate_signals": deflate_signals,
        "signals": inflate_signals + deflate_signals,
        "history": history,
        "primary_read": primary,
        "plain_english": primary,
        "disclaimer": (
            "Price-distortion scan is an educational heuristic — not evidence of market manipulation "
            "or a trading recommendation."
        ),
    }


_SECTOR_POLICY: list[tuple[tuple[str, ...], str, list[str]]] = [
    (("bank", "financ", "nbfc", "insur"), "Financials",
     ["RBI rate/regulatory circulars", "NPA provisioning norms", "Capital adequacy / dividend rules"]),
    (("power", "utility", "renewable", "energy"), "Energy / power",
     ["Coal supply & tariff policy", "Renewable purchase obligations", "Electricity Act / discom reforms"]),
    (("pharma", "health", "hospital"), "Healthcare",
     ["Drug price control (NPPA)", "Patent / compulsory licensing", "Import duty on APIs"]),
    (("telecom", "communication"), "Telecom",
     ["Spectrum auctions", "AGR / regulatory dues", "Tariff floor pricing"]),
    (("auto", "vehicle", "motor"), "Automotive",
     ["EV subsidies & FAME schemes", "Emission / CAFE norms", "Import duty on components"]),
    (("it ", "software", "tech", "information"), "IT / tech",
     ["Visa / immigration policy", "Transfer pricing & tax treaties", "Data localisation rules"]),
    (("real estate", "construction", "infra"), "Infrastructure",
     ["RERA compliance", "Infrastructure spending / PLI", "Environmental clearance norms"]),
    (("metal", "mining", "steel", "alumin"), "Metals",
     ["Export duties / mining leases", "Domestic capacity mandates", "Carbon / green steel policy"]),
    (("consumer", "fmcg", "retail"), "Consumer",
     ["GST rate changes", "FSSAI / labeling rules", "Import restrictions on goods"]),
]


def analyze_government_policy(
    news: dict[str, Any] | None = None,
    quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Government / regulatory policy exposure from news tags and sector context."""
    news = news or {}
    company = (quote or {}).get("company") or {}
    sector = str(company.get("sector") or "").lower()
    industry = str(company.get("industry") or "").lower()
    blob = f"{sector} {industry}"

    sector_label = "General market"
    sector_watch: list[str] = []
    for keys, label, watch in _SECTOR_POLICY:
        if any(k in blob for k in keys):
            sector_label = label
            sector_watch = watch
            break

    headlines = news.get("headlines") or []
    policy_tags = {"regulation_policy", "rates_macro", "government_policy"}
    policy_headlines = [
        h for h in headlines
        if (h.get("catalyst_tag") or "") in policy_tags
        or any(w in f"{h.get('title', '')} {h.get('summary', '')}".lower() for w in (
            "government", "ministry", "cabinet", "parliament", "budget", "sebi", "rbi",
            "policy", "regulation", "subsidy", "tariff", "gst", "notification", "circular",
            "fiscal", "stimulus", "ban", "duty",
        ))
    ]

    tags = news.get("tag_counts") or {}
    policy_count = tags.get("regulation_policy", 0) + tags.get("government_policy", 0) + tags.get("rates_macro", 0)

    risks: list[str] = []
    tailwinds: list[str] = []

    for h in policy_headlines[:4]:
        title = (h.get("title") or "")[:140]
        label = h.get("catalyst_label") or "Policy"
        low = title.lower()
        if any(w in low for w in ("ban", "tariff", "duty", "probe", "penalty", "cut subsidy", "hike tax")):
            risks.append(f"{label}: {title}")
        elif any(w in low for w in ("subsidy", "stimulus", "incentive", "pli", "approval", "reform")):
            tailwinds.append(f"{label}: {title}")
        else:
            risks.append(f"{label}: {title}")

    for w in sector_watch[:3]:
        risks.append(f"Sector watch — {w}")

    exposure = "low"
    if policy_count >= 3 or len(policy_headlines) >= 2:
        exposure = "high"
    elif policy_count >= 1 or len(policy_headlines) >= 1:
        exposure = "moderate"

    plain = (
        f"{sector_label} name with {exposure} government-policy headline exposure "
        f"({len(policy_headlines)} policy-tagged headline(s) in latest sweep)."
    )
    if policy_headlines:
        plain += f" Latest: “{(policy_headlines[0].get('title') or '')[:100]}”."
    elif sector_watch:
        plain += f" Watch: {sector_watch[0]}."

    return {
        "policy_exposure": exposure,
        "sector_label": sector_label,
        "sector_watch_items": sector_watch,
        "policy_headline_count": len(policy_headlines),
        "headlines": [
            {
                "title": h.get("title"),
                "catalyst_tag": h.get("catalyst_tag"),
                "catalyst_label": h.get("catalyst_label"),
                "published_at": h.get("published_at"),
                "url": h.get("url"),
            }
            for h in policy_headlines[:6]
        ],
        "policy_risks": risks[:6],
        "policy_tailwinds": tailwinds[:4],
        "plain_english": plain,
        "headline": plain,
        "disclaimer": "Policy read is from keyword-tagged headlines — verify official notifications independently.",
    }


def build_critical_signals(
    *,
    technicals: dict[str, Any],
    ratings: dict[str, Any] | None = None,
    news: dict[str, Any] | None = None,
    quote: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bundle distortion, barriers, policy, history, and corporate foundation for dossier + GenAI desk."""
    rows = (quote or {}).get("rows") or []
    symbol = (quote or {}).get("company", {}).get("symbol") or technicals.get("symbol") or ""
    history = scan_price_history(rows) if rows else {}
    barriers = detect_psychological_barriers(technicals, quote)
    distortion = detect_price_distortion(technicals, news, quote, history=history)
    policy = analyze_government_policy(news, quote)
    foundation = analyze_corporate_foundation(quote=quote, news=news, symbol=str(symbol))

    board_rows: list[dict[str, Any]] = []
    for sig in distortion.get("signals") or []:
        board_rows.append({
            "key": f"distortion_{sig['label'][:24].lower().replace(' ', '_')}",
            "group": "Market structure",
            "label": sig["label"],
            "value": sig["severity"],
            "unit": "",
            "signal": "bearish" if sig["direction"] == "inflate" and sig["score"] < 0 else (
                "bearish" if sig["direction"] == "deflate" and sig["score"] < 0 else "neutral"
            ),
            "score": sig.get("score", 0),
            "applied": f"Price-distortion heuristic ({sig['direction']}).",
            "plain_english": sig["plain_english"],
        })

    nearest = barriers.get("nearest")
    if nearest:
        board_rows.append({
            "key": "psych_barrier_nearest",
            "group": "Psychological barriers",
            "label": nearest["label"],
            "value": nearest["level"],
            "unit": "",
            "signal": "neutral",
            "score": 0,
            "applied": f"Distance {nearest['distance_pct']:+.1f}% from price.",
            "plain_english": nearest["note"],
        })

    if policy.get("policy_exposure") in {"moderate", "high"}:
        board_rows.append({
            "key": "gov_policy_exposure",
            "group": "Government policy",
            "label": "Policy headline exposure",
            "value": policy["policy_exposure"],
            "unit": "",
            "signal": "bearish" if policy.get("policy_risks") else "neutral",
            "score": -1 if policy["policy_exposure"] == "high" else 0,
            "applied": f"{policy.get('sector_label')} sector policy scan.",
            "plain_english": policy.get("plain_english", ""),
        })

    for ep in (history.get("recent_episodes") or [])[:2]:
        board_rows.append({
            "key": f"hist_{ep.get('type', 'ep')}_{str(ep.get('date') or ep.get('dump_date', ''))[:10]}",
            "group": "5y price history",
            "label": f"Recent {ep.get('type', 'episode').replace('_', ' ')}",
            "value": ep.get("move_pct") or ep.get("dump_pct"),
            "unit": "%",
            "signal": "bearish",
            "score": -1 if ep.get("severity") == "elevated" else 0,
            "applied": f"Historical scan · {ep.get('date') or ep.get('dump_date', 'n/a')}",
            "plain_english": ep.get("plain_english", ""),
        })

    if foundation.get("foundation_exposure") in {"moderate", "high"}:
        board_rows.append({
            "key": "corp_foundation_exposure",
            "group": "Corporate foundation",
            "label": "Governance / group-structure scan",
            "value": foundation["foundation_exposure"],
            "unit": "",
            "signal": "bearish" if foundation["foundation_exposure"] == "high" else "neutral",
            "score": -1 if foundation["foundation_exposure"] == "high" else 0,
            "applied": "CEO/officer + related-party headline scan.",
            "plain_english": foundation.get("plain_english", ""),
        })

    return {
        "price_distortion": distortion,
        "price_history": history,
        "psychological_barriers": barriers,
        "government_policy": policy,
        "corporate_foundation": foundation,
        "board_rows": board_rows,
        "summary": {
            "inflation_risk": distortion.get("inflation_risk"),
            "deflation_risk": distortion.get("deflation_risk"),
            "policy_exposure": policy.get("policy_exposure"),
            "barrier_count": len(barriers.get("barriers") or []),
            "pump_count_5y": history.get("pump_count_5y", 0),
            "dump_count_5y": history.get("dump_count_5y", 0),
            "pump_and_dump_count_5y": history.get("pump_and_dump_count_5y", 0),
            "repeat_pattern_risk": history.get("repeat_pattern_risk"),
            "foundation_exposure": foundation.get("foundation_exposure"),
        },
    }
