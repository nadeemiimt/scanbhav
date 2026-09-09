"""
Successful intraday trader pattern scoring for Auto Pick ranking.

Patterns (gap-and-go, ORB proxy, momentum continuation, pullback entry,
volume surge) are scored from scan row fields — no live tick required.
"""
from __future__ import annotations

from typing import Any

from trading.config_store import load_trading_config

BULLISH_STANCES = {"favorable", "strong_favorable", "bullish", "constructive"}


def pattern_cfg() -> dict[str, Any]:
    ap = load_trading_config().get("autopilot") or {}
    return {
        "enabled": bool(ap.get("agent_pattern_scoring_enabled", True)),
        "edge_weight": float(ap.get("agent_pattern_edge_weight") or 1.0),
        "min_score_for_boost": float(ap.get("agent_pattern_min_boost_score") or 55.0),
    }


def _f(row: dict[str, Any], key: str, default: float = 0.0) -> float:
    val = row.get(key)
    if val is None:
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _rvol(row: dict[str, Any]) -> float | None:
    val = row.get("rvol") if row.get("rvol") is not None else row.get("relative_volume")
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def score_intraday_patterns(
    row: dict[str, Any],
    *,
    ist_mins: int | None = None,
) -> tuple[float, list[str], dict[str, Any]]:
    """
    Score row against proven MIS patterns. Returns (pattern_score 0–100, pattern_ids, meta).
    """
    cfg = pattern_cfg()
    if not cfg["enabled"]:
        return 50.0, [], {"pattern_score": 50.0, "pattern_ids": []}

    if ist_mins is None:
        from trading.agent_selection import ist_minutes_now

        ist_mins = ist_minutes_now()

    pattern_ids: list[str] = []
    points = 0.0
    max_points = 0.0

    stance = str(row.get("stance") or "").lower()
    bullish = stance in BULLISH_STANCES
    gap = row.get("gap_pct")
    if gap is None and row.get("open_gap_pct") is not None:
        gap = row.get("open_gap_pct")
    gap_f = _f(row, "gap_pct") if gap is not None else None
    if gap is not None:
        try:
            gap_f = float(gap)
        except (TypeError, ValueError):
            gap_f = None

    horizon = _f(row, "horizon_return_pct")
    atr = _f(row, "atr_pct")
    rsi = row.get("rsi_14")
    rsi_f = float(rsi) if isinstance(rsi, (int, float)) else None
    rvol = _rvol(row)
    macd = row.get("macd_hist")
    macd_pos = isinstance(macd, (int, float)) and float(macd) > 0

    market_open = 9 * 60 + 15
    open_drive_end = 10 * 60 + 30
    early_session = market_open <= ist_mins <= open_drive_end

    # 1. Gap-and-go — gap up + bullish + continuation bias
    max_points += 18.0
    if gap_f is not None and gap_f >= 0.4 and bullish and horizon > 0:
        pts = min(18.0, 8.0 + gap_f * 1.2)
        if row.get("supertrend_dir") == 1:
            pts += 3.0
        points += pts
        pattern_ids.append("gap_and_go")

    # 2. Opening range breakout proxy — early session + volume + momentum
    max_points += 16.0
    if early_session and bullish and horizon >= 0.5:
        pts = 6.0
        if rvol is not None and rvol >= 1.2:
            pts += min(6.0, (rvol - 1.0) * 4.0)
        if macd_pos:
            pts += 2.0
        if atr >= 2.0:
            pts += 2.0
        if pts >= 10.0:
            points += min(16.0, pts)
            pattern_ids.append("orb_breakout")

    # 3. Momentum continuation — trend stack
    max_points += 14.0
    mom_pts = 0.0
    if row.get("supertrend_dir") == 1:
        mom_pts += 4.0
    if row.get("golden_cross"):
        mom_pts += 3.0
    if macd_pos:
        mom_pts += 3.0
    if horizon >= 1.0:
        mom_pts += min(4.0, horizon * 0.5)
    if mom_pts >= 7.0 and bullish:
        points += min(14.0, mom_pts)
        pattern_ids.append("momentum_continuation")

    # 4. Pullback entry — RSI dip in uptrend (buy-the-dip MIS)
    max_points += 12.0
    if rsi_f is not None and 42 <= rsi_f <= 58 and bullish:
        pts = 6.0
        if row.get("pattern_bias") == "bullish":
            pts += 3.0
        if gap_f is not None and 0.2 <= gap_f <= 2.5:
            pts += 2.0
        if row.get("supertrend_dir") == 1:
            pts += 1.0
        if pts >= 8.0:
            points += min(12.0, pts)
            pattern_ids.append("pullback_entry")

    # 5. Relative volume surge — institutional participation
    max_points += 12.0
    if rvol is not None and rvol >= 1.35 and bullish:
        pts = min(12.0, 5.0 + (rvol - 1.0) * 4.0)
        points += pts
        pattern_ids.append("volume_surge")

    # 6. News-catalyst alignment (when row already has news_score)
    news_score = row.get("news_score")
    max_points += 10.0
    if news_score is not None:
        try:
            ns = float(news_score)
            if ns >= 62 and bullish:
                points += min(10.0, (ns - 50) * 0.45)
                pattern_ids.append("news_catalyst_align")
        except (TypeError, ValueError):
            pass

    if max_points <= 0:
        return 50.0, [], {"pattern_score": 50.0, "pattern_ids": []}

    raw_pct = (points / max_points) * 100.0
    # Blend with neutral 50 when few patterns fire
    pattern_score = round(50.0 + (raw_pct - 50.0) * min(1.0, len(pattern_ids) / 2.5), 1)
    pattern_score = max(0.0, min(100.0, pattern_score))

    meta = {
        "pattern_score": pattern_score,
        "pattern_ids": pattern_ids,
        "pattern_points": round(points, 2),
        "early_session": early_session,
    }
    return pattern_score, pattern_ids, meta


