"""Broker routes — multi-provider + static-IP gateway + OAuth."""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from brokers.auth import (
    fyers_exchange_token,
    fyers_login_url,
    groww_set_token,
    kite_exchange_token,
    kite_login_url,
)
from brokers.gateway import verify_gateway_secret
from brokers.service import _get_live_quotes_direct, _place_order_direct, broker_status_overview, get_live_quotes
from trading.config_store import load_trading_config
from trading.order_router import execute_order
from trading.risk import RiskBlocked
from routes.schemas import BrokerOrderRequest, BrokerQuotesRequest

router = APIRouter(tags=["broker"])


class GatewayOrderBody(BaseModel):
    broker: str = "groww"
    symbol: str
    side: str
    quantity: int
    order_type: str = "limit"
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    product: str = "cnc"
    trade_id: Optional[str] = None


class GatewayQuotesBody(BaseModel):
    broker: str = "groww"
    symbols: list[str] = Field(default_factory=list, max_length=48)


class BrokerTokenBody(BaseModel):
    access_token: str = Field(min_length=8, max_length=4096)


def _validate_order_request(request: BrokerOrderRequest) -> None:
    if request.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive.")
    if request.order_type == "limit" and not request.limit_price:
        raise HTTPException(status_code=400, detail="Limit orders require limit_price.")
    if request.order_type in {"sl", "sl-m"} and not request.stop_price:
        raise HTTPException(status_code=400, detail="Stop-loss orders require stop_price.")


@router.get("/api/broker/status")
def broker_status() -> dict[str, Any]:
    """Provider readiness, gateway routing, static-IP deployment hints."""
    overview = broker_status_overview()
    return overview


@router.post("/api/broker/order")
def broker_place_order(request: BrokerOrderRequest) -> dict[str, Any]:
    """Paper or live order via unified router (same path as Swing desk + agent)."""
    _validate_order_request(request)
    cfg = load_trading_config()
    payload = request.model_dump()
    if not payload.get("broker") or payload.get("broker") == "stub":
        payload["broker"] = cfg.get("default_broker") or "stub"
    if not payload.get("product"):
        payload["product"] = cfg.get("default_product") or "mis"
    try:
        return execute_order(payload, source="api")
    except RiskBlocked as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code, "message": exc.message}) from exc
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotImplementedError as exc:
        raise HTTPException(status_code=501, detail=str(exc)) from exc


@router.post("/api/broker/quotes")
def broker_quotes(request: BrokerQuotesRequest) -> dict[str, Any]:
    """Live LTP from broker adapter (falls back empty until SDK wired)."""
    return get_live_quotes(request.broker, request.symbols)


@router.get("/api/broker/stream/status")
def broker_stream_status() -> dict[str, Any]:
    from brokers.ltp_stream import ltp_stream_status

    return ltp_stream_status()


@router.post("/api/broker/stream/sync")
def broker_stream_sync(body: Optional[GatewayQuotesBody] = None) -> dict[str, Any]:
    from brokers.ltp_stream import add_stream_symbols, get_manager

    if body and body.symbols:
        symbols = add_stream_symbols(body.symbols)
    else:
        symbols = get_manager().sync_now()
    return {"synced": len(symbols), "symbols": symbols}


@router.websocket("/api/broker/stream/ws")
async def broker_stream_ws(websocket: WebSocket) -> None:
    """Push LTP ticks from the in-process quote cache (Zerodha WS, REST poll, or Yahoo fallback)."""
    import asyncio
    import json

    from brokers.ltp_stream import add_stream_symbols, get_manager, register_ws_client, unregister_ws_client
    from brokers.quote_cache import get_prices

    await websocket.accept()
    loop = asyncio.get_running_loop()
    register_ws_client(websocket, loop)
    try:
        mgr = get_manager()
        symbols = mgr.sync_now()
        cached = get_prices(symbols, max_age_seconds=120)
        for sym, row in cached.items():
            await websocket.send_json({"type": "ltp", "symbol": sym, **row})
        await websocket.send_json({"type": "status", **mgr.status()})
        while True:
            msg = await websocket.receive_text()
            stripped = msg.strip().lower()
            payload = None
            if msg.startswith("{"):
                try:
                    payload = json.loads(msg)
                except json.JSONDecodeError:
                    payload = None
            if isinstance(payload, dict) and payload.get("action") == "subscribe":
                syms = add_stream_symbols(payload.get("symbols") or [])
                await websocket.send_json({"type": "subscribed", "symbols": syms})
                for sym, row in get_prices(payload.get("symbols") or [], max_age_seconds=120).items():
                    await websocket.send_json({"type": "ltp", "symbol": sym, **row})
                await websocket.send_json({"type": "status", **mgr.status()})
            elif stripped in {"ping", "sync"}:
                mgr.sync_now()
                await websocket.send_json({"type": "status", **mgr.status()})
    except WebSocketDisconnect:
        pass
    finally:
        unregister_ws_client(websocket)


@router.post("/api/broker/gateway/order")
def gateway_order(
    body: GatewayOrderBody,
    x_broker_gateway_secret: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    """Internal endpoint on static-IP host — local dev forwards here."""
    if not verify_gateway_secret(x_broker_gateway_secret):
        raise HTTPException(status_code=401, detail="Invalid broker gateway secret.")
    try:
        return _place_order_direct(body.model_dump())
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/broker/gateway/quotes")
def gateway_quotes(
    body: GatewayQuotesBody,
    x_broker_gateway_secret: Optional[str] = Header(default=None),
) -> dict[str, Any]:
    if not verify_gateway_secret(x_broker_gateway_secret):
        raise HTTPException(status_code=401, detail="Invalid broker gateway secret.")
    return _get_live_quotes_direct(body.broker, body.symbols)


@router.get("/api/broker/auth/{broker}/login-url")
def broker_auth_login_url(broker: Literal["zerodha", "fyers"]) -> dict[str, Any]:
    """OAuth login URL for Kite or FYERS (open in browser)."""
    try:
        if broker == "zerodha":
            return kite_login_url()
        return fyers_login_url()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/broker/auth/zerodha/callback")
def broker_kite_callback(request_token: str = Query(..., min_length=4)) -> HTMLResponse:
    try:
        result = kite_exchange_token(request_token)
        body = (
            f"<h2>Kite connected</h2><p>{result.get('message')}</p>"
            f"<p>User: {result.get('user_id', '—')}</p>"
            "<p>You can close this tab and return to ScanBhav.</p>"
        )
        return HTMLResponse(body)
    except Exception as exc:
        return HTMLResponse(f"<h2>Kite login failed</h2><pre>{exc}</pre>", status_code=400)


@router.get("/api/broker/auth/fyers/callback")
def broker_fyers_callback(auth_code: str = Query(..., min_length=4)) -> HTMLResponse:
    try:
        result = fyers_exchange_token(auth_code)
        body = f"<h2>FYERS connected</h2><p>{result.get('message')}</p>"
        return HTMLResponse(body)
    except Exception as exc:
        return HTMLResponse(f"<h2>FYERS login failed</h2><pre>{exc}</pre>", status_code=400)


@router.post("/api/broker/auth/groww/token")
def broker_groww_token(body: BrokerTokenBody) -> dict[str, Any]:
    """Paste Groww Trade API auth token (from Groww developer dashboard)."""
    try:
        return groww_set_token(body.access_token)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
