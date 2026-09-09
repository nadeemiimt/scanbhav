"""Daily automated pipeline — Agents 0–9 orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from analysis.llm_synthesis import build_composite_report, run_full_llm_pipeline
from quant_layer.agent0.etl import enrich_symbol_foundation, run_agent0_etl
from quant_layer.event_risk import apply_event_risk_filter
from quant_layer.feature_store import save_daily_snapshot
from quant_layer.pipeline import build_universe_shortlist
from quant_layer.regime import fetch_nifty_regime
from quant_layer.risk_sizing import attach_position_sizes
from quant_layer.trade_journal import log_signal


def daily_pipeline(
    *,
    load_rows: Callable[[str], list[dict[str, Any]]],
    limit: int = 500,
    max_shortlist: int = 30,
    use_llm: bool = True,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    account_risk_inr: float = 3500,
    max_notional_inr: float = 300000,
) -> dict[str, Any]:
    """Full PDF pipeline: Agent0 → Layer1 → Agent6 → Layer2 → Agent5 → Agent4 → Agent8."""
    started = datetime.now(timezone.utc).isoformat()
    agent0 = run_agent0_etl(force=False)
    regime = fetch_nifty_regime(load_rows)

    quant = build_universe_shortlist(
        load_rows=load_rows,
        limit=limit,
        max_shortlist=max_shortlist,
    )

    # Enrich LLM batch with Agent-0 foundation fields
    for item in quant.get("shortlist") or []:
        payload = item.get("payload") or {}
        sym = str(item.get("symbol") or payload.get("symbol_full") or "")
        extra = enrich_symbol_foundation(sym, as_of_date=payload.get("date"))
        payload.update({k: v for k, v in extra.items() if v is not None})
        item["payload"] = payload

    llm_batch = [i["payload"] for i in (quant.get("shortlist") or []) if i.get("payload")]
    llm_result = run_full_llm_pipeline(
        llm_batch,
        regime=regime,
        use_llm=use_llm,
        provider=provider,
        model=model,
    )

    report = build_composite_report(quant_scan=quant, llm_result=llm_result, regime=regime)
    ranked = report.get("ranked") or []
    survivors, filtered = apply_event_risk_filter(ranked)
    sized = attach_position_sizes(
        survivors,
        account_risk_inr=account_risk_inr,
        max_notional_inr=max_notional_inr,
    )

    final = {
        **report,
        "ranked": sized,
        "event_filtered_out": filtered,
        "agent0": agent0,
        "pipeline_started_at": started,
        "pipeline_finished_at": datetime.now(timezone.utc).isoformat(),
    }

    for row in sized[:10]:
        llm = row.get("llm") or {}
        sym = str(row.get("symbol") or "")
        log_signal(
            symbol=sym,
            conviction_score=float(llm.get("conviction_score") or 0),
            validation_score=float(llm.get("validation_score") or 0),
            triggers=(row.get("quant") or {}).get("triggers_fired") or [],
            rationale=str(llm.get("rationale") or "")[:500],
            source="daily_pipeline",
        )

    save_daily_snapshot(final)
    return final
