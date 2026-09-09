"""Runtime buy gates: RAG repeat-loser block, stop/same-day cooldown."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

COOLDOWN_PATH = BASE_DIR / "data" / "trading" / "symbol_day_blocks.json"

STOP_REASONS = frozenset({
    "stop_hit",
    "trailing_stop",
    "psychology_fear_stop",
    "unrealized_loss_cap",
})

EXIT_BLOCK_REASONS = STOP_REASONS | frozenset({
    "target_hit",
    "eod_square_off",
    "psychology_greed_take",
})


def _ist_today() -> str:
    ist = timezone(timedelta(hours=5, minutes=30))
    return datetime.now(ist).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_blocks() -> dict[str, Any]:
    COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not COOLDOWN_PATH.exists():
        return {"entries": []}
    try:
        return json.loads(COOLDOWN_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"entries": []}


def _save_blocks(data: dict[str, Any]) -> None:
    COOLDOWN_PATH.parent.mkdir(parents=True, exist_ok=True)
    COOLDOWN_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def record_symbol_day_block(
    *,
    symbol: str,
    reason: str,
    session_id: Optional[str] = None,
) -> None:
    """Block same-symbol re-entry for the rest of the IST trading day."""
    sym = str(symbol or "").upper()
    if not sym:
        return
    day = _ist_today()
    data = _load_blocks()
    entries: list[dict[str, Any]] = data.setdefault("entries", [])
    entries[:] = [e for e in entries if e.get("date_ist") == day][-500:]
    if any(e.get("symbol") == sym and e.get("date_ist") == day for e in entries):
        return
    entries.append({
        "symbol": sym,
        "date_ist": day,
        "reason": reason,
        "session_id": session_id,
        "at": _now_iso(),
    })
    _save_blocks(data)


def record_stop_cooldown(
    *,
    symbol: str,
    reason: str,
    session_id: Optional[str] = None,
    ret_pct: Optional[float] = None,
) -> None:
    """Block same-symbol re-buy after loss exits; allow re-entry after profitable books."""
    if reason == "partial_scale_out":
        return
    if reason in {"target_hit", "trailing_stop", "eod_square_off", "power_hour_profit_lock"}:
        if ret_pct is not None and ret_pct > 0:
            return
    if reason.startswith("psychology_") and ret_pct is not None and ret_pct > 0:
        return
    record_symbol_day_block(symbol=symbol, reason=reason, session_id=session_id)


def _blocked_today(symbol: str) -> Optional[dict[str, Any]]:
    sym = str(symbol or "").upper()
    day = _ist_today()
    for row in reversed(_load_blocks().get("entries") or []):
        if row.get("symbol") == sym and row.get("date_ist") == day:
            return row
    return None


def evaluate_stop_cooldown(symbol: str, *, session_id: Optional[str] = None) -> dict[str, Any]:
    from trading.config_store import load_trading_config

    ap = load_trading_config().get("autopilot") or {}
    if not ap.get("stop_cooldown_enabled", True) and not ap.get("same_day_symbol_block", True):
        return {"allowed": True, "reason": "cooldown_disabled"}

    row = _blocked_today(symbol)
    if not row:
        return {"allowed": True, "reason": "no_cooldown"}

    reason = str(row.get("reason") or "symbol_day_block")
    if reason in STOP_REASONS and not ap.get("stop_cooldown_enabled", True):
        return {"allowed": True, "reason": "stop_cooldown_disabled"}
    if reason not in STOP_REASONS and not ap.get("same_day_symbol_block", True):
        return {"allowed": True, "reason": "same_day_block_disabled"}

    return {
        "allowed": False,
        "reason": "stop_cooldown_same_day" if reason in STOP_REASONS else "same_day_symbol_block",
        "message": f"{symbol.upper()} already exited today ({reason}) — no re-buy until tomorrow.",
        "block": row,
        "session_id": session_id,
    }


def _rag_block_enabled(*, pick_mode: Optional[str] = None) -> bool:
    from trading.config_store import load_trading_config

    ap = load_trading_config().get("autopilot") or {}
    mode = str(pick_mode or "").lower()
    if mode in {"curated_list", "session_curated"}:
        return bool(ap.get("rag_block_repeat_losers_curated", False))
    if mode in {"auto_pick", "session_agent_auto", "agent_auto"}:
        return bool(ap.get("rag_block_repeat_losers", True))
    return bool(ap.get("rag_block_repeat_losers", True))


def evaluate_rag_buy_gate(
    symbol: str,
    *,
    session_id: Optional[str] = None,
    pick_mode: Optional[str] = None,
) -> dict[str, Any]:
    """Hard-skip buys when RAG + pick_log show repeat losers (desk-specific)."""
    from trading.pick_learning import retrieve_agent_lessons, symbol_pick_stats

    if not _rag_block_enabled(pick_mode=pick_mode):
        return {"allowed": True, "reason": "rag_block_disabled", "pick_mode": pick_mode}

    from trading.config_store import load_trading_config

    ap = load_trading_config().get("autopilot") or {}
    sym = str(symbol or "").upper()
    min_losses = int(ap.get("rag_block_min_loss_lessons") or 2)
    min_pick_losses = int(ap.get("rag_block_min_pick_losses") or 2)

    loss_lessons = 0
    lesson_samples: list[str] = []
    try:
        for row in retrieve_agent_lessons(sym, top_k=6):
            stance = str(row.get("stance") or "").lower()
            text = str(row.get("text") or "")[:120]
            if stance == "loss":
                loss_lessons += 1
                if len(lesson_samples) < 2:
                    lesson_samples.append(text)
    except Exception:
        pass

    stats = symbol_pick_stats(sym)
    pick_losses = int(stats.get("losses") or 0)
    pick_total = int(stats.get("total") or 0)

    blocked = False
    reasons: list[str] = []
    if loss_lessons >= min_losses:
        blocked = True
        reasons.append(f"rag_loss_lessons={loss_lessons}")
    if pick_total >= min_pick_losses and pick_losses >= min_pick_losses:
        wr = stats.get("win_rate")
        if wr is not None and float(wr) <= 0.35:
            blocked = True
            reasons.append(f"pick_log_losses={pick_losses}/{pick_total}")

    if not blocked:
        return {
            "allowed": True,
            "reason": "rag_ok",
            "loss_lessons": loss_lessons,
            "pick_stats": stats,
        }

    return {
        "allowed": False,
        "reason": "rag_repeat_loser",
        "message": f"RAG/pick history flags repeat loser on {sym}.",
        "loss_lessons": loss_lessons,
        "pick_stats": stats,
        "lesson_samples": lesson_samples,
        "detail": "; ".join(reasons),
        "session_id": session_id,
    }


def evaluate_entry_gates(
    symbol: str,
    *,
    session_id: Optional[str] = None,
    pick_mode: Optional[str] = None,
) -> dict[str, Any]:
    """Run cooldown then RAG gates (first failure wins)."""
    cooldown = evaluate_stop_cooldown(symbol, session_id=session_id)
    if not cooldown.get("allowed"):
        return cooldown
    rag = evaluate_rag_buy_gate(symbol, session_id=session_id, pick_mode=pick_mode)
    if not rag.get("allowed"):
        return rag
    return {"allowed": True, "reason": "entry_gates_ok", "cooldown": cooldown, "rag": rag}
