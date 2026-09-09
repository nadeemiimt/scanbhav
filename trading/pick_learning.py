"""Log agent pick decisions for self-learning / scoreboard sync + RAG loop."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

LOG_PATH = BASE_DIR / "data" / "trading" / "pick_log.json"
SESSION_TRADES_PATH = BASE_DIR / "data" / "trading" / "session_trades.json"
DECISIONS_PATH = BASE_DIR / "data" / "trading" / "trade_decisions.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_log() -> dict[str, Any]:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not LOG_PATH.exists():
        return {"picks": []}
    try:
        return json.loads(LOG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"picks": []}


def _save_log(data: dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_session_trades() -> dict[str, Any]:
    SESSION_TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SESSION_TRADES_PATH.exists():
        return {"trades": []}
    try:
        return json.loads(SESSION_TRADES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"trades": []}


def _save_session_trades(data: dict[str, Any]) -> None:
    SESSION_TRADES_PATH.parent.mkdir(parents=True, exist_ok=True)
    SESSION_TRADES_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_decisions() -> dict[str, Any]:
    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not DECISIONS_PATH.exists():
        return {"decisions": []}
    try:
        return json.loads(DECISIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"decisions": []}


def _save_decisions(data: dict[str, Any]) -> None:
    DECISIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    DECISIONS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def append_trade_decision(
    *,
    session_id: Optional[str],
    side: str,
    symbol: str,
    rationale: dict[str, Any],
) -> dict[str, Any]:
    data = _load_decisions()
    entry = {
        "id": f"td-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "at": _now(),
        "session_id": session_id,
        "side": side,
        "symbol": str(symbol or "").upper(),
        "rationale": rationale,
    }
    data.setdefault("decisions", []).insert(0, entry)
    data["decisions"] = data["decisions"][:3000]
    _save_decisions(data)
    return entry


def list_trade_decisions(
    session_id: str | None = None,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    rows = (_load_decisions().get("decisions") or [])
    if session_id:
        rows = [r for r in rows if r.get("session_id") == session_id]
    return rows[:limit]


def log_agent_pick(
    *,
    pick: dict[str, Any],
    trade: dict[str, Any],
    mode: str,
    morning_scan_date: str | None = None,
    session_id: str | None = None,
    decision_rationale: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    data = _load_log()
    entry = {
        "id": f"pick-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "at": _now(),
        "mode": mode,
        "session_id": session_id,
        "symbol": pick.get("symbol"),
        "quantity": pick.get("quantity"),
        "notional_inr": pick.get("notional_inr"),
        "expected_profit_inr": pick.get("expected_profit_inr"),
        "composite_score": pick.get("composite_score"),
        "pick_score": pick.get("pick_score"),
        "entry_price": pick.get("price") or trade.get("fill_price"),
        "reasons": pick.get("reasons"),
        "stance": pick.get("stance"),
        "expected_return_pct": pick.get("expected_return_pct"),
        "trade": {k: trade.get(k) for k in ("mode", "order_id", "skipped", "reason", "fill_price") if k in trade},
        "morning_scan_date": morning_scan_date,
        "decision_rationale": decision_rationale,
        "outcome": None,
        "rag_saved": False,
    }
    data.setdefault("picks", []).insert(0, entry)
    data["picks"] = data["picks"][:500]
    _save_log(data)
    return entry


def record_pick_outcome(
    *,
    symbol: str,
    exit_price: float,
    entry_price: float,
    quantity: int,
    reason: str,
    session_id: str | None = None,
    decision_rationale: Optional[dict[str, Any]] = None,
) -> dict[str, Any] | None:
    """Close the most recent open pick for symbol; feed RAG lesson."""
    sym = symbol.upper()
    data = _load_log()
    picks = data.get("picks") or []
    targets: list[dict[str, Any]] = []
    for row in picks:
        if str(row.get("symbol") or "").upper() != sym:
            continue
        if row.get("outcome") is not None:
            continue
        if session_id and row.get("session_id") and row.get("session_id") != session_id:
            continue
        targets.append(row)
    if not targets:
        return None

    target = targets[0]

    entry = float(entry_price or target.get("entry_price") or 0)
    exit_p = float(exit_price)
    pnl = round((exit_p - entry) * int(quantity or target.get("quantity") or 1), 2)
    ret_pct = ((exit_p / entry) - 1) * 100 if entry else 0.0

    outcome = {
        "closed_at": _now(),
        "exit_price": round(exit_p, 4),
        "entry_price": round(entry, 4),
        "quantity": int(quantity or target.get("quantity") or 1),
        "pnl_inr": pnl,
        "return_pct": round(ret_pct, 3),
        "exit_reason": reason,
        "decision_rationale": decision_rationale,
    }
    target["outcome"] = outcome
    target["lesson_text"] = (
        f"Autopilot {sym}: entry ₹{entry:.2f} → exit ₹{exit_p:.2f} "
        f"({ret_pct:+.2f}%, P&L ₹{pnl:+.0f}) via {reason}. "
        f"Composite {target.get('composite_score')} · mode {target.get('mode')}."
    )
    for extra in targets[1:]:
        extra["outcome"] = {
            "closed_at": _now(),
            "exit_price": round(exit_p, 4),
            "entry_price": round(float(extra.get("entry_price") or entry), 4),
            "quantity": int(extra.get("quantity") or 0),
            "pnl_inr": 0,
            "return_pct": 0,
            "exit_reason": reason,
            "aggregated_into": target.get("id"),
        }
        extra["lesson_text"] = (
            f"Autopilot top-up {sym} closed with position — "
            f"qty {extra.get('quantity')} · mode {extra.get('mode')}."
        )
    _save_log(data)

    for row in targets:
        if not row.get("rag_saved"):
            _append_pick_chroma_lesson(row)

    return target


def _append_pick_chroma_lesson(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("rag_saved"):
        return {"skipped": True, "rag_id": record.get("rag_id")}
    from genai_research import append_insight

    outcome = record.get("outcome") or {}
    insight = {
        "stance": "win" if float(outcome.get("pnl_inr") or 0) >= 0 else "loss",
        "executive_summary": record.get("lesson_text") or "",
        "symbol": record.get("symbol"),
        "mode": record.get("mode"),
        "composite_score": record.get("composite_score"),
        "return_pct": outcome.get("return_pct"),
        "pnl_inr": outcome.get("pnl_inr"),
        "exit_reason": outcome.get("exit_reason"),
    }
    stored = append_insight(
        symbol=str(record.get("symbol") or "UNKNOWN"),
        insight=insight,
        provider="autopilot_pick",
        model="session_learning",
        as_of=outcome.get("closed_at") or _now(),
        kind="autopilot_trade_outcome",
        extra_metadata={
            "mode": str(record.get("mode") or ""),
            "session_id": str(record.get("session_id") or ""),
            "top_up": bool((record.get("trade") or {}).get("source") == "session_top_up" or record.get("quantity")),
        },
    )
    record["rag_saved"] = True
    record["rag_id"] = stored.get("id")
    data = _load_log()
    for row in data.get("picks") or []:
        if row.get("id") == record.get("id"):
            row["rag_saved"] = True
            row["rag_id"] = stored.get("id")
            break
    _save_log(data)
    return stored


def retrieve_pick_lessons(symbol: str, *, top_k: int = 3) -> list[dict[str, Any]]:
    """Retrieve past autopilot trade + session lessons from Chroma for scoring context."""
    return retrieve_agent_lessons(symbol, top_k=top_k, include_trade_only=True)


def retrieve_agent_lessons(
    symbol: str,
    *,
    top_k: int = 5,
    include_trade_only: bool = False,
) -> list[dict[str, Any]]:
    """Full agent RAG: trades, timing profiles, operational lessons, session digests."""
    sym = symbol.upper()
    kinds = {
        "autopilot_trade_outcome",
        "autopilot_session_symbol_digest",
        "timing_profile",
        "autopilot_operational_lesson",
    }
    if include_trade_only:
        kinds = {
            "autopilot_trade_outcome",
            "autopilot_session_symbol_digest",
        }

    lessons: list[dict[str, Any]] = []
    lessons.extend(_query_chroma_lessons(
        sym,
        query=f"autopilot trade outcome timing lesson profit loss {sym}",
        top_k=top_k,
        kinds=kinds,
    ))
    if not include_trade_only:
        lessons.extend(_query_chroma_lessons(
            "AUTOPILOT",
            query=f"operational lesson dual desk orphan {sym}",
            top_k=max(1, top_k // 2),
            kinds={"autopilot_operational_lesson", "autopilot_session_digest"},
        ))
    lessons.extend(retrieve_session_digests(symbols=[sym], top_k=max(1, top_k // 2)))

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in lessons:
        key = (row.get("text") or "")[:80].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out[:top_k]


def _query_chroma_lessons(
    symbol: str,
    *,
    query: str,
    top_k: int,
    kinds: set[str] | None = None,
) -> list[dict[str, Any]]:
    try:
        from genai_research import insights_collection, _safe_embed

        db = insights_collection()
        if db.count() == 0:
            return []
        result = db.query(
            query_embeddings=_safe_embed([query]),
            n_results=min(top_k, db.count()),
            where={"symbol": symbol.upper()},
            include=["documents", "metadatas", "distances"],
        )
        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        dists = (result.get("distances") or [[]])[0]
        rows = []
        for doc, meta, dist in zip(docs, metas, dists):
            meta = meta or {}
            kind = meta.get("kind") or ""
            if kinds and kind not in kinds and meta.get("provider") != "autopilot_pick":
                continue
            rows.append({
                "text": (doc or "")[:400],
                "kind": kind,
                "stance": meta.get("stance"),
                "distance": round(float(dist), 4) if dist is not None else None,
                "trade_date_ist": meta.get("trade_date_ist"),
                "session_id": meta.get("session_id"),
            })
        return rows
    except Exception:
        return []


def retrieve_session_digests(*, symbols: Optional[list[str]] = None, top_k: int = 3) -> list[dict[str, Any]]:
    """Fetch consolidated session-day lessons (global + symbol-specific)."""
    from trading.session_report import SESSION_RAG_SYMBOL

    symbols = [s.upper() for s in (symbols or []) if s]
    out: list[dict[str, Any]] = []
    out.extend(_query_chroma_lessons(
        SESSION_RAG_SYMBOL,
        query="autopilot session digest win rate P&L tomorrow focus",
        top_k=top_k,
        kinds={"autopilot_session_digest"},
    ))
    for sym in symbols[:5]:
        out.extend(_query_chroma_lessons(
            sym,
            query=f"autopilot session symbol digest {sym}",
            top_k=1,
            kinds={"autopilot_session_symbol_digest", "autopilot_trade_outcome"},
        ))
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in out:
        key = (row.get("text") or "")[:80]
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped[:top_k]


def log_session_trade(
    *,
    session_id: str,
    side: str,
    symbol: str,
    quantity: int,
    price: float,
    pnl_inr: Optional[float] = None,
    notional_inr: Optional[float] = None,
    reason: str = "",
    pick_mode: str = "",
    entry_price: Optional[float] = None,
    order_id: Optional[str] = None,
    detail: Optional[dict[str, Any]] = None,
    cycle_id: str = "",
) -> dict[str, Any]:
    data = _load_session_trades()
    entry = {
        "id": f"st-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "at": _now(),
        "session_id": session_id,
        "cycle_id": cycle_id or None,
        "side": side,
        "symbol": symbol.upper(),
        "quantity": quantity,
        "price": round(float(price), 4) if price else 0,
        "pnl_inr": pnl_inr,
        "notional_inr": notional_inr,
        "entry_price": entry_price,
        "reason": reason,
        "pick_mode": pick_mode,
        "order_id": order_id,
        "detail": detail or {},
    }
    data.setdefault("trades", []).insert(0, entry)
    data["trades"] = data["trades"][:2000]
    _save_session_trades(data)

    from trading.session_autopilot import _load_store, _find_session, _save_store

    store = _load_store()
    session = _find_session(store, session_id)
    if session:
        session.setdefault("trades", []).insert(0, entry)
        session["trades"] = session["trades"][:500]
        _save_store(store)
    return entry


def on_trade_closed(
    *,
    symbol: str,
    exit_price: float,
    entry_price: float,
    quantity: int,
    reason: str,
    order_id: Optional[str] = None,
    session_id: Optional[str] = None,
    decision_rationale: Optional[dict[str, Any]] = None,
) -> None:
    from trading.config_store import load_trading_config

    if not session_id:
        try:
            from trading.session_autopilot import get_active_session_ids, _session_open_symbols

            sym = symbol.upper()
            for sid in get_active_session_ids():
                if sym in _session_open_symbols(sid):
                    session_id = sid
                    break
        except Exception:
            pass

    if not session_id:
        cfg = load_trading_config()
        ap = cfg.get("autopilot") or {}
        session_id = ap.get("session_id")
        try:
            from trading.session_autopilot import get_active_session_id

            session_id = get_active_session_id() or session_id
        except Exception:
            pass

    record_pick_outcome(
        symbol=symbol,
        exit_price=exit_price,
        entry_price=entry_price,
        quantity=quantity,
        reason=reason,
        session_id=session_id,
        decision_rationale=decision_rationale,
    )

    pnl_inr = round((exit_price - entry_price) * quantity, 2)
    try:
        from quant_layer.trade_journal import record_outcome as record_quant_journal_outcome

        record_quant_journal_outcome(
            symbol=symbol,
            pnl_inr=pnl_inr,
            outcome="win" if pnl_inr >= 0 else "loss",
            session_id=session_id,
        )
    except Exception:
        pass

    if session_id:
        from trading.session_autopilot import on_session_sell

        on_session_sell(
            session_id=str(session_id),
            symbol=symbol,
            quantity=quantity,
            entry_price=entry_price,
            exit_price=exit_price,
            reason=reason,
            order_id=order_id,
            decision_rationale=decision_rationale,
        )


def backfill_pick_rag_lessons(*, limit: int = 200) -> dict[str, Any]:
    """Push any closed pick outcomes not yet saved to Chroma."""
    data = _load_log()
    saved = 0
    skipped = 0
    for row in (data.get("picks") or [])[:limit]:
        if row.get("rag_saved"):
            skipped += 1
            continue
        if not row.get("outcome"):
            continue
        _append_pick_chroma_lesson(row)
        saved += 1
    return {"saved": saved, "skipped_already": skipped, "total_picks": len(data.get("picks") or [])}


def list_pick_log(limit: int = 50) -> list[dict[str, Any]]:
    data = _load_log()
    return (data.get("picks") or [])[:limit]


def symbol_pick_stats(symbol: str) -> dict[str, Any]:
    """Closed pick outcomes for a symbol from pick_log."""
    sym = str(symbol or "").upper()
    wins = losses = 0
    total_pnl = 0.0
    for row in _load_log().get("picks") or []:
        if str(row.get("symbol") or "").upper() != sym:
            continue
        outcome = row.get("outcome")
        if not outcome:
            continue
        pnl = float(outcome.get("pnl_inr") or 0)
        total_pnl += pnl
        if pnl >= 0:
            wins += 1
        else:
            losses += 1
    total = wins + losses
    win_rate = round(wins / total, 3) if total else None
    return {
        "symbol": sym,
        "wins": wins,
        "losses": losses,
        "total": total,
        "win_rate": win_rate,
        "total_pnl_inr": round(total_pnl, 2),
    }


def symbol_win_rate_adjustment(symbol: str) -> float:
    """Nudge live pick_score from historical symbol win rate in pick_log."""
    stats = symbol_pick_stats(symbol)
    total = int(stats.get("total") or 0)
    if total < 2:
        return 0.0
    wr = float(stats.get("win_rate") or 0.5)
    adj = (wr - 0.5) * 12.0
    if total >= 3:
        if wr >= 0.67:
            adj += 2.0
        elif wr <= 0.33:
            adj -= 3.0
    return round(max(-8.0, min(8.0, adj)), 2)


def list_session_trades(session_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    data = _load_session_trades()
    rows = data.get("trades") or []
    if session_id:
        rows = [r for r in rows if r.get("session_id") == session_id]
    return rows[:limit]


def get_learning_recommendations(
    symbols: Optional[list[str]] = None,
    *,
    top_k: int = 5,
) -> dict[str, Any]:
    """Pull RAG + pick-log lessons and return actionable recommendations for next session."""
    from trading.symbol_validate import CURATED_SYMBOLS_MAX

    symbols = [s.upper() for s in (symbols or []) if s]
    symbol_lessons: dict[str, list[dict[str, Any]]] = {}
    for sym in symbols[:CURATED_SYMBOLS_MAX]:
        symbol_lessons[sym] = retrieve_pick_lessons(sym, top_k=top_k)

    global_lessons = retrieve_session_digests(symbols=symbols, top_k=top_k)

    recommendations: list[dict[str, Any]] = []
    for sym, lessons in symbol_lessons.items():
        for row in lessons:
            stance = str(row.get("stance") or "").lower()
            if stance == "loss":
                recommendations.append({
                    "symbol": sym,
                    "action": "reduce_size_or_skip",
                    "reason": (row.get("text") or "")[:200],
                    "source": row.get("kind") or "rag",
                })
            elif stance == "win":
                recommendations.append({
                    "symbol": sym,
                    "action": "favor_entry",
                    "reason": (row.get("text") or "")[:200],
                    "source": row.get("kind") or "rag",
                })

    for row in global_lessons:
        if row.get("kind") == "autopilot_session_digest":
            recommendations.append({
                "symbol": "SESSION",
                "action": "session_context",
                "reason": (row.get("text") or "")[:300],
                "source": "autopilot_session_digest",
            })

    # Heuristic fallbacks from today's pick log when RAG sparse
    if not recommendations:
        for row in list_pick_log(30):
            sym = str(row.get("symbol") or "")
            outcome = row.get("outcome") or {}
            pnl = float(outcome.get("pnl_inr") or 0) if outcome else 0
            if outcome and pnl < -500:
                recommendations.append({
                    "symbol": sym,
                    "action": "avoid_or_reduce",
                    "reason": row.get("lesson_text") or f"Recent loss ₹{pnl:+.0f} via {outcome.get('exit_reason')}",
                    "source": "pick_log",
                })
            elif outcome and pnl > 0:
                recommendations.append({
                    "symbol": sym,
                    "action": "repeat_pattern",
                    "reason": row.get("lesson_text") or f"Recent win ₹{pnl:+.0f}",
                    "source": "pick_log",
                })

    return {
        "symbols": symbols,
        "recommendations": recommendations[:15],
        "symbol_lessons": {k: v[:3] for k, v in symbol_lessons.items()},
        "global_lessons": global_lessons[:3],
    }


OPERATIONAL_LESSONS_PATH = Path(__file__).resolve().parent.parent / "data" / "trading" / "operational_lessons_state.json"

# Populated dynamically from session reports / manual ops — no stale hardcoded lessons.
DAILY_OPERATIONAL_LESSONS: list[dict[str, Any]] = []


def _load_operational_state() -> dict[str, Any]:
    if not OPERATIONAL_LESSONS_PATH.exists():
        return {}
    try:
        return json.loads(OPERATIONAL_LESSONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_operational_state(state: dict[str, Any]) -> None:
    OPERATIONAL_LESSONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    OPERATIONAL_LESSONS_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def append_operational_lesson(
    *,
    lesson_id: str,
    symbol: str,
    summary: str,
    stance: str = "neutral",
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Push one operational lesson into Chroma for agent scoring and RAG gates."""
    from genai_research import append_insight

    stored = append_insight(
        symbol=str(symbol or "AUTOPILOT").upper(),
        insight={
            "stance": stance,
            "executive_summary": summary,
            "tags": tags or [],
            "lesson_id": lesson_id,
        },
        provider="autopilot_ops",
        model="operational_learning",
        kind="autopilot_operational_lesson",
        extra_metadata={"lesson_id": lesson_id, "tags": tags or []},
    )
    return stored


