"""Forum & community chatter sweep for the Live Research Desk.

Uses public RSS/search surfaces (Google News RSS) to find discussion threads on
well-known Indian equity communities. Treat as unverified rumor/discussion —
never as confirmed insider information.
"""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional
import requests

from news_catalysts import _dedupe, _google_news_rss
from utils.errors import swallow
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Known communities the desk monitors (via search, not scraping logins).
FORUM_SOURCES = [
    {"id": "reddit_isb", "label": "Reddit · r/IndianStreetBets", "site": "reddit.com/r/IndianStreetBets"},
    {"id": "reddit_ii", "label": "Reddit · r/IndiaInvestments", "site": "reddit.com/r/IndiaInvestments"},
    {"id": "reddit_smi", "label": "Reddit · r/StockMarketIndia", "site": "reddit.com/r/StockMarketIndia"},
    {"id": "valuepickr", "label": "ValuePickr Forum", "site": "valuepickr.com"},
    {"id": "traderji", "label": "Traderji", "site": "traderji.com"},
    {"id": "moneycontrol", "label": "Moneycontrol community", "site": "moneycontrol.com"},
    {"id": "quora", "label": "Quora India investing", "site": "quora.com"},
]

_RUMOR_WORDS = (
    "rumor", "rumour", "heard", "insider", "tip", "leak", "whisper", "circular",
    "unconfirmed", "sources say", "may announce", "might announce", "talks",
    "promoter", "stake sale", "block deal", "bulk deal",
)
_BULL_WORDS = ("buy", "accumulate", "breakout", "bull", "target", "upgrade", "strong")
_BEAR_WORDS = ("sell", "avoid", "downgrade", "bear", "fraud", "scam", "weak", "cut")


def _detect_forum(url: Optional[str], title: str) -> str:
    low = f"{url or ''} {title}".lower()
    for src in FORUM_SOURCES:
        if src["site"].replace("www.", "") in low:
            return src["id"]
    if "reddit.com" in low:
        return "reddit_other"
    return "web_forum"


def _forum_label(forum_id: str) -> str:
    for src in FORUM_SOURCES:
        if src["id"] == forum_id:
            return src["label"]
    if forum_id == "reddit_other":
        return "Reddit (other)"
    return "Web discussion"


def _tag_thread(title: str, summary: Optional[str] = None) -> str:
    blob = f"{title} {summary or ''}".lower()
    if any(w in blob for w in _RUMOR_WORDS):
        return "rumor_unverified"
    if any(w in blob for w in _BEAR_WORDS):
        return "bearish_chatter"
    if any(w in blob for w in _BULL_WORDS):
        return "bullish_chatter"
    return "general_discussion"


_TAG_LABELS = {
    "rumor_unverified": "Unverified rumor / tip",
    "bearish_chatter": "Bearish forum tone",
    "bullish_chatter": "Bullish forum tone",
    "general_discussion": "General discussion",
}


def _normalize_thread(
    *,
    title: str,
    summary: Optional[str] = None,
    url: Optional[str] = None,
    published_at: Optional[str] = None,
    publisher: Optional[str] = None,
    query: str,
) -> dict[str, Any]:
    tag = _tag_thread(title, summary)
    forum_id = _detect_forum(url, title)
    return {
        "title": re.sub(r"\s+", " ", title.strip()),
        "summary": (summary or "").strip()[:320] or None,
        "url": url,
        "published_at": published_at,
        "publisher": publisher,
        "forum_id": forum_id,
        "forum_label": _forum_label(forum_id),
        "thread_tag": tag,
        "thread_label": _TAG_LABELS.get(tag, "Discussion"),
        "search_query": query,
        "source": "forum_rss",
        "verified": False,
    }


def _search_forum_query(query: str, limit: int = 5) -> list[dict[str, Any]]:
    raw = _google_news_rss(query, limit=limit)
    out: list[dict[str, Any]] = []
    for item in raw:
        out.append(
            _normalize_thread(
                title=item.get("title") or "",
                summary=item.get("summary"),
                url=item.get("url"),
                published_at=item.get("published_at"),
                publisher=item.get("publisher"),
                query=query,
            )
        )
    return out


def gather_forum_intel(
    symbol: str,
    *,
    company_name: Optional[str] = None,
    limit: int = 12,
    max_queries: Optional[int] = None,
) -> dict[str, Any]:
    """Sweep public forum/discussion threads mentioning the symbol."""
    base = (symbol.split(".")[0] if symbol else "").strip().upper()
    name = (company_name or base).strip()
    if not base:
        return {
            "thread_count": 0,
            "rumor_count": 0,
            "forums_checked": [s["label"] for s in FORUM_SOURCES],
            "threads": [],
            "note": "No symbol provided.",
            "disclaimer": _disclaimer(),
        }

    items: list[dict[str, Any]] = []

    queries = [
        f'site:reddit.com/r/IndianStreetBets OR site:reddit.com/r/IndiaInvestments "{base}" stock',
        f'site:reddit.com/r/StockMarketIndia "{base}"',
        f'site:valuepickr.com {base}',
        f'site:traderji.com {base}',
        f'"{name}" OR "{base}" stock forum india discussion',
        f'"{base}" insider rumor OR bulk deal OR block deal india stock',
        f'site:moneycontrol.com {base} forum OR messageboard',
    ]
    if max_queries is not None:
        queries = queries[: max(1, max_queries)]

    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
        futures = [pool.submit(_search_forum_query, q, 4) for q in queries]
        for fut in as_completed(futures):
            try:
                items.extend(fut.result())
            except Exception as exc:
                logger.debug("Forum query batch failed", exc_info=exc)
                continue
            if len(items) >= limit * 2:
                break

    items = _dedupe(items)
    # Prefer rumor-tagged and recent diversity of forums
    items.sort(key=lambda x: (0 if x.get("thread_tag") == "rumor_unverified" else 1, x.get("title") or ""))
    items = items[:limit]

    rumor_count = sum(1 for t in items if t.get("thread_tag") == "rumor_unverified")
    tag_counts: dict[str, int] = {}
    forum_counts: dict[str, int] = {}
    for t in items:
        tag_counts[t.get("thread_tag") or "general_discussion"] = tag_counts.get(t.get("thread_tag") or "general_discussion", 0) + 1
        fid = t.get("forum_id") or "web_forum"
        forum_counts[fid] = forum_counts.get(fid, 0) + 1

    loudest = items[0]["title"] if items else None
    return {
        "symbol": symbol.upper(),
        "thread_count": len(items),
        "rumor_count": rumor_count,
        "tag_counts": tag_counts,
        "forum_counts": forum_counts,
        "forums_checked": [s["label"] for s in FORUM_SOURCES],
        "loudest_thread": loudest,
        "threads": items,
        "note": (
            "Public RSS/search sweep of forum-style sources (incl. Reddit via search). "
            "Threads are unverified discussion — not confirmed insider facts."
        ),
        "disclaimer": _disclaimer(),
    }


def _disclaimer() -> str:
    return (
        "Forum intel is educational context from public discussion links. "
        "It is NOT verified insider information and must not be traded on blindly."
    )
