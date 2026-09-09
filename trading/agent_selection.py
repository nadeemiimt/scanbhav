"""Seasoned-trader style ranking for agent auto-pick — cap bucket, vol, timing, edge."""
from __future__ import annotations

from typing import Any

from trading.config_store import load_trading_config

BULLISH_STANCES = {"favorable", "strong_favorable", "bullish", "constructive"}


def agent_selection_cfg() -> dict[str, Any]:
    ap = load_trading_config().get("autopilot") or {}
    return {
        "enabled": bool(ap.get("agent_smart_selection", True)),
        "min_atr_pct": float(ap.get("agent_min_atr_pct") or 2.0),
        "max_rsi_entry": float(ap.get("agent_max_rsi_entry") or 72),
        "min_rsi_entry": float(ap.get("agent_min_rsi_entry") or 35),
        "min_horizon_return_pct": float(ap.get("agent_min_horizon_return_pct") or 0.5),
        "min_quality_score": float(ap.get("agent_min_quality_score") or 0),
        "block_quality_fail": bool(ap.get("agent_block_quality_fail", False)),
        "no_buy_after_minute_ist": int(ap.get("agent_no_buy_after_minute_ist") or (10 * 60 + 30)),
        "curated_overlap_boost": float(ap.get("agent_curated_overlap_boost") or 18.0),
        "min_trade_notional_inr": float(ap.get("min_trade_notional_inr") or 25_000),
        "cap_weights": {
            "small": float(ap.get("agent_cap_weight_small") or 1.25),
            "mid": float(ap.get("agent_cap_weight_mid") or 1.12),
            "large": float(ap.get("agent_cap_weight_large") or 0.88),
        },
        "max_large_picks": int(ap.get("agent_max_large_picks") or 2),
        "max_mid_picks": int(ap.get("agent_max_mid_picks") or 5),
    }


def cap_bucket(row: dict[str, Any]) -> str:
    bucket = str(row.get("bucket") or "").lower()
    if bucket in {"large", "mid", "small"}:
        return bucket
    price = float(row.get("price") or 0)
    if price >= 2000:
        return "large"
    if price >= 500:
        return "mid"
    return "small"


def ist_minutes_now() -> int:
    from trading.market_hours import _ist_now

    now = _ist_now()
    return now.hour * 60 + now.minute


def realistic_intraday_move_pct(
    row: dict[str, Any],
    *,
    target_pct: float,
    ist_mins: int,
) -> float:
    """How much of the target is realistically reachable today (ATR, horizon, time left)."""
    atr = float(row.get("atr_pct") or 0)
    try:
        horizon = float(row.get("horizon_return_pct") or 0)
    except (TypeError, ValueError):
        horizon = 0.0

    market_open = 9 * 60 + 15
    market_close = 15 * 60 + 30
    session_len = max(1, market_close - market_open)
    time_left = max(0, market_close - ist_mins) / session_len

    # Seasoned MIS rule: expect ~60% of ATR, capped by horizon and target.
    move = min(float(target_pct), max(0.4, atr * 0.6))
    if horizon > 0:
        move = min(move, horizon * 0.45)
    move *= max(0.25, time_left)
    return round(max(0.25, move), 3)


