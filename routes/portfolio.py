"""Paper portfolio routes."""
from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException

from horizon_rank import rate_all_horizons
from portfolio import (
    buy as portfolio_buy,
    ensure_store,
    list_brokers,
    list_tax_brackets,
    portfolio_path_info,
    refresh_alerts,
    sell as portfolio_sell,
    sell_all as portfolio_sell_all,
    sell_all_preview as portfolio_sell_all_preview,
    sell_preview,
    summarize as portfolio_summarize,
    update_settings as portfolio_update_settings,
)
from routes.helpers import _latest_price, fetch_prices, rows_from_payload
from routes.schemas import (
    PortfolioBuyRequest,
    PortfolioSellAllRequest,
    PortfolioSellRequest,
    PortfolioSettingsRequest,
)
from technicals import compute_technicals

router = APIRouter(tags=["portfolio"])

@router.get("/api/portfolio")
def portfolio_get() -> dict[str, Any]:
    state = ensure_store()
    marks: dict[str, float] = {}
    for h in state.get("holdings") or []:
        try:
            marks[h["symbol"]] = _latest_price(h["symbol"])
        except Exception:
            continue
    return portfolio_summarize(state, marks)


@router.get("/api/portfolio/meta")
def portfolio_meta() -> dict[str, Any]:
    ensure_store()
    return {
        "brokers": list_brokers(),
        "tax_brackets": list_tax_brackets(),
        "files": portfolio_path_info(),
    }


@router.post("/api/portfolio/settings")
def portfolio_settings(request: PortfolioSettingsRequest) -> dict[str, Any]:
    try:
        state = portfolio_update_settings(
            broker=request.broker,
            tax_bracket_id=request.tax_bracket_id,
            tax_bracket_rate_pct=request.tax_bracket_rate_pct,
        )
        return portfolio_summarize(state)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/portfolio/buy")
def portfolio_buy_route(request: PortfolioBuyRequest) -> dict[str, Any]:
    try:
        price = request.price
        if price is None:
            price = _latest_price(request.symbol, request.provider)
        return portfolio_buy(
            symbol=request.symbol,
            quantity=request.quantity,
            price=float(price),
            asset_type=request.asset_type,
            name=request.name,
            broker=request.broker,
            bought_at=request.bought_at,
            equity_oriented=request.equity_oriented,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Buy failed: {exc}") from exc


@router.post("/api/portfolio/sell")
def portfolio_sell_route(request: PortfolioSellRequest) -> dict[str, Any]:
    try:
        state = ensure_store()
        holding = next((h for h in state["holdings"] if h["id"] == request.holding_id), None)
        if not holding:
            raise ValueError("Holding not found")
        price = request.price
        if price is None:
            price = _latest_price(holding["symbol"], request.provider)
        if request.preview_only:
            return {"preview": sell_preview(request.holding_id, float(price), request.quantity)}
        return portfolio_sell(request.holding_id, float(price), request.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sell failed: {exc}") from exc


@router.post("/api/portfolio/sell-all")
def portfolio_sell_all_route(request: PortfolioSellAllRequest) -> dict[str, Any]:
    try:
        state = ensure_store()
        price_map = dict(request.prices or {})
        for h in state.get("holdings") or []:
            sym = h["symbol"]
            if sym not in price_map:
                price_map[sym] = _latest_price(sym, request.provider)
        if request.preview_only:
            return portfolio_sell_all_preview(price_map)
        return portfolio_sell_all(price_map)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Sell-all failed: {exc}") from exc


@router.post("/api/portfolio/alerts/refresh")
def portfolio_alerts_refresh(provider: Literal["auto", "yfinance", "nse"] = "auto") -> dict[str, Any]:
    """Recompute buy-more / sell alerts from current technicals for each holding."""
    try:
        state = ensure_store()
        enrich: dict[str, dict[str, Any]] = {}
        for h in state.get("holdings") or []:
            symbol = h["symbol"]
            try:
                payload = fetch_prices(symbol, provider, force_refresh=False)
                tech = compute_technicals(rows_from_payload(payload))
                ratings = rate_all_horizons(tech)
                enrich[symbol] = {"technicals": tech, "ratings": ratings}
            except Exception:
                continue
        result = refresh_alerts(enrich)
        marks = {sym: float((data["technicals"] or {}).get("price") or 0) for sym, data in enrich.items()}
        summary = portfolio_summarize(ensure_store(), {k: v for k, v in marks.items() if v > 0})
        return {**result, "portfolio": summary}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Alert refresh failed: {exc}") from exc
