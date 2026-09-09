"""End-of-day autopilot session report, GenAI post-mortem, and RAG digest."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from trading.json_store import dumps_pretty
from trading.paper_ledger import daily_stats
from trading.pick_learning import list_pick_log, list_session_trades, retrieve_session_digests

REPORTS_DIR = BASE_DIR / "data" / "trading" / "session_reports"
SESSION_RAG_SYMBOL = "AUTOPILOT"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_ist() -> str:
    from trading.market_hours import _ist_now

    return _ist_now().strftime("%Y-%m-%d")


def _report_path(session_id: str) -> Path:
    return REPORTS_DIR / f"{session_id}.json"


def load_session_report(session_id: str) -> Optional[dict[str, Any]]:
    path = _report_path(session_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_latest_session_report() -> Optional[dict[str, Any]]:
    """Most recent saved report — prefer newest session row, else newest file on disk."""
    try:
        from trading.session_autopilot import _load_store

        for session in _load_store().get("sessions") or []:
            sid = str(session.get("id") or "")
            if not sid:
                continue
            report = load_session_report(sid)
            if report:
                return report
    except Exception:
        pass
    if REPORTS_DIR.exists():
        files = sorted(REPORTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def _session_day_trades(session: dict[str, Any]) -> list[dict[str, Any]]:
    """Trades tagged to this session id only (dual desk keeps desks isolated)."""
    session_id = str(session.get("id") or "")
    if not session_id:
        return []
    return list_session_trades(session_id, limit=500)


def _session_trade_date_ist(session: dict[str, Any]) -> str:
    started = str(session.get("started_at") or "")
    if started:
        try:
            from datetime import datetime as dt
            from datetime import timedelta, timezone

            parsed = dt.fromisoformat(started.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
        except Exception:
            pass
    return _today_ist()


def _daily_stats_for_date(trade_date: str) -> dict[str, Any]:
    from trading.paper_ledger import DAILY_PATH, _load

    data = _load(DAILY_PATH, {"days": {}})
    return dict(data.get("days", {}).get(trade_date) or {})


def _ledger_closed_legs(trade_date: str) -> list[dict[str, Any]]:
    from trading.paper_ledger import LEDGER_PATH, _load

    ledger = _load(LEDGER_PATH, {"orders": [], "positions": []})
    legs: list[dict[str, Any]] = []
    for pos in ledger.get("positions") or []:
        if str(pos.get("status") or "") != "closed":
            continue
        closed_at = str(pos.get("closed_at") or "")[:10]
        if closed_at != trade_date:
            continue
        pnl = pos.get("realized_pnl_inr")
        if pnl is None:
            continue
        legs.append({
            "symbol": str(pos.get("symbol") or "").upper(),
            "quantity": int(pos.get("quantity") or 0),
            "entry_price": pos.get("avg_price"),
            "exit_price": None,
            "pnl_inr": float(pnl),
            "return_pct": None,
            "exit_reason": "ledger_close",
            "closed_at": pos.get("closed_at"),
        })
    return legs


def _ledger_buy_notional(trade_date: str) -> float:
    from trading.paper_ledger import LEDGER_PATH, _load

    ledger = _load(LEDGER_PATH, {"orders": [], "positions": []})
    total = 0.0
    for order in ledger.get("orders") or []:
        if str(order.get("side") or "").lower() != "buy":
            continue
        if not str(order.get("created_at") or "").startswith(trade_date):
            continue
        total += float(order.get("notional_inr") or 0)
    return round(total, 2)


def report_is_stale(session: dict[str, Any], report: Optional[dict[str, Any]]) -> bool:
    """True when an early/empty EOD report no longer matches session activity."""
    if not report:
        return True
    summary = report.get("summary") or {}
    trades = _session_day_trades(session)
    closed = _closed_legs(trades)
    if closed and int(summary.get("closed_trades") or 0) == 0:
        return True
    if not closed and int(summary.get("closed_trades") or 0) > 0:
        return True
    if int(summary.get("closed_trades") or 0) != len(closed):
        return True
    if trades and int(summary.get("buy_notional_inr") or 0) == 0:
        buy_notional = sum(
            float(t.get("notional_inr") or (t.get("price") or 0) * (t.get("quantity") or 0))
            for t in trades
            if str(t.get("side") or "").lower() == "buy"
        )
        if buy_notional > 0:
            return True
    gen = str(report.get("generated_at") or "")
    stop = str(session.get("stopped_at") or session.get("completed_at") or "")
    if gen and stop and gen < stop and closed:
        return True
    return False


def _closed_legs(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Round-trip legs from sell rows that carry pnl_inr."""
    closed: list[dict[str, Any]] = []
    for row in trades:
        if str(row.get("side") or "").lower() != "sell":
            continue
        pnl = row.get("pnl_inr")
        if pnl is None:
            continue
        detail = row.get("detail") or {}
        closed.append({
            "symbol": str(row.get("symbol") or "").upper(),
            "quantity": int(row.get("quantity") or 0),
            "entry_price": detail.get("entry_price") or row.get("entry_price"),
            "exit_price": row.get("price"),
            "pnl_inr": float(pnl),
            "return_pct": detail.get("return_pct"),
            "exit_reason": row.get("reason") or detail.get("exit_reason") or "unknown",
            "closed_at": row.get("at"),
        })
    return closed


