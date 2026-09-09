"""Convert locally saved Alpha Vantage responses into the RAG analyzer input format."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR


def safe_name(symbol: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", symbol.upper())


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def number(value: Any) -> Optional[float]:
    try:
        return float(value) if value not in (None, "", "None", "-") else None
    except (TypeError, ValueError):
        return None


def pct_change(new: Optional[float], old: Optional[float]) -> Optional[float]:
    return round((new / old - 1) * 100, 2) if new is not None and old not in (None, 0) else None


def ratio_pct(numerator: Optional[float], denominator: Optional[float]) -> Optional[float]:
    return round(numerator / denominator * 100, 2) if numerator is not None and denominator not in (None, 0) else None


def pick(report: dict[str, Any], field: str) -> Optional[float]:
    return number(report.get(field))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a stock JSON input from downloaded Alpha Vantage files.")
    parser.add_argument("symbol", help="same symbol passed to fetch_stock_data.py")
    args = parser.parse_args()
    raw_dir = BASE_DIR / "data" / "raw" / safe_name(args.symbol)
    daily = load(raw_dir / "daily_adjusted.json").get("Time Series (Daily)", {})
    if not daily:
        raise SystemExit("Missing daily data. Run fetch_stock_data.py first.")
    rows = [(day, values) for day, values in sorted(daily.items(), reverse=True)]
    closes = [number(row.get("5. adjusted close") or row.get("4. close")) for _, row in rows]
    closes = [value for value in closes if value is not None]
    latest = closes[0]
    high_52 = max(closes[: min(len(closes), 252)])
    overview = load(raw_dir / "overview.json")
    income = load(raw_dir / "income_statement.json").get("annualReports", [])
    cashflow = load(raw_dir / "cash_flow.json").get("annualReports", [])
    current_income, previous_income = (income + [{}, {}])[:2]
    current_cashflow = (cashflow + [{}])[0]
    revenue = pick(current_income, "totalRevenue")
    previous_revenue = pick(previous_income, "totalRevenue")
    eps = number(overview.get("EPS"))
    stock = {
        "ticker": args.symbol.upper(),
        "company_name": overview.get("Name") or args.symbol.upper(),
        "sector": overview.get("Sector") or "unknown",
        "price": latest,
        "market_cap": number(overview.get("MarketCapitalization")),
        "data_as_of": rows[0][0],
        "financials": {
            "revenue_growth_yoy_pct": pct_change(revenue, previous_revenue),
            "gross_margin_pct": ratio_pct(pick(current_income, "grossProfit"), revenue),
            "operating_margin_pct": ratio_pct(pick(current_income, "operatingIncome"), revenue),
            "free_cash_flow": pick(current_cashflow, "operatingCashflow"),
            "debt_to_equity": number(overview.get("DebtToEquity")),
            "roe_pct": number(overview.get("ReturnOnEquityTTM")) and round(number(overview["ReturnOnEquityTTM"]) * 100, 2),
            "eps": eps,
        },
        "valuation": {
            "pe_ratio": number(overview.get("PERatio")),
            "peg_ratio": number(overview.get("PEGRatio")),
            "price_to_sales": number(overview.get("PriceToSalesRatioTTM")),
        },
        "price_performance": {
            "one_month_pct": pct_change(latest, closes[min(21, len(closes) - 1)]),
            "six_month_pct": pct_change(latest, closes[min(126, len(closes) - 1)]),
            "one_year_pct": pct_change(latest, closes[min(252, len(closes) - 1)]),
            "distance_from_52_week_high_pct": pct_change(latest, high_52),
        },
        "notes": [
            "Generated from Alpha Vantage raw files stored locally.",
            "Fundamental fields remain null when the provider did not supply coverage."
        ]
    }
    output_dir = BASE_DIR / "data" / "stock_inputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_name(args.symbol)}.json"
    output_path.write_text(json.dumps(stock, indent=2), encoding="utf-8")
    print(f"Created {output_path}")


if __name__ == "__main__":
    main()
