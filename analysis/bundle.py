"""Orchestrate all extended analysis modules into one payload."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from analysis.analyst_data import fetch_analyst_history
from analysis.divergence import compute_divergence
from analysis.external_factors import compute_external_factors
from analysis.fundamentals_ext import compute_fundamentals_extended
from analysis.india_data import compute_india_disclosures
from analysis.indicators_extended import compute_extended_indicators
from analysis.insider_data import compute_insider_context
from analysis.intraday import compute_intraday_ta
from analysis.market_context import compute_market_context
from analysis.options_context import compute_options_context
from analysis.patterns import compute_patterns
from analysis.regime import compute_regime
from analysis.score_blend import blend_extended_scores


def _run_slow_modules(sym: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Fetch india/options/insider/analyst in parallel."""

    def _safe(fn, default_status: str) -> dict[str, Any]:
        try:
            return fn()
        except Exception as exc:
            return {"status": default_status, "error": str(exc)[:80]}

    with ThreadPoolExecutor(max_workers=4) as pool:
        f_india = pool.submit(_safe, lambda: compute_india_disclosures(sym), "error")
        f_options = pool.submit(_safe, lambda: compute_options_context(sym), "error")
        f_insider = pool.submit(_safe, lambda: compute_insider_context(sym), "error")
        f_analyst = pool.submit(_safe, lambda: fetch_analyst_history(sym), "error")
        return f_india.result(), f_options.result(), f_insider.result(), f_analyst.result()


def build_extended_analysis(
    *,
    symbol: str,
    rows: list[dict[str, Any]],
    tech: dict[str, Any],
    quote: dict[str, Any] | None = None,
    news: dict[str, Any] | None = None,
    ratings: dict[str, Any] | None = None,
    include_slow: bool = True,
    screen_mode: bool = False,
    fast_social: bool = False,
) -> dict[str, Any]:
    """Build extended factor bundle and optionally blend into ratings.

    screen_mode skips per-symbol network modules (intraday, macro, social) so
    universe scans stay CPU-bound on cached daily bars.
    """
    sym = symbol.upper()
    indicators = compute_extended_indicators(rows)
    patterns = compute_patterns(rows)
    divergence = compute_divergence(rows)
    if screen_mode:
        from analysis.market_context import beta_scoring_context

        intraday = {"status": "skipped", "note": "screen_mode"}
        external = {"status": "skipped", "note": "screen_mode"}
        market_context = {
            "sector_relative_strength": {"status": "skipped", "note": "screen_mode"},
            "breadth": {"status": "skipped", "note": "screen_mode"},
            "beta_context": beta_scoring_context(tech, quote),
            "sector_board": {"status": "skipped", "note": "screen_mode"},
        }
    else:
        with ThreadPoolExecutor(max_workers=3) as pool:
            f_intra = pool.submit(compute_intraday_ta, sym)
            f_ext = pool.submit(compute_external_factors, sym, quote, news, fast_social=fast_social)
            f_mkt = pool.submit(compute_market_context, sym, tech, quote)
            intraday = f_intra.result()
            external = f_ext.result()
            market_context = f_mkt.result()
    fundamentals = compute_fundamentals_extended(quote)
    regime = compute_regime(tech, quote)

    india = {"status": "skipped"}
    options = {"status": "skipped"}
    insider = {"status": "skipped"}
    analyst = {"status": "skipped"}
    if include_slow:
        india, options, insider, analyst = _run_slow_modules(sym)

    bundle = {
        "symbol": sym,
        "indicators": indicators,
        "patterns": patterns,
        "divergence": divergence,
        "intraday": intraday,
        "fundamentals": fundamentals,
        "india": india,
        "options": options,
        "insider": insider,
        "analyst": analyst,
        "external": external,
        "market_context": market_context,
        "regime": regime,
        "coverage": _coverage_summary(indicators, patterns, fundamentals, india, options, external, intraday),
    }

    if ratings is not None:
        bundle["ratings_blended"] = blend_extended_scores(ratings, bundle)
    return bundle


def _coverage_summary(*parts) -> dict[str, Any]:
    ok = sum(1 for p in parts if isinstance(p, dict) and p.get("status") in ("ok", None))
    total = len(parts)
    return {
        "modules_ok": ok,
        "modules_total": total,
        "pct": round(100 * ok / max(total, 1)),
    }


def extended_summary_for_agents(extended: dict[str, Any]) -> str:
    """Compact text block for GenAI agent prompts."""
    if not extended:
        return ""
    lines = []
    ich = (extended.get("indicators") or {}).get("ichimoku") or {}
    if ich.get("price_vs_cloud"):
        lines.append(f"Ichimoku: price {ich['price_vs_cloud']} cloud; TK cross {ich.get('tenkan_kijun_cross')}.")
    pat = extended.get("patterns") or {}
    if pat.get("active_patterns"):
        lines.append(f"Patterns: {', '.join(pat['active_patterns'][:4])} ({pat.get('composite_bias')}).")
    div = extended.get("divergence") or {}
    if div.get("composite_signal") not in (None, "none"):
        lines.append(f"Divergence: {div.get('composite_signal')} — {div.get('headline', '')[:80]}")
    fund = extended.get("fundamentals") or {}
    qs = (fund.get("quality_scores") or {})
    if qs.get("composite_quality"):
        lines.append(f"Quality: Piotroski {qs.get('piotroski', {}).get('score')}/9, composite {qs['composite_quality']}.")
    reg = ((extended.get("regime") or {}).get("regime") or {}).get("regime")
    if reg:
        lines.append(f"Market regime: {reg}.")
    opt = extended.get("options") or {}
    if opt.get("pcr_oi"):
        lines.append(f"Options PCR(OI)={opt['pcr_oi']} ({opt.get('pcr_bias')}).")
    india = extended.get("india") or {}
    if india.get("headline"):
        lines.append(f"India disclosures: {india['headline'][:100]}.")
    intra = extended.get("intraday") or {}
    if intra.get("status") == "ok":
        lines.append(f"Intraday 1h: RSI={intra.get('rsi_14')}, vs VWAP {intra.get('price_vs_vwap')}.")
    analyst = extended.get("analyst") or {}
    if analyst.get("upgrade_bias"):
        lines.append(f"Analyst bias: {analyst.get('upgrade_bias')}, target {analyst.get('target_mean')}.")
    ins = extended.get("insider") or {}
    if ins.get("headline"):
        lines.append(ins["headline"][:90])
    return " ".join(lines)