def build_session_summary(session: dict[str, Any]) -> dict[str, Any]:
    """Aggregate P&L, win rate, and per-symbol stats for a session."""
    session_id = str(session.get("id") or "")
    trades = _session_day_trades(session)
    if not trades and session.get("trades"):
        trades = list(session.get("trades") or [])

    closed = _closed_legs(trades)
    trade_date = _session_trade_date_ist(session)
    buys = [t for t in trades if str(t.get("side") or "").lower() == "buy"]
    buy_notional = round(
        sum(float(t.get("notional_inr") or (t.get("price") or 0) * (t.get("quantity") or 0)) for t in buys),
        2,
    )

    wins = [c for c in closed if c["pnl_inr"] > 0]
    losses = [c for c in closed if c["pnl_inr"] < 0]
    flat = [c for c in closed if c["pnl_inr"] == 0]
    if closed:
        realized = round(sum(c["pnl_inr"] for c in closed), 2)
    else:
        realized = float(session.get("realized_pnl_inr") or 0)

    by_symbol: dict[str, dict[str, Any]] = defaultdict(lambda: {
        "symbol": "",
        "closed_count": 0,
        "wins": 0,
        "losses": 0,
        "pnl_inr": 0.0,
        "best_pnl_inr": None,
        "worst_pnl_inr": None,
    })
    by_reason: dict[str, int] = defaultdict(int)
    for leg in closed:
        sym = leg["symbol"]
        bucket = by_symbol[sym]
        bucket["symbol"] = sym
        bucket["closed_count"] += 1
        bucket["pnl_inr"] = round(bucket["pnl_inr"] + leg["pnl_inr"], 2)
        if leg["pnl_inr"] > 0:
            bucket["wins"] += 1
        elif leg["pnl_inr"] < 0:
            bucket["losses"] += 1
        bucket["best_pnl_inr"] = leg["pnl_inr"] if bucket["best_pnl_inr"] is None else max(bucket["best_pnl_inr"], leg["pnl_inr"])
        bucket["worst_pnl_inr"] = leg["pnl_inr"] if bucket["worst_pnl_inr"] is None else min(bucket["worst_pnl_inr"], leg["pnl_inr"])
        by_reason[str(leg.get("exit_reason") or "unknown")] += 1

    symbol_rows = sorted(by_symbol.values(), key=lambda x: x["pnl_inr"], reverse=True)
    best = symbol_rows[0] if symbol_rows else None
    worst = symbol_rows[-1] if symbol_rows else None

    pick_rows = [p for p in list_pick_log(200) if p.get("session_id") == session_id]
    rag_trade_lessons = sum(1 for p in pick_rows if p.get("rag_saved"))

    started = session.get("started_at") or ""

    from trading.session_history import list_session_events

    cycle_events = list_session_events(session_id, limit=500, event_type="cycle_complete") if session_id else []
    cycle_count = len(cycle_events) or len(session.get("cycles") or [])

    from trading.paper_ledger import open_positions

    open_count = len({
        str(p.get("symbol") or "").upper()
        for p in open_positions("mis")
        if int(p.get("quantity") or 0) > 0
    })

    return {
        "session_id": session_id,
        "trade_date_ist": trade_date,
        "pick_mode": session.get("pick_mode"),
        "curated_symbols": list(session.get("curated_symbols") or []),
        "completion_reason": session.get("completion_reason") or session.get("status"),
        "started_at": session.get("started_at"),
        "stopped_at": session.get("stopped_at") or session.get("completed_at"),
        "realized_pnl_inr": realized,
        "buy_notional_inr": buy_notional,
        "closed_trades": len(closed),
        "open_buys": open_count,
        "wins": len(wins),
        "losses": len(losses),
        "flat": len(flat),
        "win_rate_pct": round(100 * len(wins) / len(closed), 1) if closed else None,
        "avg_win_inr": round(sum(c["pnl_inr"] for c in wins) / len(wins), 2) if wins else None,
        "avg_loss_inr": round(sum(c["pnl_inr"] for c in losses) / len(losses), 2) if losses else None,
        "best_symbol": best,
        "worst_symbol": worst,
        "by_symbol": symbol_rows,
        "by_exit_reason": dict(by_reason),
        "cycle_count": cycle_count,
        "caps": session.get("caps") or {},
        "closed_legs": closed,
        "rag_trade_lessons_saved": rag_trade_lessons,
    }


