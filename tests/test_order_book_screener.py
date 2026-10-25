"""Hand-worked XYZ / PQR cases from the order-book screener spec."""
import pandas as pd

from quant_layer.order_book_screener import screen

QUARTER_ENDS = pd.date_range("2023-09-30", periods=12, freq="QE")


def quarters(symbol, revenue, margin_start, margin_step, pat_margin, inflow_mult, order_book):
    rows = []
    for i, (d, r) in enumerate(zip(QUARTER_ENDS, revenue)):
        rows.append({
            "symbol": symbol,
            "quarter_end": d,
            "revenue_cr": r,
            "ebitda_cr": r * (margin_start + margin_step * i),
            "pat_cr": r * pat_margin,
            "order_inflow_cr": r * inflow_mult,
            "order_book_cr": order_book,
        })
    return rows


def years(symbol, revenue, ebitda, ebit, equity, debt, cash, ocf, receivables, pat_margin, opening_ob):
    return [{
        "symbol": symbol,
        "fiscal_year": 2023 + i,
        "revenue_cr": revenue[i],
        "ebitda_cr": ebitda[i],
        "ebit_cr": ebit[i],
        "pat_cr": revenue[i] * pat_margin,
        "equity_cr": equity[i],
        "debt_cr": debt[i],
        "cash_cr": cash[i],
        "ocf_cr": ocf[i],
        "receivables_cr": receivables[i],
        "opening_order_book_cr": opening_ob[i],
    } for i in range(4)]


def order(sym, date, value, status, years_, client="PowerGrid", ctype="psu",
          related=False, verifiable=True, pvc=True, claims=True, gst=False):
    return {
        "symbol": sym,
        "announce_date": pd.Timestamp(date),
        "value_cr": value,
        "client": client,
        "client_type": ctype,
        "status": status,
        "execution_years": years_,
        "related_party": related,
        "client_verifiable": verifiable,
        "price_variation_clause": pvc,
        "headline_claims_order": claims,
        "gst_inclusive": gst,
        "source_url": "test",
    }


def _fixture():
    xyz_rev = [68, 70, 72, 75, 80, 83, 86, 90, 95, 98, 102, 105]
    pqr_rev = [100, 104, 108, 112, 120, 125, 130, 135, 145, 148, 152, 155]
    good = dict(
        revenue=[250, 290, 340, 390],
        ebitda=[30, 37, 46, 56],
        ebit=[24, 30, 38, 47],
        equity=[150, 165, 185, 210],
        debt=[40, 35, 30, 25],
        cash=[10, 15, 20, 30],
        ocf=[22, 28, 35, 44],
        receivables=[60, 68, 78, 88],
        pat_margin=0.08,
        opening_ob=[300, 380, 480, 600],
    )
    annual = []
    annual += years("XYZ", **good)
    annual += years("PQR", **{**good, "revenue": [380, 430, 490, 560], "pat_margin": 0.075})
    annual += years("LOWR", **{**good, "ebit": [40, 38, 36, 35]})
    annual += years("TINY", **good)
    annual += years("FLAG", **good)
    quarterly = []
    for sym in ["XYZ", "LOWR", "TINY", "FLAG"]:
        quarterly += quarters(sym, xyz_rev, 0.13, 0.003, 0.08, 1.3, 700)
    quarterly += quarters("PQR", pqr_rev, 0.12, 0.003, 0.075, 1.3, 900)
    base = dict(
        avg_daily_traded_value_cr=3,
        sector="Power T&D",
        sector_median_forward_pe=22,
        guided_net_margin=None,
        capacity_commissioned_within_12m=True,
        capacity_funded=True,
        new_marquee_client_12m=False,
        sector_tailwind=True,
        major_cancellations_3y=False,
        dilution_12m_pct=0,
        dilution_for_capacity=False,
        promoter_holding_change_pct_1y=0.5,
        pledge_pct=0,
        top_client_share_pct=35,
        mgmt_pipeline_cr=1500,
        preferential_to_unknown_after_order=False,
        promoter_selling_after_order=False,
        repeated_upper_circuits=False,
        auditor_issue_24m=False,
    )
    companies = pd.DataFrame([
        {**base, "symbol": "XYZ", "market_cap_cr": 800},
        {**base, "symbol": "PQR", "market_cap_cr": 1500, "guided_net_margin": 0.09},
        {**base, "symbol": "LOWR", "market_cap_cr": 900},
        {**base, "symbol": "TINY", "market_cap_cr": 120},
        {**base, "symbol": "FLAG", "market_cap_cr": 700, "auditor_issue_24m": True},
    ])
    orders = pd.DataFrame([
        order("XYZ", "2026-07-15", 1200, "firm", 4),
        order("XYZ", "2025-03-10", 150, "firm", 2),
        order("PQR", "2026-08-20", 2100, "L1", 3),
        order("LOWR", "2026-07-01", 1500, "firm", 4),
        order("TINY", "2026-07-01", 500, "firm", 3),
        order("FLAG", "2026-06-01", 5000, "MoU", None),
        order("FLAG", "2026-07-01", 900, "firm", 3, client="Group Co", related=True),
    ])
    return companies, pd.DataFrame(annual), pd.DataFrame(quarterly), orders


def test_order_book_screener_matches_spec():
    companies, annual, quarterly, orders = _fixture()
    shortlist, rejected = screen(companies, annual, quarterly, orders)
    x = shortlist.set_index("symbol")
    assert abs(x.loc["XYZ", "firm_order_to_revenue"] - 3.0) < 1e-9
    assert abs(x.loc["XYZ", "firm_order_to_mcap"] - 1.5) < 1e-9
    assert abs(x.loc["XYZ", "trailing_pe"] - 25.0) < 1e-9
    assert abs(x.loc["XYZ", "forward_pe_firm"] - 800 / 56) < 1e-9
    assert abs(x.loc["PQR", "pending_order_to_revenue"] - 3.5) < 1e-9
    assert abs(x.loc["PQR", "pending_order_to_mcap"] - 1.4) < 1e-9
    assert abs(x.loc["PQR", "forward_pe_firm_plus_pending"] - 1500 / 117) < 1e-9
    assert abs(x.loc["PQR", "trailing_pe"] - 1500 / 45) < 1e-9
    assert x.loc["XYZ", "trigger_score"] == 9 and x.loc["PQR", "trigger_score"] == 7
    assert x.loc["XYZ", "quality_score"] == 16 and x.loc["PQR", "quality_score"] == 15
    r = rejected.set_index("symbol")["reason"]
    assert "ROCE" in r["LOWR"] and "market cap" in r["TINY"] and "red flags" in r["FLAG"]
