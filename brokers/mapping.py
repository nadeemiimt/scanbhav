"""Map unified order payload → broker-specific constants."""
from __future__ import annotations

from typing import Any


def groww_order_params(payload: dict[str, Any], groww) -> dict[str, Any]:
    side = payload.get("side", "buy").lower()
    order_type = payload.get("order_type", "limit").lower()
    product = payload.get("product", "cnc").lower()

    txn = groww.TRANSACTION_TYPE_BUY if side == "buy" else groww.TRANSACTION_TYPE_SELL
    if order_type == "market":
        otype = groww.ORDER_TYPE_MARKET
    elif order_type in {"sl", "sl-m"}:
        otype = groww.ORDER_TYPE_STOP_LOSS_MARKET if order_type == "sl-m" else groww.ORDER_TYPE_STOP_LOSS
    else:
        otype = groww.ORDER_TYPE_LIMIT

    if product in {"mis", "intraday"}:
        prod = groww.PRODUCT_MIS
    else:
        prod = groww.PRODUCT_CNC

    from brokers.symbols import base_symbol, exchange_for

    symbol = payload.get("symbol", "")
    exchange = groww.EXCHANGE_BSE if exchange_for(symbol) == "BSE" else groww.EXCHANGE_NSE

    params: dict[str, Any] = {
        "trading_symbol": base_symbol(symbol),
        "quantity": int(payload["quantity"]),
        "validity": groww.VALIDITY_DAY,
        "exchange": exchange,
        "segment": groww.SEGMENT_CASH,
        "product": prod,
        "order_type": otype,
        "transaction_type": txn,
    }
    if payload.get("limit_price") and otype == groww.ORDER_TYPE_LIMIT:
        params["price"] = float(payload["limit_price"])
    if payload.get("stop_price"):
        params["trigger_price"] = float(payload["stop_price"])
    if payload.get("trade_id"):
        ref = str(payload["trade_id"]).replace("-", "")[:20]
        params["order_reference_id"] = ref
    return params


def kite_order_params(payload: dict[str, Any], kite) -> dict[str, Any]:
    from brokers.symbols import kite_trading_symbol

    exchange, tradingsymbol = kite_trading_symbol(payload.get("symbol", ""))
    side = payload.get("side", "buy").lower()
    order_type = payload.get("order_type", "limit").lower()
    product = payload.get("product", "cnc").lower()

    ex = kite.EXCHANGE_NSE if exchange == "NSE" else kite.EXCHANGE_BSE
    txn = kite.TRANSACTION_TYPE_BUY if side == "buy" else kite.TRANSACTION_TYPE_SELL
    prod = kite.PRODUCT_MIS if product in {"mis", "intraday"} else kite.PRODUCT_CNC

    if order_type == "market":
        otype = kite.ORDER_TYPE_MARKET
    elif order_type == "sl-m":
        otype = kite.ORDER_TYPE_SLM
    elif order_type == "sl":
        otype = kite.ORDER_TYPE_SL
    else:
        otype = kite.ORDER_TYPE_LIMIT

    params: dict[str, Any] = {
        "variety": kite.VARIETY_REGULAR,
        "exchange": ex,
        "tradingsymbol": tradingsymbol,
        "transaction_type": txn,
        "quantity": int(payload["quantity"]),
        "product": prod,
        "order_type": otype,
        "validity": kite.VALIDITY_DAY,
    }
    if payload.get("limit_price") and otype in {kite.ORDER_TYPE_LIMIT, kite.ORDER_TYPE_SL}:
        params["price"] = float(payload["limit_price"])
    if payload.get("stop_price") and otype in {kite.ORDER_TYPE_SL, kite.ORDER_TYPE_SLM}:
        params["trigger_price"] = float(payload["stop_price"])
    if payload.get("trade_id"):
        params["tag"] = str(payload["trade_id"])[:20]
    return params


def fyers_order_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from brokers.symbols import fyers_symbol

    side = payload.get("side", "buy").lower()
    order_type = payload.get("order_type", "limit").lower()
    product = payload.get("product", "cnc").lower()

    if order_type == "market":
        ftype = 2
    elif order_type == "sl-m":
        ftype = 3
    elif order_type == "sl":
        ftype = 4
    else:
        ftype = 1

    data: dict[str, Any] = {
        "symbol": fyers_symbol(payload.get("symbol", "")),
        "qty": int(payload["quantity"]),
        "type": ftype,
        "side": 1 if side == "buy" else -1,
        "productType": "INTRADAY" if product in {"mis", "intraday"} else "CNC",
        "limitPrice": float(payload.get("limit_price") or 0),
        "stopPrice": float(payload.get("stop_price") or 0),
        "validity": "DAY",
        "disclosedQty": 0,
        "offlineOrder": False,
        "isSliceOrder": False,
    }
    if payload.get("target_price"):
        data["takeProfit"] = float(payload["target_price"])
    return data