def build_markdown_report(summary: dict[str, Any], postmortem: dict[str, Any]) -> str:
    """Human-readable markdown EOD report."""
    pnl = float(summary.get("realized_pnl_inr") or 0)
    pnl_label = f"₹{pnl:+,.0f}"
    lines = [
        f"# Autopilot session report — {summary.get('trade_date_ist')}",
        "",
        f"**Session:** `{summary.get('session_id')}`  ",
        f"**Mode:** {summary.get('pick_mode')}  ",
        f"**Closed as:** {summary.get('completion_reason') or '—'}  ",
        "",
        "## Day P&L",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Realized P&L | **{pnl_label}** |",
        f"| Buy notional deployed | ₹{summary.get('buy_notional_inr', 0):,.0f} |",
        f"| Closed round-trips | {summary.get('closed_trades', 0)} |",
        f"| Win rate | {summary.get('win_rate_pct') if summary.get('win_rate_pct') is not None else '—'}% |",
        f"| Wins / losses | {summary.get('wins', 0)} / {summary.get('losses', 0)} |",
        f"| Avg win | ₹{summary.get('avg_win_inr') or 0:,.0f} |",
        f"| Avg loss | ₹{summary.get('avg_loss_inr') or 0:,.0f} |",
        f"| Scheduler cycles | {summary.get('cycle_count', 0)} |",
        "",
    ]

    best = summary.get("best_symbol")
    worst = summary.get("worst_symbol")
    if best:
        lines += [
            "## Best / worst symbol",
            "",
            f"- **Best:** {best.get('symbol')} — ₹{best.get('pnl_inr', 0):+,.0f} ({best.get('closed_count')} closes)",
        ]
    if worst and worst != best:
        lines.append(f"- **Worst:** {worst.get('symbol')} — ₹{worst.get('pnl_inr', 0):+,.0f} ({worst.get('closed_count')} closes)")
    lines.append("")

    if summary.get("by_symbol"):
        lines += ["## Per-symbol", "", "| Symbol | P&L | W/L | Closes |", "|--------|-----|-----|--------|"]
        for row in summary["by_symbol"]:
            lines.append(
                f"| {row['symbol']} | ₹{row['pnl_inr']:+,.0f} | {row['wins']}/{row['losses']} | {row['closed_count']} |"
            )
        lines.append("")

    if summary.get("by_exit_reason"):
        lines += ["## Exit reasons", ""]
        for reason, count in summary["by_exit_reason"].items():
            lines.append(f"- **{reason}:** {count}")
        lines.append("")

    if postmortem:
        lines += ["## Post-mortem", ""]
        if postmortem.get("executive_summary"):
            lines.append(postmortem["executive_summary"])
            lines.append("")
        for label, key in (
            ("What worked", "what_worked"),
            ("What didn't", "what_didnt"),
            ("Timing notes", "timing_notes"),
            ("Risk notes", "risk_notes"),
            ("Tomorrow focus", "tomorrow_focus"),
        ):
            val = postmortem.get(key)
            if not val:
                continue
            lines.append(f"### {label}")
            if isinstance(val, list):
                for item in val:
                    lines.append(f"- {item}")
            else:
                lines.append(str(val))
            lines.append("")

    lines += [
        "---",
        "*Educational paper-trading research. Not investment advice.*",
    ]
    return "\n".join(lines)


