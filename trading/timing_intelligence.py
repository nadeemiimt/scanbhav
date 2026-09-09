"""
Timing intelligence — learn when entries/exits worked historically (IST session windows).

This does NOT replicate exchange co-location or sub-second NSE/BSE tick feeds.
Pro traders with direct market access may see prices 1–5s earlier than retail Yahoo/broker polls.
We compensate with:
  - Session-window patterns (open drive, power hour, EOD)
  - Gap / range / weekday stats from daily history
  - Lead–lag vs Nifty proxy
  - Chroma lessons for agent RAG
  - Optional gate: only auto-trade in favorable windows
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from genai_research import append_insight

PROFILES_PATH = BASE_DIR / "data" / "trading" / "timing_profiles.json"
MARKET_PROFILE_PATH = BASE_DIR / "data" / "trading" / "timing_market.json"

# IST session windows (minutes from midnight)
SESSION_WINDOWS: list[dict[str, Any]] = [
    {"id": "pre_open", "start": 9 * 60 + 0, "end": 9 * 60 + 15, "label": "Pre-open", "auto_trade": False},
    {"id": "open_drive", "start": 9 * 60 + 15, "end": 9 * 60 + 45, "label": "Opening drive (9:15–9:45)", "auto_trade": True},
    {"id": "morning_trend", "start": 9 * 60 + 45, "end": 10 * 60 + 30, "label": "Morning trend", "auto_trade": True},
    {"id": "midday", "start": 10 * 60 + 30, "end": 14 * 60 + 30, "label": "Mid session", "auto_trade": True},
    {"id": "power_hour", "start": 14 * 60 + 30, "end": 15 * 60 + 20, "label": "Power hour", "auto_trade": True},
    {"id": "closing", "start": 15 * 60 + 20, "end": 15 * 60 + 30, "label": "Closing auction", "auto_trade": False},
]


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def _today_ist() -> str:
    return _ist_now().strftime("%Y-%m-%d")


def _load_rows(symbol: str) -> list[dict[str, Any]]:
    from routes.helpers import raw_path

    path = raw_path(symbol)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else payload.get("rows") or []
    except Exception:
        return []


def _ohlc(row: dict[str, Any]) -> tuple[float, float, float, float]:
    o = float(row.get("1. open") or row.get("open") or 0)
    h = float(row.get("2. high") or row.get("high") or 0)
    l = float(row.get("3. low") or row.get("low") or 0)
    c = float(row.get("4. close") or row.get("close") or row.get("5. adjusted close") or 0)
    return o, h, l, c


def current_session_window() -> dict[str, Any]:
    now = _ist_now()
    if now.weekday() >= 5:
        return {"id": "closed", "label": "Weekend", "auto_trade": False, "market_open": False}
    mins = now.hour * 60 + now.minute
    if mins < 9 * 60 + 15:
        return {"id": "pre_market", "label": "Pre-market", "auto_trade": False, "market_open": False}
    if mins > 15 * 60 + 30:
        return {"id": "closed", "label": "Market closed", "auto_trade": False, "market_open": False}
    for w in SESSION_WINDOWS:
        if w["start"] <= mins < w["end"]:
            return {**w, "market_open": True, "ist_time": now.strftime("%H:%M")}
    return {"id": "open", "label": "Market open", "auto_trade": True, "market_open": True}


def analyze_symbol_timing(symbol: str, *, lookback: int = 120) -> dict[str, Any]:
    """Learn timing patterns from daily OHLC (proxy for intraday behavior)."""
    rows = _load_rows(symbol)[-lookback:]
    if len(rows) < 30:
        return {"symbol": symbol.upper(), "error": "insufficient_history", "bars": len(rows)}

    gaps: list[float] = []
    open_strength: list[float] = []
    weekday_returns: dict[int, list[float]] = {i: [] for i in range(5)}
    continuations = 0
    reversals = 0

    for i in range(1, len(rows)):
        o, h, l, c = _ohlc(rows[i])
        _, _, _, pc = _ohlc(rows[i - 1])
        if o <= 0 or pc <= 0:
            continue
        gap_pct = (o / pc - 1) * 100
        gaps.append(gap_pct)
        day_ret = (c / o - 1) * 100 if o else 0
        rng = max(h - l, 0.01)
        open_strength.append((c - o) / rng)

        if gap_pct > 0.3 and day_ret > 0:
            continuations += 1
        elif gap_pct > 0.3 and day_ret < 0:
            reversals += 1
        elif gap_pct < -0.3 and day_ret < 0:
            continuations += 1
        elif gap_pct < -0.3 and day_ret > 0:
            reversals += 1

        try:
            dt = datetime.strptime(str(rows[i].get("date", ""))[:10], "%Y-%m-%d")
            if dt.weekday() < 5:
                weekday_returns[dt.weekday()].append(day_ret)
        except Exception:
            pass

    avg_gap = statistics.mean(gaps) if gaps else 0
    gap_up_rate = sum(1 for g in gaps if g > 0.2) / max(len(gaps), 1)
    avg_open_str = statistics.mean(open_strength) if open_strength else 0
    cont_rate = continuations / max(continuations + reversals, 1)

    best_dow = max(
        range(5),
        key=lambda d: statistics.mean(weekday_returns[d]) if weekday_returns[d] else -999,
        default=0,
    )
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]

    favorable: list[str] = []
    if cont_rate >= 0.55:
        favorable.extend(["open_drive", "morning_trend"])
    if avg_open_str > 0.05:
        favorable.append("morning_trend")
    if statistics.mean(weekday_returns[4]) if weekday_returns[4] else 0 > 0:
        favorable.append("power_hour")
    if not favorable:
        favorable = ["morning_trend", "midday"]

    return {
        "symbol": symbol.upper(),
        "bars_analyzed": len(rows),
        "avg_gap_pct": round(avg_gap, 3),
        "gap_up_rate": round(gap_up_rate, 3),
        "gap_continuation_rate": round(cont_rate, 3),
        "open_strength_bias": round(avg_open_str, 3),
        "best_weekday": dow_names[best_dow],
        "weekday_avg_return": {
            dow_names[d]: round(statistics.mean(weekday_returns[d]), 3) if weekday_returns[d] else None
            for d in range(5)
        },
        "favorable_windows": list(dict.fromkeys(favorable)),
        "suggested_entry_windows": list(dict.fromkeys(favorable))[:2],
        "latency_note": (
            "Daily-bar proxy only. For faster reaction use broker LTP poll in open window — "
            "still not co-lo tick feed."
        ),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def _session_timing_skip_count(session_id: str | None) -> int:
    if not session_id:
        return 0
    try:
        from trading.session_history import list_session_events

        count = 0
        for event in list_session_events(session_id, limit=300, event_type="cycle_complete"):
            payload = event.get("payload") or {}
            count += len(payload.get("timing_blocked") or [])
        return count
    except Exception:
        return 0


def timing_gate_allows(
    side: str = "buy",
    symbol: str = "",
    *,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Should auto-trading act now? Combines session + symbol profile."""
    from trading.config_store import load_trading_config

    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("timing_intel_enabled", True):
        return {"allowed": True, "reason": "timing_intel_disabled"}

    window = current_session_window()
    if not window.get("market_open"):
        return {"allowed": False, "reason": "market_closed", "window": window}

    adaptive = bool(ap.get("timing_adaptive_loosen", False))
    skip_threshold = int(ap.get("timing_adaptive_skip_threshold") or 5)
    timing_skips = _session_timing_skip_count(session_id) if adaptive else 0
    loosen = adaptive and timing_skips >= skip_threshold
    strict_symbol = bool(ap.get("timing_strict_symbol", False)) and not loosen

    if side == "buy" and ap.get("timing_preferred_windows_only", True) and not loosen:
        preferred = ap.get("timing_preferred_window_ids") or ["open_drive", "morning_trend"]
        wid = window.get("id")
        if wid and wid not in preferred:
            return {
                "allowed": False,
                "reason": f"outside_preferred_window_{wid}",
                "window": window,
                "preferred_windows": preferred,
            }

    if ap.get("timing_gate_auto_trades", True) and not window.get("auto_trade") and not loosen:
        return {"allowed": False, "reason": f"unfavorable_window_{window.get('id')}", "window": window}

    sym = symbol.upper()
    profile = _load_profiles().get("symbols", {}).get(sym) or {}
    fav = profile.get("favorable_windows") or []
    wid = window.get("id")
    if fav and wid and wid not in fav and strict_symbol:
        return {
            "allowed": False,
            "reason": f"symbol_timing_{wid}_not_in_favorable",
            "window": window,
            "profile": profile,
        }

    return {
        "allowed": True,
        "window": window,
        "profile_hint": profile.get("suggested_entry_windows"),
        "reason": "timing_ok",
        "timing_loosened": loosen,
        "timing_skip_count": timing_skips,
    }


