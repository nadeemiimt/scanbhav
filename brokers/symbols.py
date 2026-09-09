"""Symbol normalization across app (Yahoo) and broker formats."""
from __future__ import annotations


def base_symbol(symbol: str) -> str:
    upper = symbol.upper().strip()
    if upper.endswith(".NSE"):
        return upper[:-4]
    if upper.endswith(".BSE"):
        return upper[:-4]
    if upper.endswith(".NS"):
        return upper[:-3]
    if upper.endswith(".BO"):
        return upper[:-3]
    return upper.split(".")[0]


def exchange_for(symbol: str) -> str:
    upper = symbol.upper().strip()
    if upper.endswith(".BSE") or upper.endswith(".BO"):
        return "BSE"
    return "NSE"


def kite_instrument(symbol: str) -> str:
    base = base_symbol(symbol)
    ex = exchange_for(symbol)
    return f"{ex}:{base}"


def kite_trading_symbol(symbol: str) -> tuple[str, str]:
    base = base_symbol(symbol)
    ex = exchange_for(symbol)
    exchange_const = "NSE" if ex == "NSE" else "BSE"
    return exchange_const, base


def groww_ltp_key(symbol: str) -> str:
    return f"{exchange_for(symbol)}_{base_symbol(symbol)}"


def groww_symbol(symbol: str) -> str:
    """App symbol → Groww backtesting symbol (e.g. RELIANCE.NSE → NSE-RELIANCE)."""
    return f"{exchange_for(symbol)}-{base_symbol(symbol)}"


def fyers_symbol(symbol: str) -> str:
    base = base_symbol(symbol)
    ex = exchange_for(symbol)
    return f"{ex}:{base}-EQ"
