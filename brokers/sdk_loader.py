"""Lazy SDK imports — app starts even if a broker package is not installed."""
from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


def _import(name: str, pip_hint: str) -> Any:
    try:
        return __import__(name)
    except ImportError as exc:
        raise RuntimeError(f"Install {pip_hint} to enable this broker.") from exc


def kite_connect(api_key: str):
    mod = _import("kiteconnect", "kiteconnect")
    return mod.KiteConnect(api_key=api_key)


def kite_ticker(api_key: str, access_token: str):
    mod = _import("kiteconnect", "kiteconnect")
    return mod.KiteTicker(api_key, access_token)


def groww_api(token: str):
    mod = _import("growwapi", "growwapi")
    return mod.GrowwAPI(token)


def fyers_session(**kwargs):
    mod = _import("fyers_apiv3.fyersModel", "fyers-apiv3")
    return mod.SessionModel(**kwargs)


def fyers_model(**kwargs):
    mod = _import("fyers_apiv3.fyersModel", "fyers-apiv3")
    return mod.FyersModel(**kwargs)


def sdk_available(broker: str) -> bool:
    pkg = {"zerodha": "kiteconnect", "groww": "growwapi", "fyers": "fyers_apiv3"}.get(broker)
    if not pkg:
        return False
    try:
        __import__(pkg)
        return True
    except ImportError:
        return False
