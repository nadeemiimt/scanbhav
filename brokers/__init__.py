"""Multi-broker adapter layer (Zerodha / Groww / FYERS + static-IP gateway)."""
from brokers.service import broker_status_overview, get_live_quotes, get_adapter, place_order

__all__ = [
    "broker_status_overview",
    "get_adapter",
    "get_live_quotes",
    "place_order",
]
