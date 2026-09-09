"""Crowd psychology gates for autopilot buy/sell decisions."""
from __future__ import annotations

from typing import Any, Optional

from behavior_psychology import analyze_trader_behavior
from trading.config_store import load_trading_config


def _psych_cfg() -> dict[str, Any]:
    ap = load_trading_config().get("autopilot") or {}
    return {
        "enabled": bool(ap.get("psychology_enabled", True)),
        "gate_buys": bool(ap.get("psychology_gate_buys", True)),
        "gate_sells": bool(ap.get("psychology_gate_sells", True)),
        "block_rsi_fomo": float(ap.get("psychology_block_rsi_fomo") or 78),
        "block_sentiment_high": float(ap.get("psychology_block_sentiment_high") or 85),
        "block_sentiment_low": float(ap.get("psychology_block_sentiment_low") or 22),
        "early_take_pct": float(ap.get("psychology_early_take_pct") or 0.9),
        "fear_stop_pct": float(ap.get("psychology_fear_stop_pct") or 0.55),
        "greed_rsi_take": float(ap.get("psychology_greed_rsi_take") or 70),
    }


def _num(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _row_to_technicals(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "momentum": {"rsi_14": row.get("rsi_14")},
        "moving_averages": {
            "price_vs_sma_200_pct": row.get("price_vs_sma_200_pct"),
            "price_vs_sma_50_pct": row.get("price_vs_sma_50_pct"),
            "golden_cross": row.get("golden_cross"),
        },
        "volatility": {"atr_pct": row.get("atr_pct")},
        "volume": {"rvol": row.get("rvol") or row.get("relative_volume")},
        "levels": {
            "dist_from_52w_high_pct": row.get("dist_from_52w_high_pct"),
            "dist_from_52w_low_pct": row.get("dist_from_52w_low_pct"),
        },
        "trend": {"supertrend_dir": row.get("supertrend_dir")},
    }


def _row_to_ratings(row: dict[str, Any]) -> dict[str, Any]:
    bucket = str(row.get("bucket") or "1d")
    return {
        "composite_stance": row.get("stance") or "neutral",
        "best_horizon": bucket,
        "horizons": {
            bucket: {"horizon_return_pct": row.get("horizon_return_pct")},
        },
    }


def _social_sentiment(symbol: str, row: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    if row:
        social = row.get("social_volume") or row.get("social") or {}
        if social.get("sentiment_score") is not None:
            return {
                "sentiment_score": _num(social.get("sentiment_score")),
                "sentiment_label": social.get("sentiment_label"),
                "source": "row",
            }
    sym = str(symbol or "").upper()
    if not sym:
        return {}

    def _fetch() -> dict[str, Any]:
        try:
            from analysis.social_volume import fetch_social_volume

            data = fetch_social_volume(sym)
            if data.get("status") not in {None, "ok"}:
                return {"source": data.get("source") or "social", "status": data.get("status")}
            return {
                "sentiment_score": _num(data.get("sentiment_score")),
                "sentiment_label": data.get("sentiment_label"),
                "message_volume_score": _num(data.get("message_volume_score")),
                "source": data.get("source") or "social_volume",
                "status": data.get("status") or "ok",
            }
        except Exception as exc:
            return {"status": "error", "error": str(exc)[:120]}

    from analysis._ttl_cache import get_ttl_cached

    return get_ttl_cached(f"psych.social.{sym}", 120.0, _fetch)


def psychology_from_row(row: dict[str, Any], *, fetch_social: bool = True) -> dict[str, Any]:
    """Build psychology snapshot from screener / morning-scan row."""
    sym = str(row.get("symbol") or "").upper()
    psych = analyze_trader_behavior(_row_to_technicals(row), _row_to_ratings(row))
    if fetch_social:
        social = _social_sentiment(sym, row)
    else:
        embedded = row.get("social_volume") or row.get("social") or {}
        social = (
            {
                "sentiment_score": _num(embedded.get("sentiment_score")),
                "sentiment_label": embedded.get("sentiment_label"),
                "source": "row",
            }
            if embedded.get("sentiment_score") is not None
            else {"source": "scan_row", "status": "skipped"}
        )
    return {
        **psych,
        "symbol": sym,
        "social": social,
        "sentiment_score": social.get("sentiment_score"),
        "sentiment_label": social.get("sentiment_label"),
    }


def fetch_live_psychology(symbol: str) -> dict[str, Any]:
    """Live psychology with TTL cache — for guard exits and top-ups."""
    sym = str(symbol or "").upper()
    if not sym:
        return {}

    def _build() -> dict[str, Any]:
        try:
            from routes.helpers import fetch_prices, rows_from_payload
            from technicals import compute_technicals
            from horizon_rank import rate_all_horizons

            payload = fetch_prices(sym, "auto", force_refresh=False)
            rows = rows_from_payload(payload)
            tech = compute_technicals(rows)
            ratings = rate_all_horizons(tech)
            psych = analyze_trader_behavior(tech, ratings)
            social = _social_sentiment(sym)
            row = {
                "symbol": sym,
                "rsi_14": (tech.get("momentum") or {}).get("rsi_14"),
                "stance": ratings.get("composite_stance"),
                "horizon_return_pct": ((ratings.get("horizons") or {}).get("1d") or {}).get("horizon_return_pct"),
                "supertrend_dir": (tech.get("trend") or {}).get("supertrend_dir"),
                "dist_from_52w_high_pct": (tech.get("levels") or {}).get("dist_from_52w_high_pct"),
                "rvol": (tech.get("volume") or {}).get("rvol"),
            }
            return {
                **psych,
                "symbol": sym,
                "social": social,
                "sentiment_score": social.get("sentiment_score"),
                "sentiment_label": social.get("sentiment_label"),
                "screen_row": row,
            }
        except Exception as exc:
            return {
                "symbol": sym,
                "primary_mood": "unknown",
                "status": "error",
                "error": str(exc)[:160],
            }

    from analysis._ttl_cache import get_ttl_cached

    return get_ttl_cached(f"psych.live.{sym}", 90.0, _build)


def psychology_score_adjustment(psych: dict[str, Any]) -> tuple[float, list[str]]:
    """Pick-score nudge from crowd mood."""
    cfg = _psych_cfg()
    if not cfg["enabled"]:
        return 0.0, []

    mood = str(psych.get("primary_mood") or "balanced")
    rsi = _num(psych.get("rsi_14"))
    sentiment = _num(psych.get("sentiment_score"))
    stance = str(psych.get("composite_stance") or "").lower()
    adj = 0.0
    reasons: list[str] = []

    if mood == "optimistic":
        adj += 2.0
        reasons.append("psych_optimistic +2")
    elif mood == "balanced":
        adj += 0.5
    elif mood == "defensive":
        adj -= 3.0
        reasons.append("psych_defensive -3")
    elif mood == "greed-prone":
        adj -= 4.0
        reasons.append("psych_greed -4")
    elif mood == "fear-prone":
        if stance in {"favorable", "strong_favorable", "bullish", "constructive"}:
            adj += 2.5
            reasons.append("psych_fear_dip +2.5")
        else:
            adj -= 2.0
            reasons.append("psych_fear -2")

    if sentiment is not None:
        if sentiment >= 70:
            adj += 1.0
            reasons.append(f"sentiment_high {sentiment:.0f} +1")
        elif sentiment <= 35:
            adj -= 1.5
            reasons.append(f"sentiment_low {sentiment:.0f} -1.5")

    if rsi is not None and rsi >= 75:
        adj -= 2.0
        reasons.append(f"rsi_extended {rsi:.0f} -2")

    return round(max(-8.0, min(8.0, adj)), 2), reasons


def evaluate_buy_psychology(
    psych: dict[str, Any],
    *,
    pick: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Gate or allow a buy based on crowd psychology."""
    cfg = _psych_cfg()
    mood = str(psych.get("primary_mood") or "balanced")
    rsi = _num(psych.get("rsi_14"))
    sentiment = _num(psych.get("sentiment_score"))
    stance = str(psych.get("composite_stance") or (pick.get("stance") if pick else None) or "").lower()
    score_adj, score_reasons = psychology_score_adjustment(psych)

    allowed = True
    block_reason = ""
    warnings: list[str] = list(psych.get("behavior_risks") or [])[:2]

    if not cfg["enabled"] or not cfg["gate_buys"]:
        return {
            "allowed": True,
            "reason": "psychology_disabled",
            "primary_mood": mood,
            "score_adjustment": score_adj,
            "score_reasons": score_reasons,
            "psychology": psych,
            "warnings": warnings,
        }

    if rsi is not None and rsi >= cfg["block_rsi_fomo"] and mood == "greed-prone":
        allowed = False
        block_reason = f"FOMO block — RSI {rsi:.0f} greed-prone (≥{cfg['block_rsi_fomo']:.0f})"

    if allowed and sentiment is not None and sentiment >= cfg["block_sentiment_high"] and mood in {"greed-prone", "optimistic"}:
        allowed = False
        block_reason = f"Crowd euphoria — sentiment {sentiment:.0f} with {mood} mood"

    if allowed and sentiment is not None and sentiment <= cfg["block_sentiment_low"]:
        if not (mood == "fear-prone" and stance in {"favorable", "strong_favorable", "bullish", "constructive"}):
            allowed = False
            block_reason = f"Sentiment panic — score {sentiment:.0f} without bullish capitulation setup"

    if allowed and mood == "defensive" and stance in {"cautious", "unfavorable", "bearish", "avoid"}:
        allowed = False
        block_reason = "Defensive crowd + bearish stance — wait for confirmation"

    dist_high = _num(psych.get("dist_from_52w_high_pct"))
    if allowed and dist_high is not None and dist_high > -2 and mood == "greed-prone":
        warnings.append("Near 52w high with greed-prone mood — breakout or trap risk")

    return {
        "allowed": allowed,
        "reason": block_reason or ("psych_ok" if allowed else "psych_blocked"),
        "primary_mood": mood,
        "sentiment_score": sentiment,
        "rsi_14": rsi,
        "score_adjustment": score_adj,
        "score_reasons": score_reasons,
        "psychology": psych,
        "warnings": warnings,
        "headline": psych.get("headline") or psych.get("plain_english"),
    }


def evaluate_sell_psychology(
    *,
    symbol: str,
    ret_pct: float,
    psych: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Optional psychology-driven exit before standard target/stop."""
    cfg = _psych_cfg()
    if not cfg["enabled"] or not cfg["gate_sells"]:
        return {"trigger": None, "psychology": psych or {}}

    if psych is None:
        psych = fetch_live_psychology(symbol)

    mood = str(psych.get("primary_mood") or "balanced")
    rsi = _num(psych.get("rsi_14"))
    sentiment = _num(psych.get("sentiment_score"))
    trigger = None
    note = ""

    if (
        ret_pct >= cfg["early_take_pct"]
        and mood == "greed-prone"
        and rsi is not None
        and rsi >= cfg["greed_rsi_take"]
    ):
        trigger = "psych_take_profit"
        note = f"Book gain early — greed-prone crowd RSI {rsi:.0f}, +{ret_pct:.2f}%"

    elif (
        ret_pct <= -cfg["fear_stop_pct"]
        and mood in {"fear-prone", "defensive"}
        and (sentiment is None or sentiment <= 40)
    ):
        trigger = "psych_fear_cut"
        note = f"Tight psychology stop — fear/defensive mood, {ret_pct:.2f}%"

    elif ret_pct >= 0.5 and mood == "greed-prone" and sentiment is not None and sentiment >= 80:
        trigger = "psych_take_profit"
        note = f"Extreme social euphoria ({sentiment:.0f}) — lock partial gain +{ret_pct:.2f}%"

    return {
        "trigger": trigger,
        "note": note,
        "primary_mood": mood,
        "sentiment_score": sentiment,
        "rsi_14": rsi,
        "psychology": psych,
    }


def resolve_psychology_for_pick(pick: dict[str, Any], *, fetch_social: bool = True) -> dict[str, Any]:
    """Psychology snapshot for a pick (row-first, else live)."""
    row = pick.get("screen_row") or pick
    sym = str(pick.get("symbol") or row.get("symbol") or "").upper()
    if row.get("rsi_14") is not None or row.get("stance"):
        return psychology_from_row({**row, "symbol": sym}, fetch_social=fetch_social)
    return fetch_live_psychology(sym)
