"""NSE cash market session hours (IST) — pre-market analysis vs live trading."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

SessionPhase = Literal["weekend", "overnight", "pre_market", "trading", "post_close"]


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _minutes_ist() -> int:
    now = _ist_now()
    return now.hour * 60 + now.minute


def nse_schedule(cfg: dict[str, Any] | None = None) -> dict[str, int]:
    """Configurable NSE schedule (minutes from midnight IST), with special-session override."""
    from trading.config_store import load_trading_config

    cfg = cfg or load_trading_config()
    ap = cfg.get("autopilot") or {}
    if ap.get("use_nse_calendar", True):
        from trading.nse_calendar import _schedule_for_date

        sched = _schedule_for_date(_ist_now().strftime("%Y-%m-%d"), cfg)
        return {
            "premarket_start": sched["premarket_start"],
            "market_open": sched["market_open"],
            "market_close": sched["market_close"],
            "square_off": sched["square_off"],
        }
    return {
        "premarket_start": int(ap.get("nse_premarket_start_minute_ist") or 9 * 60),
        "market_open": int(ap.get("nse_market_open_minute_ist") or 9 * 60 + 15),
        "market_close": int(ap.get("nse_market_close_minute_ist") or 15 * 60 + 30),
        "square_off": int(ap.get("square_off_minute_ist") or 15 * 60 + 20),
    }


def nse_session_phase(cfg: dict[str, Any] | None = None) -> SessionPhase:
    from trading.config_store import load_trading_config

    cfg = cfg or load_trading_config()
    ap = cfg.get("autopilot") or {}
    now = _ist_now()
    iso_date = now.strftime("%Y-%m-%d")
    mins = _minutes_ist()
    sched = nse_schedule(cfg)

    if ap.get("use_nse_calendar", True):
        from trading.nse_calendar import is_trading_day, live_capital_market_open, special_session_for_date

        if not is_trading_day(iso_date, cfg):
            return "weekend"
        live = live_capital_market_open(cfg)
        if live is True:
            return "trading"
        if live is False and mins >= sched["square_off"]:
            return "post_close"
        special = special_session_for_date(iso_date)
        if special and now.weekday() >= 5:
            pass  # fall through to time windows for Muhurat on Sat/Sun
        elif now.weekday() >= 5 and not special:
            return "weekend"
    elif now.weekday() >= 5:
        return "weekend"

    if mins < sched["premarket_start"]:
        return "overnight"
    if mins < sched["market_open"]:
        return "pre_market"
    if mins <= sched["market_close"]:
        return "trading"
    return "post_close"


def nse_session_info(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Human-readable NSE session state for UI and scheduler."""
    from trading.config_store import load_trading_config

    cfg = cfg or load_trading_config()
    now = _ist_now()
    phase = nse_session_phase(cfg)
    sched = nse_schedule(cfg)
    mins = _minutes_ist()

    def _fmt(m: int) -> str:
        return f"{m // 60:02d}:{m % 60:02d}"

    labels = {
        "weekend": "Weekend / NSE holiday — market closed",
        "overnight": "Before pre-market — waiting for 09:00 IST analysis",
        "pre_market": "Pre-market analysis (09:00–09:15) — scoring & timing, no buys yet",
        "trading": "Live trading (09:15–15:30) — entries/exits with timing gates",
        "post_close": "Post-close — square-off & session wrap-up",
    }

    calendar_note = ""
    if (cfg or {}).get("autopilot", {}).get("use_nse_calendar", True):
        try:
            from trading.nse_calendar import calendar_snapshot

            cal = calendar_snapshot(cfg)
            if cal.get("special_session"):
                sp = cal["special_session"]
                calendar_note = f"Special session: {sp.get('name')} (NSE calendar)"
            elif cal.get("is_holiday"):
                calendar_note = "NSE CM holiday today"
            cm = (cal.get("market_status") or {})
            if cm.get("marketStatusMessage"):
                calendar_note = (calendar_note + " · " if calendar_note else "") + str(cm["marketStatusMessage"])
        except Exception:
            pass

    next_transition = None
    if phase == "overnight":
        next_transition = {"at": _fmt(sched["premarket_start"]), "event": "premarket_analysis"}
    elif phase == "pre_market":
        next_transition = {"at": _fmt(sched["market_open"]), "event": "trading_starts"}
    elif phase == "trading":
        next_transition = {"at": _fmt(sched["square_off"]), "event": "square_off_begins"}
    elif phase == "post_close":
        next_transition = {"at": "next trading day 09:00", "event": "premarket_analysis"}

    return {
        "phase": phase,
        "label": labels.get(phase, phase),
        "ist_time": now.strftime("%H:%M:%S"),
        "ist_date": now.strftime("%Y-%m-%d"),
        "weekday": now.strftime("%A"),
        "schedule": {
            "premarket_start": _fmt(sched["premarket_start"]),
            "market_open": _fmt(sched["market_open"]),
            "market_close": _fmt(sched["market_close"]),
            "square_off": _fmt(sched["square_off"]),
        },
        "can_analyze": phase in {"pre_market", "trading", "overnight"},
        "can_buy": phase == "trading",
        "can_sell": phase in {"trading", "post_close"},
        "force_square_off": phase == "post_close" or mins >= sched["square_off"],
        "minutes_to_open": max(0, sched["market_open"] - mins) if phase == "pre_market" else 0,
        "next_transition": next_transition,
        "nse_note": calendar_note or "NSE cash market trades 09:15–15:30 IST (Mon–Fri). Holidays & Muhurat from NSE API when enabled.",
        "calendar_source": "nse" if (cfg or {}).get("autopilot", {}).get("use_nse_calendar", True) else "static",
    }


def is_premarket_window(cfg: dict[str, Any] | None = None) -> bool:
    return nse_session_phase(cfg) == "pre_market"


def is_trading_window(cfg: dict[str, Any] | None = None) -> bool:
    return nse_session_phase(cfg) == "trading"


def market_open_ist(cfg: dict[str, Any] | None = None) -> bool:
    """True during NSE cash trading hours (09:15–15:30 IST, weekdays)."""
    return nse_session_phase(cfg) == "trading"


def seconds_until_ist_minutes(minutes_from_midnight: int) -> int:
    """Seconds from now (IST) until HH:MM today; 0 if already passed."""
    now = _ist_now()
    h, m = divmod(int(minutes_from_midnight), 60)
    target = now.replace(hour=h, minute=m, second=0, microsecond=0)
    if target <= now:
        return 0
    return int((target - now).total_seconds())

