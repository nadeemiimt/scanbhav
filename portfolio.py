"""Local paper portfolio: buy/sell stocks & mutual funds with broker fees + Indian tax.

Stores holdings in data/portfolio/holdings.json and a human-readable holdings.txt.
Fee schedules approximate public Zerodha / Groww equity delivery & intraday charges (educational).
Tax rates reflect post-Budget 2024 equity STCG/LTCG rules as commonly applied — verify with a CA.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from config import BASE_DIR

PORTFOLIO_DIR = BASE_DIR / "data" / "portfolio"
HOLDINGS_JSON = PORTFOLIO_DIR / "holdings.json"
HOLDINGS_TXT = PORTFOLIO_DIR / "holdings.txt"

AssetType = Literal["stock", "mutual_fund"]
Broker = Literal["zerodha", "groww"]

# Equity delivery / MF redemption approximate charges (₹ and %).
# Sources: public Zerodha / Groww pricing pages (subject to change; educational).
BROKER_FEES: dict[str, dict[str, Any]] = {
    "zerodha": {
        "label": "Zerodha",
        "equity_delivery": {
            "brokerage_pct": 0.0,
            "brokerage_flat": 0.0,
            "stt_buy_pct": 0.1,   # on buy
            "stt_sell_pct": 0.1,  # on sell
            "exchange_txn_pct": 0.00297,  # NSE approx
            "sebi_pct": 0.0001,
            "gst_pct": 18.0,  # on (brokerage + exchange + sebi)
            "stamp_buy_pct": 0.015,
            "dp_sell_flat": 15.34,  # approx incl GST
        },
        "equity_intraday": {
            "brokerage_pct": 0.03,
            "brokerage_cap": 20.0,
            "stt_buy_pct": 0.0,
            "stt_sell_pct": 0.025,
            "exchange_txn_pct": 0.00297,
            "sebi_pct": 0.0001,
            "gst_pct": 18.0,
            "stamp_buy_pct": 0.003,
            "dp_sell_flat": 0.0,
        },
        "mutual_fund": {
            "brokerage_pct": 0.0,
            "brokerage_flat": 0.0,
            "stt_buy_pct": 0.0,
            "stt_sell_pct": 0.001,  # equity-oriented MF sell approx
            "exchange_txn_pct": 0.0,
            "sebi_pct": 0.0,
            "gst_pct": 18.0,
            "stamp_buy_pct": 0.0,
            "dp_sell_flat": 0.0,
            "note": "Direct MF via Groww/Zerodha Coin typically ₹0 commission; STT on equity MF redemption.",
        },
    },
    "groww": {
        "label": "Groww",
        "equity_delivery": {
            "brokerage_pct": 0.0,  # delivery often ₹0 / free brokerage campaigns — model ₹0
            "brokerage_flat": 0.0,
            "stt_buy_pct": 0.1,
            "stt_sell_pct": 0.1,
            "exchange_txn_pct": 0.00297,
            "sebi_pct": 0.0001,
            "gst_pct": 18.0,
            "stamp_buy_pct": 0.015,
            "dp_sell_flat": 16.5,
        },
        "equity_intraday": {
            "brokerage_pct": 0.05,  # Groww often higher than Zerodha; capped models vary — use 0.05% / ₹20 style
            "brokerage_cap": 20.0,
            "stt_buy_pct": 0.0,
            "stt_sell_pct": 0.025,
            "exchange_txn_pct": 0.00297,
            "sebi_pct": 0.0001,
            "gst_pct": 18.0,
            "stamp_buy_pct": 0.003,
            "dp_sell_flat": 0.0,
        },
        "mutual_fund": {
            "brokerage_pct": 0.0,
            "brokerage_flat": 0.0,
            "stt_buy_pct": 0.0,
            "stt_sell_pct": 0.001,
            "exchange_txn_pct": 0.0,
            "sebi_pct": 0.0,
            "gst_pct": 18.0,
            "stamp_buy_pct": 0.0,
            "dp_sell_flat": 0.0,
            "note": "Direct mutual funds typically commission-free on Groww.",
        },
    },
}

# Indian equity / equity-MF capital gains (post July 2024 common understanding).
TAX_RULES = {
    "equity_stcg_pct": 20.0,       # holding < 12 months
    "equity_ltcg_pct": 12.5,       # holding >= 12 months
    "equity_ltcg_exemption": 125_000.0,  # annual exemption on LTCG
    "debt_mf_slab": True,          # debt MF / non-equity often taxed at slab (simplified)
    "holding_ltcg_days": 365,
    "note": "Illustrative FY rules for listed equity & equity-oriented MF. Debt MF often taxed at slab. Confirm with a tax professional.",
}

TAX_BRACKETS = [
    {"id": "slab_0", "label": "Nil / rebate zone (~0%)", "rate_pct": 0.0},
    {"id": "slab_5", "label": "5% slab", "rate_pct": 5.0},
    {"id": "slab_10", "label": "10% slab", "rate_pct": 10.0},
    {"id": "slab_15", "label": "15% slab", "rate_pct": 15.0},
    {"id": "slab_20", "label": "20% slab", "rate_pct": 20.0},
    {"id": "slab_30", "label": "30% slab", "rate_pct": 30.0},
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _default_state() -> dict[str, Any]:
    return {
        "version": 1,
        "updated_at": _now_iso(),
        "settings": {
            "broker": "zerodha",
            "tax_bracket_id": "slab_30",
            "tax_bracket_rate_pct": 30.0,
            "ltcg_exemption_used": 0.0,
        },
        "holdings": [],
        "closed": [],
        "alerts": [],
    }


def ensure_store() -> dict[str, Any]:
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    if not HOLDINGS_JSON.exists():
        state = _default_state()
        save_state(state)
        return state
    try:
        state = json.loads(HOLDINGS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        state = _default_state()
        save_state(state)
    return state


def save_state(state: dict[str, Any]) -> None:
    PORTFOLIO_DIR.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = _now_iso()
    HOLDINGS_JSON.write_text(json.dumps(state, indent=2), encoding="utf-8")
    HOLDINGS_TXT.write_text(_render_txt(state), encoding="utf-8")


def _render_txt(state: dict[str, Any]) -> str:
    lines = [
        "ScanBhav — Local Portfolio",
        f"Updated: {state.get('updated_at')}",
        f"Broker: {state.get('settings', {}).get('broker')}",
        f"Tax bracket: {state.get('settings', {}).get('tax_bracket_id')} "
        f"({state.get('settings', {}).get('tax_bracket_rate_pct')}%)",
        "",
        "OPEN HOLDINGS",
        "-" * 72,
    ]
    for h in state.get("holdings") or []:
        lines.append(
            f"{h.get('symbol')} | {h.get('asset_type')} | qty={h.get('quantity')} | "
            f"avg={h.get('avg_price')} | bought={h.get('bought_at')} | id={h.get('id')}"
        )
    lines += ["", "CLOSED / SOLD", "-" * 72]
    for c in (state.get("closed") or [])[-50:]:
        lines.append(
            f"{c.get('symbol')} | qty={c.get('quantity')} | buy={c.get('buy_price')} sell={c.get('sell_price')} | "
            f"net={c.get('net_proceeds')} | pnl={c.get('pnl_after_tax')} | {c.get('sold_at')}"
        )
    lines += ["", "ALERTS", "-" * 72]
    for a in (state.get("alerts") or [])[:20]:
        lines.append(f"{a.get('level')} | {a.get('symbol')} | {a.get('message')}")
    lines.append("")
    return "\n".join(lines)


def list_brokers() -> list[dict[str, Any]]:
    out = []
    for key, meta in BROKER_FEES.items():
        out.append({
            "id": key,
            "label": meta["label"],
            "delivery": meta["equity_delivery"],
            "intraday": meta["equity_intraday"],
            "mutual_fund": meta["mutual_fund"],
        })
    return out


def list_tax_brackets() -> list[dict[str, Any]]:
    return list(TAX_BRACKETS)


def update_settings(
    broker: Optional[str] = None,
    tax_bracket_id: Optional[str] = None,
    tax_bracket_rate_pct: Optional[float] = None,
) -> dict[str, Any]:
    state = ensure_store()
    settings = state.setdefault("settings", {})
    if broker:
        if broker not in BROKER_FEES:
            raise ValueError(f"Unknown broker: {broker}")
        settings["broker"] = broker
    if tax_bracket_id:
        match = next((b for b in TAX_BRACKETS if b["id"] == tax_bracket_id), None)
        if not match and tax_bracket_rate_pct is None:
            raise ValueError(f"Unknown tax bracket: {tax_bracket_id}")
        settings["tax_bracket_id"] = tax_bracket_id
        if match:
            settings["tax_bracket_rate_pct"] = match["rate_pct"]
    if tax_bracket_rate_pct is not None:
        settings["tax_bracket_rate_pct"] = float(tax_bracket_rate_pct)
    save_state(state)
    return state


def _fee_schedule(broker: str, asset_type: str, intraday: bool) -> dict[str, Any]:
    meta = BROKER_FEES.get(broker) or BROKER_FEES["zerodha"]
    if asset_type == "mutual_fund":
        return meta["mutual_fund"]
    return meta["equity_intraday"] if intraday else meta["equity_delivery"]


def estimate_charges(
    *,
    side: Literal["buy", "sell"],
    turnover: float,
    broker: str,
    asset_type: str = "stock",
    intraday: bool = False,
) -> dict[str, float]:
    """Break down statutory + brokerage charges for one leg."""
    sch = _fee_schedule(broker, asset_type, intraday)
    brokerage = turnover * float(sch.get("brokerage_pct") or 0) / 100.0
    if sch.get("brokerage_flat"):
        brokerage += float(sch["brokerage_flat"])
    if sch.get("brokerage_cap") is not None:
        brokerage = min(brokerage, float(sch["brokerage_cap"])) if brokerage > 0 else 0.0
        # Zerodha-style: max(₹20, 0.03%) per order — already capped
        if float(sch.get("brokerage_pct") or 0) > 0 and brokerage == 0 and turnover > 0:
            brokerage = min(turnover * float(sch["brokerage_pct"]) / 100.0, float(sch["brokerage_cap"]))

    stt_key = "stt_buy_pct" if side == "buy" else "stt_sell_pct"
    stt = turnover * float(sch.get(stt_key) or 0) / 100.0
    exchange = turnover * float(sch.get("exchange_txn_pct") or 0) / 100.0
    sebi = turnover * float(sch.get("sebi_pct") or 0) / 100.0
    stamp = turnover * float(sch.get("stamp_buy_pct") or 0) / 100.0 if side == "buy" else 0.0
    gst = (brokerage + exchange + sebi) * float(sch.get("gst_pct") or 0) / 100.0
    dp = float(sch.get("dp_sell_flat") or 0) if side == "sell" else 0.0
    total = brokerage + stt + exchange + sebi + stamp + gst + dp
    return {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_txn": round(exchange, 2),
        "sebi": round(sebi, 4),
        "stamp_duty": round(stamp, 2),
        "gst": round(gst, 2),
        "dp_charges": round(dp, 2),
        "total": round(total, 2),
    }


def _parse_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return date.today()


def _holding_days(bought_at: str, as_of: Optional[str] = None) -> int:
    start = _parse_date(bought_at)
    end = _parse_date(as_of) if as_of else date.today()
    return max((end - start).days, 0)


def compute_tax(
    *,
    buy_value: float,
    sell_value: float,
    holding_days: int,
    asset_type: str,
    tax_bracket_rate_pct: float,
    ltcg_exemption_remaining: float,
    equity_oriented: bool = True,
    intraday: bool = False,
) -> dict[str, Any]:
    gain = sell_value - buy_value
    if gain <= 0:
        return {
            "gain": round(gain, 2),
            "taxable_gain": 0.0,
            "tax": 0.0,
            "regime": "loss_or_flat",
            "rate_pct": 0.0,
            "exemption_applied": 0.0,
            "is_long_term": holding_days >= TAX_RULES["holding_ltcg_days"],
        }

    # Same-day equity trades are typically speculative business income → slab (simplified).
    if intraday and asset_type == "stock":
        rate = tax_bracket_rate_pct
        tax = gain * rate / 100.0
        return {
            "gain": round(gain, 2),
            "taxable_gain": round(gain, 2),
            "tax": round(tax, 2),
            "regime": "intraday_slab",
            "rate_pct": rate,
            "exemption_applied": 0.0,
            "is_long_term": False,
        }

    is_lt = holding_days >= TAX_RULES["holding_ltcg_days"]
    # Debt / non-equity MF → slab (simplified). Equity stock / equity MF → STCG/LTCG.
    if asset_type == "mutual_fund" and not equity_oriented:
        rate = tax_bracket_rate_pct
        tax = gain * rate / 100.0
        return {
            "gain": round(gain, 2),
            "taxable_gain": round(gain, 2),
            "tax": round(tax, 2),
            "regime": "debt_mf_slab",
            "rate_pct": rate,
            "exemption_applied": 0.0,
            "is_long_term": is_lt,
        }

    if is_lt:
        rate = TAX_RULES["equity_ltcg_pct"]
        exempt = min(max(ltcg_exemption_remaining, 0.0), gain)
        taxable = max(gain - exempt, 0.0)
        tax = taxable * rate / 100.0
        return {
            "gain": round(gain, 2),
            "taxable_gain": round(taxable, 2),
            "tax": round(tax, 2),
            "regime": "equity_ltcg",
            "rate_pct": rate,
            "exemption_applied": round(exempt, 2),
            "is_long_term": True,
        }

    rate = TAX_RULES["equity_stcg_pct"]
    tax = gain * rate / 100.0
    return {
        "gain": round(gain, 2),
        "taxable_gain": round(gain, 2),
        "tax": round(tax, 2),
        "regime": "equity_stcg",
        "rate_pct": rate,
        "exemption_applied": 0.0,
        "is_long_term": False,
    }


def buy(
    *,
    symbol: str,
    quantity: float,
    price: float,
    asset_type: AssetType = "stock",
    name: str = "",
    broker: Optional[str] = None,
    bought_at: Optional[str] = None,
    equity_oriented: bool = True,
) -> dict[str, Any]:
    if quantity <= 0 or price <= 0:
        raise ValueError("quantity and price must be positive")
    state = ensure_store()
    broker = broker or state["settings"].get("broker") or "zerodha"
    turnover = quantity * price
    charges = estimate_charges(side="buy", turnover=turnover, broker=broker, asset_type=asset_type, intraday=False)
    total_cost = turnover + charges["total"]
    holding = {
        "id": str(uuid.uuid4())[:8],
        "symbol": symbol.upper(),
        "name": name or symbol.upper(),
        "asset_type": asset_type,
        "equity_oriented": equity_oriented if asset_type == "mutual_fund" else True,
        "quantity": round(quantity, 4),
        "avg_price": round(price, 4),
        "buy_charges": charges,
        "total_cost": round(total_cost, 2),
        "broker": broker,
        "bought_at": (bought_at or date.today().isoformat()),
        "created_at": _now_iso(),
    }
    state["holdings"].append(holding)
    save_state(state)
    return {"holding": holding, "portfolio": summarize(state)}


def _mark_intraday(bought_at: str, sell_date: Optional[str] = None) -> bool:
    return _parse_date(bought_at) == _parse_date(sell_date or date.today().isoformat())


def sell_preview(
    holding_id: str,
    sell_price: float,
    quantity: Optional[float] = None,
    sell_date: Optional[str] = None,
) -> dict[str, Any]:
    state = ensure_store()
    holding = next((h for h in state["holdings"] if h["id"] == holding_id), None)
    if not holding:
        raise ValueError("Holding not found")
    qty = float(quantity if quantity is not None else holding["quantity"])
    if qty <= 0 or qty > float(holding["quantity"]) + 1e-9:
        raise ValueError("Invalid sell quantity")
    broker = holding.get("broker") or state["settings"].get("broker") or "zerodha"
    intraday = _mark_intraday(holding["bought_at"], sell_date) and holding.get("asset_type") == "stock"
    buy_turnover = qty * float(holding["avg_price"])
    sell_turnover = qty * sell_price
    # Allocate buy charges pro-rata
    buy_charges_total = float((holding.get("buy_charges") or {}).get("total") or 0) * (qty / float(holding["quantity"]))
    sell_charges = estimate_charges(
        side="sell",
        turnover=sell_turnover,
        broker=broker,
        asset_type=holding.get("asset_type") or "stock",
        intraday=intraday,
    )
    days = _holding_days(holding["bought_at"], sell_date)
    tax = compute_tax(
        buy_value=buy_turnover,
        sell_value=sell_turnover,
        holding_days=days,
        asset_type=holding.get("asset_type") or "stock",
        tax_bracket_rate_pct=float(state["settings"].get("tax_bracket_rate_pct") or 30),
        ltcg_exemption_remaining=max(
            TAX_RULES["equity_ltcg_exemption"] - float(state["settings"].get("ltcg_exemption_used") or 0),
            0.0,
        ),
        equity_oriented=bool(holding.get("equity_oriented", True)),
        intraday=intraday,
    )
    net_before_tax = sell_turnover - sell_charges["total"]
    cost_basis = buy_turnover + buy_charges_total
    pnl_after_charges = net_before_tax - cost_basis
    pnl_after_tax = pnl_after_charges - tax["tax"]
    net_to_user = net_before_tax - tax["tax"]
    return {
        "holding_id": holding_id,
        "symbol": holding["symbol"],
        "asset_type": holding.get("asset_type"),
        "quantity": qty,
        "buy_price": holding["avg_price"],
        "sell_price": sell_price,
        "intraday": intraday,
        "holding_days": days,
        "broker": broker,
        "buy_turnover": round(buy_turnover, 2),
        "sell_turnover": round(sell_turnover, 2),
        "buy_charges_allocated": round(buy_charges_total, 2),
        "sell_charges": sell_charges,
        "deduction_total": round(buy_charges_total + sell_charges["total"], 2),
        "gross_pnl": round(sell_turnover - buy_turnover, 2),
        "pnl_after_charges": round(pnl_after_charges, 2),
        "tax": tax,
        "pnl_after_tax": round(pnl_after_tax, 2),
        "net_amount_you_get": round(net_to_user, 2),
        "tax_rules_note": TAX_RULES["note"],
    }


def sell(
    holding_id: str,
    sell_price: float,
    quantity: Optional[float] = None,
    sell_date: Optional[str] = None,
) -> dict[str, Any]:
    preview = sell_preview(holding_id, sell_price, quantity, sell_date)
    state = ensure_store()
    holdings = state["holdings"]
    idx = next(i for i, h in enumerate(holdings) if h["id"] == holding_id)
    holding = holdings[idx]
    qty = preview["quantity"]
    remaining = round(float(holding["quantity"]) - qty, 4)
    closed = {
        **preview,
        "name": holding.get("name"),
        "bought_at": holding.get("bought_at"),
        "sold_at": sell_date or date.today().isoformat(),
        "closed_at": _now_iso(),
    }
    state["closed"].append(closed)
    if preview["tax"]["regime"] == "equity_ltcg":
        used = float(state["settings"].get("ltcg_exemption_used") or 0)
        state["settings"]["ltcg_exemption_used"] = round(used + preview["tax"]["exemption_applied"], 2)
    if remaining <= 1e-9:
        holdings.pop(idx)
    else:
        # Scale remaining cost
        ratio = remaining / float(holding["quantity"])
        holding["quantity"] = remaining
        holding["total_cost"] = round(float(holding["total_cost"]) * ratio, 2)
        if holding.get("buy_charges"):
            holding["buy_charges"] = {
                k: (round(v * ratio, 4) if isinstance(v, (int, float)) else v)
                for k, v in holding["buy_charges"].items()
            }
    _prune_alerts(state)
    save_state(state)
    return {"sale": closed, "portfolio": summarize(state)}


def _prune_alerts(state: dict[str, Any]) -> None:
    open_symbols = {h.get("symbol") for h in state.get("holdings") or []}
    state["alerts"] = [
        a for a in (state.get("alerts") or [])
        if a.get("symbol") in open_symbols and a.get("level") in ("sell", "buy_more")
    ]


def sell_all_preview(price_map: dict[str, float], sell_date: Optional[str] = None) -> dict[str, Any]:
    """Preview sell-all: market value, broker fees, STCG/LTCG, net transfer, tax payable later."""
    state = ensure_store()
    lines = []
    total_market = 0.0
    total_cost = 0.0
    total_buy_fees = 0.0
    total_sell_fees = 0.0
    total_tax = 0.0
    total_net = 0.0
    total_gross_pnl = 0.0
    stcg_tax = 0.0
    ltcg_tax = 0.0
    slab_tax = 0.0

    for holding in list(state.get("holdings") or []):
        price = price_map.get(holding["symbol"]) or price_map.get(holding["symbol"].upper())
        if price is None:
            raise ValueError(f"Missing sell price for {holding['symbol']}")
        preview = sell_preview(holding["id"], float(price), sell_date=sell_date)
        regime = (preview.get("tax") or {}).get("regime") or ""
        tax_amt = float((preview.get("tax") or {}).get("tax") or 0)
        if regime == "equity_ltcg":
            ltcg_tax += tax_amt
            tax_label = "Long-term capital gains (LTCG)"
        elif regime == "equity_stcg":
            stcg_tax += tax_amt
            tax_label = "Short-term capital gains (STCG)"
        elif regime in ("intraday_slab", "debt_mf_slab"):
            slab_tax += tax_amt
            tax_label = "Intraday / slab tax"
        elif regime == "loss_or_flat" or tax_amt <= 0:
            tax_label = "No tax (loss / flat)"
        else:
            slab_tax += tax_amt
            tax_label = pretty_regime(regime)

        sell_fee = float((preview.get("sell_charges") or {}).get("total") or 0)
        buy_fee = float(preview.get("buy_charges_allocated") or 0)
        transfer_now = float(preview["sell_turnover"]) - sell_fee

        total_market += preview["sell_turnover"]
        total_cost += preview["buy_turnover"] + buy_fee
        total_buy_fees += buy_fee
        total_sell_fees += sell_fee
        total_tax += tax_amt
        total_net += preview["net_amount_you_get"]
        total_gross_pnl += preview["gross_pnl"]
        lines.append({
            **preview,
            "bought_at": holding.get("bought_at"),
            "name": holding.get("name"),
            "tax_label": tax_label,
            "sell_fee": round(sell_fee, 2),
            "buy_fee_already_paid": round(buy_fee, 2),
            "transfer_now": round(transfer_now, 2),
        })

    net_transfer_now = round(total_market - total_sell_fees, 2)

    return {
        "preview": True,
        "positions": lines,
        "totals": {
            "positions": len(lines),
            "market_value": round(total_market, 2),
            "invested_cost": round(total_cost, 2),
            "gross_pnl": round(total_gross_pnl, 2),
            "buy_fees_already_paid": round(total_buy_fees, 2),
            "sell_broker_deductions": round(total_sell_fees, 2),
            "broker_deductions": round(total_sell_fees, 2),  # alias: exit deductions only
            "all_round_trip_fees": round(total_buy_fees + total_sell_fees, 2),
            "tax_payable_later": round(total_tax, 2),
            "stcg_tax": round(stcg_tax, 2),
            "ltcg_tax": round(ltcg_tax, 2),
            "slab_or_other_tax": round(slab_tax, 2),
            "net_transfer_after_broker": net_transfer_now,
            "net_after_tax_estimate": round(total_net, 2),
        },
        "tax_rules_note": TAX_RULES["note"],
        "explanation": (
            "Overall worth is mark value of holdings. "
            "Sell broker deductions (STT/brokerage/GST/etc. on the sell leg) come off proceeds now. "
            "Buy-side fees were already paid at purchase and are not deducted again from this transfer. "
            "Capital-gains tax is estimated for later ITR payment when there is a gain."
        ),
    }


def pretty_regime(regime: str) -> str:
    return (regime or "tax").replace("_", " ")


def sell_all(price_map: dict[str, float]) -> dict[str, Any]:
    """Sell every open holding using provided symbol→price map."""
    preview = sell_all_preview(price_map)
    state = ensure_store()
    results = []
    total_net = 0.0
    total_tax = 0.0
    total_deductions = 0.0
    ids = [h["id"] for h in list(state["holdings"])]
    for hid in ids:
        state = ensure_store()
        holding = next((h for h in state["holdings"] if h["id"] == hid), None)
        if not holding:
            continue
        price = price_map.get(holding["symbol"]) or price_map.get(holding["symbol"].upper())
        if price is None:
            raise ValueError(f"Missing sell price for {holding['symbol']}")
        result = sell(hid, float(price))
        sale = result["sale"]
        results.append(sale)
        total_net += sale["net_amount_you_get"]
        total_tax += sale["tax"]["tax"]
        total_deductions += sale["deduction_total"]
    state = ensure_store()
    _prune_alerts(state)
    save_state(state)
    return {
        "sold_count": len(results),
        "sales": results,
        "preview_totals": preview.get("totals"),
        "total_net_you_get": round(total_net, 2),
        "total_tax": round(total_tax, 2),
        "total_broker_deductions": round(total_deductions, 2),
        "net_transfer_after_broker": preview["totals"]["net_transfer_after_broker"],
        "tax_payable_later": preview["totals"]["tax_payable_later"],
        "portfolio": summarize(state),
    }


def build_alerts(holding: dict[str, Any], tech: dict[str, Any], ratings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """TA-driven buy-more / sell alerts for a held name."""
    alerts: list[dict[str, Any]] = []
    mom = tech.get("momentum") or {}
    ma = tech.get("moving_averages") or {}
    trend = tech.get("trend") or {}
    vol = tech.get("volume") or {}
    symbol = holding.get("symbol")
    rsi = mom.get("rsi_14")
    st = trend.get("supertrend_dir")
    vs200 = ma.get("price_vs_sma_200_pct")
    macd_hist = mom.get("macd_hist")
    stance = (ratings or {}).get("composite_stance")

    if rsi is not None and rsi >= 72 and st == -1:
        alerts.append({
            "level": "sell",
            "symbol": symbol,
            "message": f"Consider selling / trimming {symbol}: RSI {rsi} overbought with bearish Supertrend.",
        })
    elif rsi is not None and rsi >= 78:
        alerts.append({
            "level": "sell",
            "symbol": symbol,
            "message": f"Momentum stretched on {symbol} (RSI {rsi}) — review for partial booking.",
        })

    if st == -1 and vs200 is not None and vs200 < -5 and (macd_hist or 0) < 0:
        alerts.append({
            "level": "sell",
            "symbol": symbol,
            "message": f"Trend damaged on {symbol}: Supertrend down, below SMA200, MACD hist negative.",
        })

    if rsi is not None and rsi <= 32 and st == 1 and (macd_hist or 0) > 0:
        alerts.append({
            "level": "buy_more",
            "symbol": symbol,
            "message": f"Dip-buy zone on {symbol}: oversold RSI {rsi} but Supertrend/MACD still constructive.",
        })
    elif rsi is not None and 40 <= rsi <= 55 and ma.get("ema_stack_bullish") and (vol.get("rvol") or 0) >= 1.2:
        alerts.append({
            "level": "buy_more",
            "symbol": symbol,
            "message": f"Add-on setup for {symbol}: healthy RSI, bullish EMA stack, elevated relative volume.",
        })

    if stance in ("strong_buy", "buy") and vs200 is not None and vs200 < 0:
        alerts.append({
            "level": "buy_more",
            "symbol": symbol,
            "message": f"Composite stance {stance} while below SMA200 — accumulation candidate.",
        })
    if stance in ("strong_sell", "sell"):
        alerts.append({
            "level": "sell",
            "symbol": symbol,
            "message": f"Composite stance {stance} — technical desk flags exit review for {symbol}.",
        })

    return alerts


def refresh_alerts(enrich: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """enrich: symbol -> {technicals, ratings}"""
    state = ensure_store()
    alerts: list[dict[str, Any]] = []
    for h in state["holdings"]:
        payload = enrich.get(h["symbol"]) or enrich.get(h["symbol"].upper()) or {}
        tech = payload.get("technicals") or {}
        ratings = payload.get("ratings") or {}
        if tech:
            alerts.extend(build_alerts(h, tech, ratings))
    state["alerts"] = alerts
    save_state(state)
    return {"alerts": alerts, "count": len(alerts)}


def summarize(state: Optional[dict[str, Any]] = None, marks: Optional[dict[str, float]] = None) -> dict[str, Any]:
    state = state or ensure_store()
    before = list(state.get("alerts") or [])
    _prune_alerts(state)
    if state.get("alerts") != before:
        save_state(state)
    marks = marks or {}
    rows = []
    invested = 0.0
    market = 0.0
    for h in state.get("holdings") or []:
        qty = float(h["quantity"])
        avg = float(h["avg_price"])
        cost = float(h.get("total_cost") or qty * avg)
        mark = marks.get(h["symbol"])
        mkt = (mark * qty) if mark is not None else None
        invested += cost
        if mkt is not None:
            market += mkt
        rows.append({
            **h,
            "mark_price": mark,
            "market_value": round(mkt, 2) if mkt is not None else None,
            "unrealized_pnl": round(mkt - cost, 2) if mkt is not None else None,
            "holding_days": _holding_days(h["bought_at"]),
        })
    return {
        "settings": state.get("settings"),
        "holdings": rows,
        "closed": state.get("closed") or [],
        "alerts": state.get("alerts") or [],
        "totals": {
            "positions": len(rows),
            "invested": round(invested, 2),
            "market_value": round(market, 2) if marks else None,
            "unrealized_pnl": round(market - invested, 2) if marks else None,
        },
        "tax_rules": TAX_RULES,
        "brokers": list_brokers(),
        "tax_brackets": list_tax_brackets(),
        "files": {
            "json": str(HOLDINGS_JSON.relative_to(BASE_DIR)),
            "txt": str(HOLDINGS_TXT.relative_to(BASE_DIR)),
        },
        "updated_at": state.get("updated_at"),
    }


def portfolio_path_info() -> dict[str, str]:
    ensure_store()
    return {
        "json": str(HOLDINGS_JSON),
        "txt": str(HOLDINGS_TXT),
    }
