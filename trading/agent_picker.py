"""Agent-autonomous stock picker — Nifty 500, budget-aware, max-profit allocation."""
from __future__ import annotations

from typing import Any, Optional

from screener import load_cached_screen
from trading.config_store import load_trading_config
from trading.morning_scan import load_morning_scan, rows_from_morning_scan
from trading.order_router import agent_trade_from_signal
from trading.paper_ledger import daily_stats, open_positions
from trading.symbol_validate import CURATED_SYMBOLS_MAX
from universe import universe_symbols

BULLISH_STANCES = {"favorable", "strong_favorable", "bullish", "constructive"}
BEARISH_STANCES = {"cautious", "unfavorable", "bearish", "avoid"}


def _resolve_max_picks(max_picks: int) -> int:
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    risk = cfg.get("risk") or {}
    cap = int(ap.get("max_concurrent_picks") or risk.get("max_open_positions") or 3)
    requested = int(max_picks) if max_picks else cap
    return max(1, min(10, min(requested, cap)))


def _agent_scan_top_n() -> int:
    """Max morning-scan rows to deep-score per agent cycle (rest are skipped)."""
    ap = load_trading_config().get("autopilot") or {}
    n = int(ap.get("agent_scan_top_n") or ap.get("morning_scan_rag_top") or 80)
    return max(20, min(200, n))


def _prefilter_bullish_rows(
    rows: list[dict[str, Any]],
    *,
    min_composite: float,
    held: set[str],
    top_n: int,
) -> list[dict[str, Any]]:
    """Cheap filter before scoring — rows are assumed ranked by composite (morning scan)."""
    out: list[dict[str, Any]] = []
    for row in rows:
        sym = str(row.get("symbol") or "").upper()
        if not sym or sym in held:
            continue
        composite = float(row.get("composite_score") or 0)
        stance = str(row.get("stance") or "").lower()
        if composite < min_composite or stance not in BULLISH_STANCES:
            continue
        price = float(row.get("price") or 0)
        if price <= 0:
            continue
        out.append(row)
        if len(out) >= top_n:
            break
    return out


def _rag_score_adjustment(symbol: str) -> float:
    """Nudge pick score from past autopilot outcomes + session digests in RAG."""
    try:
        from trading.pick_learning import retrieve_agent_lessons, retrieve_session_digests

        lessons = retrieve_agent_lessons(symbol, top_k=4)
        if not lessons:
            return 0.0
        adj = 0.0
        for row in lessons:
            stance = str(row.get("stance") or "").lower()
            kind = str(row.get("kind") or "")
            if stance == "win":
                adj += 2.5 if kind == "autopilot_session_symbol_digest" else 2.0
            elif stance == "loss":
                adj -= 3.5 if kind == "autopilot_session_symbol_digest" else 3.0
            elif kind == "autopilot_operational_lesson":
                adj -= 4.0 if stance == "loss" else (2.0 if stance == "win" else 0)
            elif kind == "autopilot_session_digest":
                adj += 0.5 if stance == "win" else (-0.5 if stance == "loss" else 0)
        # Global session context (last day lessons)
        for row in retrieve_session_digests(symbols=[symbol], top_k=1):
            if row.get("kind") == "autopilot_session_digest":
                if str(row.get("stance") or "").lower() == "win":
                    adj += 1.0
                elif str(row.get("stance") or "").lower() == "loss":
                    adj -= 1.0
        return max(-10.0, min(10.0, adj))
    except Exception:
        return 0.0