def _heuristic_postmortem(summary: dict[str, Any]) -> dict[str, Any]:
    """Rule-based fallback when GenAI is unavailable."""
    what_worked: list[str] = []
    what_didnt: list[str] = []
    for row in summary.get("by_symbol") or []:
        sym = row["symbol"]
        pnl = row["pnl_inr"]
        if pnl > 0:
            what_worked.append(f"{sym}: ₹{pnl:+,.0f} across {row['closed_count']} close(s)")
        elif pnl < 0:
            what_didnt.append(f"{sym}: ₹{pnl:+,.0f} — review entry timing or stop width")
    reasons = summary.get("by_exit_reason") or {}
    timing_notes = ", ".join(f"{k}×{v}" for k, v in reasons.items()) or "No closed trades to analyze."
    win_rate = summary.get("win_rate_pct")
    pnl = float(summary.get("realized_pnl_inr") or 0)
    executive = (
        f"Session P&L ₹{pnl:+,.0f}"
        + (f", win rate {win_rate}%" if win_rate is not None else "")
        + f". {len(what_worked)} symbol(s) net positive, {len(what_didnt)} net negative."
    )
    tomorrow = []
    if what_didnt:
        tomorrow.append(f"Re-check timing gates on: {', '.join(r['symbol'] for r in summary.get('by_symbol', []) if r['pnl_inr'] < 0)}")
    if pnl > 0:
        tomorrow.append("Repeat high-conviction curated entries; respect profit cap.")
    else:
        tomorrow.append("Tighten entry composite threshold or reduce concurrent picks after loss day.")
    return {
        "executive_summary": executive,
        "what_worked": what_worked or ["No winning symbols — consider wider scan or stricter filters."],
        "what_didnt": what_didnt or ["No losing closed legs recorded."],
        "timing_notes": timing_notes,
        "risk_notes": f"Cycles run: {summary.get('cycle_count', 0)}. Buy notional ₹{summary.get('buy_notional_inr', 0):,.0f}.",
        "tomorrow_focus": tomorrow,
        "source": "heuristic",
    }


