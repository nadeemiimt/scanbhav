"""Extended fundamentals: TTM metrics, debt quality, quality scores (Piotroski, Altman, Graham)."""
from __future__ import annotations

from typing import Any, Optional

from analysis._helpers import clamp, num


def _piotroski_f_score(f: dict[str, Any]) -> dict[str, Any]:
    score = 0
    checks: list[str] = []
    roa = num(f.get("roa_pct")) or num(f.get("returnOnAssets"))
    if roa is not None and roa > 0:
        score += 1
        checks.append("Positive ROA")
    ocf = num(f.get("operating_cashflow")) or num(f.get("free_cashflow"))
    ni = num(f.get("net_income")) or num(f.get("netIncome"))
    if ocf and ni and ocf > 0:
        score += 1
        checks.append("Positive operating cash flow")
    roe = num(f.get("roe_pct"))
    if roe is not None and roe > 0:
        score += 1
        checks.append("Positive ROE")
    de = num(f.get("debt_to_equity"))
    if de is not None and de < 1.5:
        score += 1
        checks.append("Manageable leverage")
    cr = num(f.get("current_ratio"))
    if cr is not None and cr >= 1.2:
        score += 1
        checks.append("Adequate current ratio")
    gm = num(f.get("gross_margin_pct"))
    if gm is not None and gm > 20:
        score += 1
        checks.append("Healthy gross margin")
    rev_g = num(f.get("revenue_growth_yoy_pct"))
    if rev_g is not None and rev_g > 0:
        score += 1
        checks.append("Revenue growth")
    asset_turn = num(f.get("asset_turnover"))
    if asset_turn is not None and asset_turn > 0.5:
        score += 1
        checks.append("Asset turnover ok")
    label = "strong" if score >= 7 else ("average" if score >= 4 else "weak")
    return {"score": score, "max": 9, "label": label, "checks": checks}


def _altman_z(mcap: Optional[float], f: dict[str, Any]) -> dict[str, Any]:
    """Simplified Altman Z for non-manufacturing proxy (educational)."""
    ta = num(f.get("total_assets")) or (mcap or 0) * 2
    tl = num(f.get("total_liabilities")) or ta * 0.4
    wc = num(f.get("working_capital")) or ta * 0.1
    ebit = num(f.get("ebit")) or num(f.get("operating_income"))
    sales = num(f.get("revenue_ttm")) or num(f.get("total_revenue"))
    re = num(f.get("retained_earnings")) or ta * 0.2
    if not ta or ta <= 0:
        return {"z_score": None, "zone": "unknown", "note": "Insufficient balance sheet inputs."}
    z = 1.2 * (wc / ta) + 1.4 * (re / ta) + 3.3 * ((ebit or 0) / ta) + 0.6 * ((mcap or 0) / max(tl, 1)) + 1.0 * ((sales or 0) / ta)
    zone = "safe" if z >= 2.6 else ("grey" if z >= 1.1 else "distress")
    return {"z_score": round(z, 2), "zone": zone}


def _graham_number(eps: Optional[float], bv: Optional[float]) -> dict[str, Any]:
    if not eps or not bv or eps <= 0 or bv <= 0:
        return {"graham_number": None, "margin_of_safety_pct": None}
    g = (22.5 * eps * bv) ** 0.5
    return {"graham_number": round(g, 2)}


def compute_fundamentals_extended(quote: dict[str, Any] | None) -> dict[str, Any]:
    quote = quote or {}
    company = quote.get("company") or {}
    f = dict(quote.get("fundamentals") or {})
    price = num(quote.get("summary", {}).get("close")) or num(company.get("current_price"))
    mcap = num(company.get("market_cap"))

    ebit = num(f.get("ebit")) or num(f.get("operating_income"))
    interest = num(f.get("interest_expense")) or (ebit or 0) * 0.08
    ebitda = num(f.get("ebitda")) or (ebit or 0) * 1.2
    net_debt = num(f.get("net_debt")) or num(f.get("total_debt"))
    interest_coverage = round(ebit / interest, 2) if ebit and interest and interest > 0 else None
    net_debt_ebitda = round(net_debt / ebitda, 2) if net_debt is not None and ebitda and ebitda > 0 else None

    eps = num(company.get("trailing_eps")) or num(f.get("eps_ttm"))
    bv = num(company.get("book_value")) or num(f.get("book_value_per_share"))
    graham = _graham_number(eps, bv)
    if graham.get("graham_number") and price:
        graham["margin_of_safety_pct"] = round((1 - price / graham["graham_number"]) * 100, 1)

    piotroski = _piotroski_f_score({**f, **company})
    altman = _altman_z(mcap, f)

    rev_q = f.get("quarterly_revenue") or company.get("quarterly_revenue")
    ttm_note = "TTM/quarterly from Yahoo when available; annual-only otherwise."
    analyst = {
        "target_mean": num(company.get("target_mean_price")),
        "target_high": num(company.get("target_high_price")),
        "target_low": num(company.get("target_low_price")),
        "recommendation": company.get("recommendation") or company.get("analyst_rating"),
        "num_analysts": num(company.get("num_analysts")),
        "eps_estimate": num(company.get("forward_eps")) or num(company.get("eps_estimate")),
    }
    if analyst["target_mean"] and price:
        analyst["upside_pct"] = round((analyst["target_mean"] / price - 1) * 100, 1)

    segments = company.get("segment_revenue") or f.get("segments") or []
    quality_score = int(clamp(50 + piotroski["score"] * 3 + (10 if altman.get("zone") == "safe" else 0)))

    return {
        "status": "ok",
        "ttm": {
            "revenue_ttm": num(f.get("revenue_ttm")) or num(f.get("total_revenue")),
            "ebitda_ttm": ebitda,
            "eps_ttm": eps,
            "quarterly_available": bool(rev_q),
            "note": ttm_note,
        },
        "debt_quality": {
            "interest_coverage": interest_coverage,
            "net_debt_ebitda": net_debt_ebitda,
            "debt_to_equity": num(f.get("debt_to_equity")) or num(company.get("debt_to_equity")),
        },
        "quality_scores": {
            "piotroski": piotroski,
            "altman": altman,
            "graham": graham,
            "composite_quality": quality_score,
            "composite_label": "high" if quality_score >= 70 else ("moderate" if quality_score >= 50 else "low"),
        },
        "analyst_consensus": analyst,
        "segment_revenue": segments if isinstance(segments, list) else [],
        "fundamental_screener_flags": {
            "quality_ok": quality_score >= 55,
            "debt_ok": (net_debt_ebitda or 99) < 3.5 and (interest_coverage or 0) > 2,
            "growth_ok": (num(f.get("revenue_growth_yoy_pct")) or 0) > 0,
        },
    }
