#!/usr/bin/env python3
"""Generate Autopilot Trading System Reference PDF."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from remaining_desk import build_pdf_bytes


def sections() -> list[dict]:
    return [
        {
            "heading": "1. High-level flow (both desks)",
            "body": [
                "Product: MIS intraday (same-day square-off). Modes: curated_list | agent_auto | dual_desk.",
                "09:00 IST — Pre-market analysis (no orders).",
                "09:15 IST — Market open; scheduler cycles begin.",
                "Each cycle: (1) Monitor exits (position_guard + LTP guard), (2) Check session/global caps,",
                "(3) Rank & pick candidates, (4) Run buy gates sequentially, (5) Execute MIS market buy,",
                "(6) Log pick + RAG lessons on close.",
                "15:20 IST — Mandatory EOD square-off window. 15:30 IST — Market close; auto-stop if flat.",
            ],
        },
        {
            "heading": "2. Shared scoring (_score_screen_row)",
            "body": [
                "Calibration base score — historical win-rate from calibration.json.",
                "Composite stance: +12 strong_favorable, +10 favorable, +9 bullish, +7 constructive; -15 bearish.",
                "RSI 14: +3 if 45-65; -5 if >=78.",
                "Quality: +4 if quality_ok; -8 if quality_fail. Pattern: +5 bullish; -6 bearish.",
                "Quality score +3 if >=65. Psychology mood/sentiment adjustments.",
                "RAG adjustment: +/- per win/loss lesson. Symbol win-rate from pick_log.",
                "Minimum composite to trade: entry_min_composite / agent_min_composite = 55 (default).",
            ],
        },
        {
            "heading": "3. Curated List — stock selection",
            "body": [
                "Universe: Your list only — 1-20 symbols (curated_symbols / watchlist).",
                "Pre-market: learn_timing_batch() on all curated symbols -> timing profiles + Chroma RAG.",
                "Data: Morning scan rows; missing symbols get live _analyze_symbol().",
                "Ranking: allocate_budget_picks(agent_smart=False) — sort by expected profit INR within budget.",
                "Filter: Bullish stance + composite >= 55; skip already-held symbols.",
                "No agent-only filters: no cap diversification, no cross-desk block, no min-notional skip.",
            ],
        },
        {
            "heading": "4. Auto Pick — stock selection",
            "body": [
                "Universe: Nifty 500 via morning scan (preferred) or screener cache.",
                "Pre-market: run_morning_scan() + agent_premarket_learn() — timing on top 30 + curated overlap.",
                "Deep analyze: Top 20 rows missing ATR/horizon get full _analyze_symbol().",
                "Scan depth: Top 80 rows (agent_scan_top_n). Ranking: rank_rows_for_agent() intraday edge.",
                "Intraday edge: composite x0.22, ATR (+18 if >=2%), horizon return, RSI, cap bucket weights",
                "(small 1.25, mid 1.12, large 0.88), pattern/supertrend/golden cross, rvol, realistic move.",
                "Agent learning layer: curated overlap +18, timing profile +/-8/6, learning curve from pick_log,",
                "RAG lessons +/-12. Diversification: max 2 large, 5 mid caps.",
                "Auto-only skips: cross-desk duplicate, notional < 25000 INR, agent_candidate_gate, 10:30 cutoff.",
            ],
        },
        {
            "heading": "5. Agent candidate gate (auto only)",
            "body": [
                "agent_min_atr_pct: 2.0 — block low volatility.",
                "agent_max_rsi_entry: 72 — block extended RSI.",
                "agent_min_horizon_return_pct: 0.5 — block negative horizon.",
                "agent_no_buy_after_minute_ist: 630 (10:30 IST) — no new auto picks after this.",
                "agent_block_quality_fail: optional quality gate.",
            ],
        },
        {
            "heading": "6. Position sizing (both desks)",
            "body": [
                "ATR risk sizing (default): qty sized so stop-out risks ~ risk_per_trade_inr.",
                "Effective stop = max(configured stop%, 50% of ATR%, 0.5%).",
                "Conviction multiplier when edge >= 75: x1.5 conservative / x2.5 home run.",
                "Capped by max_position_inr, remaining session budget, max_concurrent_picks slots.",
                "Conservative profile: risk_per_trade_inr = 3500. Home run: 8000.",
                "Conservative max_position_inr = 300000. Home run: 500000.",
            ],
        },
        {
            "heading": "7. BUY gates — exact order (first failure = skip)",
            "body": [
                "1. Late session block — no buys after 14:30 IST (no_buy_after_minute_ist=870). Both desks.",
                "2. Cross-desk duplicate — auto only; skip if other desk holds symbol.",
                "3. Agent candidate gate — auto only; ATR, RSI, horizon, 10:30 cutoff.",
                "4. Stop cooldown — no same-day re-buy after stop (stop_cooldown_enabled).",
                "5. Same-day symbol block — no re-buy after any exit today.",
                "6. RAG repeat-loser — block if >=2 RAG loss lessons OR pick_log WR <=35% with >=2 losses.",
                "7. Timing gate — preferred windows only: open_drive (9:15-9:45), morning_trend (9:45-10:30).",
                "8. Latency compensation — block negative momentum; optional early entry on pattern.",
                "9. Psychology buy gate — FOMO, euphoria, panic, defensive+bearish blocks.",
                "10. Risk validate_order — orders, loss cap, profit cap, positions, notional.",
                "11. validate_auto_entry — composite >= 55 for auto sources.",
                "Pre-market 9:00-9:15: plan only, no buys. Top-up: +0.5% after 10 min, max 25-50% of cap.",
            ],
        },
        {
            "heading": "8. SELL exits — priority order",
            "body": [
                "1. eod_square_off — >= 15:20 IST (square_off_minute_ist=920) or market closed.",
                "2. stop_hit — return <= -stop_pct.",
                "3. partial_scale_out — return >= scale-out level; sell 50% qty once per position.",
                "4. trailing_stop — peak >= trail_arm then pullback >= trail_pct from peak.",
                "5. power_hour_profit_lock — after 15:00, peak >= 0.4%, pullback >= 0.25%.",
                "6. target_hit — return >= effective target.",
                "7. unrealized_loss_cap — position loss exceeds max_unrealized_loss_inr; halts trading.",
                "8. psych_take_profit — greed + RSI>=70 + return >= 0.9%.",
                "9. psych_fear_cut — fear/defensive + return <= -0.55%.",
                "LTP guard: 3-second debounced tick triggers fast stop/target checks.",
            ],
        },
        {
            "heading": "9. Time-decay exit parameters",
            "body": [
                "Before 14:30: base target (profile), trail_arm 1.0%, trail 0.5%.",
                "14:30-15:00 power hour: target min(base, 1.0%), trail_arm 0.6%, trail 0.35%.",
                "After 15:00: target min(base, 0.8%), trail_arm 0.5%, trail 0.3%.",
                "Dynamic targets: small cap + ATR>=3.5% -> home_run_target (3.5% conservative / 5% home run).",
                "ATR>=3.0% -> extended_target (2.5% / 3.5%). Default target_pct = 2.0%.",
                "Partial scale-out: enabled, 50% of qty at 50% of target (~1% if target is 2%).",
            ],
        },
        {
            "heading": "10. RAG and learning curve",
            "body": [
                "Trade outcomes written on every sell; read during ranking and RAG buy gate.",
                "Timing profiles from pre-market learn; operational lessons (Aug 14 rules).",
                "Session digests at session end. Morning scan chunks at 9:00. Pick log win rate accumulated.",
                "RAG blocks buy: >=2 loss lessons OR pick_log >=2 losses with WR <=35%.",
                "On close: lessons feed Chroma -> tomorrow's picks rank higher/lower automatically.",
                "Agent also uses: timing_profile boost, curated overlap, learning_curve_adjustment.",
            ],
        },
        {
            "heading": "11. Global risk caps",
            "body": [
                "max_orders_per_day: 5 default (30 in active session).",
                "max_intraday_loss_inr: 5000 — halt all trading.",
                "max_profit_inr: 8000 — block new buys when hit (halt_new_buys_on_profit).",
                "max_unrealized_loss_inr: 3000 — halt + force exit.",
                "max_position_inr: 50000 default (300k conservative / 500k home run).",
                "max_daily_notional_inr: 100000. max_open_positions: 3.",
                "agent_min_composite: 55. default_stop_pct: 0.75%. default_target_pct: 1.5%.",
            ],
        },
        {
            "heading": "12. Per-session caps (dual desk typical)",
            "body": [
                "max_daily_notional_inr: up to 10L per desk.",
                "max_profit_inr: 50k-150k per desk (profit profile).",
                "max_intraday_loss_inr: 15k per desk. max_concurrent_picks: 3-5 per desk.",
                "Session ends: desk profit cap, desk loss cap, global halt, EOD auto-stop, user stop.",
                "On stop: desk positions flattened (session_stop_square).",
                "Before restart: orphan positions auto-squared (pre_restart_square).",
            ],
        },
        {
            "heading": "13. Profit profiles",
            "body": [
                "CONSERVATIVE: max_position 300k, risk/trade 3500, home_run_target 3.5%, conviction x1.5,",
                "pyramid 25%, desk profit cap 50k each. Tagline: 15-30k typical days.",
                "HOME RUN: max_position 500k, risk/trade 8000, home_run_target 5%, conviction x2.5,",
                "pyramid 50%, desk profit cap 150k each. Tagline: 150k ceiling on trend days.",
                "Auto home-run: morning score >= 65 switches agent to home_run; reverts if score <= 45.",
            ],
        },
        {
            "heading": "14. Timing windows (IST)",
            "body": [
                "pre_open 9:00-9:15 — No trades; analysis only.",
                "open_drive 9:15-9:45 — YES preferred buy window.",
                "morning_trend 9:45-10:30 — YES preferred buy window.",
                "midday 10:30-14:30 — Blocked for new buys if timing_preferred_windows_only=true.",
                "power_hour 14:30-15:20 — Exits tighten; no new buys (late block 14:30).",
                "closing 15:20-15:30 — EOD square-off. Agent hard cutoff: 10:30 for new auto picks.",
            ],
        },
        {
            "heading": "15. Psychology parameters",
            "body": [
                "psychology_block_rsi_fomo: 78 — block buy if greed + high RSI.",
                "psychology_block_sentiment_high: 85 — block euphoria buys.",
                "psychology_block_sentiment_low: 22 — block panic (unless fear dip + bullish).",
                "psychology_early_take_pct: 0.9% — early take in greed on sell.",
                "psychology_fear_stop_pct: 0.55% — tight fear cut on sell.",
                "psychology_greed_rsi_take: 70 — take profit trigger.",
            ],
        },
        {
            "heading": "16. Dual desk and operational guards",
            "body": [
                "Cross-desk dedup: Auto won't buy what curated already holds.",
                "Square on stop: stopping a desk flattens its open MIS legs.",
                "Square before restart: legacy orphan positions auto-squared before new session.",
                "Orphan banner in UI + manual Square all API endpoint.",
                "Mac sleep guard during session. LTP stream 3s poll for fast exits.",
            ],
        },
        {
            "heading": "17. Curated vs Auto — side by side",
            "body": [
                "Universe: Curated 1-20 your picks | Auto Nifty 500.",
                "Pre-market: Curated timing on all symbols | Auto scan 500 + timing top 30.",
                "Ranking: Curated expected profit INR | Auto edge + RAG + learning + diversification.",
                "Extra filters: Curated none | Auto ATR/RSI/horizon, 10:30 cutoff, min 25k, cross-desk.",
                "Buy gates after pick: IDENTICAL 11-step pipeline.",
                "Sell rules: IDENTICAL.",
                "RAG loop: IDENTICAL; Auto has richer ranking RAG.",
            ],
        },
        {
            "heading": "18. Full autopilot config keys",
            "body": [
                "Scan: morning_scan_enabled, morning_scan_hour_ist=9, morning_scan_rag_top=60, agent_scan_top_n=80.",
                "Agent selection: agent_smart_selection, agent_min_atr_pct=2, agent_max_rsi_entry=72,",
                "agent_min_rsi_entry=35, agent_min_horizon_return_pct=0.5, agent_no_buy_after=630,",
                "agent_max_large_picks=2, agent_max_mid_picks=5, cap weights small/mid/large.",
                "Agent learning: agent_learning_enabled, agent_timing_learn_top_n=30, agent_deep_analyze_top_n=20,",
                "agent_rag_top_k=5, agent_curated_overlap_boost=18, min_trade_notional_inr=25000.",
                "Entry/exit: target_pct, stop_pct, trailing_stop_*, no_buy_after=870, square_off=920,",
                "partial_scale_out_*, dynamic_target_*, home_run_target_pct, extended_target_pct.",
                "Sizing: atr_risk_sizing_enabled, risk_per_trade_inr, conviction_*, momentum_pyramid_*, top_up_*.",
                "Timing: timing_intel_enabled, timing_preferred_windows_only, timing_preferred_window_ids,",
                "timing_gate_auto_trades, timing_strict_symbol, timing_adaptive_loosen.",
                "RAG: rag_block_repeat_losers, rag_block_min_loss_lessons=2, rag_block_min_pick_losses=2,",
                "stop_cooldown_enabled, same_day_symbol_block.",
                "LTP: ltp_guard_enabled, ltp_guard_debounce_seconds=3, ltp_poll_seconds=3.",
                "Profiles: profit_profile, auto_home_run_enabled, auto_home_run_min_score=65.",
                "Session: max_concurrent_picks, session_auto_stop_at_close, poll_seconds=120.",
                "Live values may differ in data/trading/config.json and active profit profile.",
            ],
        },
        {
            "heading": "Disclaimer",
            "body": (
                "This document describes the ScanBhav / Stock Analyzer autopilot system behaviour "
                "as implemented in software. Paper trading uses stub/simulated fills unless live mode "
                "is armed. Not investment advice. Verify all parameters in config.json and the "
                "Autopilot Desk UI before trading."
            ),
        },
    ]


def main() -> None:
    out_dir = ROOT / "docs"
    out_dir.mkdir(exist_ok=True)
    date_str = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime("%Y-%m-%d")
    out_path = out_dir / f"Autopilot_Trading_System_Reference_{date_str}.pdf"

    title = "Autopilot Trading System Reference"
    subtitle = f"Curated List + Auto Pick — complete buy/sell pipeline | Generated {date_str}"
    pdf_bytes = build_pdf_bytes(f"{title}\n{subtitle}", sections())

    out_path.write_bytes(pdf_bytes)
    print(str(out_path))
    print(f"Size: {len(pdf_bytes):,} bytes")


if __name__ == "__main__":
    main()
