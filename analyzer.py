"""Retrieve investment-framework passages and apply them to supplied stock data."""
from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from config import INSIGHTS_CACHE_TTL_SECONDS, LLM_MODEL, OLLAMA_KEEP_ALIVE, TOP_K
from rag import ollama_client, retrieve

# Simple in-process cache so repeated "Generate insight" clicks for the same
# stock snapshot don't re-run retrieval + the LLM every time. Keyed by a hash
# of the stock input (which includes data_as_of), so it naturally busts when
# the underlying data changes.
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def _cache_key(stock: dict[str, Any]) -> str:
    return hashlib.sha1(json.dumps(stock, sort_keys=True, default=str).encode()).hexdigest()



SYSTEM_PROMPT = """You are an educational stock-analysis assistant. Apply only the supplied stock data and retrieved book passages. Never invent prices, financial values, news, or citations. This is not personalized financial advice. Return valid JSON only, matching the requested schema. Be candid when information is missing or the evidence is mixed.

Numerical integrity rules:
- Never call a negative return “strong price performance.” A one-year or six-month return below 0 is a concern or mixed evidence, unless a separately supplied positive trend metric explicitly offsets it.
- Market capitalization by itself is neither a strength nor a concern. Discuss valuation only from supplied valuation, growth, margin, debt, or cash-flow data.
- State each important number with its sign and period when it drives the conclusion. Do not replace it with a vague positive/negative label.
- A missing value is unknown, not evidence for a positive or negative conclusion.
- Use `accumulate` only when the evidence supports it; otherwise use `watchlist` or `insufficient_data`.
- If `peers` data is supplied, compare this company's valuation (P/E, forward P/E, price-to-book, dividend yield) against the peer group only using the supplied numbers. Do not invent peer figures beyond what is supplied, and do not treat an empty peer list as evidence of anything.
- If `recent_news` is supplied, treat each headline/summary as a data point only for the stated date; never assume a headline is still relevant beyond what it says, and never invent a headline, source, or event that is not literally present in `recent_news`. An empty `recent_news` list means no news was available, not that nothing happened.
- Before writing `peer_comparison`, count the items in the `peers` array of STOCK INPUT. If that count is greater than 0, you MUST NOT say "the list of peers is empty" or "no peer data supplied" — instead compare the company's valuation numbers against those peers by name. Only use "no peer data supplied" wording when the `peers` array is literally `[]`.
- Before writing `news_summary`, count the items in the `recent_news` array of STOCK INPUT and set `headlines_considered` to that exact count. If the count is greater than 0, you MUST reference at least one actual headline title from `recent_news` in your `notes` — never say "no recent news supplied" or "empty list" when `recent_news` is non-empty. Only use that wording when `recent_news` is literally `[]`.
- For `trade_view`, propose an educational entry ("buy_zone") and exit ("sell_zone") price range using only the supplied `price`, `price_performance` (sma_50, sma_200, distance_from_52_week_high_pct), and `valuation` figures. A buy_zone is typically near or below a support level such as the 50-day/200-day SMA or a pullback from the current price; a sell_zone is typically near a resistance level such as the 52-week high or a level where valuation looks expensive versus peers. Always give both `low` and `high` as real numbers derived from the supplied figures (e.g. sma_50 to current price, or current price to 52-week high) — never leave them null if `price` is supplied. State the reasoning behind each zone in `rationale`, and write one plain-English sentence in `one_line` summarizing when it could make sense to accumulate versus book profits, based only on this data."""


def retrieval_query(stock: dict[str, Any]) -> str:
    financials = stock.get("financials", {})
    valuation = stock.get("valuation", {})
    performance = stock.get("price_performance", {})
    peers = stock.get("peers", [])
    news = stock.get("recent_news", [])
    return "Investment framework for evaluating this company: " + json.dumps({
        "sector": stock.get("sector"),
        "industry": stock.get("industry"),
        "financials": financials,
        "valuation": valuation,
        "price_performance": performance,
        "peer_count": len(peers),
        "news_headlines": [item.get("title") for item in news],
    }, separators=(",", ":"))


def parse_json(text: str) -> dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {"verdict": "unable_to_parse", "summary": text, "strengths": [], "concerns": [], "framework_checks": [], "missing_data": [], "questions_to_research": []}
        return json.loads(match.group())


