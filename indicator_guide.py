"""Hover/help copy for every technical parameter shown in ScanBhav."""
from __future__ import annotations

INDICATOR_GUIDE: dict[str, dict[str, str]] = {
    "sma_20": {
        "title": "SMA 20",
        "what": "20-day simple moving average — average closing price over the last 20 sessions.",
        "why": "Short-term trend filter. Price above SMA20 often means near-term buyers are in control.",
    },
    "sma_50": {
        "title": "SMA 50",
        "what": "50-day simple moving average — medium-term trend baseline.",
        "why": "Widely watched swing level. Sustained trades above SMA50 support a medium-term uptrend.",
    },
    "sma_100": {
        "title": "SMA 100",
        "what": "100-day simple moving average.",
        "why": "Bridge between swing and position trends; useful confirmation with SMA50/200.",
    },
    "sma_200": {
        "title": "SMA 200",
        "what": "200-day simple moving average — long-term trend line.",
        "why": "Classic bull/bear regime marker. Institutions watch price vs SMA200 closely.",
    },
    "ema_9": {
        "title": "EMA 9",
        "what": "9-day exponential moving average — reacts faster to recent prices.",
        "why": "Short-term momentum trigger; often used with EMA21 for quick trend shifts.",
    },
    "ema_12": {
        "title": "EMA 12",
        "what": "Fast EMA used inside the classic MACD calculation.",
        "why": "Helps measure short-cycle momentum versus the slower EMA26.",
    },
    "ema_21": {
        "title": "EMA 21",
        "what": "21-day exponential moving average.",
        "why": "Popular swing trend guide; pullbacks to EMA21 are often watched in uptrends.",
    },
    "ema_26": {
        "title": "EMA 26",
        "what": "Slow EMA used inside MACD.",
        "why": "Anchors MACD; crossover with EMA12 signals momentum change.",
    },
    "ema_50": {
        "title": "EMA 50",
        "what": "50-day exponential moving average.",
        "why": "Faster than SMA50; useful for medium-term trend confirmation.",
    },
    "ema_200": {
        "title": "EMA 200",
        "what": "200-day exponential moving average.",
        "why": "Long-term trend with slightly faster response than SMA200.",
    },
    "rsi_14": {
        "title": "RSI 14",
        "what": "Relative Strength Index (14) — momentum oscillator from 0–100.",
        "why": "Above 70 can flag overbought; below 30 oversold. Mid-50s often supports trend continuation.",
    },
    "rsi_7": {
        "title": "RSI 7",
        "what": "Faster RSI for short-horizon swings.",
        "why": "More sensitive for 1D–1W decisions; noisier than RSI14.",
    },
    "macd": {
        "title": "MACD line",
        "what": "EMA12 − EMA26 momentum differential.",
        "why": "Shows whether short-term momentum is stronger than the slower trend.",
    },
    "macd_signal": {
        "title": "MACD signal",
        "what": "9-period EMA of the MACD line.",
        "why": "Crossovers with the MACD line are classic entry/exit timing cues.",
    },
    "macd_hist": {
        "title": "MACD histogram",
        "what": "MACD line minus signal line.",
        "why": "Positive histogram = bullish momentum; shrinking bars can warn of fading strength.",
    },
    "stoch_k": {
        "title": "Stochastic %K",
        "what": "Where close sits inside the recent high-low range (14).",
        "why": "High readings can mean stretched upside; low readings stretched downside.",
    },
    "stoch_d": {
        "title": "Stochastic %D",
        "what": "Smoothed %K (signal).",
        "why": "%K/%D crosses refine overbought/oversold timing.",
    },
    "atr_14": {
        "title": "ATR 14",
        "what": "Average True Range — typical daily movement size.",
        "why": "Position sizing and stop distance; rising ATR means expanding volatility.",
    },
    "atr_pct": {
        "title": "ATR %",
        "what": "ATR as a percent of price.",
        "why": "Comparable volatility across cheap vs expensive stocks.",
    },
    "bb_upper": {
        "title": "Bollinger upper",
        "what": "SMA20 + 2 standard deviations.",
        "why": "Stretch zone; closes above can mean strong trend or short-term exhaustion.",
    },
    "bb_middle": {
        "title": "Bollinger middle",
        "what": "20-day SMA at the center of the bands.",
        "why": "Mean-reversion magnet in sideways markets; trend guide in strong markets.",
    },
    "bb_lower": {
        "title": "Bollinger lower",
        "what": "SMA20 − 2 standard deviations.",
        "why": "Support/stretch zone on pullbacks; often watched for bounce setups.",
    },
    "bb_pct_b": {
        "title": "BB %B",
        "what": "Where price sits between lower (0) and upper (1) bands.",
        "why": ">1 = above upper band; <0 = below lower band — extremes matter for timing.",
    },
    "bb_bandwidth_pct": {
        "title": "BB bandwidth",
        "what": "Band width as % of middle band.",
        "why": "Squeeze (low bandwidth) often precedes big moves; expansion confirms breakouts.",
    },
    "adx_14": {
        "title": "ADX 14",
        "what": "Average Directional Index — trend strength (not direction).",
        "why": "ADX > 25 usually means a usable trend; low ADX means choppy range.",
    },
    "plus_di": {
        "title": "+DI",
        "what": "Positive directional indicator.",
        "why": "When +DI > −DI, upside pressure dominates the directional move.",
    },
    "minus_di": {
        "title": "−DI",
        "what": "Negative directional indicator.",
        "why": "When −DI > +DI, downside pressure dominates.",
    },
    "supertrend": {
        "title": "Supertrend",
        "what": "ATR-based trailing trend line (period 10, multiplier 3).",
        "why": "Simple trend-following guide for stay-long vs stay-short regimes.",
    },
    "supertrend_dir": {
        "title": "Supertrend direction",
        "what": "+1 bullish regime, −1 bearish regime.",
        "why": "Quick binary trend state for alerts and horizon scoring.",
    },
    "rvol": {
        "title": "Relative volume",
        "what": "Today’s volume vs 20-day average volume.",
        "why": "High RVOL with rising price confirms conviction; with falling price warns of distribution.",
    },
    "obv": {
        "title": "OBV",
        "what": "On-Balance Volume — cumulative volume signed by up/down closes.",
        "why": "Rising OBV with flat price can hint at accumulation.",
    },
    "obv_slope_20": {
        "title": "OBV slope (20)",
        "what": "Change in OBV over ~20 sessions.",
        "why": "Positive slope supports accumulation; negative supports distribution.",
    },
    "cci_20": {
        "title": "CCI 20",
        "what": "Commodity Channel Index — deviation from typical price mean.",
        "why": "Beyond ±100 flags strong momentum extremes useful for swing timing.",
    },
    "williams_r": {
        "title": "Williams %R",
        "what": "Close location in the high-low range (inverted scale).",
        "why": "Similar to stochastic; −20/−80 zones mark short-term extremes.",
    },
    "roc_12": {
        "title": "ROC 12",
        "what": "12-session rate of change of price.",
        "why": "Pure momentum percentage — useful for short/medium horizon ranking.",
    },
    "mfi_14": {
        "title": "MFI 14",
        "what": "Money Flow Index — RSI-like oscillator that includes volume.",
        "why": "Confirms whether money is actually flowing with the move.",
    },
    "pivot": {
        "title": "Classic pivot",
        "what": "Prior session (H+L+C)/3 reference level.",
        "why": "Intraday/short-swing magnets for support and resistance.",
    },
    "golden_cross": {
        "title": "Golden cross",
        "what": "SMA50 above SMA200.",
        "why": "Classic longer-term bullish regime signal.",
    },
    "death_cross": {
        "title": "Death cross",
        "what": "SMA50 below SMA200.",
        "why": "Classic longer-term cautious/bearish regime signal.",
    },
    "ema_stack_bullish": {
        "title": "EMA stack",
        "what": "EMA9 > EMA21 > EMA50 alignment.",
        "why": "Clean short-to-medium bullish trend structure.",
    },
    "dist_from_52w_high_pct": {
        "title": "Distance from 52w high",
        "what": "How far price sits below the 52-week peak.",
        "why": "Near highs = strength; deep discounts need thesis confirmation.",
    },
    "dist_from_52w_low_pct": {
        "title": "Distance from 52w low",
        "what": "How far price has bounced from the 52-week low.",
        "why": "Large rallies off lows show recovery momentum — and sometimes late-cycle risk.",
    },
    "r1": {
        "title": "Resistance R1",
        "what": "First classic pivot resistance (2×pivot − prior low).",
        "why": "Near-term upside ceiling often watched by day/swing traders.",
    },
    "s1": {
        "title": "Support S1",
        "what": "First classic pivot support (2×pivot − prior high).",
        "why": "Near-term downside floor; breaks can accelerate selling.",
    },
    "r2": {
        "title": "Resistance R2",
        "what": "Second pivot resistance (pivot + prior range).",
        "why": "Extension target if R1 is cleared with volume.",
    },
    "s2": {
        "title": "Support S2",
        "what": "Second pivot support (pivot − prior range).",
        "why": "Deeper support; useful for stop placement context.",
    },
    "high_52w": {
        "title": "52-week high",
        "what": "Highest close over roughly the last year.",
        "why": "Breakouts above can attract momentum; failures can trap bulls.",
    },
    "low_52w": {
        "title": "52-week low",
        "what": "Lowest close over roughly the last year.",
        "why": "Capitulation zone; bounces off lows can start recoveries.",
    },
    "volume": {
        "title": "Volume",
        "what": "Shares traded in the latest session.",
        "why": "Confirms conviction behind the price move.",
    },
    "volume_sma_20": {
        "title": "Volume SMA 20",
        "what": "20-day average volume.",
        "why": "Baseline for spotting unusual participation (RVOL).",
    },
    "price_vs_sma_20_pct": {
        "title": "Price vs SMA20",
        "what": "Percent distance of price from the 20-day SMA.",
        "why": "Stretched premiums/discounts vs short-term mean.",
    },
    "price_vs_sma_50_pct": {
        "title": "Price vs SMA50",
        "what": "Percent distance of price from the 50-day SMA.",
        "why": "Shows how extended the medium-term trend is.",
    },
    "price_vs_sma_200_pct": {
        "title": "Price vs SMA200",
        "what": "Percent distance of price from the 200-day SMA.",
        "why": "Long-term regime stretch — deep discounts can be value or value traps.",
    },
    "price_vs_ema_21_pct": {
        "title": "Price vs EMA21",
        "what": "Percent distance of price from the 21-day EMA.",
        "why": "Swing-trade extension vs a popular pullback line.",
    },
    "vwap": {
        "title": "VWAP",
        "what": "Volume-Weighted Average Price — average price paid weighted by shares traded (chart window).",
        "why": "Institutions often benchmark vs VWAP; price above VWAP suggests buyers paid up on the day.",
    },
    "poc": {
        "title": "POC (point of control)",
        "what": "Price bucket with the highest traded volume in the chart window.",
        "why": "Acts like a magnet — price often reacts when returning to high-volume nodes.",
    },
    "candlestick": {
        "title": "Candlestick",
        "what": "One bar = Open, High, Low, Close for a session. Body = open→close; wicks = extremes beyond the body.",
        "why": "Shows who won the session (bullish close ≥ open) and where rejection happened (long wicks).",
    },
    "adjusted_close": {
        "title": "Adjusted close",
        "what": "Closing price adjusted for splits, bonuses, and dividends.",
        "why": "Use this for long-term charts so old prices are comparable to today.",
    },
    "ichimoku_cloud": {
        "title": "Ichimoku cloud",
        "what": "Tenkan/Kijun lines plus Senkou span A/B forming a forward cloud.",
        "why": "Price above cloud supports bullish regime; TK cross adds timing.",
    },
    "fibonacci": {
        "title": "Fibonacci retracements",
        "what": "23.6–78.6% pullback levels from the recent swing leg.",
        "why": "Widely watched reaction zones in trending markets.",
    },
    "keltner": {"title": "Keltner channels", "what": "EMA middle band ± ATR multiple.", "why": "Trend channel; breaks signal momentum extension."},
    "donchian": {"title": "Donchian channels", "what": "Highest high / lowest low over N bars.", "why": "Breakout systems (Turtle) use Donchian edges."},
    "parabolic_sar": {"title": "Parabolic SAR", "what": "Stop-and-reverse dots trailing price.", "why": "Flips flag potential trend reversals."},
    "cmf": {"title": "Chaikin Money Flow", "what": "Volume-weighted accumulation over 20 sessions.", "why": "Positive CMF = buying pressure despite close location."},
    "ad_line": {"title": "Accumulation/Distribution", "what": "Running sum of money flow multiplier × volume.", "why": "Rising A/D with flat price can precede breakouts."},
    "aroon": {"title": "Aroon", "what": "Time since highest high / lowest low.", "why": "Aroon Up > 70 with Down < 30 = uptrend."},
    "tsi": {"title": "True Strength Index", "what": "Double-smoothed momentum oscillator.", "why": "Less noisy than RSI for swing trend shifts."},
    "hull_ma": {"title": "Hull MA", "what": "Weighted MA designed for low lag.", "why": "Faster trend flips than SMA/EMA of same length."},
    "rsi_macd_divergence": {"title": "RSI/MACD divergence", "what": "Price vs oscillator disagree at swing points.", "why": "Can warn of fading momentum before price turns."},
    "patterns_candlestick": {"title": "Candlestick patterns", "what": "Doji, Hammer, Engulfing, Morning Star, etc.", "why": "Session-level reversal/continuation cues."},
    "patterns_chart": {"title": "Chart patterns", "what": "H&S, double tops, triangles, flags, cup-handle.", "why": "Geometry of crowd psychology over weeks."},
    "piotroski": {"title": "Piotroski F-Score", "what": "Nine-point financial health checklist.", "why": "Higher scores correlate with quality factor outperformance."},
    "altman_z": {"title": "Altman Z-Score", "what": "Distress probability from balance sheet ratios.", "why": "Low Z flags credit risk beyond simple D/E."},
    "graham_number": {"title": "Graham number", "what": "Fair-value anchor from EPS × book value.", "why": "Classic margin-of-safety reference for value investors."},
    "options_pcr": {"title": "Options PCR (OI)", "what": "Put OI ÷ Call OI on nearest NSE expiry.", "why": "Extreme PCR can signal hedging or contrarian sentiment."},
    "fii_dii": {"title": "FII/DII flows", "what": "Daily foreign vs domestic institution net buys.", "why": "Flows drive index-level liquidity in India."},
    "market_regime": {"title": "Market regime", "what": "Bull/bear/sideways from VIX, SMA200, FII.", "why": "Regime filters which setups work best."},
}


