"""Layer 1 — deterministic quant pipeline for Nifty 500 (no LLM).

Computes indicators + backtestable trigger flags from OHLCV, filters to a shortlist.
"""
from quant_layer.features import row_to_llm_payload
from quant_layer.pipeline import analyze_symbol_rows, build_universe_shortlist
from quant_layer.triggers import TRIGGER_COLUMNS, compute_triggers, fired_triggers

__all__ = [
    "TRIGGER_COLUMNS",
    "analyze_symbol_rows",
    "build_universe_shortlist",
    "compute_triggers",
    "fired_triggers",
    "row_to_llm_payload",
]