def _load_profiles() -> dict[str, Any]:
    if not PROFILES_PATH.exists():
        return {"symbols": {}, "updated_at": None}
    try:
        return json.loads(PROFILES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"symbols": {}, "updated_at": None}


def learn_timing_batch(symbols: list[str], *, feed_rag: bool = True) -> dict[str, Any]:
    """Analyze symbols and persist timing profiles + optional Chroma lessons."""
    profiles: dict[str, Any] = {}
    rag_count = 0
    errors: list[dict[str, str]] = []

    for sym in symbols[:80]:
        sym = sym.upper().strip()
        if not sym:
            continue
        try:
            p = analyze_symbol_timing(sym)
            if p.get("error"):
                errors.append({"symbol": sym, "error": p["error"]})
                continue
            profiles[sym] = p
            if feed_rag:
                insight = {
                    "stance": "constructive" if p.get("gap_continuation_rate", 0) >= 0.5 else "neutral",
                    "executive_summary": (
                        f"Timing profile {sym}: gap continuation {p.get('gap_continuation_rate')}, "
                        f"best weekday {p.get('best_weekday')}, "
                        f"favor windows {', '.join(p.get('favorable_windows') or [])}."
                    ),
                    "timing_profile": p,
                    "what_changed_vs_prior": "Learned from daily OHLC timing patterns.",
                    "not_advice_disclaimer": "Historical timing proxy — not HFT edge.",
                }
                append_insight(
                    symbol=sym,
                    insight=insight,
                    provider="timing_intel",
                    model="session_patterns",
                    as_of=_today_ist(),
                    kind="timing_profile",
                )
                rag_count += 1
        except Exception as exc:
            errors.append({"symbol": sym, "error": str(exc)})

    payload = {
        "symbols": profiles,
        "learned": len(profiles),
        "rag_chunks": rag_count,
        "errors": errors[:20],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": (
            "Timing profiles use daily bars + IST session rules. "
            "They do not replicate exchange co-location or tick-level front-running."
        ),
    }
    PROFILES_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILES_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    market = {
        "trade_date_ist": _today_ist(),
        "current_window": current_session_window(),
        "session_windows": SESSION_WINDOWS,
        "latency_reality": {
            "pro_feed": "Co-lo / direct NSE-BSE tick — 1–5s faster than retail",
            "our_feed": "Yahoo/NSE daily + broker LTP poll (seconds, not milliseconds)",
            "strategy": "Pattern timing + faster poll in open window, not speed arbitrage",
        },
    }
    MARKET_PROFILE_PATH.write_text(json.dumps(market, indent=2), encoding="utf-8")
    try:
        from trading.latency_compensation import learn_latency_compensation_rag

        lag_rag = learn_latency_compensation_rag(list(profiles.keys()))
    except Exception:
        lag_rag = 0
    return {**payload, "market": market, "latency_compensation_rag": lag_rag}


