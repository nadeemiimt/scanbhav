"""Two-week paper-trading simulator using locally saved daily candles.

Simulates buying at the open/close of a session ~2 weeks ago and holding
through the latest available session, including optional AI commentary grounded
in retrieved investment-framework passages. Educational only — not a broker
backtest with fees/slippage guarantees.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from config import LLM_MODEL, OLLAMA_KEEP_ALIVE, TOP_K
from rag import ollama_client, retrieve

# ~2 calendar weeks of Indian/US market sessions (Mon–Fri).
DEFAULT_TRADING_DAYS = 10
ASSUMED_FEE_BPS = 10  # 0.10% round-trip fee assumption for educational realism


def _close(row: dict[str, Any]) -> float:
    return float(row.get("5. adjusted close") or row.get("4. close") or 0)


def _open(row: dict[str, Any]) -> float:
    return float(row.get("1. open") or _close(row) or 0)


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"lesson": text, "would_repeat": "unknown"}
        return json.loads(match.group())


def simulate_hold(
    symbol: str,
    rows: list[dict[str, Any]],
    *,
    capital: float = 100_000.0,
    trading_days: int = DEFAULT_TRADING_DAYS,
    entry: str = "close",
) -> dict[str, Any]:
    """Buy `trading_days` sessions ago and hold to the latest close."""
    if trading_days < 2:
        raise ValueError("Paper trade needs at least 2 trading days.")
    cleaned = [row for row in rows if _close(row) > 0]
    if len(cleaned) < trading_days + 1:
        raise ValueError(
            f"Need at least {trading_days + 1} daily candles for a {trading_days}-session paper trade; "
            f"only {len(cleaned)} available for {symbol}."
        )

    window = cleaned[-(trading_days + 1):]
    entry_row = window[0]
    exit_row = window[-1]
    entry_price = _open(entry_row) if entry == "open" else _close(entry_row)
    if entry_price <= 0:
        raise ValueError(f"Invalid entry price for {symbol}.")

    fee_frac = ASSUMED_FEE_BPS / 10_000
    spendable = capital * (1 - fee_frac / 2)
    shares = spendable / entry_price
    equity_curve = []
    for row in window:
        mark = _close(row)
        market_value = shares * mark
        # Exit fee only applied on the final day for realized P&L clarity.
        fee_drag = market_value * (fee_frac / 2) if row is exit_row else 0.0
        equity = market_value - fee_drag
        pnl = equity - capital
        equity_curve.append({
            "date": row["date"],
            "close": round(mark, 4),
            "equity": round(equity, 2),
            "pnl": round(pnl, 2),
            "pnl_pct": round((equity / capital - 1) * 100, 3),
        })

    exit_price = _close(exit_row)
    final = equity_curve[-1]
    peak = max(point["equity"] for point in equity_curve)
    trough = min(point["equity"] for point in equity_curve)
    max_drawdown_pct = round((trough / peak - 1) * 100, 3) if peak else 0.0
    daily_returns = [
        (equity_curve[i]["equity"] / equity_curve[i - 1]["equity"] - 1) * 100
        for i in range(1, len(equity_curve))
        if equity_curve[i - 1]["equity"]
    ]
    best_day = max(daily_returns) if daily_returns else 0.0
    worst_day = min(daily_returns) if daily_returns else 0.0

    return {
        "symbol": symbol.upper(),
        "capital": capital,
        "trading_days": trading_days,
        "entry_style": entry,
        "entry_date": entry_row["date"],
        "exit_date": exit_row["date"],
        "entry_price": round(entry_price, 4),
        "exit_price": round(exit_price, 4),
        "shares": round(shares, 6),
        "fee_bps_assumed": ASSUMED_FEE_BPS,
        "final_equity": final["equity"],
        "pnl": final["pnl"],
        "pnl_pct": final["pnl_pct"],
        "max_drawdown_pct": max_drawdown_pct,
        "best_day_pct": round(best_day, 3),
        "worst_day_pct": round(worst_day, 3),
        "outcome": "gain" if final["pnl"] > 0 else ("loss" if final["pnl"] < 0 else "flat"),
        "equity_curve": equity_curve,
    }


def ai_paper_lesson(simulation: dict[str, Any], stock_context: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """RAG-grounded lesson on what the 2-week hold teaches about risk/process."""
    query = (
        "Swing trading risk management, position sizing, and reviewing a short hold: "
        + json.dumps({
            "pnl_pct": simulation.get("pnl_pct"),
            "max_drawdown_pct": simulation.get("max_drawdown_pct"),
            "trading_days": simulation.get("trading_days"),
            "outcome": simulation.get("outcome"),
        }, separators=(",", ":"))
    )
    sources = retrieve(query, min(TOP_K, 4))
    context = "\n\n".join(
        f"[Source {i}: {item['source']}, page {item['page']}]\n{item['text']}"
        for i, item in enumerate(sources, start=1)
    )
    schema = {
        "headline": "one-line lesson title",
        "lesson": "2-3 sentences on what this paper trade illustrates",
        "process_tips": ["actionable process tips grounded in the books"],
        "would_repeat": "yes | no | depends",
        "risk_note": "Educational simulation only; past paper P&L is not a forecast.",
    }
    stock_blob = json.dumps(stock_context or {}, indent=2)[:2500]
    user_prompt = f"""PAPER TRADE RESULT:\n{json.dumps(simulation, indent=2)}\n\nOPTIONAL STOCK CONTEXT:\n{stock_blob}\n\nRETRIEVED BOOK PASSAGES:\n{context}\n\nReturn JSON matching:\n{json.dumps(schema, indent=2)}\nCite only Source numbers above. Do not invent prices."""

    response = ollama_client().chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an educational trading coach. Explain what a completed paper trade "
                    "teaches about process and risk using only the supplied simulation and book "
                    "passages. Never invent market data. Not investment advice. Return JSON only."
                ),
            },
            {"role": "user", "content": user_prompt},
        ],
        format="json",
        options={"temperature": 0.25, "num_ctx": 4096},
        keep_alive=OLLAMA_KEEP_ALIVE,
    )
    lesson = _parse_json(response["message"]["content"])
    lesson["retrieved_sources"] = [
        {k: item[k] for k in ("source", "page", "chunk", "distance")} for item in sources
    ]
    return lesson


def compare_paper_trades(sims: list[dict[str, Any]]) -> dict[str, Any]:
    """Rank multiple paper-trade simulations by final P&L %."""
    if not sims:
        raise ValueError("At least one simulation is required.")
    ranked = sorted(sims, key=lambda s: s.get("pnl_pct") or 0, reverse=True)
    winner = ranked[0]
    return {
        "winner_symbol": winner["symbol"],
        "winner_pnl_pct": winner["pnl_pct"],
        "spread_pct": round((ranked[0]["pnl_pct"] or 0) - (ranked[-1]["pnl_pct"] or 0), 3),
        "ranked": [
            {
                "symbol": s["symbol"],
                "pnl": s["pnl"],
                "pnl_pct": s["pnl_pct"],
                "max_drawdown_pct": s["max_drawdown_pct"],
                "outcome": s["outcome"],
            }
            for s in ranked
        ],
    }
