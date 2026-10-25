"""Score the fixed Playwright world. Same input always yields the same ranking."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

WORLD_PATH = Path(__file__).with_name("playwright_world.json")

# Weights are part of the contract the Playwright test checks.
TECH_WEIGHT = 0.5
NEWS_WEIGHT = 0.3
ORDER_WEIGHT = 0.2
REVIEW_FLOOR = 60.0


def load_world() -> dict[str, Any]:
    return json.loads(WORLD_PATH.read_text(encoding="utf-8"))


def _order_points(row: dict[str, Any] | None) -> float:
    if not row:
        return 50.0
    quality = float(row.get("quality_score") or 0)
    return round(max(0.0, min(16.0, quality)) / 16.0 * 100.0, 2)


def score_symbol(symbol: str, world: dict[str, Any]) -> dict[str, Any]:
    tech = (world.get("technicals") or {}).get(symbol) or {}
    news = (world.get("news") or {}).get(symbol) or {}
    order = (world.get("order_book") or {}).get(symbol)
    tech_score = float(tech.get("composite_score") or 0)
    news_score = float(news.get("news_score") or 0)
    order_score = _order_points(order)
    score = round(tech_score * TECH_WEIGHT + news_score * NEWS_WEIGHT + order_score * ORDER_WEIGHT, 2)
    decision = "review" if score >= REVIEW_FLOOR else "skip"
    headline = (news.get("headlines") or [{}])[0].get("title") if news.get("headlines") else "No headlines"
    return {
        "symbol": symbol,
        "decision": decision,
        "score": score,
        "technical_score": tech_score,
        "news_score": news_score,
        "order_score": order_score,
        "stance": tech.get("stance"),
        "headline": headline,
        "why": (
            f"{symbol}: technical {tech_score:.0f}, news {news_score:.0f}, "
            f"order-book {order_score:.0f}. Combined {score:.2f} → {decision}."
        ),
    }


def recommend(world: dict[str, Any] | None = None) -> dict[str, Any]:
    world = world or load_world()
    symbols = list((world.get("technicals") or {}).keys())
    ranked = [score_symbol(sym, world) for sym in symbols]
    ranked.sort(key=lambda row: (-float(row["score"]), row["symbol"]))
    for index, row in enumerate(ranked, start=1):
        row["rank"] = index
    return {
        "fixture": "playwright",
        "deterministic": True,
        "as_of": world.get("as_of"),
        "regime": world.get("regime"),
        "weights": {"technical": TECH_WEIGHT, "news": NEWS_WEIGHT, "order_book": ORDER_WEIGHT},
        "review_floor": REVIEW_FLOOR,
        "recommendations": ranked,
        "top": ranked[0]["symbol"] if ranked else None,
    }


def playwright_payload() -> dict[str, Any]:
    world = load_world()
    return {
        "world": world,
        "recommendation": recommend(world),
    }
