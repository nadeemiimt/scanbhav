"""Phase B — intraday paper simulator (one symbol, rules, EOD flat)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR
from trading.order_router import execute_order
from trading.paper_ledger import open_positions, square_off_position
from trading.scoreboard import record_outcome

SIM_PATH = BASE_DIR / "data" / "trading" / "intraday_sim.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ist_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def market_open_ist() -> bool:
    from trading.market_hours import market_open_ist as nse_trading_open
    return nse_trading_open()


def _load() -> dict[str, Any]:
    SIM_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not SIM_PATH.exists():
        return {"state": "idle", "symbol": "", "log": [], "updated_at": _now()}
    try:
        return json.loads(SIM_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"state": "idle", "symbol": "", "log": [], "updated_at": _now()}


def _save(data: dict[str, Any]) -> dict[str, Any]:
    data["updated_at"] = _now()
    SIM_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def _log(data: dict[str, Any], event: str, detail: str = "", extra: Optional[dict] = None) -> None:
    data.setdefault("log", []).insert(
        0,
        {"at": _now(), "event": event, "detail": detail, **(extra or {})},
    )
    data["log"] = data["log"][:200]


def sim_status() -> dict[str, Any]:
    data = _load()
    sym = data.get("symbol") or ""
    pos = [p for p in open_positions("mis") if p.get("symbol") == sym] if sym else []
    return {
        **data,
        "market_open_ist": market_open_ist(),
        "open_position": pos[0] if pos else None,
    }


def sim_configure(symbol: str, rules: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    data = _load()
    data["symbol"] = symbol.upper().strip()
    data["rules"] = {
        "entry_min_composite": 55.0,
        "target_pct": 1.5,
        "stop_pct": 0.75,
        "qty": 1,
        **(rules or {}),
    }
    data["state"] = "armed"
    _log(data, "configure", f"Symbol set to {data['symbol']}")
    return _save(data)


def sim_tick(
    *,
    price: float,
    composite_score: float,
    stance: str,
    force_eod: bool = False,
) -> dict[str, Any]:
    data = _load()
    sym = data.get("symbol") or ""
    rules = data.get("rules") or {}
    if not sym:
        return {"action": "none", "reason": "no_symbol"}

    target_pct = float(rules.get("target_pct") or 1.5)
    stop_pct = float(rules.get("stop_pct") or 0.75)
    min_score = float(rules.get("entry_min_composite") or 55)
    qty = int(rules.get("qty") or 1)

    pos_list = [p for p in open_positions("mis") if p.get("symbol") == sym]
    pos = pos_list[0] if pos_list else None

    ist = _ist_now()
    eod = force_eod or ist.hour * 60 + ist.minute >= int(rules.get("square_off_minute_ist") or 920)

    if pos and eod:
        order = square_off_position(sym, price, product="mis")
        entry = float(pos.get("avg_price") or price)
        record_outcome(
            symbol=sym,
            source="intraday_sim",
            predicted_stance=data.get("last_stance") or stance,
            predicted_horizon="1d",
            entry_price=entry,
            exit_price=price,
            summary="EOD square-off",
            composite_score=composite_score,
        )
        data["state"] = "flat"
        _log(data, "eod_square_off", f"Closed at {price}", {"order": order})
        _save(data)
        return {"action": "square_off", "order": order, "reason": "eod"}

    if pos:
        entry = float(pos.get("avg_price") or price)
        ret_pct = ((price / entry) - 1) * 100 if entry else 0
        if ret_pct >= target_pct:
            order = square_off_position(sym, price, product="mis")
            record_outcome(
                symbol=sym,
                source="intraday_sim",
                predicted_stance=stance,
                predicted_horizon="1d",
                entry_price=entry,
                exit_price=price,
                summary=f"Target hit {ret_pct:.2f}%",
                composite_score=composite_score,
            )
            data["state"] = "flat"
            _log(data, "target_exit", f"{ret_pct:.2f}%", {"order": order})
            _save(data)
            return {"action": "target_exit", "order": order, "return_pct": ret_pct}
        if ret_pct <= -stop_pct:
            order = square_off_position(sym, price, product="mis")
            record_outcome(
                symbol=sym,
                source="intraday_sim",
                predicted_stance=stance,
                predicted_horizon="1d",
                entry_price=entry,
                exit_price=price,
                summary=f"Stop hit {ret_pct:.2f}%",
                composite_score=composite_score,
            )
            data["state"] = "flat"
            _log(data, "stop_exit", f"{ret_pct:.2f}%", {"order": order})
            _save(data)
            return {"action": "stop_exit", "order": order, "return_pct": ret_pct}
        return {"action": "hold", "return_pct": ret_pct, "position": pos}

    if not market_open_ist() and not force_eod:
        return {"action": "none", "reason": "market_closed"}

    bullish = stance.lower() in {"favorable", "strong_favorable", "bullish", "constructive"}
    if composite_score >= min_score and bullish:
        order = execute_order(
            {
                "symbol": sym,
                "side": "buy",
                "quantity": qty,
                "order_type": "market",
                "limit_price": price,
                "product": "mis",
            },
            source="intraday_sim",
        )
        data["state"] = "long"
        data["last_stance"] = stance
        data["entry_composite"] = composite_score
        _log(data, "entry", f"Buy {qty} @ {price}", {"order": order})
        _save(data)
        return {"action": "entry", "order": order}

    return {"action": "wait", "composite_score": composite_score, "stance": stance}