INDICATOR_CATEGORIES: list[dict[str, str | list[str]]] = [
    {
        "id": "trend",
        "label": "Trend & moving averages",
        "summary": "Where price sits vs short, medium, and long-term averages.",
        "keys": [
            "sma_20", "sma_50", "sma_100", "sma_200",
            "ema_9", "ema_12", "ema_21", "ema_26", "ema_50", "ema_200",
            "golden_cross", "death_cross", "ema_stack_bullish",
            "supertrend", "supertrend_dir",
            "price_vs_sma_20_pct", "price_vs_sma_50_pct", "price_vs_sma_200_pct", "price_vs_ema_21_pct",
        ],
    },
    {
        "id": "momentum",
        "label": "Momentum oscillators",
        "summary": "Speed and strength of recent price moves.",
        "keys": [
            "rsi_14", "rsi_7", "macd", "macd_signal", "macd_hist",
            "stoch_k", "stoch_d", "cci_20", "williams_r", "roc_12", "mfi_14",
        ],
    },
    {
        "id": "volatility",
        "label": "Volatility & bands",
        "summary": "Typical range and stretch from the mean.",
        "keys": [
            "atr_14", "atr_pct", "bb_upper", "bb_middle", "bb_lower",
            "bb_pct_b", "bb_bandwidth_pct",
        ],
    },
    {
        "id": "strength",
        "label": "Trend strength (ADX)",
        "summary": "Whether the market is trending or chopping.",
        "keys": ["adx_14", "plus_di", "minus_di"],
    },
    {
        "id": "volume",
        "label": "Volume & participation",
        "summary": "Conviction behind price — accumulation vs distribution.",
        "keys": ["volume", "volume_sma_20", "rvol", "obv", "obv_slope_20", "vwap", "poc"],
    },
    {
        "id": "levels",
        "label": "Levels & range context",
        "summary": "Support, resistance, pivots, and 52-week positioning.",
        "keys": [
            "pivot", "r1", "s1", "r2", "s2",
            "high_52w", "low_52w", "dist_from_52w_high_pct", "dist_from_52w_low_pct",
        ],
    },
    {
        "id": "price",
        "label": "Price & candles",
        "summary": "Raw OHLC inputs feeding every indicator.",
        "keys": ["candlestick", "adjusted_close"],
    },
    {
        "id": "extended_ta",
        "label": "Extended technicals",
        "summary": "Ichimoku, Fibonacci, channels, PSAR, CMF, Aroon, TSI, Hull, divergence.",
        "keys": [
            "ichimoku_cloud", "fibonacci", "keltner", "donchian", "parabolic_sar",
            "cmf", "ad_line", "aroon", "tsi", "hull_ma", "rsi_macd_divergence",
            "patterns_candlestick", "patterns_chart",
        ],
    },
    {
        "id": "fundamentals_ext",
        "label": "Fundamentals & quality",
        "summary": "TTM metrics, debt quality, Piotroski, Altman, Graham, analyst consensus.",
        "keys": ["piotroski", "altman_z", "graham_number"],
    },
    {
        "id": "market_context",
        "label": "Market & India context",
        "summary": "Options, FII/DII, regime, sector RS, macro FX/commodities.",
        "keys": ["options_pcr", "fii_dii", "market_regime"],
    },
]


