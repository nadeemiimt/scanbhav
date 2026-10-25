"""
Order-Book Screener (Agent 10) — deterministic Layer-1 logic.

Hard filters, order metrics, quality score, healthy-trigger score,
red flags and ranking. All money values are in Rs crore.
Research only: ranked watchlist for a human review, not a buy/sell.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from config import BASE_DIR

AS_OF = pd.Timestamp("2026-09-30")
ORDER_WINDOW_DAYS = 183
REPEAT_CLIENT_DAYS = 730
MIN_MARKET_CAP_CR = 150
GST_RATE = 0.18
STRONG_CLIENT_TYPES = {"central_govt", "psu", "large_private", "export"}

STORE_DIR = BASE_DIR / "data" / "quant_foundation" / "order_book"
SCREEN_CACHE = BASE_DIR / "data" / "quant_cache" / "order_book_screen.json"


def num(v, default=None):
    """Number or `default` if the value is missing."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return default
    return float(v)


def yes(v):
    """True only if the value is explicitly True (missing counts as False)."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return False
    return bool(v)


def strictly_rising(values):
    v = list(values)
    if len(v) < 2 or any(pd.isna(x) for x in v):
        return False
    return all(b > a for a, b in zip(v, v[1:]))


def ttm(q, col):
    """Sum of the last 4 quarters, or None if any of them is missing."""
    if col not in q.columns:
        return None
    last4 = q[col].tail(4)
    if len(last4) < 4 or last4.isna().any():
        return None
    return float(last4.sum())


def roce_pct(a):
    """ROCE % for each fiscal year = EBIT / (equity + debt) x 100."""
    return a["ebit_cr"] / (a["equity_cr"] + a["debt_cr"]) * 100


def roce_rising(a, years=3):
    """ROCE higher in each of the last `years` fiscal years."""
    r = roce_pct(a).tail(years)
    return len(r) == years and strictly_rising(r)


def ebitda_rising_regularly(a, q, years=3, min_yoy_quarters=6):
    """Annual EBITDA higher every year AND quarterly YoY up in enough recent quarters."""
    annual_ok = len(a) >= years and strictly_rising(a["ebitda_cr"].tail(years))
    e = q["ebitda_cr"]
    if len(e) < 12:
        return False
    yoy_up = (e > e.shift(4)).tail(8)
    return annual_ok and int(yoy_up.sum()) >= min_yoy_quarters


def hard_filters(c, a, q):
    reasons = []
    if not num(c["market_cap_cr"], 0) > MIN_MARKET_CAP_CR:
        reasons.append(f"market cap not above Rs {MIN_MARKET_CAP_CR} cr")
    if not roce_rising(a):
        reasons.append("ROCE not rising in each of the last 3 years")
    if not ebitda_rising_regularly(a, q):
        reasons.append("EBITDA not rising regularly")
    return len(reasons) == 0, reasons


def recent_orders(o, as_of=AS_OF, window_days=ORDER_WINDOW_DAYS):
    """Orders in the window. MoU and framework agreements are never counted."""
    start = as_of - pd.Timedelta(days=window_days)
    w = o[(o["announce_date"] > start) & (o["announce_date"] <= as_of)].copy()
    gst = w["gst_inclusive"].eq(True)
    w["value_ex_gst_cr"] = w["value_cr"].where(~gst, w["value_cr"] / (1 + GST_RATE))
    counted = w[w["status"].isin(["firm", "L1", "LoI"])]
    firm = counted[counted["status"] == "firm"]
    pending = counted[counted["status"].isin(["L1", "LoI"])]
    return w, firm, pending, counted


def net_margin(c, a):
    """Management-guided net margin if given, else 3-year average PAT/revenue."""
    guided = num(c.get("guided_net_margin"))
    if guided is not None:
        return guided
    last3 = a.tail(3)
    return float((last3["pat_cr"] / last3["revenue_cr"]).mean())


def order_metrics(orders_df, c, a, q):
    ttm_rev, ttm_pat = ttm(q, "revenue_cr"), ttm(q, "pat_cr")
    mcap = num(c["market_cap_cr"])
    known = orders_df[orders_df["value_ex_gst_cr"].notna()]
    total = float(known["value_ex_gst_cr"].sum()) if len(known) else 0.0
    period = known["execution_years"].astype(float) if len(known) else pd.Series(dtype=float)
    with_period = known[period.notna() & (period > 0)] if len(known) else known
    annual = (
        float((with_period["value_ex_gst_cr"] / with_period["execution_years"].astype(float)).sum())
        if len(with_period)
        else 0.0
    )
    implied_pat = (ttm_rev + annual) * net_margin(c, a) if ttm_rev else None
    return {
        "order_value_cr": total,
        "orders_missing_value": int(orders_df["value_ex_gst_cr"].isna().sum()) if len(orders_df) else 0,
        "orders_missing_period": int(len(known) - len(with_period)),
        "order_to_revenue": total / ttm_rev if ttm_rev else None,
        "order_to_mcap": total / mcap if mcap else None,
        "annual_rev_from_orders_cr": annual,
        "capacity_stretch": annual / ttm_rev if ttm_rev else None,
        "order_implied_pat_cr": implied_pat,
        "forward_pe": mcap / implied_pat if implied_pat and implied_pat > 0 else None,
        "trailing_pe": mcap / ttm_pat if ttm_pat and ttm_pat > 0 else None,
    }


def ttm_ebitda_margin(q, quarters_back=0):
    """TTM EBITDA margin %, optionally measured `quarters_back` quarters ago."""
    sub = q.iloc[: len(q) - quarters_back] if quarters_back else q
    r, e = ttm(sub, "revenue_cr"), ttm(sub, "ebitda_cr")
    return e / r * 100 if r and e is not None else None


def sustained_book_to_bill(q, threshold=1.2, quarters=4):
    """Rolling 4-quarter book-to-bill above threshold at each recent quarter-end."""
    if "order_inflow_cr" not in q.columns or len(q) < quarters + 3:
        return None
    ratio = (
        q["order_inflow_cr"].rolling(4).sum() / q["revenue_cr"].rolling(4).sum()
    ).tail(quarters)
    if ratio.isna().any():
        return None
    return bool((ratio > threshold).all())


def company_metrics(a, q):
    latest, prev = a.iloc[-1], a.iloc[-2]
    last3 = a.tail(3)
    ttm_rev = ttm(q, "revenue_cr")

    def rec_days(row):
        return row["receivables_cr"] / row["revenue_cr"] * 365

    def exec_rate(row):
        ob = num(row.get("opening_order_book_cr"))
        return row["revenue_cr"] / ob if ob else None

    ob_latest = num(q["order_book_cr"].iloc[-1]) if "order_book_cr" in q.columns else None
    inflow4 = ttm(q, "order_inflow_cr")
    cagr = None
    if len(a) >= 4 and a["revenue_cr"].iloc[-4] > 0:
        cagr = (a["revenue_cr"].iloc[-1] / a["revenue_cr"].iloc[-4]) ** (1 / 3) - 1
    return {
        "ttm_revenue_cr": ttm_rev,
        "roce_latest_pct": float(roce_pct(a).iloc[-1]),
        "revenue_cagr_3y": cagr,
        "receivable_days": rec_days(latest),
        "receivable_days_prev": rec_days(prev),
        "cash_conversion_3y": float(last3["ocf_cr"].sum() / last3["ebitda_cr"].sum()),
        "debt_to_equity": latest["debt_cr"] / latest["equity_cr"],
        "net_debt_cr": latest["debt_cr"] - latest["cash_cr"],
        "net_debt_prev_cr": prev["debt_cr"] - prev["cash_cr"],
        "visibility_years": ob_latest / ttm_rev if ob_latest and ttm_rev else None,
        "book_to_bill_4q": inflow4 / ttm_rev if inflow4 is not None and ttm_rev else None,
        "sustained_book_to_bill": sustained_book_to_bill(q),
        "ebitda_margin_ttm": ttm_ebitda_margin(q),
        "ebitda_margin_ttm_prev": ttm_ebitda_margin(q, 4),
        "exec_rate": exec_rate(latest),
        "exec_rate_prev": exec_rate(prev),
    }


def has_repeat_client(o, as_of=AS_OF):
    """Same client gave 2+ firm orders in the last 24 months."""
    start = as_of - pd.Timedelta(days=REPEAT_CLIENT_DAYS)
    f = o[(o["status"] == "firm") & (o["announce_date"] > start) & (o["announce_date"] <= as_of)]
    if f.empty:
        return False
    return bool((f["client"].value_counts() >= 2).any())


def inclusion(c, m, firm_m, pend_m, repeat_client):
    def big(x):
        return (x["order_to_revenue"] or 0) >= 1 or (x["order_to_mcap"] or 0) >= 1

    pipeline = num(c.get("mgmt_pipeline_cr"))
    ttm_rev = m["ttm_revenue_cr"]
    pipeline_ok = pipeline is not None and bool(ttm_rev) and pipeline >= 2 * ttm_rev
    return {
        "A_firm_big": big(firm_m),
        "B_pending_big": big(pend_m),
        "C_repeatable": pipeline_ok or repeat_client or yes(c.get("sector_tailwind")),
    }


def red_flags(c, a, m, window_all, counted):
    flags = []
    nonbinding = window_all["status"].isin(["MoU", "framework"])
    if (nonbinding & window_all["headline_claims_order"].eq(True)).any():
        flags.append("non-binding agreement announced as an order")
    if counted["related_party"].eq(True).any() or counted["client_verifiable"].eq(False).any():
        flags.append("related-party or unverifiable client")
    biggest = counted["value_ex_gst_cr"].max() if len(counted) else float("nan")
    if pd.notna(biggest) and biggest > 5 * a["revenue_cr"].max() and not yes(c.get("capacity_funded")):
        flags.append("order > 5x best-ever annual revenue, no funded plan")
    if yes(c.get("preferential_to_unknown_after_order")) or yes(c.get("promoter_selling_after_order")):
        flags.append("preferential issue to unknowns or promoter selling after order")
    if (
        num(c.get("avg_daily_traded_value_cr"), 999) < 1
        and len(window_all) >= 3
        and yes(c.get("repeated_upper_circuits"))
    ):
        flags.append("illiquid stock with repeated order news and upper circuits")
    last2 = a.tail(2)
    if (last2["ocf_cr"] < 0).all() and last2["pat_cr"].iloc[-1] > last2["pat_cr"].iloc[0]:
        flags.append("rising profit with negative operating cash flow for 2 years")
    if m["receivable_days"] > 180 and m["receivable_days"] > m["receivable_days_prev"]:
        flags.append("receivable days above 180 and rising")
    if yes(c.get("auditor_issue_24m")):
        flags.append("auditor resignation, qualified opinion or regulatory action")
    return flags


def quality_score(c, m, all_m, counted):
    """8 checks, 0-2 points each, max 16."""
    s = {}
    if yes(c.get("major_cancellations_3y")):
        s["execution_record"] = 0
    else:
        s["execution_record"] = 2 if (m["revenue_cagr_3y"] or 0) >= 0.10 else 1
    total = counted["value_ex_gst_cr"].sum() if len(counted) else 0
    strong = (
        counted.loc[counted["client_type"].isin(STRONG_CLIENT_TYPES), "value_ex_gst_cr"].sum()
        if len(counted)
        else 0
    )
    s["order_quality"] = (1 if total and strong / total >= 0.7 else 0) + (
        0 if len(counted) and counted["price_variation_clause"].eq(False).any() else 1
    )
    now, before = m["ebitda_margin_ttm"], m["ebitda_margin_ttm_prev"]
    s["margins"] = 0 if now is None or before is None else (
        2 if now >= before else 1 if now >= before - 1 else 0
    )
    s["working_capital"] = int(m["receivable_days"] <= m["receivable_days_prev"]) + int(
        m["cash_conversion_3y"] >= 0.6
    )
    dil_ok = num(c.get("dilution_12m_pct"), 0) <= 1 or yes(c.get("dilution_for_capacity"))
    s["balance_sheet"] = int(m["debt_to_equity"] < 0.5) + int(dil_ok)
    stretch = all_m["capacity_stretch"]
    s["capacity"] = (
        2 if stretch is not None and stretch <= 1 else 1 if yes(c.get("capacity_funded")) else 0
    )
    s["promoters"] = int(num(c.get("promoter_holding_change_pct_1y"), -1) >= 0) + int(
        num(c.get("pledge_pct"), 100) <= 1
    )
    top = num(c.get("top_client_share_pct"))
    s["concentration"] = 0 if top is None else 2 if top < 50 else 1 if top < 70 else 0
    return s


def trigger_checks(c, m, firm_m, repeat_client):
    """The 10 healthy triggers. True / False, or None = data not found."""
    t = {}
    t["1_sustained_order_inflow"] = m["sustained_book_to_bill"]
    er, er_prev = m["exec_rate"], m["exec_rate_prev"]
    t["2_execution_ability"] = None if er is None or er_prev is None else er >= 0.9 * er_prev
    cap = c.get("capacity_commissioned_within_12m")
    t["3_capacity_added"] = None if num(cap) is None else yes(cap)
    now, before = m["ebitda_margin_ttm"], m["ebitda_margin_ttm_prev"]
    t["4_operating_leverage"] = None if now is None or before is None else now - before >= 2
    t["5_cash_conversion"] = m["cash_conversion_3y"] >= 0.6 and m["receivable_days"] <= m["receivable_days_prev"]
    t["6_rising_roce_18plus"] = m["roce_latest_pct"] >= 18
    debt_ok = m["net_debt_cr"] <= 0 or m["net_debt_cr"] < m["net_debt_prev_cr"]
    dil_ok = num(c.get("dilution_12m_pct"), 0) <= 1 or yes(c.get("dilution_for_capacity"))
    t["7_clean_balance_sheet"] = debt_ok and dil_ok
    tail = c.get("sector_tailwind")
    t["8_sector_tailwind"] = None if num(tail) is None else yes(tail)
    t["9_client_upgrade"] = yes(c.get("new_marquee_client_12m")) or repeat_client
    fpe, median = firm_m["forward_pe"], num(c.get("sector_median_forward_pe"))
    t["10_rerating_room"] = None if fpe is None or median is None else fpe < median
    return {k: (None if v is None else bool(v)) for k, v in t.items()}


def screen(companies, annual, quarterly, orders, as_of=AS_OF):
    """Returns (shortlist, rejected). Shortlist ranked by trigger score, then quality."""
    shortlist, rejected = [], []
    for _, c in companies.iterrows():
        sym = c["symbol"]
        a = annual[annual["symbol"] == sym].sort_values("fiscal_year").reset_index(drop=True)
        q = quarterly[quarterly["symbol"] == sym].sort_values("quarter_end").reset_index(drop=True)
        o = orders[orders["symbol"] == sym]
        if len(a) < 3 or len(q) < 12:
            rejected.append({"symbol": sym, "reason": "not enough history (3 years + 12 quarters)"})
            continue
        ok, reasons = hard_filters(c, a, q)
        if not ok:
            rejected.append({"symbol": sym, "reason": "; ".join(reasons)})
            continue
        window_all, firm, pending, counted = recent_orders(o, as_of)
        m = company_metrics(a, q)
        firm_m = order_metrics(firm, c, a, q)
        pend_m = order_metrics(pending, c, a, q)
        all_m = order_metrics(counted, c, a, q)
        repeat = has_repeat_client(o, as_of)
        inc = inclusion(c, m, firm_m, pend_m, repeat)
        if not ((inc["A_firm_big"] or inc["B_pending_big"]) and inc["C_repeatable"]):
            why = (
                "orders too small vs revenue and market cap"
                if not (inc["A_firm_big"] or inc["B_pending_big"])
                else "no evidence of repeatable pipeline"
            )
            rejected.append({"symbol": sym, "reason": why})
            continue
        flags = red_flags(c, a, m, window_all, counted)
        if len(flags) >= 2:
            rejected.append({"symbol": sym, "reason": "red flags: " + "; ".join(flags)})
            continue
        qs = quality_score(c, m, all_m, counted)
        tr = trigger_checks(c, m, firm_m, repeat)
        shortlist.append({
            "symbol": sym,
            "sector": c.get("sector"),
            "status": "Firm" if inc["A_firm_big"] else "L1/LoI only",
            "firm_order_cr": firm_m["order_value_cr"],
            "pending_order_cr": pend_m["order_value_cr"],
            "firm_order_to_revenue": firm_m["order_to_revenue"],
            "firm_order_to_mcap": firm_m["order_to_mcap"],
            "pending_order_to_revenue": pend_m["order_to_revenue"],
            "pending_order_to_mcap": pend_m["order_to_mcap"],
            "visibility_years": m["visibility_years"],
            "book_to_bill_4q": m["book_to_bill_4q"],
            "trailing_pe": firm_m["trailing_pe"],
            "forward_pe_firm": firm_m["forward_pe"],
            "forward_pe_firm_plus_pending": all_m["forward_pe"],
            "roce_latest_pct": m["roce_latest_pct"],
            "quality_score": sum(qs.values()),
            "trigger_score": sum(1 for v in tr.values() if v is True),
            "triggers_not_found": [k for k, v in tr.items() if v is None],
            "red_flags": flags,
            "orders_missing_period": all_m["orders_missing_period"],
            "quality_detail": qs,
            "trigger_detail": tr,
            "decision": "review",
        })
    sl = pd.DataFrame(shortlist)
    if len(sl):
        sl = sl.sort_values(["trigger_score", "quality_score"], ascending=False).reset_index(drop=True)
    return sl, pd.DataFrame(rejected)


def _read_table(name: str) -> Optional[pd.DataFrame]:
    path = STORE_DIR / f"{name}.json"
    if not path.exists():
        return None
    rows = json.loads(path.read_text(encoding="utf-8"))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for col in ("announce_date", "quarter_end"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


def tables_available() -> bool:
    needed = ("companies", "annual", "quarterly", "orders")
    return all((STORE_DIR / f"{name}.json").exists() for name in needed)


def screen_stored(*, as_of: Optional[pd.Timestamp] = None) -> dict[str, Any]:
    """Run Agent 10 on JSON tables under data/quant_foundation/order_book/."""
    if not tables_available():
        return {"skipped": True, "reason": "no_order_tables", "shortlist": [], "rejected": []}
    companies = _read_table("companies")
    annual = _read_table("annual")
    quarterly = _read_table("quarterly")
    orders = _read_table("orders")
    if companies is None or companies.empty:
        return {"skipped": True, "reason": "empty_companies", "shortlist": [], "rejected": []}
    sl, rejected = screen(companies, annual, quarterly, orders, as_of=as_of or AS_OF)
    payload = {
        "as_of": str((as_of or AS_OF).date()),
        "run_at": datetime.now(timezone.utc).isoformat(),
        "shortlist": sl.to_dict(orient="records"),
        "rejected": rejected.to_dict(orient="records"),
        "note": "Research watchlist. Review before any order. Not a buy or sell.",
    }
    SCREEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SCREEN_CACHE.write_text(json.dumps(payload, default=str, indent=2), encoding="utf-8")
    return payload


def load_order_book_screen() -> Optional[dict[str, Any]]:
    if not SCREEN_CACHE.exists():
        return None
    try:
        return json.loads(SCREEN_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return None
