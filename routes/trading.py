"""Trading desk API — paper/live mode, autopilot, scoreboard, calibration."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from routes.schemas import DualSessionStartBody, IntradaySimConfigure, IntradaySimTick, SessionEventsClearBody, SessionStartBody, SessionStopBody, TradingConfigPatch
from trading.autopilot import load_calibration, recalibrate_from_scoreboard, run_autopilot_cycle
from trading.config_store import load_trading_config, save_trading_config
from trading.intraday_sim import sim_configure, sim_status, sim_tick
from trading.paper_ledger import clear_trading_halt, ledger_summary, list_orders
from trading.risk import get_risk_snapshot
from trading.scheduler import _analyze_symbol, _quote_symbol
from trading.scoreboard import scoreboard_payload, sync_from_predictions
from trading.watchlist_agent import list_alerts

router = APIRouter(tags=["trading"])


@router.get("/api/trading/config")
def trading_config_get() -> dict[str, Any]:
    cfg = load_trading_config()
    quote_fn = lambda s: _quote_symbol(s)
    return {
        **cfg,
        "ledger": ledger_summary(),
        "risk_snapshot": get_risk_snapshot(quote_fn),
        "disclaimer": "Educational paper/live routing. Live orders require live_armed + broker credentials.",
    }


@router.get("/api/trading/profit-profile")
def trading_profit_profile_get() -> dict[str, Any]:
    from trading.profit_profiles import profit_profile_status

    return profit_profile_status()


@router.post("/api/trading/profit-profile")
def trading_profit_profile_set(body: dict[str, Any]) -> dict[str, Any]:
    from trading.profit_profiles import apply_profit_profile

    name = str(body.get("profile") or body.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="profile is required (conservative | home_run)")
    try:
        return apply_profit_profile(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/api/trading/config")
def trading_config_patch(body: TradingConfigPatch) -> dict[str, Any]:
    patch = body.model_dump(exclude_none=True)
    if patch.get("execution_mode") == "live" and patch.get("live_armed") is not False:
        patch.setdefault("live_armed", False)
    try:
        saved = save_trading_config(patch)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"config": saved, "ledger": ledger_summary()}


@router.post("/api/trading/config/arm-live")
def trading_arm_live(confirm: bool = False) -> dict[str, Any]:
    if not confirm:
        raise HTTPException(status_code=400, detail="Pass confirm=true to arm live trading.")
    from trading.pre_live_gates import check_pre_live_gates

    gates = check_pre_live_gates(run_reconcile=True)
    if not gates.get("ok") and not gates.get("skipped"):
        raise HTTPException(
            status_code=409,
            detail={"message": "Pre-live gates failed", "blockers": gates.get("blockers"), "warnings": gates.get("warnings")},
        )
    saved = save_trading_config({"execution_mode": "live", "live_armed": True})
    return {
        "config": saved,
        "message": "Live trading ARMED — orders will route to broker when placed.",
        "pre_live_gates": gates,
    }


@router.get("/api/trading/pre-live-gates")
def trading_pre_live_gates(reconcile: bool = False) -> dict[str, Any]:
    from trading.pre_live_gates import check_pre_live_gates

    return check_pre_live_gates(run_reconcile=reconcile)


@router.post("/api/trading/learning/reset")
def trading_learning_reset(
    confirm: bool = False,
    keep_morning_scan_rows: bool = True,
    wipe_session_reports: bool = True,
) -> dict[str, Any]:
    """Wipe trading RAG + pick_log + blocks. Preserves book RAG and price data."""
    from trading.learning_reset import run_learning_reset

    return run_learning_reset(
        confirm=confirm,
        keep_morning_scan_rows=keep_morning_scan_rows,
        wipe_session_reports=wipe_session_reports,
    )


@router.post("/api/trading/pre-live-hygiene")
def trading_pre_live_hygiene(
    stop_stale: bool = True,
    square_orphans: bool = True,
    sync_calibration: bool = True,
    run_quant_scan: bool = False,
) -> dict[str, Any]:
    """Stop stale sessions, square orphans, sync calibration — safe before live."""
    from trading.pre_live_hygiene import run_pre_live_hygiene

    return run_pre_live_hygiene(
        stop_stale=stop_stale,
        square_orphans=square_orphans,
        sync_calibration=sync_calibration,
        run_quant_scan=run_quant_scan,
    )


@router.post("/api/trading/config/disarm")
def trading_disarm() -> dict[str, Any]:
    saved = save_trading_config({"live_armed": False, "execution_mode": "paper"})
    return {"config": saved, "message": "Disarmed — paper mode."}


@router.post("/api/trading/risk/clear-halt")
def trading_clear_halt() -> dict[str, Any]:
    clear_trading_halt()
    return {"cleared": True, "ledger": ledger_summary(), "risk_snapshot": get_risk_snapshot(lambda s: _quote_symbol(s))}


@router.get("/api/trading/risk")
def trading_risk_get() -> dict[str, Any]:
    return get_risk_snapshot(lambda s: _quote_symbol(s))


@router.get("/api/trading/scoreboard")
def trading_scoreboard(limit: int = 50) -> dict[str, Any]:
    return scoreboard_payload(limit=limit)


@router.post("/api/trading/scoreboard/sync")
def trading_scoreboard_sync() -> dict[str, Any]:
    return sync_from_predictions()


@router.get("/api/trading/paper/ledger")
def trading_paper_ledger() -> dict[str, Any]:
    return {"orders": list_orders(100), **ledger_summary()}


@router.get("/api/trading/alerts")
def trading_alerts(limit: int = 50) -> dict[str, Any]:
    return list_alerts(limit=limit)


@router.get("/api/trading/intraday/status")
def trading_intraday_status() -> dict[str, Any]:
    return sim_status()


@router.post("/api/trading/intraday/configure")
def trading_intraday_configure(body: IntradaySimConfigure) -> dict[str, Any]:
    return sim_configure(body.symbol, body.rules)


@router.post("/api/trading/intraday/tick")
def trading_intraday_tick(body: IntradaySimTick) -> dict[str, Any]:
    analysis = _analyze_symbol(body.symbol, body.provider)
    price = body.price or _quote_symbol(body.symbol, body.provider)
    if not price:
        raise HTTPException(status_code=400, detail="Could not resolve price.")
    return sim_tick(
        price=float(price),
        composite_score=float(analysis.get("composite_score") or 50),
        stance=str(analysis.get("composite_stance") or "neutral"),
        force_eod=body.force_eod,
    )


@router.post("/api/trading/autopilot/run")
def trading_autopilot_run() -> dict[str, Any]:
    return run_autopilot_cycle(
        analyze_fn=lambda s: _analyze_symbol(s),
        quote_fn=lambda s: _quote_symbol(s),
    )


@router.post("/api/trading/agent/picks")
def trading_agent_picks(
    execute: bool = False,
    max_picks: int = 3,
    quantity: int = 1,
    seed_symbol: str = "",
    autonomous: bool = True,
    symbols: str = "",
) -> dict[str, Any]:
    from trading.agent_picker import run_autonomous_stock_picks, run_given_stock_trades
    sym_list = [s.strip().upper() for s in symbols.split(",") if s.strip()] if symbols else None
    if autonomous:
        return run_autonomous_stock_picks(
            execute=execute,
            quantity=quantity,
            max_picks=max_picks,
            seed_symbol=seed_symbol,
        )
    return run_given_stock_trades(
        execute=execute,
        quantity=quantity,
        max_picks=max_picks,
        seed_symbol=seed_symbol,
        symbols=sym_list,
    )


@router.post("/api/trading/session/start")
def trading_session_start(body: SessionStartBody) -> dict[str, Any]:
    from trading.session_autopilot import start_session

    result = start_session(
        pick_mode=body.pick_mode,
        symbols=body.symbols,
        max_spend_inr=body.max_spend_inr,
        max_profit_inr=body.max_profit_inr,
        max_loss_inr=body.max_loss_inr,
        max_concurrent_picks=body.max_concurrent_picks,
        auto_square_orphans=body.auto_square_orphans,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Could not start session.")
    return result


@router.post("/api/trading/session/start-dual")
def trading_session_start_dual(body: DualSessionStartBody) -> dict[str, Any]:
    from trading.session_autopilot import start_dual_session

    result = start_dual_session(
        agent_max_spend_inr=body.agent_max_spend_inr,
        agent_max_profit_inr=body.agent_max_profit_inr,
        agent_max_loss_inr=body.agent_max_loss_inr,
        agent_max_concurrent_picks=body.agent_max_concurrent_picks,
        curated_symbols=body.curated_symbols,
        curated_max_spend_inr=body.curated_max_spend_inr,
        curated_max_profit_inr=body.curated_max_profit_inr,
        curated_max_loss_inr=body.curated_max_loss_inr,
        curated_max_concurrent_picks=body.curated_max_concurrent_picks,
        auto_square_orphans=body.auto_square_orphans,
    )
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("error") or "Could not start dual desk.")
    return result


@router.post("/api/trading/session/stop")
def trading_session_stop(body: Optional[SessionStopBody] = None) -> dict[str, Any]:
    from trading.session_autopilot import stop_session

    session_id = body.session_id if body else None
    return stop_session(session_id=session_id)


@router.post("/api/trading/session/square-orphans")
def trading_session_square_orphans() -> dict[str, Any]:
    """Square all open MIS positions not tied to an active desk."""
    from trading.session_autopilot import _active_sessions, _load_store, square_orphan_positions

    store = _load_store()
    active_ids = {str(s.get("id") or "") for s in _active_sessions(store)}
    result = square_orphan_positions(active_session_ids=active_ids, reason="manual_orphan_square")
    return {"ok": True, **result}


@router.post("/api/trading/session/compact-store")
def trading_compact_session_store(body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Trim sessions.json + session_events.json (safe while API is running)."""
    from trading.session_maintenance import trim_session_stores

    opts = body or {}
    retention = str(opts.get("retention") or "7d")
    if retention not in {"1h", "12h", "1d", "3d", "7d"}:
        retention = "7d"
    return trim_session_stores(
        retention=retention,  # type: ignore[arg-type]
        max_events=int(opts.get("max_events") or 2000),
        max_sessions=int(opts.get("max_sessions") or 25),
        max_cycles_per_session=int(opts.get("max_cycles_per_session") or 40),
        slim_event_details=opts.get("slim_details", True) is not False,
    )


