"""Multi-agent research pipeline: specialist agents + synthesizer, all RAG-grounded.

Each agent retrieves its own book passages for a focused lens (fundamentals,
technicals, risk), then a chief synthesizer merges their findings. Educational
only — not personalized investment advice.
"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

from config import LLM_MODEL, OLLAMA_KEEP_ALIVE, TOP_K
from rag import ollama_client, retrieve


def _parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"findings": [], "stance": "unknown", "notes": text}
        return json.loads(match.group())


def _chat(system: str, user: str) -> dict[str, Any]:
    response = ollama_client().chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        format="json",
        options={"temperature": 0.2, "num_ctx": 4096},
        keep_alive=OLLAMA_KEEP_ALIVE,
    )
    return _parse_json(response["message"]["content"])


def _run_agent(
    *,
    name: str,
    role: str,
    query_builder: Callable[[dict[str, Any]], str],
    stock: dict[str, Any],
    schema: dict[str, Any],
) -> dict[str, Any]:
    query = query_builder(stock)
    sources = retrieve(query, min(TOP_K, 4))
    context = "\n\n".join(
        f"[Source {i}: {item['source']}, page {item['page']}]\n{item['text']}"
        for i, item in enumerate(sources, start=1)
    )
    system = (
        f"You are the {role} on an educational multi-agent research desk. "
        "Use only the supplied stock JSON and retrieved book passages. "
        "Never invent numbers or citations. Not investment advice. Return JSON only."
    )
    user = (
        f"STOCK INPUT:\n{json.dumps(stock, indent=2)}\n\n"
        f"RETRIEVED BOOK PASSAGES:\n{context}\n\n"
        f"Return JSON matching:\n{json.dumps(schema, indent=2)}\n"
        "Only cite Source numbers that appear above."
    )
    output = _chat(system, user)
    return {
        "agent": name,
        "role": role,
        "output": output,
        "retrieved_sources": [
            {k: item[k] for k in ("source", "page", "chunk", "distance")} for item in sources
        ],
    }


def fundamental_agent(stock: dict[str, Any]) -> dict[str, Any]:
    return _run_agent(
        name="fundamental",
        role="Fundamental Quality Analyst",
        query_builder=lambda s: (
            "Fundamental quality framework: margins, growth, cash flow, debt, ROE for "
            f"{s.get('sector')} / {s.get('industry')}: "
            + json.dumps(s.get("financials") or {}, separators=(",", ":"))
        ),
        stock=stock,
        schema={
            "stance": "constructive | cautious | negative | insufficient_data",
            "findings": ["evidence-based findings"],
            "quality_score": "1-5 integer as string",
            "missing_data": ["missing fundamental items"],
            "source_refs": ["Source 1"],
        },
    )


def technical_agent(stock: dict[str, Any]) -> dict[str, Any]:
    return _run_agent(
        name="technical",
        role="Technical / Momentum Analyst",
        query_builder=lambda s: (
            "Technical and momentum framework using moving averages, trend, and volatility: "
            + json.dumps(s.get("price_performance") or {}, separators=(",", ":"))
        ),
        stock=stock,
        schema={
            "stance": "bullish | neutral | bearish | insufficient_data",
            "trend": "uptrend | downtrend | sideways | unknown",
            "findings": ["evidence-based findings"],
            "momentum_score": "1-5 integer as string",
            "source_refs": ["Source 1"],
        },
    )


def risk_agent(stock: dict[str, Any]) -> dict[str, Any]:
    return _run_agent(
        name="risk",
        role="Risk & Valuation Officer",
        query_builder=lambda s: (
            "Risk management and valuation discipline for equity research: "
            + json.dumps({
                "valuation": s.get("valuation") or {},
                "volatility": (s.get("price_performance") or {}).get("annualized_volatility_30d_pct"),
                "beta": (s.get("price_performance") or {}).get("beta"),
                "debt_to_equity": (s.get("financials") or {}).get("debt_to_equity"),
                "peers": len(s.get("peers") or []),
            }, separators=(",", ":"))
        ),
        stock=stock,
        schema={
            "stance": "acceptable | elevated | high | insufficient_data",
            "findings": ["evidence-based risk findings"],
            "risk_score": "1-5 integer as string where 5 is safest",
            "valuation_view": "cheap | fair | expensive | unknown",
            "source_refs": ["Source 1"],
        },
    )


def synthesize(stock: dict[str, Any], agent_reports: list[dict[str, Any]]) -> dict[str, Any]:
    compact = [
        {
            "agent": report["agent"],
            "role": report["role"],
            "output": report["output"],
        }
        for report in agent_reports
    ]
    schema = {
        "verdict": "accumulate | watchlist | avoid | insufficient_data",
        "confidence": "low | medium | high",
        "summary": "chief-analyst synthesis in 3 sentences",
        "agreements": ["where agents agree"],
        "disagreements": ["where agents conflict"],
        "action_plan": ["next educational research steps"],
        "one_liner": "single sentence board-ready takeaway",
        "risk_note": "Educational multi-agent research only; not investment advice.",
    }
    system = (
        "You are the Chief Investment Research Synthesizer. Merge specialist agent "
        "reports without inventing data. Prefer caution when agents disagree or data "
        "is missing. Not investment advice. Return JSON only."
    )
    user = (
        f"TICKER: {stock.get('ticker')}\nCOMPANY: {stock.get('company_name')}\n\n"
        f"AGENT REPORTS:\n{json.dumps(compact, indent=2)}\n\n"
        f"Return JSON matching:\n{json.dumps(schema, indent=2)}"
    )
    return _chat(system, user)


def run_research_desk(stock: dict[str, Any]) -> dict[str, Any]:
    if not stock.get("ticker"):
        raise ValueError("Input must include a ticker.")
    agents = [fundamental_agent, technical_agent, risk_agent]
    reports = [agent(stock) for agent in agents]
    synthesis = synthesize(stock, reports)
    return {
        "ticker": stock.get("ticker"),
        "company_name": stock.get("company_name"),
        "agents": reports,
        "synthesis": synthesis,
    }


def ask_rag(question: str, stock: dict[str, Any] | None = None) -> dict[str, Any]:
    """Conversational RAG: answer a free-form research question with book retrieval."""
    cleaned = (question or "").strip()
    if len(cleaned) < 5:
        raise ValueError("Ask a more specific research question (at least 5 characters).")

    stock_hint = ""
    if stock:
        stock_hint = json.dumps({
            "ticker": stock.get("ticker"),
            "company_name": stock.get("company_name"),
            "sector": stock.get("sector"),
            "financials": stock.get("financials"),
            "valuation": stock.get("valuation"),
            "price_performance": stock.get("price_performance"),
        }, separators=(",", ":"))
    query = f"Investment research question: {cleaned}. Context: {stock_hint}"
    sources = retrieve(query, TOP_K)
    context = "\n\n".join(
        f"[Source {i}: {item['source']}, page {item['page']}, chunk {item['chunk']}]\n{item['text']}"
        for i, item in enumerate(sources, start=1)
    )
    schema = {
        "answer": "clear educational answer",
        "bullets": ["key points"],
        "caveats": ["what is unknown or unverified"],
        "source_refs": ["Source 1"],
        "risk_note": "Educational answer only; not investment advice.",
    }
    system = (
        "You are a local RAG research assistant for educational equity analysis. "
        "Answer using retrieved book passages and optional stock JSON only. "
        "Never invent figures or citations. Return JSON only."
    )
    user = (
        f"QUESTION:\n{cleaned}\n\n"
        f"OPTIONAL STOCK JSON:\n{json.dumps(stock or {}, indent=2)[:4000]}\n\n"
        f"RETRIEVED BOOK PASSAGES:\n{context}\n\n"
        f"Return JSON matching:\n{json.dumps(schema, indent=2)}"
    )
    output = _chat(system, user)
    output["retrieved_sources"] = [
        {k: item[k] for k in ("source", "page", "chunk", "distance")} for item in sources
    ]
    output["question"] = cleaned
    return output