def pattern_edge_boost(row: dict[str, Any], *, ist_mins: int | None = None) -> tuple[float, list[str], dict[str, Any]]:
    """Convert pattern_score into ranking edge points for intraday_edge_score."""
    cfg = pattern_cfg()
    score, pattern_ids, meta = score_intraday_patterns(row, ist_mins=ist_mins)
    if score < cfg["min_score_for_boost"]:
        boost = max(-4.0, (score - 50.0) * 0.08 * cfg["edge_weight"])
    else:
        boost = (score - 50.0) * 0.22 * cfg["edge_weight"]
    boost = round(max(-6.0, min(18.0, boost)), 2)
    reasons = [f"pat_{pid}" for pid in pattern_ids[:4]]
    if score >= 65:
        reasons.append(f"pattern_score_{score:.0f}")
    meta["pattern_edge_boost"] = boost
    return boost, reasons, meta


def batch_attach_pattern_scores(
    rows: list[dict[str, Any]],
    *,
    top_n: int | None = None,
    ist_mins: int | None = None,
) -> list[dict[str, Any]]:
    """Attach pattern_score / pattern_ids to top rows (cheap — no network)."""
    cfg = pattern_cfg()
    if not cfg["enabled"] or not rows:
        return rows

    n = top_n or int(load_trading_config().get("autopilot", {}).get("agent_news_enrich_top_n") or 80)
    ranked = sorted(rows, key=lambda r: float(r.get("composite_score") or 0), reverse=True)
    target_syms = {str(r.get("symbol") or "").upper() for r in ranked[:n] if r.get("symbol")}

    out: list[dict[str, Any]] = []
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        if sym not in target_syms:
            out.append(row)
            continue
        score, pattern_ids, meta = score_intraday_patterns(row, ist_mins=ist_mins)
        out.append({
            **row,
            "pattern_score": score,
            "pattern_ids": pattern_ids,
            **{k: v for k, v in meta.items() if k not in row},
        })
    return out
