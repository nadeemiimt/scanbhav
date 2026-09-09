"""Head-to-head stock comparison with deterministic metrics + RAG-backed GenAI verdict."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from config import LLM_MODEL, OLLAMA_KEEP_ALIVE, TOP_K
from rag import ollama_client, retrieve


SYSTEM_PROMPT = """You are an educational stock-comparison assistant. Compare only the two supplied stock snapshots and the retrieved book passages. Never invent prices, financials, news, or citations. This is not personalized financial advice. Return valid JSON only.

Rules:
- Pick a winner only when the supplied evidence clearly favors one side; otherwise use "tie" or "insufficient_data".
- Every claim must reference a supplied number or a retrieved source number.
- Prefer risk-adjusted quality (margins, debt, cash flow, valuation vs peers, momentum) over raw market-cap or one-week price moves.
- Be explicit when one side is missing critical data."""


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {
                "winner": "unable_to_parse",
                "summary": text,
                "scorecard": [],
                "recommendation": "insufficient_data",
            }
        return json.loads(match.group())


def _metric_side(stock: dict[str, Any]) -> dict[str, Any]:
    financials = stock.get("financials") or {}
    valuation = stock.get("valuation") or {}
    performance = stock.get("price_performance") or {}
    return {
        "ticker": stock.get("ticker"),
        "company_name": stock.get("company_name"),
        "sector": stock.get("sector"),
        "industry": stock.get("industry"),
        "price": stock.get("price"),
        "market_cap": stock.get("market_cap"),
        "pe_ratio": valuation.get("pe_ratio"),
        "forward_pe": valuation.get("forward_pe_ratio"),
        "peg_ratio": valuation.get("peg_ratio"),
        "price_to_book": valuation.get("price_to_book"),
        "dividend_yield_pct": valuation.get("dividend_yield_pct"),
        "revenue_growth_yoy_pct": financials.get("revenue_growth_yoy_pct"),
        "net_margin_pct": financials.get("net_margin_pct"),
        "operating_margin_pct": financials.get("operating_margin_pct"),
        "roe_pct": financials.get("roe_pct"),
        "debt_to_equity": financials.get("debt_to_equity"),
        "current_ratio": financials.get("current_ratio"),
        "free_cash_flow": financials.get("free_cash_flow"),
        "one_month_pct": performance.get("one_month_pct"),
        "six_month_pct": performance.get("six_month_pct"),
        "one_year_pct": performance.get("one_year_pct"),
        "volatility_30d_pct": performance.get("annualized_volatility_30d_pct"),
        "price_vs_sma_50_pct": performance.get("price_vs_sma_50_pct"),
        "price_vs_sma_200_pct": performance.get("price_vs_sma_200_pct"),
        "beta": performance.get("beta"),
        "peer_count": len(stock.get("peers") or []),
        "news_count": len(stock.get("recent_news") or []),
    }


def _better(a: Optional[float], b: Optional[float], higher_is_better: bool = True) -> str:
    if a is None and b is None:
        return "tie"
    if a is None:
        return "b"
    if b is None:
        return "a"
    if a == b:
        return "tie"
    if higher_is_better:
        return "a" if a > b else "b"
    return "a" if a < b else "b"


def deterministic_scorecard(left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, Any]]:
    """Transparent numeric comparison so the UI is useful even before the LLM finishes."""
    a, b = _metric_side(left), _metric_side(right)
    rows = [
        ("Trailing P/E", a["pe_ratio"], b["pe_ratio"], False, "Lower multiple is cheaper if earnings quality is similar."),
        ("Forward P/E", a["forward_pe"], b["forward_pe"], False, "Lower forward multiple suggests cheaper expected earnings."),
        ("PEG ratio", a["peg_ratio"], b["peg_ratio"], False, "Lower PEG is usually more attractive growth-adjusted valuation."),
        ("Price / Book", a["price_to_book"], b["price_to_book"], False, "Lower P/B can signal cheaper book valuation."),
        ("Dividend yield %", a["dividend_yield_pct"], b["dividend_yield_pct"], True, "Higher yield means more cash returned, if sustainable."),
        ("Revenue growth YoY %", a["revenue_growth_yoy_pct"], b["revenue_growth_yoy_pct"], True, "Faster top-line growth."),
        ("Net margin %", a["net_margin_pct"], b["net_margin_pct"], True, "Higher profitability per revenue rupee."),
        ("Operating margin %", a["operating_margin_pct"], b["operating_margin_pct"], True, "Core operating efficiency."),
        ("ROE %", a["roe_pct"], b["roe_pct"], True, "Capital efficiency for shareholders."),
        ("Debt / Equity", a["debt_to_equity"], b["debt_to_equity"], False, "Lower leverage is generally safer."),
        ("Current ratio", a["current_ratio"], b["current_ratio"], True, "Short-term liquidity cushion."),
        ("1-month return %", a["one_month_pct"], b["one_month_pct"], True, "Recent price momentum."),
        ("1-year return %", a["one_year_pct"], b["one_year_pct"], True, "Longer-horizon price performance."),
        ("30d annualized vol %", a["volatility_30d_pct"], b["volatility_30d_pct"], False, "Lower volatility is usually less risky."),
    ]
    scorecard = []
    for label, left_v, right_v, higher, note in rows:
        winner = _better(left_v, right_v, higher_is_better=higher)
        scorecard.append({
            "metric": label,
            "left": left_v,
            "right": right_v,
            "edge": winner,
            "note": note,
        })
    return scorecard


def scorecard_only(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """Numeric comparison without calling the LLM — useful for fast UI previews."""
    if not left.get("ticker") or not right.get("ticker"):
        raise ValueError("Both stocks must include a ticker.")
    if left["ticker"].upper() == right["ticker"].upper():
        raise ValueError("Choose two different symbols to compare.")
    scorecard = deterministic_scorecard(left, right)
    left_wins = sum(1 for row in scorecard if row["edge"] == "a")
    right_wins = sum(1 for row in scorecard if row["edge"] == "b")
    return {
        "left": _metric_side(left),
        "right": _metric_side(right),
        "scorecard": scorecard,
        "tally": {
            "left_metric_wins": left_wins,
            "right_metric_wins": right_wins,
            "ties_or_missing": len(scorecard) - left_wins - right_wins,
        },
        "ai": None,
    }


def compare_stocks(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if not left.get("ticker") or not right.get("ticker"):
        raise ValueError("Both stocks must include a ticker.")
    if left["ticker"].upper() == right["ticker"].upper():
        raise ValueError("Choose two different symbols to compare.")

    base = scorecard_only(left, right)
    scorecard = base["scorecard"]

    query = (
        "Investment framework for comparing two companies on valuation, quality, "
        "momentum, leverage, and risk: "
        + json.dumps({"left": _metric_side(left), "right": _metric_side(right)}, separators=(",", ":"))
    )
    sources = retrieve(query, TOP_K)
    context = "\n\n".join(
        f"[Source {i}: {item['source']}, page {item['page']}, chunk {item['chunk']}]\n{item['text']}"
        for i, item in enumerate(sources, start=1)
    )
    schema = {
        "winner": "left | right | tie | insufficient_data",
        "confidence": "low | medium | high",
        "summary": "2-4 sentence evidence-based comparison",
        "left_advantages": ["advantages for the first stock"],
        "right_advantages": ["advantages for the second stock"],
        "key_tradeoffs": ["honest tradeoffs between the two"],
        "framework_checks": [
            {"criterion": "", "favors": "left | right | tie | unknown", "evidence": "", "source_refs": ["Source 1"]}
        ],
        "who_should_prefer_left": "investor profile that might prefer left",
        "who_should_prefer_right": "investor profile that might prefer right",
        "risk_note": "Educational comparison only; not investment advice.",
    }
    user_prompt = f"""STOCK A (left):\n{json.dumps(left, indent=2)}\n\nSTOCK B (right):\n{json.dumps(right, indent=2)}\n\nDETERMINISTIC SCORECARD (edge a=left, b=right):\n{json.dumps(scorecard, indent=2)}\n\nRETRIEVED BOOK PASSAGES:\n{context}\n\nReturn JSON matching exactly this shape:\n{json.dumps(schema, indent=2)}\nOnly cite Source numbers that appear above."""

    response = ollama_client().chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        format="json",
        options={"temperature": 0.2, "num_ctx": 8192},
        keep_alive=OLLAMA_KEEP_ALIVE,
    )
    ai = _parse_json(response["message"]["content"])
    ai["retrieved_sources"] = [
        {k: item[k] for k in ("source", "page", "chunk", "distance")} for item in sources
    ]
    return {**base, "ai": ai}