DESK_SECTIONS: list[dict[str, str | list[str]]] = [
    {
        "id": "analyze",
        "label": "Analyze desk",
        "route": "/",
        "summary": "Deep single-stock research — technical board, charts, investor lenses, dossier.",
        "includes": [
            "Composite score & grade across 10 horizons (1D → 5Y)",
            "Technical indicator board with hover explainers",
            "Candle charts with SMA/EMA/Bollinger/Supertrend overlays",
            "Deep dossier: conviction band, trend structure, risk flags",
            "Famous-investor pattern lenses (Buffett, Lynch, etc.)",
            "Session levels, events, news catalysts",
            "Live prediction lab — pin thesis vs price",
            "Gen AI live desk — research memo + RAG memory",
            "Extended factors — Ichimoku, patterns, quality scores, options PCR, regime",
        ],
    },
    {
        "id": "screener",
        "label": "Multi screener (Nifty 500)",
        "route": "/multi",
        "summary": "Rank the full Nifty 500 universe by horizon-aligned composite scores.",
        "includes": [
            "Large / mid / small cap buckets",
            "Sort & filter by grade, stance, RSI, composite",
            "Same indicator engine as Analyze — batch scored",
            "Sector heat map from cached run",
        ],
    },
    {
        "id": "swing",
        "label": "Swing desk",
        "route": "/swing",
        "summary": "Multi-day setup scan, ATR-sized plans, paper/live broker orders.",
        "includes": [
            "1W / 1M setup score from horizon ratings",
            "ATR-based position size, stop, and target",
            "Swing book — planned vs active trades",
            "Broker routing (Stub / Kite / Groww / FYERS)",
            "Live P&L from broker LTP or Yahoo fallback",
        ],
    },
    {
        "id": "autopilot",
        "label": "Autopilot desk",
        "route": "/autopilot",
        "summary": "Paper/live scheduler, timing intelligence, morning scan, risk caps.",
        "includes": [
            "Watchlist agent — alerts on composite shifts",
            "Paper autopilot entries on favorable windows",
            "Timing intel — IST session patterns + latency compensation",
            "Morning Nifty 500 scan → RAG for agent desk",
            "Prediction scoreboard & calibration weights",
            "Live reconcile, margin gate, SL-M at entry",
        ],
    },
    {
        "id": "portfolio",
        "label": "Portfolio desk",
        "route": "/portfolio",
        "summary": "Paper ledger with Indian fees and STCG/LTCG tax estimates.",
        "includes": [
            "Buy/sell with Zerodha/Groww charge schedules",
            "Holdings P&L, allocation, TA alerts",
            "Sell-all preview with tax and broker deductions",
        ],
    },
    {
        "id": "composite",
        "label": "Composite scoring",
        "route": "/method",
        "summary": "How horizon ratings roll up into one composite score and stance.",
        "includes": [
            "Each horizon (1D–5Y) scored from trend, momentum, volatility, volume inputs",
            "Grade A–F and stance (favorable / neutral / cautious)",
            "Best horizon highlighted for swing alignment",
            "Relative strength vs Nifty 50 where available",
            "Educational heuristic — not a buy/sell signal",
        ],
    },
]


def build_reference() -> dict[str, object]:
    categorized: dict[str, list[dict[str, str]]] = {}
    for cat in INDICATOR_CATEGORIES:
        rows = []
        for key in cat["keys"]:
            row = INDICATOR_GUIDE.get(key)
            if row:
                rows.append({"id": key, **row})
        categorized[str(cat["id"])] = rows

    uncategorized = [
        {"id": k, **v}
        for k, v in INDICATOR_GUIDE.items()
        if not any(k in cat["keys"] for cat in INDICATOR_CATEGORIES)
    ]

    return {
        "indicator_count": len(INDICATOR_GUIDE),
        "categories": INDICATOR_CATEGORIES,
        "indicators_by_category": categorized,
        "indicators_uncategorized": uncategorized,
        "all_indicators": [{"id": k, **v} for k, v in INDICATOR_GUIDE.items()],
        "desk_sections": DESK_SECTIONS,
    }


def guide_for(keys: list[str] | None = None) -> dict[str, dict[str, str]]:
    if not keys:
        return INDICATOR_GUIDE
    return {k: INDICATOR_GUIDE[k] for k in keys if k in INDICATOR_GUIDE}
