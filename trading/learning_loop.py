"""Turn a weak backtest into a lesson, then optionally ask GenAI or Cursor."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from config import BASE_DIR

GAPS_PATH = BASE_DIR / "data" / "trading" / "learning_gaps.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load() -> dict[str, Any]:
    if not GAPS_PATH.exists():
        return {"gaps": []}
    try:
        return json.loads(GAPS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"gaps": []}


def _save(data: dict[str, Any]) -> None:
    GAPS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GAPS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def gap_from_stats(stats: dict[str, Any], *, symbol: str = "", trigger: str = "") -> Optional[dict[str, Any]]:
    """A gap is a result we should not trust or should not repeat."""
    n = int(stats.get("n_trades") or 0)
    exp = stats.get("expectancy_pct")
    win_rate = stats.get("win_rate")
    reasons: list[str] = []
    if n < 8:
        reasons.append("too few completed trades to trust the result")
    if exp is not None and float(exp) < 0:
        reasons.append("the average trade lost money after a simple cost allowance")
    if win_rate is not None and n >= 8 and float(win_rate) < 0.45:
        reasons.append("fewer than 45% of trades were winners")
    if not reasons:
        return None
    return {
        "id": f"gap-{uuid.uuid4().hex[:10]}",
        "at": _now(),
        "symbol": symbol,
        "trigger": trigger,
        "summary": "; ".join(reasons),
        "stats": {
            "n_trades": n,
            "expectancy_pct": exp,
            "win_rate": win_rate,
        },
        "status": "open",
    }


def record_gaps(gaps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not gaps:
        return []
    data = _load()
    data.setdefault("gaps", [])
    data["gaps"] = (gaps + data["gaps"])[:80]
    _save(data)
    return gaps


def list_gaps(limit: int = 20) -> list[dict[str, Any]]:
    return (_load().get("gaps") or [])[:limit]


def explain_gap_with_genai(gap_id: str) -> dict[str, Any]:
    """Ask the configured chat model for a plain recommendation. No code edits."""
    gap = next((g for g in list_gaps(80) if g.get("id") == gap_id), None)
    if not gap:
        return {"ok": False, "reason": "Gap not found."}
    from llm_providers import chat_completion

    system = (
        "You help a person who may not know markets. "
        "Explain one backtest gap in 4 short sentences. "
        "Say what failed, one safer rule to try next, and that this is not a buy or sell. "
        "Do not invent numbers that were not given."
    )
    user = json.dumps({"gap": gap}, default=str)
    try:
        result = chat_completion(system=system, user=user)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:200], "gap_id": gap_id}
    text = result.text
    _attach(gap_id, "genai_note", text[:1200])
    return {"ok": True, "gap_id": gap_id, "provider": result.provider, "note": text[:1200]}


def apply_gap_with_cursor(gap_id: str, *, allow_code_edits: bool = False) -> dict[str, Any]:
    """
    Local Cursor agent. Edits recommendation code only when allow_code_edits is true.
    Never asked to place or route orders.
    """
    gap = next((g for g in list_gaps(80) if g.get("id") == gap_id), None)
    if not gap:
        return {"ok": False, "reason": "Gap not found."}
    from integrations.keys import get_secret

    api_key = get_secret("cursor")
    if not api_key:
        from llm_providers import cursor_api_key

        api_key = cursor_api_key()
    if not api_key:
        return {"ok": False, "reason": "Add a Cursor API key in Settings."}
    try:
        from cursor_sdk import Agent, AgentOptions, CursorAgentError, LocalAgentOptions
    except ImportError:
        return {"ok": False, "reason": "Install the Cursor SDK in this environment: pip install cursor-sdk"}

    scope = (
        "You may edit trading/agent_learning.py, trading/agent_selection.py, and quant_layer/ only."
        if allow_code_edits
        else "Do not edit Python. Write the proposal to data/trading/learning_proposals.md only."
    )
    prompt = (
        "A backtest found a learning gap in Scan Bhav. Improve the recommendation, not order placement.\n"
        f"{scope}\n"
        "Do not edit brokers/, trading/order_router.py, trading/paper_ledger.py, or routes that place orders.\n"
        "Do not commit or push.\n"
        f"Gap JSON:\n{json.dumps(gap, default=str)}\n"
        "Finish with a short summary of what you changed or proposed."
    )
    try:
        result = Agent.prompt(
            prompt,
            AgentOptions(
                api_key=api_key,
                model="composer-2.5",
                local=LocalAgentOptions(cwd=str(BASE_DIR)),
            ),
        )
    except CursorAgentError as exc:
        return {"ok": False, "reason": f"Cursor did not start: {exc.message}"[:240], "retryable": bool(exc.is_retryable)}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:240]}

    status = str(getattr(result, "status", "") or "")
    text = str(getattr(result, "result", "") or "")
    ok = status in {"finished", "completed", "success"}
    _attach(gap_id, "cursor_note", text[:1500] or status)
    return {"ok": ok, "status": status, "gap_id": gap_id, "summary": text[:1500]}


def _attach(gap_id: str, field: str, text: str) -> None:
    data = _load()
    for gap in data.get("gaps") or []:
        if gap.get("id") == gap_id:
            gap[field] = text
            gap["status"] = "reviewed"
            break
    _save(data)