@router.get("/api/trading/session/status")
def trading_session_status() -> dict[str, Any]:
    from trading.session_autopilot import session_status

    return session_status()


@router.get("/api/trading/plan/preview")
def trading_plan_preview(symbols: str = "") -> dict[str, Any]:
    """Dry-run intraday entry/exit plans for curated symbols (no orders)."""
    from trading.trade_plan import build_plan_preview

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        cfg = load_trading_config()
        sym_list = list((cfg.get("autopilot") or {}).get("curated_symbols") or [])
    return build_plan_preview(sym_list)


@router.get("/api/trading/session/trades")
def trading_session_trades(session_id: str = "", limit: int = 100) -> dict[str, Any]:
    from trading.pick_learning import list_session_trades

    sid = session_id or None
    cfg = load_trading_config()
    if not sid:
        sid = (cfg.get("autopilot") or {}).get("session_id")
    return {"trades": list_session_trades(sid, limit=limit), "session_id": sid}


@router.get("/api/trading/session/events")
def trading_session_events(
    session_id: str = "",
    limit: int = 200,
    event_type: str = "",
    cycle_id: str = "",
) -> dict[str, Any]:
    from trading.session_history import list_session_events

    sid = session_id or None
    cfg = load_trading_config()
    if not sid:
        sid = (cfg.get("autopilot") or {}).get("session_id")
    events = list_session_events(sid, limit=limit, event_type=event_type, cycle_id=cycle_id) if sid else []
    return {"events": events, "session_id": sid}