def _budget_limits(session: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    cfg = load_trading_config()
    risk = cfg.get("risk") or {}
    daily = daily_stats()
    open_p = open_positions("mis")

    max_per_order = float(risk.get("max_position_inr") or 50000)
    max_orders = int(risk.get("max_orders_per_day") or 5)
    orders_left = max(0, max_orders - int(daily.get("orders") or 0))

    if session:
        caps = session.get("caps") or {}
        session_id = str(session.get("id") or "")
        max_daily = float(caps.get("max_daily_notional_inr") or risk.get("max_daily_notional_inr") or 100000)
        used_notional = 0.0
        cross_desk: set[str] = set()
        try:
            from trading.session_autopilot import _session_buy_notional, _session_open_symbols, cross_desk_held_symbols

            used_notional = _session_buy_notional(session_id)
            held = _session_open_symbols(session_id)
            cross_desk = cross_desk_held_symbols(session_id)
        except Exception:
            held = {p.get("symbol") for p in open_p}
            used_notional = float(daily.get("buy_notional_inr") or 0)
        max_open = int(session.get("max_concurrent_picks") or risk.get("max_open_positions") or 3)
        slots = max(0, max_open - len(held))
    else:
        held = {p.get("symbol") for p in open_p}
        cross_desk = set()
        max_daily = float(risk.get("max_daily_notional_inr") or 100000)
        used_notional = float(daily.get("buy_notional_inr") or 0)
        max_open = int(risk.get("max_open_positions") or 3)
        slots = max(0, max_open - len(open_p))

    remaining_budget = max(0.0, max_daily - used_notional)

    return {
        "max_per_order_inr": max_per_order,
        "max_daily_notional_inr": max_daily,
        "buy_notional_used_inr": used_notional,
        "remaining_budget_inr": remaining_budget,
        "open_positions": len(held) if session else len(open_p),
        "position_slots": slots,
        "orders_left": orders_left,
        "held_symbols": held,
        "cross_desk_symbols": cross_desk,
        "halted": bool(daily.get("halted")),
        "session_id": str(session.get("id") or "") if session else None,
    }


def _load_nifty500_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Ranked Nifty 500 rows — prefer morning scan, then screener cache."""
    ms = load_morning_scan()
    if ms and ms.get("rows"):
        meta = {
            "source": "morning_scan",
            "as_of": ms.get("trade_date_ist"),
            "scored": ms.get("scored"),
        }
        return list(ms["rows"]), meta

    cached = load_cached_screen()
    meta: dict[str, Any] = {"source": "nifty500_screen_cache", "cache_available": bool(cached)}
    if cached:
        meta["as_of"] = (cached.get("meta") or {}).get("as_of")
        meta["scored"] = cached.get("scored")
        rows = list(cached.get("top") or [])
        if rows:
            valid = set(universe_symbols())
            rows = [r for r in rows if str(r.get("symbol", "")).upper() in valid]
            return rows, meta

    meta["source"] = "nifty500_symbols_only"
    meta["warning"] = "Run morning scan or Nifty 500 screen for ranked picks."
    syms = universe_symbols()
    return [{"symbol": s, "price": None, "composite_score": 0, "stance": "neutral"} for s in syms], meta


def _given_stock_universe(seed_symbol: str = "") -> list[str]:
    cfg = load_trading_config()
    watchlist = [s.upper().strip() for s in (cfg.get("watchlist") or []) if s]
    seed = seed_symbol.upper().strip() if seed_symbol else ""
    out = list(dict.fromkeys([s for s in ([seed] if seed else []) + watchlist if s]))
    return out


def _technicals_factor_score(row: dict[str, Any]) -> float:
    score = 50.0
    if row.get("supertrend_dir") == 1:
        score += 8
    elif row.get("supertrend_dir") == -1:
        score -= 8
    if row.get("golden_cross"):
        score += 6
    macd = row.get("macd_hist")
    if isinstance(macd, (int, float)):
        score += max(-8.0, min(8.0, float(macd) * 2))
    rsi = row.get("rsi_14")
    if isinstance(rsi, (int, float)):
        if 45 <= rsi <= 65:
            score += 5
        elif rsi >= 78:
            score -= 8
        elif rsi <= 25:
            score -= 5
    adx = row.get("adx_14")
    if isinstance(adx, (int, float)) and adx >= 25:
        score += 4
    return max(0.0, min(100.0, score))


def _horizons_factor_score(row: dict[str, Any]) -> float:
    hr = row.get("horizon_return_pct")
    if hr is None:
        return 50.0
    try:
        return max(0.0, min(100.0, 50.0 + float(hr) * 4.0))
    except (TypeError, ValueError):
        return 50.0


def _competitive_factor_score(row: dict[str, Any]) -> float:
    qs = row.get("quality_score")
    if isinstance(qs, (int, float)):
        return max(0.0, min(100.0, float(qs)))
    if row.get("quality_ok") is True:
        return 65.0
    if row.get("quality_ok") is False:
        return 35.0
    return 50.0


def _calibration_base_score(row: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    """Weighted factor score from scoreboard calibration weights."""
    try:
        from trading.autopilot import load_calibration

        weights = load_calibration().get("weights") or {}
    except Exception:
        weights = {}

    composite = float(row.get("composite_score") or 50)
    if not weights:
        return composite * 0.5, {"source": "composite_fallback"}

    try:
        from trading.market_news_intel import news_factor_from_row

        news_factor = news_factor_from_row(row)
    except Exception:
        news_factor = 50.0

    factors = {
        "technicals": _technicals_factor_score(row),
        "composite": composite,
        "horizons": _horizons_factor_score(row),
        "competitive": _competitive_factor_score(row),
        "news": news_factor,
    }
    total_w = sum(float(weights.get(k, 0)) for k in factors) or 1.0
    weighted = sum(float(weights.get(k, 0)) / total_w * v for k, v in factors.items())
    return round(weighted * 0.55, 2), {"calibration_factors": factors, "calibration_weights": weights}


def _expected_return_pct(row: dict[str, Any], *, target_pct: float) -> float:
    """Intraday MIS profit expectation (%)."""
    horizon_ret = row.get("horizon_return_pct")
    _, cal_meta = _calibration_base_score(row)
    factors = cal_meta.get("calibration_factors") or {}
    composite = float(factors.get("composite") or row.get("composite_score") or 50)
    base = float(target_pct)
    if horizon_ret is not None:
        try:
            hr = float(horizon_ret)
            if 0 < hr < 20:
                base = min(base * 1.25, hr)
        except (TypeError, ValueError):
            pass
    confidence = max(0.35, min(1.0, composite / 100.0))
    tech_boost = 0.0
    if row.get("supertrend_dir") == 1:
        tech_boost += 0.15
    if row.get("golden_cross"):
        tech_boost += 0.1
    macd = row.get("macd_hist")
    if isinstance(macd, (int, float)) and macd > 0:
        tech_boost += 0.08
    horizons = float(factors.get("horizons") or 50)
    if horizons >= 60:
        tech_boost += 0.05
    return round(base * confidence * (1 + tech_boost), 4)


def _score_screen_row(
    row: dict[str, Any],
    *,
    target_pct: float,
    desk_symbol: str = "",
    fast: bool = False,
    include_rag: bool = False,
) -> dict[str, Any]:
    sym = str(row.get("symbol") or "").upper()
    composite = float(row.get("composite_score") or 0)
    stance = str(row.get("stance") or "neutral").lower()
    price = row.get("price")
    exp_ret = _expected_return_pct(row, target_pct=target_pct)

    score, cal_meta = _calibration_base_score(row)
    reasons: list[str] = [f"cal_base {score:.1f}"]
    if cal_meta.get("calibration_factors"):
        top_factor = max(
            cal_meta["calibration_factors"].items(),
            key=lambda kv: kv[1],
        )
        reasons.append(f"top_factor {top_factor[0]} {top_factor[1]:.0f}")

    if stance in BULLISH_STANCES:
        score += {"strong_favorable": 12, "favorable": 10, "bullish": 9, "constructive": 7}.get(stance, 5)
        reasons.append(stance)
    elif stance in BEARISH_STANCES:
        score -= 15

    rsi = row.get("rsi_14")
    if isinstance(rsi, (int, float)):
        if 45 <= rsi <= 65:
            score += 3
        elif rsi >= 78:
            score -= 5

    if desk_symbol and sym == desk_symbol.upper():
        score += 2

    if row.get("quality_ok") is False:
        score -= 8
        reasons.append("quality_fail")
    elif row.get("quality_ok") is True:
        score += 4
    if row.get("pattern_bias") == "bullish":
        score += 5
        reasons.append("pattern_bullish")
    elif row.get("pattern_bias") == "bearish":
        score -= 6
        reasons.append("pattern_bearish")
    if not fast or include_rag:
        rag_adj = _rag_score_adjustment(sym)
        if rag_adj:
            score += rag_adj
            reasons.append(f"rag_adj {rag_adj:+.1f}")
        try:
            from trading.pick_learning import symbol_win_rate_adjustment

            wr_adj = symbol_win_rate_adjustment(sym)
            if wr_adj:
                score += wr_adj
                reasons.append(f"symbol_wr {wr_adj:+.1f}")
        except Exception:
            pass
    qs = row.get("quality_score")
    if isinstance(qs, (int, float)) and qs >= 65:
        score += 3

    psychology_gate: dict[str, Any] = {}
    try:
        from trading.psychology_gates import evaluate_buy_psychology, psychology_from_row, psychology_score_adjustment

        psych = psychology_from_row(row, fetch_social=not fast)
        psych_adj, psych_reasons = psychology_score_adjustment(psych)
        if psych_adj:
            score += psych_adj
            reasons.extend(psych_reasons)
        psychology_gate = evaluate_buy_psychology(psych)
    except Exception:
        psych = {}
        psychology_gate = {"allowed": True, "reason": "psych_unavailable"}

    return {
        "symbol": sym,
        "pick_score": round(score, 2),
        "composite_score": composite,
        "stance": stance,
        "price": price,
        "expected_return_pct": exp_ret,
        "reasons": reasons,
        "calibration": cal_meta,
        "screen_row": row,
        "psychology": psych,
        "psychology_gate": psychology_gate,
    }


def _size_for_budget(
    price: float,
    *,
    limits: dict[str, Any],
    remaining_budget: float,
    max_shares_cap: Optional[int] = None,
    atr_pct: Optional[float] = None,
    stop_pct: Optional[float] = None,
    row: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    if price <= 0:
        return None
    max_per_order = float(limits["max_per_order_inr"])
    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    risk = cfg.get("risk") or {}
    stop = float(stop_pct if stop_pct is not None else ap.get("stop_pct") or risk.get("default_stop_pct") or 1.0)

    if ap.get("atr_risk_sizing_enabled", True) and atr_pct is not None:
        from trading.intraday_rules import conviction_risk_multiplier, risk_per_trade_inr, size_by_atr_risk

        risk_inr = risk_per_trade_inr(ap, risk)
        if row:
            risk_inr *= conviction_risk_multiplier(row, ap)
        atr_sized = size_by_atr_risk(
            price,
            atr_pct=float(atr_pct or 0),
            stop_pct=stop,
            risk_inr=risk_inr,
            max_per_order_inr=max_per_order,
            remaining_budget_inr=remaining_budget,
            max_shares_cap=max_shares_cap,
        )
        if atr_sized:
            return atr_sized

    max_qty_order = int(max_per_order // price)
    max_qty_budget = int(remaining_budget // price)
    qty = min(max_qty_order, max_qty_budget)
    if max_shares_cap and max_shares_cap > 0:
        qty = min(qty, int(max_shares_cap))
    if qty < 1:
        return None
    notional = round(price * qty, 2)
    if notional > max_per_order + 0.01 or notional > remaining_budget + 0.01:
        return None
    return {"quantity": qty, "notional_inr": notional, "price": price, "sizing_method": "max_cap"}


def allocate_budget_picks(
    rows: list[dict[str, Any]],
    *,
    limits: dict[str, Any],
    max_picks: int,
    min_composite: float,
    target_pct: float,
    max_shares_cap: Optional[int] = None,
    desk_symbol: str = "",
    agent_smart: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    From Nifty 500 ranked rows, pick names that fit per-order + daily budget.
    When agent_smart=True, rank by intraday edge (ATR, cap bucket, timing) and
    diversify across large/mid/small — not just max notional × composite.
    """
    remaining = float(limits["remaining_budget_inr"])
    slots = int(limits["position_slots"])
    orders_left = int(limits["orders_left"])
    held = limits.get("held_symbols") or set()
    cross_desk = limits.get("cross_desk_symbols") or set()
    cfg = load_trading_config()
    ap_cfg = cfg.get("autopilot") or {}
    risk_cfg = cfg.get("risk") or {}
    min_notional = float(ap_cfg.get("min_trade_notional_inr") or risk_cfg.get("min_trade_notional_inr") or 25_000)
    curated_set: set[str] = set()
    if agent_smart:
        curated_set = {
            str(s or "").upper().replace(".NSE", "")
            for s in (
                (ap_cfg.get("curated_symbols") or [])
                + list(cfg.get("watchlist") or [])
            )
        }
    max_trades = min(max(1, max_picks), slots, orders_left)
    if max_trades <= 0 or remaining <= 0 or limits.get("halted"):
        return [], []

    stop_pct = float(ap_cfg.get("stop_pct") or risk_cfg.get("default_stop_pct") or 1.0)
    from trading.intraday_rules import dynamic_target_pct

    candidates: list[dict[str, Any]] = []
    scan_top_n = max(_agent_scan_top_n(), max_trades * 12)
    if agent_smart:
        from trading.agent_selection import (
            agent_selection_cfg,
            cap_bucket,
            expected_profit_inr,
            intraday_edge_score,
            ist_minutes_now,
            rank_rows_for_agent,
            select_diversified_picks,
        )

        sel_cfg = agent_selection_cfg()
        ist_mins = ist_minutes_now()
        eligible_rows = rank_rows_for_agent(
            rows,
            min_composite=min_composite,
            held=held,
            top_n=scan_top_n,
            target_pct=target_pct,
            curated_symbols=curated_set,
            cross_desk_held=cross_desk,
        )
    else:
        sel_cfg = None
        ist_mins = None
        eligible_rows = _prefilter_bullish_rows(
            rows,
            min_composite=min_composite,
            held=held,
            top_n=scan_top_n,
        )
    for row in eligible_rows:
        sym = str(row.get("symbol") or "").upper()
        scored = _score_screen_row(
            row,
            target_pct=target_pct,
            desk_symbol=desk_symbol,
            fast=True,
            include_rag=agent_smart,
        )
        psych_gate = scored.get("psychology_gate") or {}
        if psych_gate.get("allowed") is False:
            continue
        price = float(scored.get("price") or row.get("price") or 0)
        sized = _size_for_budget(
            price,
            limits=limits,
            remaining_budget=remaining,
            max_shares_cap=max_shares_cap,
            atr_pct=float(row.get("atr_pct") or 0),
            stop_pct=stop_pct,
            row=row,
        )
        if not sized:
            continue
        if agent_smart and float(sized.get("notional_inr") or 0) < min_notional:
            continue
        row_target = dynamic_target_pct(row, ap_cfg) if ap_cfg.get("dynamic_target_enabled", True) else target_pct
        if agent_smart and sel_cfg:
            edge, edge_reasons, edge_meta = intraday_edge_score(
                row, target_pct=target_pct, cfg=sel_cfg, ist_mins=ist_mins or 0
            )
            expected_profit, realistic_move = expected_profit_inr(
                sized["notional_inr"], row, target_pct=row_target, ist_mins=ist_mins
            )
            cap_b = edge_meta.get("cap_bucket") or cap_bucket(row)
            fit = (
                f"₹{sized['notional_inr']:,.0f} · {cap_b} · "
                f"edge {edge:.0f} · target {row_target:.1f}% · ~{realistic_move:.1f}% move"
            )
            candidates.append({
                **scored,
                **sized,
                "edge_score": edge,
                "learning_adj": float((row.get("learning_adj") or 0)),
                "agent_learning": row.get("agent_learning") or {},
                "learning_reasons": row.get("learning_reasons") or [],
                "cap_bucket": cap_b,
                "target_pct": row_target,
                "realistic_move_pct": realistic_move,
                "expected_profit_inr": expected_profit,
                "edge_reasons": edge_reasons,
                "fit_reason": fit,
            })
        else:
            row_target = dynamic_target_pct(row, ap_cfg)
            exp_ret = float(scored.get("expected_return_pct") or row_target)
            expected_profit = round(sized["notional_inr"] * (exp_ret / 100.0), 2)
            candidates.append({
                **scored,
                **sized,
                "target_pct": row_target,
                "expected_profit_inr": expected_profit,
                "fit_reason": f"₹{sized['notional_inr']:,.0f} · target {row_target:.1f}%",
            })

    candidates.sort(
        key=lambda x: (
            x.get("edge_score") or 0,
            float((x.get("agent_learning") or {}).get("rag_adj") or 0),
            x.get("learning_adj") or float((x.get("screen_row") or {}).get("learning_adj") or 0),
            x.get("expected_profit_inr") or 0,
            x.get("pick_score") or 0,
        ),
        reverse=True,
    )

    if agent_smart and sel_cfg:
        picks = select_diversified_picks(candidates, max_picks=max_trades, cfg=sel_cfg)
        from trading.agent_capital_goals import agent_capital_goals, optimize_picks_for_profit_target

        goals = agent_capital_goals(cfg)
        min_target = float(goals.get("min_daily_profit_target_inr") or 0)
        if min_target > 0:
            picks = optimize_picks_for_profit_target(
                picks,
                candidates,
                min_target_inr=min_target,
                max_picks=max_trades,
            )
        budget_left = remaining
        final_picks: list[dict[str, Any]] = []
        for cand in picks:
            notional = float(cand.get("notional_inr") or 0)
            if notional > budget_left:
                price = float(cand.get("price") or 0)
                resized = _size_for_budget(
                    price,
                    limits=limits,
                    remaining_budget=budget_left,
                    max_shares_cap=max_shares_cap,
                )
                if not resized:
                    continue
                move = float(cand.get("realistic_move_pct") or target_pct)
                cand = {
                    **cand,
                    **resized,
                    "expected_profit_inr": round(resized["notional_inr"] * (move / 100.0), 2),
                }
                notional = resized["notional_inr"]
            final_picks.append(cand)
            budget_left = round(budget_left - notional, 2)
        return final_picks, candidates[:25]

    picks: list[dict[str, Any]] = []
    budget_left = remaining
    for cand in candidates:
        if len(picks) >= max_trades:
            break
        notional = float(cand.get("notional_inr") or 0)
        if notional > budget_left:
            price = float(cand.get("price") or 0)
            resized = _size_for_budget(
                price,
                limits=limits,
                remaining_budget=budget_left,
                max_shares_cap=max_shares_cap,
            )
            if not resized:
                continue
            cand = {**cand, **resized}
            cand["expected_profit_inr"] = round(
                resized["notional_inr"] * (float(cand.get("expected_return_pct") or target_pct) / 100.0),
                2,
            )
            notional = resized["notional_inr"]
        picks.append(cand)
        budget_left = round(budget_left - notional, 2)

    return picks, candidates[:25]


def _refresh_prices(picks: list[dict[str, Any]], provider: str = "auto") -> list[dict[str, Any]]:
    """Refresh LTP for final picks before execution."""
    out = []
    for pick in picks:
        sym = pick["symbol"]
        try:
            from trading.scheduler import _quote_symbol
            px = float(_quote_symbol(sym, provider))
            if px > 0:
                limits = _budget_limits(session)
                sized = _size_for_budget(
                    px,
                    limits=limits,
                    remaining_budget=limits["remaining_budget_inr"],
                    max_shares_cap=pick.get("max_shares_cap"),
                )
                if sized:
                    exp_ret = float(pick.get("expected_return_pct") or 1.5)
                    pick = {
                        **pick,
                        "price": px,
                        "quantity": sized["quantity"],
                        "notional_inr": sized["notional_inr"],
                        "expected_profit_inr": round(sized["notional_inr"] * (exp_ret / 100.0), 2),
                        "price_refreshed": True,
                    }
        except Exception:
            pick = {**pick, "price_refreshed": False}
        out.append(pick)
    return out


def _record_buy_decision(
    *,
    pick: dict[str, Any],
    trade: dict[str, Any],
    gate: dict[str, Any],
    limits: dict[str, Any],
    min_composite: float,
    target_pct: float,
    session_id: str | None,
    cycle_id: str = "",
    skipped: bool = False,
    skip_reason: str = "",
    psych_gate: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    from trading.decision_rationale import build_buy_rationale, log_trade_decision

    rationale = build_buy_rationale(
        pick=pick,
        gate=gate,
        limits=limits,
        trade=trade,
        min_composite=min_composite,
        target_pct=target_pct,
        skipped=skipped,
        skip_reason=skip_reason,
        psych_gate=psych_gate,
    )
    if session_id:
        log_trade_decision(
            session_id=session_id,
            side="buy",
            symbol=str(pick.get("symbol") or ""),
            rationale=rationale,
            cycle_id=cycle_id,
        )
    return rationale


def _psychology_buy_gate(pick: dict[str, Any]) -> dict[str, Any]:
    from trading.psychology_gates import evaluate_buy_psychology, resolve_psychology_for_pick

    psych = resolve_psychology_for_pick(pick, fetch_social=True)
    return evaluate_buy_psychology(psych, pick=pick)


def _execute_pick_with_gates(
    *,
    pick: dict[str, Any],
    cfg: dict[str, Any],
    limits: dict[str, Any],
    min_score: float,
    target_pct: float,
    session_id: str | None,
    pick_mode: str,
    ms_date: str | None,
) -> dict[str, Any]:
    """Run timing + psychology gates, execute buy, log rationale."""
    from trading.latency_compensation import compensated_entry_allowed
    from trading.order_router import agent_trade_from_signal
    from trading.pick_learning import log_agent_pick

    sym = pick["symbol"]
    if pick_mode in {"auto_pick", "session_agent_auto"}:
        from trading.agent_learning import attach_rag_to_pick

        pick = attach_rag_to_pick(pick)

    from trading.entry_gates import evaluate_entry_gates
    from trading.intraday_rules import late_buy_blocked

    blocked, late_reason = late_buy_blocked(cfg.get("autopilot") or {})
    if blocked:
        rationale = _record_buy_decision(
            pick=pick,
            trade={"skipped": True, "reason": late_reason},
            gate={"reason": late_reason},
            limits=limits,
            min_composite=min_score,
            target_pct=target_pct,
            session_id=session_id,
            skipped=True,
            skip_reason=late_reason,
        )
        return {
            "symbol": sym,
            "skipped": True,
            "reason": late_reason,
            "decision_rationale": rationale,
        }

    if pick_mode in {"auto_pick", "session_agent_auto"}:
        cross = limits.get("cross_desk_symbols") or set()
        sym_base = sym.upper().replace(".NSE", "")
        if sym in cross or sym_base in {str(s).upper().replace(".NSE", "") for s in cross}:
            rationale = _record_buy_decision(
                pick=pick,
                trade={"skipped": True, "reason": "cross_desk_duplicate"},
                gate={"reason": "cross_desk_duplicate"},
                limits=limits,
                min_composite=min_score,
                target_pct=target_pct,
                session_id=session_id,
                skipped=True,
                skip_reason="cross_desk_duplicate",
            )
            return {
                "symbol": sym,
                "skipped": True,
                "reason": "cross_desk_duplicate",
                "decision_rationale": rationale,
            }

    if pick_mode in {"auto_pick", "session_agent_auto"}:
        from trading.agent_selection import agent_candidate_gate, agent_selection_cfg

        row = pick.get("screen_row") or pick
        allowed, gate_reason = agent_candidate_gate(row, cfg=agent_selection_cfg())
        if not allowed:
            rationale = _record_buy_decision(
                pick=pick,
                trade={"skipped": True, "reason": gate_reason},
                gate={"reason": gate_reason},
                limits=limits,
                min_composite=min_score,
                target_pct=target_pct,
                session_id=session_id,
                skipped=True,
                skip_reason=gate_reason,
            )
            return {
                "symbol": sym,
                "skipped": True,
                "reason": gate_reason,
                "decision_rationale": rationale,
            }

    entry_gate = evaluate_entry_gates(sym, session_id=session_id, pick_mode=pick_mode)
    if not entry_gate.get("allowed"):
        rationale = _record_buy_decision(
            pick=pick,
            trade={"skipped": True, "reason": entry_gate.get("reason")},
            gate={"reason": entry_gate.get("reason"), "entry_gate": entry_gate},
            limits=limits,
            min_composite=min_score,
            target_pct=target_pct,
            session_id=session_id,
            skipped=True,
            skip_reason=str(entry_gate.get("reason") or "entry_gate_blocked"),
        )
        return {
            "symbol": sym,
            "skipped": True,
            "reason": entry_gate.get("reason"),
            "entry_gate": entry_gate,
            "decision_rationale": rationale,
        }

    gate = compensated_entry_allowed(symbol=sym, session_id=session_id)
    if not gate.get("allowed"):
        rationale = _record_buy_decision(
            pick=pick,
            trade={"skipped": True, "reason": gate.get("reason")},
            gate=gate,
            limits=limits,
            min_composite=min_score,
            target_pct=target_pct,
            session_id=session_id,
            skipped=True,
            skip_reason=str(gate.get("reason") or "timing_blocked"),
        )
        return {
            "symbol": sym,
            "skipped": True,
            "reason": gate.get("reason"),
            "timing": gate,
            "decision_rationale": rationale,
        }

    psych_gate = _psychology_buy_gate(pick)
    if not psych_gate.get("allowed"):
        rationale = _record_buy_decision(
            pick=pick,
            trade={"skipped": True, "reason": psych_gate.get("reason")},
            gate=gate,
            limits=limits,
            min_composite=min_score,
            target_pct=target_pct,
            session_id=session_id,
            skipped=True,
            skip_reason=str(psych_gate.get("reason") or "psychology_blocked"),
            psych_gate=psych_gate,
        )
        return {
            "symbol": sym,
            "skipped": True,
            "reason": psych_gate.get("reason"),
            "timing": gate,
            "psychology_gate": psych_gate,
            "decision_rationale": rationale,
        }

    trade = agent_trade_from_signal(
        symbol=sym,
        side="buy",
        quantity=int(pick.get("quantity") or 1),
        stance=pick.get("stance") or "favorable",
        composite_score=float(pick.get("composite_score") or 0),
        product=str(cfg.get("default_product") or "mis"),
        source="genai_agent",
        session_id=session_id,
        position_meta={
            "target_pct": float(pick.get("target_pct") or target_pct),
            "cap_bucket": pick.get("cap_bucket"),
            "edge_score": pick.get("edge_score"),
        },
    )
    row = {
        "symbol": sym,
        "quantity": pick.get("quantity"),
        "notional_inr": pick.get("notional_inr"),
        "expected_profit_inr": pick.get("expected_profit_inr"),
        "pick_score": pick.get("pick_score"),
        **trade,
    }
    if not trade.get("skipped"):
        rationale = _record_buy_decision(
            pick={**pick, "psychology_gate": psych_gate},
            trade=trade,
            gate=gate,
            limits=limits,
            min_composite=min_score,
            target_pct=target_pct,
            session_id=session_id,
            psych_gate=psych_gate,
        )
        log_agent_pick(
            pick={**pick, "psychology_gate": psych_gate},
            trade=trade,
            mode=pick_mode,
            morning_scan_date=ms_date,
            session_id=session_id,
            decision_rationale=rationale,
        )
        try:
            from quant_layer.pipeline import load_quant_digest_lookup
            from quant_layer.trade_journal import log_signal

            lookup = load_quant_digest_lookup()
            llm = lookup.get(sym) or lookup.get(sym.replace(".NSE", "")) or {}
            screen = pick.get("screen_row") or {}
            triggers = pick.get("quant_triggers") or screen.get("quant_triggers") or []
            log_signal(
                symbol=sym,
                conviction_score=float(llm.get("conviction_score") or pick.get("edge_score") or 0),
                validation_score=float(llm.get("validation_score") or 0),
                triggers=list(triggers)[:12] if isinstance(triggers, list) else [],
                rationale=str(llm.get("rationale") or pick.get("reasons") or "")[:500],
                session_id=session_id,
                source=f"agent_buy_{pick_mode}",
            )
        except Exception:
            pass
        row["decision_rationale"] = rationale
    elif session_id:
        _record_buy_decision(
            pick=pick,
            trade=trade,
            gate=gate,
            limits=limits,
            min_composite=min_score,
            target_pct=target_pct,
            session_id=session_id,
            skipped=True,
            skip_reason=str(trade.get("reason") or "risk_blocked"),
            psych_gate=psych_gate,
        )
    return row


def _position_age_minutes(pos: dict[str, Any]) -> float:
    """Minutes since position opened (IST-aware)."""
    opened = pos.get("opened_at")
    if not opened:
        return 0.0
    try:
        from datetime import datetime, timezone

        ts = str(opened).replace("Z", "+00:00")
        opened_dt = datetime.fromisoformat(ts)
        if opened_dt.tzinfo is None:
            opened_dt = opened_dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - opened_dt).total_seconds() / 60.0)
    except Exception:
        return 0.0


