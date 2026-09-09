"""Personal Advisor: track holdings and flag educational exit / review actions."""
from __future__ import annotations

import json
import re
from typing import Any, Callable, Optional

from config import LLM_MODEL, OLLAMA_KEEP_ALIVE, TOP_K
from rag import ollama_client, retrieve


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"summary": text, "actions": []}
        return json.loads(match.group())


def _pct(new: Optional[float], old: Optional[float]) -> Optional[float]:
    if new is None or old is None or old == 0:
        return None
    return round((new / old - 1) * 100, 2)


def _holding_pnl(holding: dict[str, Any], live: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    qty = holding.get("quantity")
    avg = holding.get("avg_cost")
    invested = holding.get("invested_value")
    current_value = holding.get("current_value")
    current_price = holding.get("current_price")

    if live:
        current_price = live.get("price") or current_price
        if qty and current_price is not None:
            current_value = qty * current_price
        elif live.get("market_value") is not None:
            current_value = live.get("market_value")

    if invested is None and qty is not None and avg is not None:
        invested = qty * avg
    if current_value is None and qty is not None and current_price is not None:
        current_value = qty * current_price

    pnl = None
    pnl_pct = None
    if invested is not None and current_value is not None:
        pnl = round(current_value - invested, 2)
        pnl_pct = _pct(current_value, invested)

    return {
        **holding,
        "invested_value": round(invested, 2) if invested is not None else None,
        "current_value": round(current_value, 2) if current_value is not None else None,
        "current_price": round(current_price, 4) if current_price is not None else None,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "live": live or {},
    }


def deterministic_exit_signal(enriched: dict[str, Any], risk_tolerance: str = "moderate") -> dict[str, Any]:
    """Rule-based educational signals — not trade instructions."""
    reasons: list[str] = []
    urgency = "watch"
    action = "hold_review"

    pnl_pct = enriched.get("pnl_pct")
    live = enriched.get("live") or {}
    vs_sma_50 = live.get("price_vs_sma_50_pct")
    vs_sma_200 = live.get("price_vs_sma_200_pct")
    from_high = live.get("distance_from_52_week_high_pct")
    one_month = live.get("one_month_pct")

    take_profit = 25 if risk_tolerance == "conservative" else (40 if risk_tolerance == "moderate" else 60)
    stop_loss = -12 if risk_tolerance == "conservative" else (-18 if risk_tolerance == "moderate" else -25)

    if pnl_pct is not None and pnl_pct >= take_profit:
        urgency = "review_exit"
        action = "consider_partial_exit"
        reasons.append(f"Unrealized gain {pnl_pct}% is above the {risk_tolerance} take-profit review level ({take_profit}%).")
    if pnl_pct is not None and pnl_pct <= stop_loss:
        urgency = "review_exit"
        action = "consider_exit_review"
        reasons.append(f"Unrealized loss {pnl_pct}% is beyond the {risk_tolerance} loss-review level ({stop_loss}%).")

    if isinstance(vs_sma_50, (int, float)) and isinstance(vs_sma_200, (int, float)):
        if vs_sma_50 < -5 and vs_sma_200 < -8:
            urgency = "review_exit" if urgency != "review_exit" else urgency
            action = "consider_exit_review"
            reasons.append("Price is meaningfully below both the 50-day and 200-day averages.")
        elif vs_sma_50 > 0 and vs_sma_200 > 0 and action == "hold_review":
            reasons.append("Price remains above both major moving averages (momentum still intact).")

    if isinstance(from_high, (int, float)) and from_high <= -20:
        reasons.append(f"About {abs(from_high)}% below the 52-week high — review thesis and risk.")
        if urgency == "watch":
            urgency = "attention"

    if isinstance(one_month, (int, float)) and one_month <= -10:
        reasons.append(f"1-month return is {one_month}%.")
        if urgency == "watch":
            urgency = "attention"

    if not reasons:
        reasons.append("No strong rule-based exit flag from supplied P&L / trend inputs; keep on watchlist.")

    return {
        "urgency": urgency,
        "action": action,
        "reasons": reasons,
    }


def enrich_holding(
    holding: dict[str, Any],
    *,
    load_market: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    """Attach live market snapshot for stocks when a symbol is present."""
    live = None
    symbol = holding.get("symbol")
    if holding.get("asset_type") == "stock" and symbol:
        try:
            live = load_market(symbol)
        except Exception as exc:
            live = {"error": str(exc)}
    elif holding.get("asset_type") == "mutual_fund":
        live = {
            "note": "Mutual-fund live NAV is taken from the ingested current_price/current_value when provided.",
            "price": holding.get("current_price"),
        }
    return _holding_pnl(holding, live)


def advise_portfolio(
    profile: dict[str, Any],
    *,
    load_market: Callable[[str], dict[str, Any]],
    with_ai: bool = True,
) -> dict[str, Any]:
    holdings = profile.get("holdings") or []
    risk = profile.get("risk_tolerance") or "moderate"
    enriched = [enrich_holding(item, load_market=load_market) for item in holdings]
    for item in enriched:
        item["signal"] = deterministic_exit_signal(item, risk)

    ranked = sorted(
        enriched,
        key=lambda h: {"review_exit": 0, "attention": 1, "watch": 2}.get((h.get("signal") or {}).get("urgency"), 9),
    )

    totals = {
        "invested_value": round(sum(h["invested_value"] or 0 for h in enriched), 2),
        "current_value": round(sum(h["current_value"] or 0 for h in enriched), 2),
    }
    totals["pnl"] = round(totals["current_value"] - totals["invested_value"], 2) if enriched else 0
    totals["pnl_pct"] = _pct(totals["current_value"], totals["invested_value"]) if totals["invested_value"] else None

    ai = None
    if with_ai and enriched:
        ai = _ai_portfolio_coach(profile, ranked, totals)

    return {
        "profile_id": profile.get("id"),
        "email": profile.get("email"),
        "name": profile.get("name"),
        "risk_tolerance": risk,
        "totals": totals,
        "holdings": ranked,
        "exit_candidates": [
            h for h in ranked if (h.get("signal") or {}).get("urgency") in {"review_exit", "attention"}
        ],
        "ai": ai,
        "disclaimer": (
            "Educational personal-advisor screen only. Not personalized investment advice, "
            "not a brokerage order, and not a guarantee that it is time to exit."
        ),
    }


def _ai_portfolio_coach(profile: dict[str, Any], holdings: list[dict[str, Any]], totals: dict[str, Any]) -> dict[str, Any]:
    compact = [
        {
            "asset_type": h.get("asset_type"),
            "symbol": h.get("symbol"),
            "name": h.get("name"),
            "pnl_pct": h.get("pnl_pct"),
            "signal": h.get("signal"),
            "live": {
                "price_vs_sma_50_pct": (h.get("live") or {}).get("price_vs_sma_50_pct"),
                "price_vs_sma_200_pct": (h.get("live") or {}).get("price_vs_sma_200_pct"),
                "one_month_pct": (h.get("live") or {}).get("one_month_pct"),
                "distance_from_52_week_high_pct": (h.get("live") or {}).get("distance_from_52_week_high_pct"),
            },
        }
        for h in holdings
    ]
    query = (
        "Portfolio risk management, when to book profits, and when to cut losses for "
        f"{profile.get('risk_tolerance')} investors: "
        + json.dumps({"totals": totals, "count": len(holdings)}, separators=(",", ":"))
    )
    try:
        sources = retrieve(query, min(TOP_K, 4))
    except Exception:
        sources = []
    context = "\n\n".join(
        f"[Source {i}: {item['source']}, page {item['page']}]\n{item['text']}"
        for i, item in enumerate(sources, start=1)
    ) or "No book passages retrieved."

    schema = {
        "headline": "one-line portfolio status",
        "summary": "2-4 sentences on overall posture",
        "priority_exits": [
            {"symbol_or_name": "", "why": "why this name deserves an exit review now", "suggested_stance": "trim | exit_review | hold"}
        ],
        "keep_watching": ["names that can stay on watch"],
        "process_tips": ["book-grounded process tips"],
        "risk_note": "Educational only; not investment advice.",
    }
    response = ollama_client().chat(
        model=LLM_MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an educational personal portfolio advisor. Use only supplied holdings, "
                    "signals, and book passages. Never invent prices. Prefer 'exit review' language "
                    "over hard sell orders. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"PROFILE: {profile.get('name')} · risk={profile.get('risk_tolerance')} · email={profile.get('email')}\n"
                    f"TOTALS: {json.dumps(totals)}\n"
                    f"HOLDINGS + SIGNALS:\n{json.dumps(compact, indent=2)}\n\n"
                    f"RETRIEVED BOOK PASSAGES:\n{context}\n\n"
                    f"Return JSON matching:\n{json.dumps(schema, indent=2)}"
                ),
            },
        ],
        format="json",
        options={"temperature": 0.2, "num_ctx": 8192},
        keep_alive=OLLAMA_KEEP_ALIVE,
    )
    ai = _parse_json(response["message"]["content"])
    ai["retrieved_sources"] = [
        {k: item[k] for k in ("source", "page", "chunk", "distance")} for item in sources
    ]
    return ai


def market_snapshot_from_analysis_input(stock: dict[str, Any]) -> dict[str, Any]:
    """Map analyzer input into the compact live block used by exit rules."""
    performance = stock.get("price_performance") or {}
    return {
        "price": stock.get("price"),
        "one_month_pct": performance.get("one_month_pct"),
        "six_month_pct": performance.get("six_month_pct"),
        "one_year_pct": performance.get("one_year_pct"),
        "price_vs_sma_50_pct": performance.get("price_vs_sma_50_pct"),
        "price_vs_sma_200_pct": performance.get("price_vs_sma_200_pct"),
        "distance_from_52_week_high_pct": performance.get("distance_from_52_week_high_pct"),
        "annualized_volatility_30d_pct": performance.get("annualized_volatility_30d_pct"),
        "data_as_of": stock.get("data_as_of"),
    }
