"""Layer 2 — LLM synthesis (Agents 1, 2, 7, 8)."""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from llm_providers import LLMResult, chat_completion
from quant_layer.playbooks import (
    AGENT1_ENTRY_PLAYBOOK,
    AGENT2_VALIDATION_PLAYBOOK,
    COMBINED_PLAYBOOK,
    MARKET_REGIME_PLAYBOOK,
)


def _extract_json_payload(text: str) -> Any:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        for pattern in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    continue
    return {"narrative": text}


def _llm_json_call(system: str, user: str, *, provider: Optional[str], model: Optional[str]) -> dict[str, Any]:
    result: LLMResult = chat_completion(system=system, user=user, provider=provider, model=model, temperature=0.15)
    parsed = _extract_json_payload(result.text)
    return {"parsed": parsed, "provider": result.provider, "model": result.model, "raw": result.text[:1500]}


def agent1_entry_rank(
    shortlist_rows: list[dict[str, Any]],
    *,
    regime: Optional[dict[str, Any]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    user = (
        AGENT1_ENTRY_PLAYBOOK
        + "\n\nRegime:\n"
        + json.dumps(regime or {}, indent=2)
        + "\n\nStocks:\n"
        + json.dumps(shortlist_rows, indent=2)
        + '\n\nReturn JSON: {"rankings":[{"symbol","conviction_score","rationale","signal_types","conflicting_signals"}]}'
    )
    try:
        out = _llm_json_call(
            "Agent 1 entry ranker. JSON only.",
            user,
            provider=provider,
            model=model,
        )
        rankings = (out["parsed"] or {}).get("rankings")
        if isinstance(rankings, list):
            return {"rankings": rankings, "llm_used": True, **{k: out[k] for k in ("provider", "model")}}
    except Exception as exc:
        return {"rankings": _fallback_rank(shortlist_rows), "llm_used": False, "error": str(exc), "fallback": True}
    return {"rankings": _fallback_rank(shortlist_rows), "llm_used": False, "fallback": True}


def agent2_validate(
    shortlist_rows: list[dict[str, Any]],
    *,
    entry_rankings: list[dict[str, Any]],
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    user = (
        AGENT2_VALIDATION_PLAYBOOK
        + "\n\nEntry rankings:\n"
        + json.dumps(entry_rankings, indent=2)
        + "\n\nStock facts:\n"
        + json.dumps(shortlist_rows, indent=2)
        + '\n\nReturn JSON: {"validations":[{"symbol","validation_score","validation_notes","false_breakout_risk"}]}'
    )
    try:
        out = _llm_json_call("Agent 2 validator. JSON only.", user, provider=provider, model=model)
        vals = (out["parsed"] or {}).get("validations")
        if isinstance(vals, list):
            return {"validations": vals, "llm_used": True}
    except Exception:
        pass
    return {"validations": _fallback_validation(shortlist_rows), "llm_used": False, "fallback": True}


def agent7_news_context(symbols: list[str], *, provider: Optional[str] = None, model: Optional[str] = None) -> dict[str, Any]:
    notes: list[dict[str, Any]] = []
    try:
        from trading.market_news_intel import fetch_symbol_news_intel

        for sym in symbols[:20]:
            sym_u = sym if sym.endswith(".NSE") else f"{sym}.NSE"
            try:
                scored = fetch_symbol_news_intel(sym_u, fast=True)
                notes.append({
                    "symbol": sym_u,
                    "news_score": scored.get("news_score"),
                    "headline_count": scored.get("headline_count"),
                    "tags": scored.get("tags") or [],
                })
            except Exception:
                continue
    except Exception as exc:
        return {"notes": notes, "error": str(exc)[:120]}
    return {"notes": notes}


def run_full_llm_pipeline(
    shortlist_rows: list[dict[str, Any]],
    *,
    regime: Optional[dict[str, Any]] = None,
    use_llm: bool = True,
    provider: Optional[str] = None,
    model: Optional[str] = None,
) -> dict[str, Any]:
    if not shortlist_rows:
        return {"rankings": [], "llm_used": False}
    symbols = [str(r.get("symbol_full") or r.get("symbol") or "") for r in shortlist_rows]
    news = agent7_news_context(symbols)
    for row in shortlist_rows:
        sym = str(row.get("symbol_full") or row.get("symbol") or "")
        note = next((n for n in news.get("notes") or [] if n.get("symbol") == sym), None)
        if note:
            row["news_score"] = note.get("news_score")
            row["news_tags"] = note.get("tags")

    if not use_llm:
        return {"rankings": _fallback_rank(shortlist_rows), "llm_used": False, "fallback": True, "news": news}

    a1 = agent1_entry_rank(shortlist_rows, regime=regime, provider=provider, model=model)
    a2 = agent2_validate(
        shortlist_rows,
        entry_rankings=a1.get("rankings") or [],
        provider=provider,
        model=model,
    )
    merged = _merge_agents(a1.get("rankings") or [], a2.get("validations") or [], shortlist_rows)
    return {
        "rankings": merged,
        "llm_used": bool(a1.get("llm_used") or a2.get("llm_used")),
        "agent1": a1,
        "agent2": a2,
        "agent7_news": news,
    }


def _merge_agents(
    entries: list[dict[str, Any]],
    validations: list[dict[str, Any]],
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    val_by = {str(v.get("symbol")): v for v in validations}
    if not entries:
        entries = _fallback_rank(rows)
    merged: list[dict[str, Any]] = []
    for e in entries:
        sym = str(e.get("symbol") or "")
        v = val_by.get(sym) or val_by.get(sym.replace(".NSE", "")) or {}
        merged.append({
            **e,
            "validation_score": v.get("validation_score", e.get("validation_score", 0)),
            "validation_notes": v.get("validation_notes"),
            "false_breakout_risk": v.get("false_breakout_risk", False),
        })
    merged.sort(key=lambda x: -float(x.get("conviction_score") or 0))
    return merged


def rank_shortlist_with_llm(
    shortlist_rows: list[dict[str, Any]],
    *,
    regime: Optional[dict[str, Any]] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    max_retries: int = 2,
) -> dict[str, Any]:
    return run_full_llm_pipeline(
        shortlist_rows,
        regime=regime,
        use_llm=True,
        provider=provider,
        model=model,
    )


def _fallback_rank(shortlist_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for row in shortlist_rows:
        triggers = row.get("triggers_fired") or []
        score = min(10.0, 2.0 + len(triggers) * 0.8)
        rsi = row.get("rsi_14")
        if rsi is not None and float(rsi) < 35:
            score += 1.0
        if row.get("trend_50_over_200"):
            score += 0.5
        ranked.append({
            "symbol": row.get("symbol") or row.get("symbol_full"),
            "conviction_score": round(min(10.0, score), 1),
            "validation_score": min(5, len(triggers) // 2),
            "rationale": f"Quant fallback: {len(triggers)} triggers.",
            "conflicting_signals": [],
            "signal_types": triggers,
        })
    ranked.sort(key=lambda x: -float(x.get("conviction_score") or 0))
    return ranked


def _fallback_validation(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        score = 0
        if float(row.get("vol_vs_avg20") or 0) >= 1.5:
            score += 1
        if row.get("delivery_pct") and float(row["delivery_pct"]) >= 55:
            score += 1
        if row.get("oi_change_signal") in ("long_buildup", "short_covering"):
            score += 1
        out.append({
            "symbol": row.get("symbol") or row.get("symbol_full"),
            "validation_score": min(5, score),
            "validation_notes": "Deterministic Agent-2 fallback",
            "false_breakout_risk": float(row.get("vol_vs_avg20") or 0) < 1.2 and "52w_breakout" in (row.get("triggers_fired") or []),
        })
    return out


def build_composite_report(
    *,
    quant_scan: dict[str, Any],
    llm_result: dict[str, Any],
    regime: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    rankings = llm_result.get("rankings") or []
    by_symbol = {str(r.get("symbol")): r for r in rankings}
    merged: list[dict[str, Any]] = []
    for item in quant_scan.get("shortlist") or []:
        sym = str((item.get("payload") or {}).get("symbol") or item.get("symbol") or "")
        llm_row = by_symbol.get(sym) or by_symbol.get(sym.replace(".NSE", ""))
        merged.append({
            "symbol": item.get("symbol"),
            "quant": item,
            "llm": llm_row,
            "composite_score": _composite_score(item, llm_row, regime),
        })
    merged.sort(key=lambda x: -float(x.get("composite_score") or 0))
    conflicts = [
        {"symbol": m["symbol"], "note": "LLM low conviction despite quant triggers"}
        for m in merged
        if int((m.get("quant") or {}).get("trigger_count") or 0) >= 3
        and float((m.get("llm") or {}).get("conviction_score") or 0) < 4
    ]
    return {
        "regime": regime,
        "quant_summary": {
            "universe_size": quant_scan.get("universe_size"),
            "triggered_count": quant_scan.get("triggered_count"),
            "shortlist_count": quant_scan.get("shortlist_count"),
        },
        "ranked": merged,
        "conflicts": conflicts,
        "llm_meta": {
            "llm_used": llm_result.get("llm_used"),
            "fallback": llm_result.get("fallback"),
            "provider": (llm_result.get("agent1") or {}).get("provider"),
            "error": llm_result.get("error"),
        },
    }


def _composite_score(quant_item: dict[str, Any], llm_row: Optional[dict[str, Any]], regime: Optional[dict[str, Any]]) -> float:
    q = float(quant_item.get("trigger_count") or 0) * 1.5
    if llm_row:
        q += float(llm_row.get("conviction_score") or 0) * 0.8
        q += float(llm_row.get("validation_score") or 0) * 0.4
        if llm_row.get("false_breakout_risk"):
            q *= 0.7
    if regime and regime.get("regime") == "trending_down":
        q *= 0.85
    return round(q, 2)