@router.post("/api/trading/session/events/clear")
def trading_session_events_clear(body: SessionEventsClearBody) -> dict[str, Any]:
    """Delete autopilot log entries older than the retention window."""
    from trading.session_history import purge_session_events

    sid = body.session_id
    cfg = load_trading_config()
    if not sid:
        sid = (cfg.get("autopilot") or {}).get("session_id")
    return purge_session_events(session_id=sid, retention=body.retention)


@router.get("/api/trading/session/detail")
def trading_session_detail(session_id: str = "") -> dict[str, Any]:
    from trading.session_autopilot import _find_session, _hydrate_session, _load_store, _resolve_display_session
    from trading.session_history import list_session_events
    from trading.pick_learning import list_session_trades

    store = _load_store()
    sid = session_id.strip()
    if not sid:
        display = _resolve_display_session(store)
        sid = (display or {}).get("id") or ""
        cfg = load_trading_config()
        if not sid:
            sid = (cfg.get("autopilot") or {}).get("session_id") or ""
    session = _find_session(store, sid) if sid else None
    if not session:
        display = _resolve_display_session(store)
        if display:
            session = display
            sid = display.get("id")
    session = _hydrate_session(session) if session else None
    trades: list = []
    if session:
        from trading.session_report import _session_day_trades

        trades = _session_day_trades(session)
    return {
        "session": session,
        "session_id": sid,
        "events": list_session_events(sid, limit=500) if sid else [],
        "trades": trades,
    }