def generate_postmortem(summary: dict[str, Any], *, prior_lessons: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """GenAI post-mortem with heuristic fallback."""
    prior = prior_lessons or []
    prior_block = "\n".join(f"- {(l.get('text') or '')[:200]}" for l in prior[:6]) or "No prior RAG lessons."

    system = (
        "You are an intraday MIS autopilot coach for Indian equities. "
        "Return strict JSON only with keys: executive_summary (string), what_worked (string[]), "
        "what_didnt (string[]), timing_notes (string), risk_notes (string), tomorrow_focus (string[]). "
        "Be specific to the numbers provided. Educational only — not investment advice."
    )
    user = (
        f"SESSION SUMMARY:\n{json.dumps(summary, indent=2, default=str)[:8000]}\n\n"
        f"PRIOR RAG LESSONS:\n{prior_block}\n\n"
        "Analyze what worked, what failed, timing/exit patterns, and concrete focus for the next session."
    )
    try:
        from llm_providers import chat_completion, parse_llm_json

        result = chat_completion(system=system, user=user, temperature=0.15)
        parsed = parse_llm_json(result.text)
        if isinstance(parsed, dict) and parsed.get("executive_summary"):
            parsed["source"] = "genai"
            parsed["provider"] = result.provider
            parsed["model"] = result.model
            return parsed
    except Exception:
        pass
    return _heuristic_postmortem(summary)


def save_session_rag_digest(
    summary: dict[str, Any],
    postmortem: dict[str, Any],
    *,
    session_id: str,
) -> dict[str, Any]:
    """Persist one consolidated session lesson + per-symbol nuggets to Chroma."""
    from genai_research import append_insight

    trade_date = summary.get("trade_date_ist") or _today_ist()
    pnl = float(summary.get("realized_pnl_inr") or 0)
    stance = "win" if pnl >= 0 else "loss"

    digest_text = (
        f"Autopilot session {trade_date} ({session_id}): P&L ₹{pnl:+,.0f}, "
        f"win rate {summary.get('win_rate_pct')}% over {summary.get('closed_trades', 0)} closes. "
        f"{postmortem.get('executive_summary', '')} "
        f"Worked: {'; '.join((postmortem.get('what_worked') or [])[:4])}. "
        f"Improve: {'; '.join((postmortem.get('what_didnt') or [])[:4])}. "
        f"Tomorrow: {'; '.join((postmortem.get('tomorrow_focus') or [])[:3])}."
    )

    insight = {
        "stance": stance,
        "executive_summary": digest_text[:2000],
        "what_worked": postmortem.get("what_worked") or [],
        "what_didnt": postmortem.get("what_didnt") or [],
        "timing_notes": postmortem.get("timing_notes") or "",
        "risk_notes": postmortem.get("risk_notes") or "",
        "tomorrow_focus": postmortem.get("tomorrow_focus") or [],
        "session_summary": {
            k: summary.get(k)
            for k in (
                "realized_pnl_inr", "win_rate_pct", "closed_trades", "wins", "losses",
                "best_symbol", "worst_symbol", "by_exit_reason",
            )
        },
        "not_advice_disclaimer": "Session digest for autopilot learning — not investment advice.",
    }

    stored = append_insight(
        symbol=SESSION_RAG_SYMBOL,
        insight=insight,
        provider="autopilot_session",
        model=postmortem.get("model") or postmortem.get("source") or "session_report",
        as_of=summary.get("stopped_at") or _now(),
        kind="autopilot_session_digest",
        extra_metadata={
            "session_id": session_id,
            "trade_date_ist": trade_date,
            "realized_pnl_inr": str(round(pnl, 2)),
            "win_rate_pct": str(summary.get("win_rate_pct") or ""),
        },
    )

    symbol_rag_ids: list[dict[str, str]] = []
    for row in (summary.get("by_symbol") or [])[:8]:
        sym = row.get("symbol")
        if not sym:
            continue
        sym_insight = {
            "stance": "win" if float(row.get("pnl_inr") or 0) >= 0 else "loss",
            "executive_summary": (
                f"{sym} on {trade_date}: session net ₹{row.get('pnl_inr', 0):+,.0f} "
                f"({row.get('wins', 0)}W/{row.get('losses', 0)}L). "
                f"Session context: {digest_text[:400]}"
            ),
            "session_id": session_id,
            "trade_date_ist": trade_date,
        }
        sym_stored = append_insight(
            symbol=str(sym),
            insight=sym_insight,
            provider="autopilot_session",
            model="session_symbol_digest",
            as_of=summary.get("stopped_at") or _now(),
            kind="autopilot_session_symbol_digest",
            extra_metadata={"session_id": session_id, "trade_date_ist": trade_date},
        )
        symbol_rag_ids.append({"symbol": sym, "rag_id": sym_stored.get("id", "")})

    return {"session_rag_id": stored.get("id"), "symbol_rag_ids": symbol_rag_ids, "digest_preview": digest_text[:500]}


def build_and_save_session_report(
    session: dict[str, Any],
    completion_reason: str = "",
) -> dict[str, Any]:
    """Full EOD pipeline: summary → post-mortem → markdown → RAG → disk."""
    if completion_reason:
        session = {**session, "completion_reason": completion_reason}

    summary = build_session_summary(session)
    prior = retrieve_session_digests(symbols=summary.get("curated_symbols") or [], top_k=4)
    postmortem = generate_postmortem(summary, prior_lessons=prior)
    markdown = build_markdown_report(summary, postmortem)
    rag = save_session_rag_digest(summary, postmortem, session_id=str(summary.get("session_id") or ""))

    report = {
        "session_id": summary["session_id"],
        "generated_at": _now(),
        "trade_date_ist": summary.get("trade_date_ist"),
        "completion_reason": summary.get("completion_reason"),
        "summary": summary,
        "postmortem": postmortem,
        "markdown": markdown,
        "rag": rag,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    _report_path(summary["session_id"]).write_text(dumps_pretty(report), encoding="utf-8")
    return report


def finalize_session_report(session: dict[str, Any], reason: str = "", *, force: bool = False) -> Optional[dict[str, Any]]:
    """Generate EOD report once per session (idempotent unless force/stale)."""
    session_id = str(session.get("id") or "")
    if not session_id:
        return None

    existing = load_session_report(session_id)
    if existing and not force and not report_is_stale(session, existing):
        session["eod_report_generated"] = True
        return existing

    if session.get("eod_report_generated") and not force and not report_is_stale(session, existing):
        return existing

    report = build_and_save_session_report(session, completion_reason=reason or session.get("completion_reason") or "")
    session["eod_report_generated"] = True
    session["eod_report_at"] = report.get("generated_at")

    from trading.session_history import log_event

    log_event(
        session_id,
        event_type="eod_report",
        title=f"EOD report — P&L ₹{float(report['summary'].get('realized_pnl_inr') or 0):+,.0f}",
        detail={
            "win_rate_pct": report["summary"].get("win_rate_pct"),
            "closed_trades": report["summary"].get("closed_trades"),
            "best_symbol": report["summary"].get("best_symbol"),
            "worst_symbol": report["summary"].get("worst_symbol"),
            "rag_session_id": (report.get("rag") or {}).get("session_rag_id"),
            "postmortem_source": (report.get("postmortem") or {}).get("source"),
            "executive_summary": (report.get("postmortem") or {}).get("executive_summary", "")[:400],
            "regenerated": bool(force or report_is_stale(session, existing)),
        },
        level="complete",
    )
    return report


def _fmt_ist(iso: Optional[str]) -> Optional[str]:
    if not iso:
        return None
    try:
        from datetime import datetime as dt
        from datetime import timedelta, timezone

        parsed = dt.fromisoformat(str(iso).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone(timedelta(hours=5, minutes=30))).strftime("%d %b %Y, %H:%M IST")
    except Exception:
        return str(iso)[:19]


def _gross_pnl(summary: dict[str, Any]) -> tuple[float, float]:
    """Return (gross_profit_inr, gross_loss_inr as positive magnitude)."""
    closed = summary.get("closed_legs") or []
    profit = round(sum(float(c.get("pnl_inr") or 0) for c in closed if float(c.get("pnl_inr") or 0) > 0), 2)
    loss = round(abs(sum(float(c.get("pnl_inr") or 0) for c in closed if float(c.get("pnl_inr") or 0) < 0)), 2)
    return profit, loss


def list_session_report_cards(*, limit: int = 50) -> list[dict[str, Any]]:
    """Compact cards for session history UI — one row per past session."""
    from trading.session_autopilot import _hydrate_session, _load_store

    store = _load_store()
    cards: list[dict[str, Any]] = []
    for session in (store.get("sessions") or [])[:limit]:
        hydrated = _hydrate_session(dict(session))
        sid = str(hydrated.get("id") or "")
        if not sid:
            continue
        report = load_session_report(sid)
        summary = build_session_summary(hydrated)
        postmortem = (report or {}).get("postmortem") or {}
        gross_profit, gross_loss = _gross_pnl(summary)
        best = summary.get("best_symbol") or {}
        worst = summary.get("worst_symbol") or {}
        cards.append({
            "session_id": sid,
            "trade_date_ist": summary.get("trade_date_ist"),
            "pick_mode": summary.get("pick_mode"),
            "status": hydrated.get("status"),
            "completion_reason": summary.get("completion_reason") or hydrated.get("completion_reason"),
            "started_at": summary.get("started_at") or hydrated.get("started_at"),
            "stopped_at": summary.get("stopped_at") or hydrated.get("stopped_at") or hydrated.get("completed_at"),
            "started_at_ist": _fmt_ist(summary.get("started_at") or hydrated.get("started_at")),
            "stopped_at_ist": _fmt_ist(
                summary.get("stopped_at") or hydrated.get("stopped_at") or hydrated.get("completed_at")
            ),
            "realized_pnl_inr": float(summary.get("realized_pnl_inr") or 0),
            "gross_profit_inr": gross_profit,
            "gross_loss_inr": gross_loss,
            "buy_notional_inr": float(summary.get("buy_notional_inr") or 0),
            "closed_trades": int(summary.get("closed_trades") or 0),
            "wins": int(summary.get("wins") or 0),
            "losses": int(summary.get("losses") or 0),
            "win_rate_pct": summary.get("win_rate_pct"),
            "cycle_count": int(summary.get("cycle_count") or 0),
            "best_symbol": best.get("symbol"),
            "best_pnl_inr": best.get("pnl_inr"),
            "worst_symbol": worst.get("symbol"),
            "worst_pnl_inr": worst.get("pnl_inr"),
            "curated_symbols": list(summary.get("curated_symbols") or []),
            "has_report": bool(report),
            "report_generated_at": (report or {}).get("generated_at"),
            "postmortem_preview": (postmortem.get("executive_summary") or "")[:280],
            "lessons_preview": (postmortem.get("tomorrow_focus") or [])[:3],
        })
    return cards


def build_session_report_pdf(session_id: str) -> bytes:
    """PDF bytes for a session EOD report."""
    from remaining_desk import build_pdf_bytes
    from trading.session_autopilot import _find_session, _hydrate_session, _load_store

    store = _load_store()
    session = _find_session(store, session_id)
    if not session:
        raise ValueError("Session not found.")
    hydrated = _hydrate_session(session)
    report = load_session_report(session_id)
    if not report or report_is_stale(hydrated, report):
        report = build_and_save_session_report(hydrated, completion_reason=hydrated.get("completion_reason") or "pdf_export")
    summary = report.get("summary") or build_session_summary(hydrated)
    postmortem = report.get("postmortem") or _heuristic_postmortem(summary)
    gross_profit, gross_loss = _gross_pnl(summary)
    pnl = float(summary.get("realized_pnl_inr") or 0)

    sections: list[dict[str, Any]] = [
        {
            "heading": "Session overview",
            "body": [
                f"Session ID: {session_id}",
                f"Trade date: {summary.get('trade_date_ist')}",
                f"Mode: {summary.get('pick_mode')}",
                f"Time: {_fmt_ist(summary.get('started_at'))} → {_fmt_ist(summary.get('stopped_at'))}",
                f"Status: {summary.get('completion_reason') or hydrated.get('status')}",
            ],
        },
        {
            "heading": "P&L highlights",
            "body": [
                f"Net realized P&L: ₹{pnl:+,.0f}",
                f"Gross profit: ₹{gross_profit:,.0f} · Gross loss: ₹{gross_loss:,.0f}",
                f"Buy notional deployed: ₹{float(summary.get('buy_notional_inr') or 0):,.0f}",
                f"Closed trades: {summary.get('closed_trades', 0)} ({summary.get('wins', 0)}W / {summary.get('losses', 0)}L)",
                f"Win rate: {summary.get('win_rate_pct') if summary.get('win_rate_pct') is not None else '—'}%",
                f"Scheduler cycles: {summary.get('cycle_count', 0)}",
            ],
        },
    ]
    if summary.get("best_symbol"):
        sections.append({
            "heading": "Best / worst symbol",
            "body": [
                f"Best: {summary['best_symbol'].get('symbol')} ₹{float(summary['best_symbol'].get('pnl_inr') or 0):+,.0f}",
                f"Worst: {(summary.get('worst_symbol') or {}).get('symbol', '—')} "
                f"₹{float((summary.get('worst_symbol') or {}).get('pnl_inr') or 0):+,.0f}",
            ],
        })
    if postmortem.get("executive_summary"):
        sections.append({"heading": "Executive summary", "body": postmortem["executive_summary"]})
    for label, key in (
        ("What worked", "what_worked"),
        ("What didn't", "what_didnt"),
        ("Course corrections", "tomorrow_focus"),
        ("Timing notes", "timing_notes"),
        ("Risk notes", "risk_notes"),
    ):
        val = postmortem.get(key)
        if not val:
            continue
        sections.append({"heading": label, "body": val if isinstance(val, list) else str(val)})

    title = f"Autopilot Session {summary.get('trade_date_ist') or session_id}"
    return build_pdf_bytes(title, sections)