def _top_up_open_positions(
    *,
    limits: dict[str, Any],
    target_pct: float,
    execute: bool,
    market_provider: str = "auto",
    session_id: Optional[str] = None,
    pick_mode: str = "given_stocks",
) -> list[dict[str, Any]]:
    """Scale existing MIS positions up toward max_position_inr when budget allows."""
    if limits.get("halted") or float(limits.get("remaining_budget_inr") or 0) <= 0:
        return []

    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    top_up_fraction = float(ap.get("top_up_max_fraction") or 0.25)
    top_up_daily_pct = float(ap.get("top_up_max_daily_pct") or 0.85)
    max_daily = float(limits.get("max_daily_notional_inr") or cfg.get("risk", {}).get("max_daily_notional_inr") or 0)
    used_daily = float(limits.get("buy_notional_used_inr") or 0)
    if max_daily > 0 and used_daily / max_daily >= top_up_daily_pct:
        return []

    from trading.latency_compensation import compensated_entry_allowed
    from trading.order_router import agent_trade_from_signal
    from trading.pick_learning import log_agent_pick
    from trading.scheduler import _quote_symbol

    max_per = float(limits["max_per_order_inr"])
    remaining = float(limits["remaining_budget_inr"])
    max_top_up_notional = max_per * top_up_fraction
    trades: list[dict[str, Any]] = []
    ms_date = (load_morning_scan() or {}).get("trade_date_ist")

    for pos in open_positions("mis", session_id=session_id) if session_id else open_positions("mis"):
        sym = str(pos.get("symbol") or "").upper()
        held = limits.get("held_symbols") or set()
        if held and sym not in {str(s).upper() for s in held}:
            continue
        held_qty = int(pos.get("quantity") or 0)
        avg = float(pos.get("avg_price") or 0)
        if not sym or held_qty <= 0 or avg <= 0:
            continue
        try:
            px = float(_quote_symbol(sym, market_provider))
        except Exception:
            px = avg
        if px <= 0:
            continue

        ret_pct = ((px / avg) - 1) * 100
        cycle_top_up_fraction = top_up_fraction
        if ret_pct >= float(ap.get("momentum_pyramid_min_pct") or 1.0):
            cycle_top_up_fraction = float(ap.get("momentum_pyramid_fraction") or 0.5)
        elif ap.get("top_up_guard_enabled", True):
            min_profit = float(ap.get("top_up_min_profit_pct") or 0.5)
            min_mins = int(ap.get("top_up_min_minutes") or 10)
            held_mins = _position_age_minutes(pos)
            if held_mins >= min_mins and ret_pct < min_profit:
                trades.append({
                    "symbol": sym,
                    "skipped": True,
                    "reason": "top_up_guard_no_momentum",
                    "top_up": True,
                    "held_minutes": round(held_mins, 1),
                    "return_pct": round(ret_pct, 2),
                    "fit_reason": (
                        f"Top-up blocked — held {held_mins:.0f}m at {ret_pct:+.2f}% "
                        f"(need +{min_profit}% after {min_mins}m)"
                    ),
                })
                continue

        room = max_per - (avg * held_qty)
        if room < px:
            continue
        # Gradual top-up: max 25% of per-position cap per cycle (not full room in one shot).
        max_add = min(
            int(room // px),
            int(remaining // px),
            int((max_per * cycle_top_up_fraction) // px),
        )
        if max_add < 1:
            continue
        notional = round(px * max_add, 2)
        exp_ret = target_pct
        pick = {
            "symbol": sym,
            "quantity": max_add,
            "notional_inr": notional,
            "price": px,
            "expected_return_pct": exp_ret,
            "expected_profit_inr": round(notional * (exp_ret / 100.0), 2),
            "fit_reason": f"Top-up {max_add} sh (gradual, max {top_up_fraction:.0%} of ₹{max_per:,.0f} cap per cycle)",
            "top_up": True,
            "held_quantity": held_qty,
        }
        if not execute:
            trades.append({**pick, "skipped": True, "reason": "dry_run"})
            continue
        from trading.entry_gates import evaluate_entry_gates

        entry_gate = evaluate_entry_gates(sym, session_id=session_id, pick_mode=pick_mode)
        if not entry_gate.get("allowed"):
            rationale = _record_buy_decision(
                pick=pick,
                trade={"skipped": True, "reason": entry_gate.get("reason")},
                gate={"reason": entry_gate.get("reason"), "entry_gate": entry_gate},
                limits=limits,
                min_composite=0,
                target_pct=target_pct,
                session_id=session_id,
                skipped=True,
                skip_reason=str(entry_gate.get("reason") or "entry_gate_blocked"),
            )
            trades.append({**pick, "skipped": True, "reason": entry_gate.get("reason"), "entry_gate": entry_gate, "decision_rationale": rationale})
            continue
        gate = compensated_entry_allowed(symbol=sym, session_id=session_id)
        if not gate.get("allowed"):
            rationale = _record_buy_decision(
                pick=pick,
                trade={"skipped": True, "reason": gate.get("reason")},
                gate=gate,
                limits=limits,
                min_composite=0,
                target_pct=target_pct,
                session_id=session_id,
                skipped=True,
                skip_reason=str(gate.get("reason") or "timing_blocked"),
            )
            trades.append({**pick, "skipped": True, "reason": gate.get("reason"), "timing": gate, "decision_rationale": rationale})
            continue
        psych_gate = _psychology_buy_gate(pick)
        if not psych_gate.get("allowed"):
            rationale = _record_buy_decision(
                pick=pick,
                trade={"skipped": True, "reason": psych_gate.get("reason")},
                gate=gate,
                limits=limits,
                min_composite=0,
                target_pct=target_pct,
                session_id=session_id,
                skipped=True,
                skip_reason=str(psych_gate.get("reason") or "psychology_blocked"),
                psych_gate=psych_gate,
            )
            trades.append({
                **pick,
                "skipped": True,
                "reason": psych_gate.get("reason"),
                "timing": gate,
                "psychology_gate": psych_gate,
                "decision_rationale": rationale,
            })
            continue
        trade = agent_trade_from_signal(
            symbol=sym,
            side="buy",
            quantity=max_add,
            stance="favorable",
            composite_score=0,
            product=str(cfg.get("default_product") or "mis"),
            source="session_top_up",
            session_id=session_id,
        )
        row = {**pick, **trade}
        trades.append(row)
        if not trade.get("skipped"):
            rationale = _record_buy_decision(
                pick={**pick, "psychology_gate": psych_gate},
                trade=trade,
                gate=gate,
                limits=limits,
                min_composite=0,
                target_pct=target_pct,
                session_id=session_id,
                psych_gate=psych_gate,
            )
            log_agent_pick(
                pick={**pick, "psychology_gate": psych_gate},
                trade=trade,
                mode=pick_mode,
                morning_scan_date=ms_date,
                session_id=session_id,
                decision_rationale=rationale,
            )
            remaining = round(remaining - notional, 2)
            if remaining <= 0:
                break
    return trades


def run_given_stock_trades(
    *,
    execute: bool = False,
    quantity: int = 0,
    max_picks: int = 1,
    seed_symbol: str = "",
    market_provider: str = "auto",
    symbols: Optional[list[str]] = None,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Trade only from user watchlist + desk symbol (no Nifty 500 auto-pick).
    Uses morning-scan RAG data when available for scoring.
    """
    cfg = load_trading_config()
    risk = cfg.get("risk") or {}
    ap = cfg.get("autopilot") or {}
    min_score = float(risk.get("agent_min_composite") or ap.get("entry_min_composite") or 55)
    target_pct = float(ap.get("target_pct") or risk.get("default_target_pct") or 1.5)
    max_shares_cap = quantity if quantity and quantity > 0 else None

    universe = [s.upper().strip() for s in (symbols or _given_stock_universe(seed_symbol)) if s]
    universe = list(dict.fromkeys(universe))[:CURATED_SYMBOLS_MAX]
    if not universe:
        return {
            "mode": "given_stocks",
            "error": "Set symbols on Autopilot watchlist or analyze a desk symbol first.",
            "picks": [],
            "trades": [],
        }

    limits = _budget_limits(session)
    rows = rows_from_morning_scan(universe)
    missing = [s for s in universe if not any(str(r.get("symbol", "")).upper() == s for r in rows)]
    for sym in missing[:CURATED_SYMBOLS_MAX]:
        try:
            from trading.scheduler import _analyze_symbol
            a = _analyze_symbol(sym, market_provider)
            rows.append({
                "symbol": sym,
                "price": a.get("price"),
                "composite_score": a.get("composite_score"),
                "stance": a.get("composite_stance"),
            })
        except Exception:
            pass

    picks, candidates = allocate_budget_picks(
        rows,
        limits=limits,
        max_picks=_resolve_max_picks(max_picks),
        min_composite=min_score,
        target_pct=target_pct,
        max_shares_cap=max_shares_cap,
        desk_symbol=seed_symbol,
    )

    if execute and picks:
        picks = _refresh_prices(picks, market_provider)

    trades: list[dict[str, Any]] = []
    ms_date = (load_morning_scan() or {}).get("trade_date_ist")
    timing_blocked: list[dict[str, Any]] = []
    if execute:
        session_id = str(session.get("id") or "") if session else None
        if not session_id and ap.get("session_active"):
            session_id = ap.get("session_id")
        if not session_id:
            try:
                from trading.session_autopilot import get_active_session_id

                session_id = get_active_session_id()
            except Exception:
                pass
        pick_mode = "session_curated_list" if session_id else "given_stocks"

        trades.extend(
            _top_up_open_positions(
                limits=_budget_limits(session),
                target_pct=target_pct,
                execute=True,
                market_provider=market_provider,
                session_id=session_id,
                pick_mode=pick_mode,
            )
        )

        for pick in picks:
            row = _execute_pick_with_gates(
                pick=pick,
                cfg=cfg,
                limits=limits,
                min_score=min_score,
                target_pct=target_pct,
                session_id=session_id,
                pick_mode=pick_mode,
                ms_date=ms_date,
            )
            trades.append(row)
            if row.get("skipped") and (row.get("timing") or row.get("psychology_gate")):
                timing_blocked.append(row)

    from trading.session_history import build_universe_audit

    universe_audit = build_universe_audit(
        universe=universe,
        rows=rows,
        picks=picks,
        candidates=candidates,
        limits=limits,
        min_composite=min_score,
        target_pct=target_pct,
    )

    ms = load_morning_scan()
    return {
        "mode": "given_stocks",
        "universe": universe,
        "universe_meta": {
            "source": "watchlist",
            "morning_scan_date": ms.get("trade_date_ist") if ms else None,
        },
        "budget": limits,
        "scanned_count": len(rows),
        "affordable_candidates": len(candidates),
        "candidates": candidates[:25],
        "picks": picks,
        "trades": trades,
        "executed": execute,
        "min_composite": min_score,
        "target_pct": target_pct,
        "allocation_strategy": "max_expected_profit_within_budget",
        "timing_blocked": timing_blocked,
        "universe_audit": universe_audit,
        "disclaimer": "Trades limited to your watchlist/desk symbol. Not investment advice.",
    }


def run_autonomous_stock_picks(
    *,
    execute: bool = False,
    quantity: int = 0,
    max_picks: int = 1,
    seed_symbol: str = "",
    market_provider: str = "auto",
    extra_symbols: Optional[list[str]] = None,
    session: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """
    Scan Nifty 500 (screener cache), size orders to per-order + daily budget caps,
    rank by expected profit, optionally execute MIS buys.
    """
    cfg = load_trading_config()
    risk = cfg.get("risk") or {}
    ap = cfg.get("autopilot") or {}
    min_score = float(risk.get("agent_min_composite") or ap.get("entry_min_composite") or 55)
    target_pct = float(ap.get("target_pct") or risk.get("default_target_pct") or 1.5)
    max_shares_cap = quantity if quantity and quantity > 0 else None

    limits = _budget_limits(session)
    rows, universe_meta = _load_nifty500_rows()

    from trading.agent_learning import enrich_agent_candidate_rows

    rows = enrich_agent_candidate_rows(rows)

    if seed_symbol:
        seed = seed_symbol.upper()
        if not any(str(r.get("symbol", "")).upper() == seed for r in rows):
            rows.insert(0, {"symbol": seed, "price": None, "composite_score": 0, "stance": "neutral"})

    picks, candidates = allocate_budget_picks(
        rows,
        limits=limits,
        max_picks=_resolve_max_picks(max_picks),
        min_composite=min_score,
        target_pct=target_pct,
        max_shares_cap=max_shares_cap,
        desk_symbol=seed_symbol,
        agent_smart=True,
    )

    if execute and picks:
        picks = _refresh_prices(picks, market_provider)

    trades: list[dict[str, Any]] = []
    ms_date = (load_morning_scan() or {}).get("trade_date_ist")
    timing_blocked: list[dict[str, Any]] = []
    if execute:
        session_id = str(session.get("id") or "") if session else None
        if not session_id and ap.get("session_active"):
            session_id = ap.get("session_id")
        pick_mode = "session_agent_auto" if session_id else "auto_pick"

        trades.extend(
            _top_up_open_positions(
                limits=_budget_limits(session),
                target_pct=target_pct,
                execute=True,
                market_provider=market_provider,
                session_id=session_id,
                pick_mode=pick_mode,
            )
        )

        for pick in picks:
            row = _execute_pick_with_gates(
                pick=pick,
                cfg=cfg,
                limits=limits,
                min_score=min_score,
                target_pct=target_pct,
                session_id=session_id,
                pick_mode=pick_mode,
                ms_date=ms_date,
            )
            trades.append(row)
            if row.get("skipped") and (row.get("timing") or row.get("psychology_gate")):
                timing_blocked.append(row)

    from trading.session_history import build_universe_audit

    audit_symbols = list(dict.fromkeys(
        [str(p.get("symbol") or "").upper() for p in picks]
        + [str(c.get("symbol") or "").upper() for c in candidates]
        + [str(r.get("symbol") or "").upper() for r in rows[:40]]
    ))
    audit_symbols = [s for s in audit_symbols if s]
    universe_audit = build_universe_audit(
        universe=audit_symbols,
        rows=rows,
        picks=picks,
        candidates=candidates,
        limits=limits,
        min_composite=min_score,
        target_pct=target_pct,
    )

    return {
        "universe": "NIFTY_500",
        "mode": "auto_pick",
        "universe_meta": universe_meta,
        "budget": limits,
        "scanned_count": len(rows),
        "affordable_candidates": len(candidates),
        "candidates": candidates[:25],
        "picks": picks,
        "trades": trades,
        "executed": execute,
        "min_composite": min_score,
        "target_pct": target_pct,
        "allocation_strategy": "agent_smart_edge_diversified",
        "timing_blocked": timing_blocked,
        "universe_audit": universe_audit,
        "disclaimer": (
            "Nifty 500 agent picks ranked by intraday edge + RAG learning curve + timing profiles "
            "(same learning stack as curated desk). Not investment advice."
        ),
    }


def resolve_universe(*, seed_symbol: str = "", extra: Optional[list[str]] = None) -> list[str]:
    """Full Nifty 500 symbol list."""
    syms = universe_symbols()
    out = list(dict.fromkeys([*(extra or []), seed_symbol.upper(), *syms]))
    return [s for s in out if s]