def intraday_edge_score(
    row: dict[str, Any],
    *,
    target_pct: float,
    cfg: dict[str, Any],
    ist_mins: int,
) -> tuple[float, list[str], dict[str, Any]]:
    """Score a candidate for intraday MIS edge (higher = better profit potential)."""
    reasons: list[str] = []
    meta: dict[str, Any] = {}

    score = float(row.get("composite_score") or 0) * 0.22

    atr = float(row.get("atr_pct") or 0)
    if atr >= cfg["min_atr_pct"]:
        score += min(18.0, atr * 2.8)
        reasons.append(f"atr_{atr:.1f}%")
    else:
        score -= 10.0
        reasons.append(f"low_atr_{atr:.1f}")

    try:
        horizon = float(row.get("horizon_return_pct") or 0)
    except (TypeError, ValueError):
        horizon = 0.0
    if horizon >= cfg["min_horizon_return_pct"]:
        score += min(14.0, horizon * 0.85)
        reasons.append(f"horizon_{horizon:.1f}%")
    elif horizon < 0:
        score -= 8.0

    rsi = row.get("rsi_14")
    if isinstance(rsi, (int, float)):
        rsi_f = float(rsi)
        if cfg["min_rsi_entry"] <= rsi_f <= cfg["max_rsi_entry"]:
            score += 6.0
            reasons.append(f"rsi_{rsi_f:.0f}")
        elif rsi_f > cfg["max_rsi_entry"]:
            score -= 14.0
            reasons.append(f"rsi_extended_{rsi_f:.0f}")
        elif rsi_f < cfg["min_rsi_entry"]:
            score -= 5.0

    bucket = cap_bucket(row)
    score *= float(cfg["cap_weights"].get(bucket, 1.0))
    reasons.append(f"cap_{bucket}")
    meta["cap_bucket"] = bucket

    if row.get("pattern_bias") == "bullish":
        score += 5.0
        reasons.append("pattern_bullish")
    if row.get("supertrend_dir") == 1:
        score += 4.0
    if row.get("golden_cross"):
        score += 2.0

    rvol = row.get("rvol") if row.get("rvol") is not None else row.get("relative_volume")
    if isinstance(rvol, (int, float)) and float(rvol) >= 1.15:
        score += min(8.0, (float(rvol) - 1.0) * 5.0)
        reasons.append(f"rvol_{float(rvol):.1f}")

    qs = row.get("quality_score")
    if isinstance(qs, (int, float)) and float(qs) >= max(cfg["min_quality_score"], 45):
        score += 3.0

    realistic = realistic_intraday_move_pct(row, target_pct=target_pct, ist_mins=ist_mins)
    meta["realistic_move_pct"] = realistic
    score += realistic * 4.0
    reasons.append(f"realistic_{realistic:.1f}%")

    news_score = row.get("news_score")
    if news_score is not None:
        try:
            ns = float(news_score)
            news_boost = max(-5.0, min(14.0, (ns - 50.0) * 0.28))
            score += news_boost
            meta["news_score"] = ns
            if ns >= 58:
                reasons.append(f"news_{ns:.0f}")
        except (TypeError, ValueError):
            pass

    try:
        from trading.intraday_patterns import pattern_edge_boost

        pat_boost, pat_reasons, pat_meta = pattern_edge_boost(row, ist_mins=ist_mins)
        score += pat_boost
        reasons.extend(pat_reasons)
        meta.update(pat_meta)
    except Exception:
        pass

    qboost = row.get("quant_trigger_boost")
    qtriggers = row.get("quant_triggers") or []
    if qboost is not None:
        try:
            score += float(qboost)
            if qtriggers:
                reasons.append(f"quant_triggers_{len(qtriggers)}")
                meta["quant_triggers"] = qtriggers[:6]
        except (TypeError, ValueError):
            pass
    elif qtriggers:
        score += min(12.0, len(qtriggers) * 2.5)
        reasons.append(f"quant_triggers_{len(qtriggers)}")
        meta["quant_triggers"] = qtriggers[:6]

    return round(score, 2), reasons, meta


def agent_candidate_gate(
    row: dict[str, Any],
    *,
    cfg: dict[str, Any] | None = None,
    ist_mins: int | None = None,
    check_session_time: bool = True,
) -> tuple[bool, str]:
    cfg = cfg or agent_selection_cfg()
    ist_mins = ist_mins if ist_mins is not None else ist_minutes_now()

    if check_session_time and ist_mins >= cfg["no_buy_after_minute_ist"]:
        return False, "agent_late_session_no_buy"

    atr = float(row.get("atr_pct") or 0)
    if atr < cfg["min_atr_pct"] * 0.9:
        return False, f"atr_too_low_{atr:.1f}"

    rsi = row.get("rsi_14")
    if isinstance(rsi, (int, float)) and float(rsi) > cfg["max_rsi_entry"]:
        return False, f"rsi_extended_{float(rsi):.0f}"

    try:
        horizon = float(row.get("horizon_return_pct") or 0)
    except (TypeError, ValueError):
        horizon = 0.0
    if horizon < 0:
        return False, "negative_horizon"

    if cfg["block_quality_fail"] and row.get("quality_ok") is False:
        qs = float(row.get("quality_score") or 0)
        if qs < cfg["min_quality_score"]:
            return False, "quality_fail"

    try:
        from trading.config_store import load_trading_config

        ap = load_trading_config().get("autopilot") or {}
        if ap.get("quant_llm_synthesis_enabled"):
            from quant_layer.pipeline import load_quant_digest_lookup

            lookup = load_quant_digest_lookup()
            sym = str(row.get("symbol") or "").upper()
            llm = lookup.get(sym) or lookup.get(sym.replace(".NSE", ""))
            if llm:
                min_conv = float(ap.get("quant_llm_min_conviction") or 4.0)
                conv = float(llm.get("conviction_score") or 0)
                if conv < min_conv:
                    return False, f"quant_llm_low_conviction_{conv:.1f}"
                if llm.get("false_breakout_risk"):
                    return False, "quant_llm_false_breakout_risk"
    except Exception:
        pass

    return True, "ok"


