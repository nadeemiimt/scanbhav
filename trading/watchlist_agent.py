"""Phase C — scheduled watchlist scan (alerts only, no trades)."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

ALERTS_PATH = BASE_DIR / "data" / "trading" / "watchlist_alerts.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ALERTS_PATH.exists():
        return {"alerts": [], "last_scan_at": None}
    try:
        return json.loads(ALERTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"alerts": [], "last_scan_at": None}


def _save(data: dict[str, Any]) -> dict[str, Any]:
    ALERTS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return data


def list_alerts(limit: int = 50) -> dict[str, Any]:
    data = _load()
    return {
        "alerts": (data.get("alerts") or [])[:limit],
        "last_scan_at": data.get("last_scan_at"),
        "count": len(data.get("alerts") or []),
    }


def push_alert(message: str, *, symbol: str = "", severity: str = "info", meta: Optional[dict] = None) -> dict[str, Any]:
    data = _load()
    alert = {
        "id": f"wl-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "at": _now(),
        "symbol": symbol.upper() if symbol else "",
        "severity": severity,
        "message": message,
        "meta": meta or {},
        "read": False,
    }
    data.setdefault("alerts", []).insert(0, alert)
    data["alerts"] = data["alerts"][:300]
    _save(data)
    return alert


def scan_watchlist(
    symbols: list[str],
    *,
    quote_fn,
    analyze_fn,
    rules: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """quote_fn(sym)->price, analyze_fn(sym)->{composite_score, stance, ...}"""
    rules = rules or {}
    min_score = float(rules.get("entry_min_composite") or 55)
    alerts_created = []
    for sym in symbols[:20]:
        sym = sym.upper().strip()
        if not sym:
            continue
        try:
            analysis = analyze_fn(sym)
            score = float(analysis.get("composite_score") or 0)
            stance = str(analysis.get("composite_stance") or "neutral")
            price = analysis.get("price") or quote_fn(sym)
        except Exception as exc:
            push_alert(f"Scan failed: {exc}", symbol=sym, severity="warn")
            continue

        bullish = stance.lower() in {"favorable", "strong_favorable", "bullish", "constructive"}
        if score >= min_score and bullish:
            a = push_alert(
                f"{sym} composite {score:.1f} ({stance}) — watchlist signal",
                symbol=sym,
                severity="signal",
                meta={"composite_score": score, "stance": stance, "price": price},
            )
            alerts_created.append(a)
        bearish = stance.lower() in {"cautious", "unfavorable", "bearish"}
        if score <= 40 and bearish:
            a = push_alert(
                f"{sym} weak composite {score:.1f} ({stance})",
                symbol=sym,
                severity="caution",
                meta={"composite_score": score, "stance": stance, "price": price},
            )
            alerts_created.append(a)

    data = _load()
    data["last_scan_at"] = _now()
    _save(data)
    return {"scanned": len(symbols), "alerts_created": len(alerts_created), "alerts": alerts_created}