def analyze_stock(stock: dict[str, Any]) -> dict[str, Any]:
    if not stock.get("ticker"):
        raise ValueError("Input must include a ticker.")

    key = _cache_key(stock)
    cached = _CACHE.get(key)
    if cached and (time.time() - cached[0]) < INSIGHTS_CACHE_TTL_SECONDS:
        return cached[1]

    sources = retrieve(retrieval_query(stock), TOP_K)
    context = "\n\n".join(
        f"[Source {i}: {item['source']}, page {item['page']}, chunk {item['chunk']}]\n{item['text']}"
        for i, item in enumerate(sources, start=1)
    )
    schema = {
        "verdict": "accumulate | watchlist | avoid | insufficient_data",
        "confidence": "low | medium | high",
        "summary": "short evidence-based summary",
        "strengths": ["items based on input"],
        "concerns": ["items based on input"],
        "framework_checks": [{"criterion": "", "assessment": "positive | mixed | negative | unknown", "evidence": "", "source_refs": ["Source 1"]}],
        "missing_data": ["data needed before a decision"],
        "questions_to_research": ["next research steps"],
        "catalysts": ["upcoming events or triggers that could move the evidence, based only on supplied data"],
        "technical_view": {"trend": "uptrend | downtrend | sideways | unknown", "notes": "observations strictly from supplied price_performance figures"},
        "peer_comparison": {"assessment": "cheap | in_line | expensive | unknown", "notes": "comparison strictly from supplied peers valuation figures, or 'no peer data supplied' if the peers list is empty"},
        "news_summary": {"headlines_considered": 0, "notes": "brief note on how supplied recent_news headlines relate to the evidence, or 'no recent news supplied' if the list is empty"},
        "trade_view": {
            "buy_zone": {"low": 0, "high": 0, "rationale": "why this range could be a reasonable accumulation zone, based only on supplied price/technical/valuation figures"},
            "sell_zone": {"low": 0, "high": 0, "rationale": "why this range could be a reasonable profit-booking zone, based only on supplied price/technical/valuation figures"},
            "one_line": "one plain-English sentence summarizing the buy/sell view"
        },
        "risk_note": "Educational analysis only; not investment advice."
    }

    user_prompt = f"""STOCK INPUT:\n{json.dumps(stock, indent=2)}\n\nRETRIEVED BOOK PASSAGES:\n{context}\n\nReturn JSON matching exactly this shape:\n{json.dumps(schema, indent=2)}\nOnly cite Source numbers that appear above. A verdict is an educational screen, never a trade instruction."""
    response = ollama_client().chat(model=LLM_MODEL, messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ], format="json", options={"temperature": 0.2, "num_ctx": 4096}, keep_alive=OLLAMA_KEEP_ALIVE)
    output = parse_json(response["message"]["content"])
    output["retrieved_sources"] = [{k: item[k] for k in ("source", "page", "chunk", "distance")} for item in sources]

    # The local LLM sometimes claims "no peers" / "no news" even when
    # non-empty lists were supplied. Rather than trust the model's self
    # report, deterministically correct these two fields from the actual
    # input so the UI never shows a false "empty" claim.
    peers = stock.get("peers") or []
    news = stock.get("recent_news") or []

    peer_comparison = output.get("peer_comparison")
    if not isinstance(peer_comparison, dict):
        peer_comparison = {}
    if not peers:
        peer_comparison["assessment"] = peer_comparison.get("assessment") or "unknown"
        peer_comparison["notes"] = "No peer data supplied."
    elif "empty" in str(peer_comparison.get("notes", "")).lower() or "no peer data supplied" in str(peer_comparison.get("notes", "")).lower():
        peer_names = ", ".join(p.get("symbol", "?") for p in peers if p.get("symbol"))
        peer_comparison["notes"] = f"Peers supplied ({peer_names}); the model did not use them in its comparison. Re-run insights or review the raw figures directly."
    output["peer_comparison"] = peer_comparison

    news_summary = output.get("news_summary")
    if not isinstance(news_summary, dict):
        news_summary = {}
    news_summary["headlines_considered"] = len(news)
    existing_notes = str(news_summary.get("notes") or "").strip()
    if not news:
        news_summary["notes"] = "No recent news supplied."
    elif not existing_notes or "no recent news" in existing_notes.lower() or "empty list" in existing_notes.lower():
        first_title = news[0].get("title") or "a recent headline"
        news_summary["notes"] = f"{len(news)} headline(s) were supplied (e.g. \"{first_title}\"); the model did not reference them. Re-run insights or review the headlines directly."
    output["news_summary"] = news_summary

    output["trade_view"] = _resolve_trade_view(stock, output.get("trade_view"))
    output["risk_reward"] = _risk_reward_score(stock, output["trade_view"])

    _CACHE[key] = (time.time(), output)
    return output