def rank_rows_for_agent(
    rows: list[dict[str, Any]],
    *,
    min_composite: float,
    held: set[str],
    top_n: int,
    target_pct: float,
    ist_mins: int | None = None,
    curated_symbols: set[str] | None = None,
    cross_desk_held: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Filter + rank by intraday edge (not just morning-scan composite order)."""
    cfg = agent_selection_cfg()
    ist_mins = ist_mins if ist_mins is not None else ist_minutes_now()
    curated = {str(s or "").upper().replace(".NSE", "") for s in (curated_symbols or set())}
    cross = {str(s or "").upper().replace(".NSE", "") for s in (cross_desk_held or set())}
    ranked: list[tuple[float, dict[str, Any]]] = []

    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        sym_base = sym.replace(".NSE", "")
        if not sym or sym in held or sym_base in cross:
            continue
        composite = float(row.get("composite_score") or 0)
        stance = str(row.get("stance") or "").lower()
        if composite < min_composite or stance not in BULLISH_STANCES:
            continue
        if float(row.get("price") or 0) <= 0:
            continue
        if not cfg["enabled"]:
            ranked.append((composite, row))
            continue
        allowed, _reason = agent_candidate_gate(
            row, cfg=cfg, ist_mins=ist_mins, check_session_time=False
        )
        if not allowed:
            continue
        edge, _reasons, _meta = intraday_edge_score(row, target_pct=target_pct, cfg=cfg, ist_mins=ist_mins)
        from trading.agent_learning import agent_learning_score

        learn_adj, learn_meta, learn_reasons = agent_learning_score(
            row,
            curated_symbols=curated,
            ist_mins=ist_mins,
        )
        edge += learn_adj
        row_out = {
            **row,
            "edge_score": round(edge, 2),
            "agent_learning": learn_meta,
            "learning_reasons": learn_reasons,
            "learning_adj": learn_adj,
        }
        ranked.append((edge, row_out))

    ranked.sort(key=lambda x: x[0], reverse=True)
    if not cfg["enabled"]:
        return [r for _, r in ranked[:top_n]]
    return [r for _, r in ranked[:top_n]]


def expected_profit_inr(notional: float, row: dict[str, Any], *, target_pct: float, ist_mins: int | None = None) -> tuple[float, float]:
    """Return (expected_profit_inr, realistic_move_pct) using edge-aware move estimate."""
    ist_mins = ist_mins if ist_mins is not None else ist_minutes_now()
    move = realistic_intraday_move_pct(row, target_pct=target_pct, ist_mins=ist_mins)
    return round(notional * (move / 100.0), 2), move


def select_diversified_picks(
    candidates: list[dict[str, Any]],
    *,
    max_picks: int,
    cfg: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Pick across large/mid/small — avoid all-large bank basket."""
    cfg = cfg or agent_selection_cfg()
    if not cfg["enabled"] or max_picks <= 0:
        return candidates[:max_picks]

    picks: list[dict[str, Any]] = []
    bucket_counts = {"large": 0, "mid": 0, "small": 0}
    picked_syms: set[str] = set()

    for cand in candidates:
        if len(picks) >= max_picks:
            break
        sym = str(cand.get("symbol") or "").upper()
        if sym in picked_syms:
            continue
        bucket = str(cand.get("cap_bucket") or cap_bucket(cand.get("screen_row") or cand))
        if bucket == "large" and bucket_counts["large"] >= cfg["max_large_picks"]:
            continue
        if bucket == "mid" and bucket_counts["mid"] >= cfg["max_mid_picks"]:
            continue
        picks.append(cand)
        picked_syms.add(sym)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    if len(picks) < max_picks:
        for cand in candidates:
            if len(picks) >= max_picks:
                break
            sym = str(cand.get("symbol") or "").upper()
            if sym in picked_syms:
                continue
            picks.append(cand)
            picked_syms.add(sym)
    return picks