def feed_daily_operational_lessons(*, force: bool = False) -> dict[str, Any]:
    """Ingest dated operational lessons (once per day unless force)."""
    from trading.market_hours import _ist_now

    today = _ist_now().strftime("%Y-%m-%d")
    state = _load_operational_state()
    fed_ids = set(state.get("fed_lesson_ids") or [])
    if not force and state.get("last_feed_date") == today and len(fed_ids) >= len(DAILY_OPERATIONAL_LESSONS):
        return {"skipped": True, "last_feed_date": today, "already_fed": len(fed_ids)}

    saved = 0
    for lesson in DAILY_OPERATIONAL_LESSONS:
        lid = str(lesson.get("id") or "")
        if not force and lid in fed_ids:
            continue
        append_operational_lesson(
            lesson_id=lid,
            symbol=str(lesson.get("symbol") or "AUTOPILOT"),
            summary=str(lesson.get("summary") or ""),
            stance=str(lesson.get("stance") or "neutral"),
            tags=list(lesson.get("tags") or []),
        )
        fed_ids.add(lid)
        saved += 1

    state["last_feed_date"] = today
    state["fed_lesson_ids"] = sorted(fed_ids)
    _save_operational_state(state)
    return {"saved": saved, "last_feed_date": today, "total_lessons": len(DAILY_OPERATIONAL_LESSONS)}
