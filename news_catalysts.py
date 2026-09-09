"""News & macro catalysts that may move a stock (war, supply, rates, etc.).

Pulls company headlines (Yahoo) plus a light Google News RSS sweep for
sector/macro themes. Educational context only — not a live news terminal.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Optional
from urllib.parse import quote_plus

import requests

from fetch_stock_data import fetch_yfinance_news
from utils.errors import swallow
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Keyword → catalyst tag (first match wins priority order below).
_TAG_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("geopolitics_war", (
        "war", "invasion", "missile", "conflict", "geopolit", "sanction",
        "military", "israel", "gaza", "ukraine", "taiwan", "iran", "strike",
    )),
    ("supply_constraints", (
        "supply chain", "shortage", "constraint", "bottleneck", "disruption",
        "logistics", "freight", "port congestion", "chip shortage", "raw material",
    )),
    ("commodity_energy", (
        "oil", "crude", "brent", "natural gas", "lng", "coal", "commodity",
        "opec", "refinery", "diesel",
    )),
    ("rates_macro", (
        "fed", "rbi", "interest rate", "inflation", "cpi", "gdp", "recession",
        "bond yield", "monetary policy", "rate hike", "rate cut",
    )),
    ("regulation_policy", (
        "regulation", "ban", "tariff", "duty", "antitrust", "sebi", "rbi circular",
        "policy", "subsidy", "gst", "tax",
    )),
    ("government_policy", (
        "government", "ministry", "cabinet", "parliament", "budget", "fiscal",
        "notification", "circular", "ordinance", "legislation", "bill passed",
        "pli scheme", "production linked", "stimulus", "reform bill", "niti aayog",
        "finance ministry", "commerce ministry", "environment ministry",
    )),
    ("earnings_corporate", (
        "earnings", "results", "profit", "revenue", "guidance", "dividend",
        "buyback", "merger", "acquisition", "ipo", "fii", "dii",
    )),
    ("weather_climate", (
        "monsoon", "drought", "flood", "cyclone", "climate", "heatwave",
    )),
]

_TAG_LABELS = {
    "geopolitics_war": "Geopolitics / war",
    "supply_constraints": "Supply constraints",
    "commodity_energy": "Commodity / energy",
    "rates_macro": "Rates / macro",
    "regulation_policy": "Regulation / policy",
    "government_policy": "Government policy",
    "earnings_corporate": "Earnings / corporate",
    "weather_climate": "Weather / climate",
    "general": "General",
}


def _tag_headline(text: str) -> str:
    low = (text or "").lower()
    for tag, words in _TAG_RULES:
        if any(w in low for w in words):
            return tag
    return "general"


def _normalize_item(
    *,
    title: str,
    summary: Optional[str] = None,
    publisher: Optional[str] = None,
    published_at: Optional[str] = None,
    url: Optional[str] = None,
    source: str = "yahoo",
) -> dict[str, Any]:
    blob = f"{title} {summary or ''}"
    tag = _tag_headline(blob)
    return {
        "title": title.strip(),
        "summary": (summary or "").strip() or None,
        "publisher": publisher,
        "published_at": published_at,
        "url": url,
        "source": source,
        "catalyst_tag": tag,
        "catalyst_label": _TAG_LABELS.get(tag, "General"),
    }


def _parse_rss_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception as exc:
        logger.debug("RSS date parse failed for %r", value, exc_info=exc)
        return value


def _google_news_rss(query: str, limit: int = 8) -> list[dict[str, Any]]:
    url = (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    )
    try:
        resp = requests.get(
            url,
            timeout=12,
            headers={"User-Agent": "ScanBhav/1.0 (educational research)"},
        )
        if resp.status_code >= 400:
            return []
        root = ET.fromstring(resp.content)
    except Exception as exc:
        logger.debug("Google News RSS failed for %r", query, exc_info=exc)
        return []

    items: list[dict[str, Any]] = []
    for node in root.findall("./channel/item"):
        title = (node.findtext("title") or "").strip()
        if not title:
            continue
        items.append(
            _normalize_item(
                title=re.sub(r"\s+", " ", title),
                summary=(node.findtext("description") or None),
                publisher=(node.findtext("source") or None),
                published_at=_parse_rss_date(node.findtext("pubDate")),
                url=(node.findtext("link") or None),
                source="google_news_rss",
            )
        )
        if len(items) >= limit:
            break
    return items


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for item in items:
        key = re.sub(r"[^a-z0-9]+", "", (item.get("title") or "").lower())[:120]
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def gather_news_catalysts(
    symbol: str,
    *,
    company_name: Optional[str] = None,
    sector: Optional[str] = None,
    industry: Optional[str] = None,
    existing_news: Optional[list[dict[str, Any]]] = None,
    limit: int = 14,
    skip_rss: bool = False,
) -> dict[str, Any]:
    """Company headlines + macro/sector RSS sweep, tagged for GenAI."""
    items: list[dict[str, Any]] = []

    for raw in existing_news or []:
        title = raw.get("title")
        if not title:
            continue
        items.append(
            _normalize_item(
                title=title,
                summary=raw.get("summary"),
                publisher=raw.get("publisher"),
                published_at=raw.get("published_at"),
                url=raw.get("url"),
                source="yahoo_company",
            )
        )

    if len(items) < 4:
        try:
            for raw in fetch_yfinance_news(symbol, limit=10):
                items.append(
                    _normalize_item(
                        title=raw["title"],
                        summary=raw.get("summary"),
                        publisher=raw.get("publisher"),
                        published_at=raw.get("published_at"),
                        url=raw.get("url"),
                        source="yahoo_company",
                    )
                )
        except Exception as exc:
            swallow(f"Yahoo news fetch failed for {symbol}", exc)

    if not skip_rss:
        name = (company_name or symbol.split(".")[0]).strip()
        sector_q = (sector or industry or "").strip()
        macro_query = (
            f"({name} OR {symbol.split('.')[0]}) "
            f"(war OR geopolitics OR sanctions OR \"supply chain\" OR shortage "
            f"OR oil OR inflation OR tariff OR regulation OR government policy OR budget"
            f"{f' OR {sector_q}' if sector_q else ''})"
        )
        try:
            items.extend(_google_news_rss(macro_query, limit=8))
        except Exception as exc:
            swallow(f"Macro RSS sweep failed for {symbol}", exc)

        if sector_q:
            try:
                items.extend(
                    _google_news_rss(
                        f"{sector_q} India (supply OR war OR oil OR policy OR rates OR government OR budget)",
                        limit=5,
                    )
                )
            except Exception as exc:
                swallow(f"Sector RSS sweep failed for {sector_q}", exc)

    items = _dedupe(items)[:limit]

    by_tag: dict[str, int] = {}
    for item in items:
        tag = item.get("catalyst_tag") or "general"
        by_tag[tag] = by_tag.get(tag, 0) + 1

    high_impact = [
        i for i in items
        if i.get("catalyst_tag") in {
            "geopolitics_war", "supply_constraints", "commodity_energy",
            "rates_macro", "regulation_policy", "government_policy", "weather_climate",
        }
    ]

    policy_headlines = [
        i for i in items
        if i.get("catalyst_tag") in {"regulation_policy", "government_policy", "rates_macro"}
    ]

    return {
        "as_of": datetime.now(timezone.utc).isoformat(),
        "headline_count": len(items),
        "high_impact_count": len(high_impact),
        "tag_counts": by_tag,
        "headlines": items,
        "high_impact_headlines": high_impact[:8],
        "government_policy_headlines": policy_headlines[:8],
        "note": (
            "Headlines are best-effort from Yahoo + Google News RSS. "
            "Tags are keyword heuristics for GenAI context — not verified event classification."
        ),
    }