@router.get("/api/trading/session/reports")
def trading_session_reports(limit: int = 50) -> dict[str, Any]:
    """List past sessions with P&L highlights for the reports gallery."""
    from trading.session_report import list_session_report_cards

    cards = list_session_report_cards(limit=min(max(1, limit), 100))
    return {"sessions": cards, "count": len(cards)}


@router.get("/api/trading/session/report/pdf")
def trading_session_report_pdf(session_id: str = "") -> StreamingResponse:
    """Download session EOD report as PDF."""
    from trading.session_report import build_session_report_pdf

    sid = session_id.strip()
    if not sid:
        raise HTTPException(status_code=400, detail="session_id required")
    try:
        pdf_bytes = build_session_report_pdf(sid)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"PDF build failed: {exc}") from exc
    safe = sid.replace('"', "")
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe}_report.pdf"'},
    )


@router.get("/api/trading/session/report")
def trading_session_report(session_id: str = "") -> dict[str, Any]:
    """EOD summary report — P&L, win rate, post-mortem, RAG digest metadata."""
    from trading.session_autopilot import _find_session, _hydrate_session, _load_store, _resolve_display_session
    from trading.session_report import (
        build_and_save_session_report,
        load_latest_session_report,
        load_session_report,
        report_is_stale,
    )

    store = _load_store()
    sid = session_id.strip()
    if not sid:
        display = _resolve_display_session(store)
        sid = (display or {}).get("id") or ""
        cfg = load_trading_config()
        if not sid:
            sid = (cfg.get("autopilot") or {}).get("session_id") or ""
    session = _find_session(store, sid) if sid else None
    if not session:
        display = _resolve_display_session(store)
        session = display
        sid = (display or {}).get("id") or sid
    report = load_session_report(sid) if sid else load_latest_session_report()
    if session and report_is_stale(_hydrate_session(session), report):
        try:
            report = build_and_save_session_report(
                session,
                completion_reason=session.get("completion_reason") or session.get("status") or "auto_refresh",
            )
            session["eod_report_generated"] = True
            session["eod_report_at"] = report.get("generated_at")
            from trading.session_autopilot import _save_store

            _save_store(store)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Report build failed: {exc}") from exc
    if not report:
        raise HTTPException(status_code=404, detail="No session report yet. Stop session or wait for EOD.")
    return report


