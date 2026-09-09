"""Corporate foundation scan: CEO, officers, group / related-party news hints.

Uses Yahoo officers when available + keyword scan of news headlines.
Educational governance context only — not fraud findings.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from news_catalysts import _google_news_rss


_FOUNDATION_KEYWORDS = (
    "sebi", "penalty", "fine", "fraud", "probe", "investigation", "default",
    "insolvency", "nclt", "related party", "related-party", "promoter pledge",
    "pledge", "diversion", "siphoning", "audit qualification", "resignation",
    "subsidiary", "associate company", "group company", "holding company",
    "shell", "wilful defaulter", "sfio", "enforcement directorate", "ed raid",
    "cbi", "misstatement", "restated", "accounting irregular",
)

_GROUP_KEYWORDS = (
    "subsidiary", "associate", "group company", "holding", "parent company",
    "step-down", "joint venture", "promoter group", "affiliate",
)


def _ceo_from_company(company: dict[str, Any]) -> Optional[dict[str, Any]]:
    ceo = company.get("ceo")
    if isinstance(ceo, dict) and ceo.get("name"):
        return ceo
    officers = company.get("officers") or []
    for o in officers:
        title = str(o.get("title") or "").lower()
        if "chief executive" in title or title.strip() == "ceo" or "managing director" in title:
            return o
    return officers[0] if officers else None


def _scan_headlines(
    headlines: list[dict[str, Any]],
    *,
    names: list[str],
    symbol: str,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    sym_base = symbol.split(".")[0].upper()
    for h in headlines:
        blob = f"{h.get('title', '')} {h.get('summary', '')}".lower()
        if any(k in blob for k in _FOUNDATION_KEYWORDS):
            matched_name = next((n for n in names if n and n.lower() in blob), None)
            mentions_group = any(k in blob for k in _GROUP_KEYWORDS)
            mentions_symbol = sym_base.lower() in blob or symbol.lower() in blob
            if matched_name or mentions_group or mentions_symbol:
                hits.append({
                    "title": h.get("title"),
                    "published_at": h.get("published_at"),
                    "url": h.get("url"),
                    "catalyst_label": h.get("catalyst_label") or "Governance",
                    "matched_officer": matched_name,
                    "mentions_group_structure": mentions_group,
                    "severity": "elevated" if any(w in blob for w in ("fraud", "sebi", "probe", "raid", "default")) else "moderate",
                })
    return hits[:8]


def _fetch_officer_news(name: str, company_name: str, limit: int = 4) -> list[dict[str, Any]]:
    if not name or len(name.split()) < 2:
        return []
    query = f'"{name}" ({company_name or "India"}) (SEBI OR subsidiary OR promoter OR fraud OR investigation OR group company)'
    try:
        return _google_news_rss(query, limit=limit)
    except Exception:
        return []


def analyze_corporate_foundation(
    *,
    quote: dict[str, Any] | None = None,
    news: dict[str, Any] | None = None,
    symbol: str = "",
) -> dict[str, Any]:
    """Scan leadership + headlines for group-structure / governance stress signals."""
    company = (quote or {}).get("company") or {}
    news = news or {}
    sym = (symbol or company.get("symbol") or "").upper()
    company_name = company.get("name") or sym.split(".")[0]

    officers = list(company.get("officers") or [])[:8]
    ceo = _ceo_from_company(company)
    ceo_name = (ceo or {}).get("name") or ""
    officer_names = [str(o.get("name") or "") for o in officers if o.get("name")]

    headlines = list(news.get("headlines") or [])
    governance_hits = _scan_headlines(headlines, names=officer_names, symbol=sym)

    # Extra RSS sweep for CEO + group companies (best-effort)
    if ceo_name and len(governance_hits) < 3:
        for item in _fetch_officer_news(ceo_name, company_name, limit=4):
            headlines.append(item)
        governance_hits = _scan_headlines(headlines, names=officer_names, symbol=sym)

    associated_mentions: list[str] = []
    for h in governance_hits:
        if h.get("mentions_group_structure"):
            associated_mentions.append(h.get("title") or "")
        elif h.get("matched_officer"):
            associated_mentions.append(f"{h['matched_officer']}: {h.get('title', '')[:100]}")

    # Name-pattern hints (holding / ventures)
    structure_hints: list[str] = []
    name_low = str(company_name).lower()
    if any(w in name_low for w in ("holdings", "ventures", "investments", "capital")):
        structure_hints.append(f"Name suggests a holding/investment structure — map subsidiaries and related parties carefully.")

    flags: list[str] = []
    elevated = sum(1 for h in governance_hits if h.get("severity") == "elevated")
    if elevated:
        flags.append(f"{elevated} elevated governance headline(s) in latest sweep.")
    if associated_mentions:
        flags.append(f"{len(associated_mentions)} headline(s) mention group / officer / related-party context.")
    if not officers:
        flags.append("Officer roster unavailable — foundation scan is thinner until Yahoo profile loads.")

    exposure = "low"
    if elevated >= 2:
        exposure = "high"
    elif elevated >= 1 or len(governance_hits) >= 2:
        exposure = "moderate"
    elif structure_hints:
        exposure = "moderate"

    plain_parts = []
    if ceo_name:
        plain_parts.append(f"CEO/key executive: {ceo_name}" + (f" ({ceo.get('title')})" if ceo else "") + ".")
    else:
        plain_parts.append("CEO name not available from profile data.")
    plain_parts.append(f"Foundation stress exposure: {exposure}.")
    if governance_hits:
        plain_parts.append(f"Latest flag: “{(governance_hits[0].get('title') or '')[:90]}”.")
    elif structure_hints:
        plain_parts.append(structure_hints[0])
    else:
        plain_parts.append("No group/officer governance headlines flagged in current news sweep.")

    return {
        "ceo": ceo,
        "officers": officers,
        "foundation_exposure": exposure,
        "governance_headlines": governance_hits,
        "associated_company_mentions": associated_mentions[:6],
        "structure_hints": structure_hints,
        "foundation_flags": flags,
        "plain_english": " ".join(plain_parts),
        "headline": plain_parts[0] + " " + plain_parts[1],
        "disclaimer": (
            "Corporate foundation scan uses public headlines and officer lists — "
            "not a legal or forensic finding. Verify SEBI/MCA filings independently."
        ),
    }