def timing_status() -> dict[str, Any]:
    profiles = _load_profiles()
    market = {}
    if MARKET_PROFILE_PATH.exists():
        try:
            market = json.loads(MARKET_PROFILE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    window = current_session_window()
    gate = timing_gate_allows()
    try:
        from trading.latency_compensation import compensation_status

        compensation = compensation_status()
    except Exception:
        compensation = {}
    return {
        "current_window": window,
        "auto_trade_allowed_now": gate.get("allowed"),
        "gate_reason": gate.get("reason"),
        "profiles_learned": len(profiles.get("symbols") or {}),
        "last_learned_at": profiles.get("updated_at"),
        "market": market,
        "session_windows": SESSION_WINDOWS,
        "latency_compensation": compensation,
    }


def recommended_poll_seconds(default: int = 120) -> int:
    """Faster poll during NSE pre-market + opening window when timing intel enabled."""
    from trading.config_store import load_trading_config
    from trading.market_hours import nse_session_phase

    cfg = load_trading_config()
    ap = cfg.get("autopilot") or {}
    if not ap.get("timing_intel_enabled", True):
        return default

    phase = nse_session_phase(cfg)
    if ap.get("session_active") and phase == "pre_market":
        return min(45, default)

    if not ap.get("fast_poll_open_window", True):
        return default

    w = current_session_window()
    if w.get("id") in {"open_drive", "morning_trend"}:
        return min(30, default)
    if phase == "trading":
        return min(60, default)
    return default