@router.post("/api/trading/session/report/generate")
def trading_session_report_generate(session_id: str = "") -> dict[str, Any]:
    """Manually (re)generate EOD report for a session."""
    from trading.session_autopilot import _find_session, _load_store
    from trading.session_report import build_and_save_session_report, load_session_report

    store = _load_store()
    sid = session_id.strip()
    if not sid:
        sid = store.get("active_session_id") or ""
        if not sid and (store.get("sessions") or []):
            sid = store["sessions"][0].get("id") or ""
    session = _find_session(store, sid) if sid else None
    if not session:
        raise HTTPException(status_code=404, detail="Session not found.")
    session["eod_report_generated"] = False
    report = build_and_save_session_report(session, completion_reason=session.get("completion_reason") or "manual")
    session["eod_report_generated"] = True
    session["eod_report_at"] = report.get("generated_at")
    from trading.session_autopilot import _save_store

    _save_store(store)
    return report


@router.get("/api/trading/session/recommendations")
def trading_session_recommendations(symbols: str = "") -> dict[str, Any]:
    """RAG + pick-log based recommendations for next autopilot session."""
    from trading.pick_learning import get_learning_recommendations

    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        cfg = load_trading_config()
        sym_list = list((cfg.get("autopilot") or {}).get("curated_symbols") or [])
    return get_learning_recommendations(sym_list)


@router.get("/api/trading/session/nse-hours")
def trading_session_nse_hours() -> dict[str, Any]:
    from trading.market_hours import nse_session_info
    return nse_session_info(load_trading_config())


@router.get("/api/trading/nse-calendar")
def trading_nse_calendar(refresh: bool = False) -> dict[str, Any]:
    """NSE holiday list, live market status, special sessions (Muhurat)."""
    from trading.nse_calendar import calendar_snapshot, fetch_holiday_master, load_special_sessions

    cfg = load_trading_config()
    if refresh:
        fetch_holiday_master(force=True)
    snap = calendar_snapshot(cfg)
    return {
        **snap,
        "special_sessions_file": load_special_sessions().get("sessions") or [],
        "disclaimer": "Equity hours from NSE holiday-master + marketStatus. Update nse_special_sessions.json when Muhurat circular publishes exact times.",
    }


@router.get("/api/trading/morning-scan/status")
def trading_morning_scan_status() -> dict[str, Any]:
    from trading.morning_scan import morning_scan_status
    return morning_scan_status()


@router.post("/api/trading/morning-scan/run")
def trading_morning_scan_run(force: bool = False) -> dict[str, Any]:
    from trading.morning_scan import run_morning_scan
    return run_morning_scan(force=force)


@router.get("/api/trading/daily-universe/status")
def trading_daily_universe_status() -> dict[str, Any]:
    from trading.daily_universe import daily_universe_status
    return daily_universe_status()


@router.post("/api/trading/daily-universe/run")
def trading_daily_universe_run(force: bool = False, use_llm: bool = False, conviction: bool = False) -> dict[str, Any]:
    from trading.daily_universe import run_daily_universe
    return run_daily_universe(force=force, use_llm=use_llm, run_conviction=conviction)


@router.get("/api/trading/timing/status")
def trading_timing_status() -> dict[str, Any]:
    from trading.timing_intelligence import timing_status
    return timing_status()


@router.get("/api/trading/timing/compensation")
def trading_timing_compensation(symbol: str = "") -> dict[str, Any]:
    from trading.latency_compensation import compensation_status
    return compensation_status(symbol=symbol)