def _risk_reward_score(stock: dict[str, Any], trade_view: dict[str, Any]) -> dict[str, Any]:
    """Deterministic 1-5 risk/reward score computed purely from supplied numbers.

    No LLM call is involved here; every input is a figure already present in
    the stock_input or the resolved trade_view, so the score is fully
    reproducible and auditable. Higher is more favorable (more potential
    upside per unit of downside, reasonable valuation vs peers, and positive
    momentum); lower flags rich valuation, negative momentum, or poor
    reward-to-risk skew.
    """
    price = stock.get("price")
    performance = stock.get("price_performance", {}) or {}
    valuation = stock.get("valuation", {}) or {}
    peers = stock.get("peers") or []

    def is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    factors: list[str] = []
    score = 3.0  # neutral midpoint on a 1-5 scale

    buy_zone = trade_view.get("buy_zone", {}) or {}
    sell_zone = trade_view.get("sell_zone", {}) or {}
    upside = downside = None
    if is_number(price) and is_number(buy_zone.get("low")) and is_number(sell_zone.get("high")) and price > 0:
        upside = (sell_zone["high"] / price - 1) * 100
        downside = (1 - buy_zone["low"] / price) * 100
        if downside > 0.01:
            ratio = upside / downside
            if ratio >= 2:
                score += 1
                factors.append(f"Reward-to-risk is favorable (~{round(ratio, 1)}x): {round(upside, 1)}% upside to the sell zone vs {round(downside, 1)}% downside to the buy zone.")
            elif ratio < 1:
                score -= 1
                factors.append(f"Reward-to-risk is unfavorable (~{round(ratio, 1)}x): only {round(upside, 1)}% upside to the sell zone vs {round(downside, 1)}% downside to the buy zone.")
            else:
                factors.append(f"Reward-to-risk is roughly balanced (~{round(ratio, 1)}x): {round(upside, 1)}% upside vs {round(downside, 1)}% downside.")

    sma_50 = performance.get("sma_50")
    sma_200 = performance.get("sma_200")
    if is_number(price) and is_number(sma_50) and is_number(sma_200):
        if price > sma_50 > sma_200:
            score += 1
            factors.append("Price is above both the 50-day and 200-day moving averages, a positive momentum signal.")
        elif price < sma_50 < sma_200:
            score -= 1
            factors.append("Price is below both the 50-day and 200-day moving averages, a negative momentum signal.")

    pe_ratio = valuation.get("pe_ratio")
    peer_pes = [p.get("trailing_pe") for p in peers if is_number(p.get("trailing_pe"))]
    if is_number(pe_ratio) and peer_pes:
        avg_peer_pe = sum(peer_pes) / len(peer_pes)
        if avg_peer_pe > 0:
            if pe_ratio <= avg_peer_pe * 0.85:
                score += 1
                factors.append(f"Trailing P/E ({round(pe_ratio, 1)}) is meaningfully below the peer average ({round(avg_peer_pe, 1)}), suggesting relatively cheaper valuation.")
            elif pe_ratio >= avg_peer_pe * 1.15:
                score -= 1
                factors.append(f"Trailing P/E ({round(pe_ratio, 1)}) is meaningfully above the peer average ({round(avg_peer_pe, 1)}), suggesting relatively expensive valuation.")

    score = max(1, min(5, round(score)))
    if not factors:
        factors.append("Not enough supplied data (price zones, moving averages, or peer valuations) to score risk/reward beyond the neutral midpoint.")

    return {"score": score, "scale": "1 (poor) to 5 (favorable)", "factors": factors}



