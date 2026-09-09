"""Background autopilot scheduler (asyncio)."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from utils.logging_config import get_logger

logger = get_logger(__name__)

_task: Optional[asyncio.Task] = None
_morning_ran_date: Optional[str] = None


def _analyze_symbol(symbol: str, provider: str = "auto") -> dict[str, Any]:
    from routes.helpers import fetch_prices, rows_from_payload
    from technicals import compute_technicals
    from analysis.trading_context import extended_trade_context

    payload = fetch_prices(symbol, provider, force_refresh=False)
    rows = rows_from_payload(payload)
    tech = compute_technicals(rows)
    ctx = extended_trade_context(symbol, rows, tech)
    ext = ctx.get("extended") or {}
    ratings = ext.get("ratings_blended") or {}
    return {
        "symbol": symbol.upper(),
        "price": tech.get("price"),
        "composite_score": ctx.get("composite_score"),
        "composite_stance": ratings.get("composite_stance") or ctx.get("regime"),
        "pattern_bias": ctx.get("pattern_bias"),
        "extended_allowed": ctx.get("extended_allowed"),
        "composite_grade": ratings.get("composite_grade"),
    }


def _quote_symbol(symbol: str, provider: str = "auto") -> float:
    from trading.config_store import load_trading_config
    from brokers.service import get_live_quotes

    cfg = load_trading_config()
    broker = str(cfg.get("default_broker") or "stub")
    sym = symbol.upper()
    q = get_live_quotes(broker, [sym])
    price = (q.get("quotes") or {}).get(sym, {}).get("price")
    if price:
        return float(price)
    return float(_analyze_symbol(sym, provider).get("price") or 0)


async def _loop() -> None:
    global _morning_ran_date
    from trading.config_store import load_trading_config
    from trading.autopilot import run_autopilot_cycle
    from trading.morning_scan import run_morning_scan, should_run_morning_scan, _today_ist

    while True:
        try:
            cfg = load_trading_config()
            ap = cfg.get("autopilot") or {}
            interval = max(60, int(ap.get("poll_seconds") or 120))
            from trading.timing_intelligence import recommended_poll_seconds

            interval = recommended_poll_seconds(interval)

            if ap.get("morning_scan_enabled", True) and should_run_morning_scan(cfg):
                today = _today_ist()
                if _morning_ran_date != today:
                    if ap.get("unified_daily_job_enabled", True):
                        try:
                            from trading.daily_universe import run_daily_universe

                            logger.info("Running unified daily universe job (Agent0 + quant + morning + optional conviction)…")
                            result = await asyncio.to_thread(
                                run_daily_universe,
                                force=False,
                                use_llm=bool(ap.get("quant_llm_synthesis_enabled")),
                                run_conviction=bool(ap.get("daily_universe_conviction_enabled", False)),
                            )
                            _morning_ran_date = today
                            logger.info(
                                "Daily universe done: %s",
                                (result.get("summary") or {}),
                            )
                        except Exception as exc:
                            logger.warning("Unified daily job failed: %s", exc)
                    else:
                        logger.info("Starting morning Nifty 500 scan + RAG feed…")
                        result = await asyncio.to_thread(run_morning_scan, force=False)
                        _morning_ran_date = today
                        logger.info("Morning scan done: scored=%s", result.get("scored"))

            # Session active: also run during pre-market (09:00+) for analysis before 09:15 open
            if ap.get("enabled"):
                try:
                    from brokers.ltp_stream import get_manager
                    from trading.order_lifecycle import poll_all_pending
                    from trading.reconcile import reconcile_broker_positions

                    get_manager().sync_now()
                    bid = str(cfg.get("default_broker") or "stub")
                    if bid != "stub":
                        poll_all_pending(bid)
                        if cfg.get("reconcile_enabled", True):
                            reconcile_broker_positions(broker_id=bid)
                except Exception:
                    pass
                result = await asyncio.to_thread(
                    run_autopilot_cycle,
                    analyze_fn=lambda s: _analyze_symbol(s),
                    quote_fn=lambda s: _quote_symbol(s),
                )
                if not result.get("skipped"):
                    logger.info("Autopilot cycle: %s", result.get("steps"))
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("Autopilot scheduler error: %s", exc, exc_info=exc)
            await asyncio.sleep(120)


def start_scheduler() -> None:
    global _task
    if _task and not _task.done():
        return
    try:
        loop = asyncio.get_event_loop()
        _task = loop.create_task(_loop())
        logger.info("Trading autopilot scheduler started")
    except RuntimeError:
        logger.debug("No event loop for autopilot scheduler")


def stop_scheduler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
    _task = None