@router.post("/api/trading/timing/learn")
def trading_timing_learn() -> dict[str, Any]:
    from trading.config_store import load_trading_config
    from trading.morning_scan import load_morning_scan
    from trading.timing_intelligence import learn_timing_batch

    cfg = load_trading_config()
    symbols: list[str] = [str(s).upper() for s in (cfg.get("watchlist") or []) if s]
    ms = load_morning_scan() or {}
    for row in (ms.get("top_bullish") or [])[:40]:
        sym = str(row.get("symbol") or "").upper()
        if sym:
            symbols.append(sym)
    if not symbols:
        from trading.agent_picker import universe_symbols
        symbols = universe_symbols()[:40]
    return learn_timing_batch(list(dict.fromkeys(symbols)))


@router.get("/api/trading/pick-log")
def trading_pick_log(limit: int = 30) -> dict[str, Any]:
    from trading.pick_learning import list_pick_log, list_session_trades

    cfg = load_trading_config()
    sid = (cfg.get("autopilot") or {}).get("session_id")
    return {
        "picks": list_pick_log(limit=limit),
        "session_trades": list_session_trades(sid, limit=limit) if sid else [],
    }


@router.get("/api/trading/trade-decisions")
def trading_trade_decisions(
    session_id: Optional[str] = None,
    limit: int = 100,
) -> dict[str, Any]:
    from trading.pick_learning import list_trade_decisions

    return {
        "session_id": session_id,
        "decisions": list_trade_decisions(session_id, limit=limit),
    }


@router.get("/api/trading/calibration")
def trading_calibration_get() -> dict[str, Any]:
    return load_calibration()


@router.post("/api/trading/calibration/recalibrate")
def trading_calibration_recalibrate() -> dict[str, Any]:
    return recalibrate_from_scoreboard()


@router.post("/api/trading/session/learn-feed")
def trading_session_learn_feed() -> dict[str, Any]:
    """Backfill pick RAG from closed trades, regenerate session digests, recalibrate, timing."""
    from trading.pick_learning import backfill_pick_rag_lessons
    from trading.session_autopilot import _load_store
    from trading.session_report import build_and_save_session_report
    from trading.timing_intelligence import learn_timing_batch

    cfg = load_trading_config()
    symbols = list((cfg.get("autopilot") or {}).get("curated_symbols") or [])

    pick_rag = backfill_pick_rag_lessons()
    session_reports: list[dict[str, Any]] = []
    for row in _load_store().get("sessions") or []:
        sid = str(row.get("id") or "")
        if not sid or row.get("status") not in {"stopped", "completed"}:
            continue
        try:
            row["eod_report_generated"] = False
            report = build_and_save_session_report(
                row,
                completion_reason=str(row.get("completion_reason") or "learn_feed"),
            )
            session_reports.append({
                "session_id": sid,
                "rag_session_id": (report.get("rag") or {}).get("session_rag_id"),
                "pnl": (report.get("summary") or {}).get("realized_pnl_inr"),
            })
        except Exception as exc:
            session_reports.append({"session_id": sid, "error": str(exc)[:200]})

    calibration = recalibrate_from_scoreboard()
    timing = learn_timing_batch(symbols, feed_rag=True) if symbols else {"skipped": True}

    return {
        "ok": True,
        "pick_rag": pick_rag,
        "session_reports": session_reports,
        "calibration": calibration,
        "timing_learn": timing,
    }


@router.get("/api/trading/health")
def trading_health_get(run_reconcile: bool = False) -> dict[str, Any]:
    from trading.health import trading_health

    return trading_health(run_reconcile=run_reconcile)


@router.post("/api/trading/reconcile")
def trading_reconcile_post() -> dict[str, Any]:
    from trading.reconcile import reconcile_broker_positions

    return reconcile_broker_positions()


@router.get("/api/trading/positions/live")
def trading_live_positions(product: str = "mis") -> dict[str, Any]:
    from brokers.service import get_positions

    cfg = load_trading_config()
    bid = str(cfg.get("default_broker") or "stub")
    return get_positions(bid, product=product)


@router.get("/api/trading/orders/events")
def trading_order_events(limit: int = 40) -> dict[str, Any]:
    from trading.order_book import list_pending, recent_events

    return {"pending": list_pending(), "events": recent_events(limit)}
