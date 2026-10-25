"""User API keys, custom data connectors, simple backtests, and learning."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["integrations"])


class SecretBody(BaseModel):
    provider_id: str
    api_key: str = ""


class ConnectorBody(BaseModel):
    id: str = "custom"
    label: str = "Custom API"
    base_url: str = ""
    path_template: str = "/quote?symbol={symbol}"
    header_name: str = "Authorization"
    header_prefix: str = "Bearer"
    api_key: str = ""
    clear_key: bool = False


class TestBody(BaseModel):
    provider_id: str
    symbol: str = "RELIANCE.NSE"
    custom: bool = False


class BacktestBody(BaseModel):
    mode: str = "walk_forward"
    symbols: list[str] = Field(default_factory=lambda: ["RELIANCE.NSE"])
    start: Optional[str] = None
    end: Optional[str] = None
    random_count: int = 8
    trigger: str = "trigger_rsi_oversold_bounce"


class LearnBody(BaseModel):
    gap_id: str
    allow_code_edits: bool = False


@router.get("/api/fixtures/playwright")
def playwright_fixture() -> dict[str, Any]:
    """Fixed prices, news, order book, and the recommendation they produce."""
    from fixtures.playwright_recommend import playwright_payload

    return playwright_payload()


@router.get("/api/integrations")
def integrations_status() -> dict[str, Any]:
    from integrations.catalog import integration_catalog
    from integrations.keys import list_connectors, public_key_status

    broker_tokens = {}
    try:
        from brokers.token_store import token_meta

        for broker in ("zerodha", "groww", "fyers"):
            broker_tokens[broker] = token_meta(broker)
    except Exception:
        broker_tokens = {}

    return {
        "catalog": integration_catalog(),
        "keys": public_key_status(),
        "connectors": list_connectors(),
        "broker_tokens": broker_tokens,
    }


@router.post("/api/integrations/key/clear")
def integrations_clear_key(body: SecretBody) -> dict[str, Any]:
    from integrations.keys import set_secret

    return set_secret(body.provider_id.strip().lower(), "")


@router.post("/api/integrations/broker-token/clear")
def integrations_clear_broker_token(body: SecretBody) -> dict[str, Any]:
    """Drop a stored broker access token (does not remove app key/secret)."""
    from brokers.token_store import TOKENS_PATH, clear_token

    result = clear_token(body.provider_id.strip().lower())
    result["store"] = str(TOKENS_PATH.name)
    return result


@router.post("/api/integrations/key")
def integrations_save_key(body: SecretBody) -> dict[str, Any]:
    from integrations.keys import set_secret

    return set_secret(body.provider_id.strip().lower(), body.api_key)


@router.post("/api/integrations/connector")
def integrations_save_connector(body: ConnectorBody) -> dict[str, Any]:
    from integrations.keys import save_connector

    return save_connector(body.id.strip().lower() or "custom", body.model_dump())


@router.post("/api/integrations/test")
def integrations_test(body: TestBody) -> dict[str, Any]:
    from integrations.connectors import test_builtin, test_custom

    if body.custom:
        return test_custom(body.provider_id, body.symbol)
    return test_builtin(body.provider_id, body.symbol)


@router.post("/api/backtest/simple")
def backtest_simple(body: BacktestBody) -> dict[str, Any]:
    from trading.simple_backtest import run_simple_backtest

    return run_simple_backtest(body.model_dump())


@router.post("/api/backtest/simple/stream")
def backtest_simple_stream(body: BacktestBody):
    """SSE progress for the simple backtest desk."""
    import json

    from fastapi.responses import StreamingResponse

    from trading.simple_backtest import iter_simple_backtest

    def generate():
        try:
            for event in iter_simple_backtest(body.model_dump()):
                yield f"data: {json.dumps(event, default=str)}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)[:240], 'progress': 100})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/api/learning/gaps")
def learning_gaps(limit: int = 20) -> dict[str, Any]:
    from trading.learning_loop import list_gaps

    return {"gaps": list_gaps(limit)}


@router.post("/api/learning/explain")
def learning_explain(body: LearnBody) -> dict[str, Any]:
    from trading.learning_loop import explain_gap_with_genai

    return explain_gap_with_genai(body.gap_id)


@router.post("/api/learning/cursor")
def learning_cursor(body: LearnBody) -> dict[str, Any]:
    from trading.learning_loop import apply_gap_with_cursor

    return apply_gap_with_cursor(body.gap_id, allow_code_edits=body.allow_code_edits)