def _resolve_trade_view(stock: dict[str, Any], model_view: Any) -> dict[str, Any]:
    """Ensure buy/sell zones are always real numbers derived from supplied data.

    Falls back to a deterministic zone built from price, SMA levels, and the
    52-week high/low whenever the model's numbers are missing, non-numeric,
    or nonsensical (e.g. low > high), so the UI always has something concrete
    to show instead of nulls or invented text.
    """
    price = stock.get("price")
    performance = stock.get("price_performance", {}) or {}
    sma_50 = performance.get("sma_50")
    sma_200 = performance.get("sma_200")
    distance_from_high_pct = performance.get("distance_from_52_week_high_pct")

    def is_number(value: Any) -> bool:
        return isinstance(value, (int, float)) and not isinstance(value, bool)

    view = model_view if isinstance(model_view, dict) else {}
    buy_zone = view.get("buy_zone") if isinstance(view.get("buy_zone"), dict) else {}
    sell_zone = view.get("sell_zone") if isinstance(view.get("sell_zone"), dict) else {}

    buy_low, buy_high = buy_zone.get("low"), buy_zone.get("high")
    sell_low, sell_high = sell_zone.get("low"), sell_zone.get("high")

    buy_valid = is_number(buy_low) and is_number(buy_high) and buy_low > 0 and buy_high > 0 and buy_low <= buy_high
    sell_valid = is_number(sell_low) and is_number(sell_high) and sell_low > 0 and sell_high > 0 and sell_low <= sell_high

    # A sell/profit-booking zone must sit meaningfully above the buy zone; if
    # the model returned overlapping or identical ranges, treat the sell zone
    # as invalid so the deterministic fallback (based on the 52-week high)
    # takes over instead.
    if buy_valid and sell_valid and sell_low < buy_high:
        sell_valid = False

    if not buy_valid and is_number(price):

        support = sma_50 if is_number(sma_50) else (sma_200 if is_number(sma_200) else price * 0.95)
        low = min(support, price)
        high = max(support, price) if support != price else price
        # Keep a small band even if support == current price.
        if low == high:
            low, high = round(price * 0.97, 2), price
        buy_zone = {
            "low": round(low, 2), "high": round(high, 2),
            "rationale": (
                f"Derived from the current price ({round(price, 2)}) and the 50-day moving average "
                f"({round(sma_50, 2)})." if is_number(sma_50) else
                f"Derived from the current price ({round(price, 2)}) with a modest pullback allowance, since no moving-average support level was supplied."
            ),
        }
    elif buy_valid:
        buy_zone = {"low": round(buy_low, 2), "high": round(buy_high, 2), "rationale": buy_zone.get("rationale") or ""}

    if not sell_valid and is_number(price):
        if is_number(distance_from_high_pct) and distance_from_high_pct < 0:
            fifty_two_week_high = price / (1 + distance_from_high_pct / 100)
        else:
            fifty_two_week_high = price * 1.08
        low = max(price, fifty_two_week_high * 0.97)
        high = max(fifty_two_week_high, low)
        sell_zone = {
            "low": round(low, 2), "high": round(high, 2),
            "rationale": (
                f"Derived from the current price ({round(price, 2)}) approaching the estimated 52-week-high level "
                f"({round(fifty_two_week_high, 2)}), based on the supplied distance-from-high figure."
                if is_number(distance_from_high_pct) else
                f"Derived from the current price ({round(price, 2)}) with a modest upside allowance, since no 52-week-high distance was supplied."
            ),
        }
    elif sell_valid:
        sell_zone = {"low": round(sell_low, 2), "high": round(sell_high, 2), "rationale": sell_zone.get("rationale") or ""}

    one_line = str(view.get("one_line") or "").strip()
    if not one_line and is_number(price):
        one_line = (
            f"Based on supplied data, accumulation looks more reasonable near {buy_zone.get('low')}\u2013{buy_zone.get('high')}, "
            f"with profit-booking more reasonable near {sell_zone.get('low')}\u2013{sell_zone.get('high')}."
        )

    return {"buy_zone": buy_zone, "sell_zone": sell_zone, "one_line": one_line}



