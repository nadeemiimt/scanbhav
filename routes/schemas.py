"""Pydantic request/response models for API routes."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator

from paper_trade import DEFAULT_TRADING_DAYS

class FetchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40, examples=["RELIANCE.BSE"])
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    force_refresh: bool = False


class CompareRequest(BaseModel):
    left_symbol: str = Field(min_length=1, max_length=40, examples=["RELIANCE.NSE"])
    right_symbol: str = Field(min_length=1, max_length=40, examples=["TCS.NSE"])
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    with_ai: bool = True


class PaperTradeRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=4, examples=[["RELIANCE.NSE", "TCS.NSE"]])
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    capital: float = Field(default=100_000.0, gt=1000, le=10_000_000)
    trading_days: int = Field(default=DEFAULT_TRADING_DAYS, ge=5, le=30)
    entry: Literal["close", "open"] = "close"
    with_ai: bool = True


class AgentResearchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    provider: Literal["auto", "yfinance", "nse"] = "auto"


class RagAskRequest(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    symbol: Optional[str] = Field(default=None, max_length=40)
    provider: Literal["auto", "yfinance", "nse"] = "auto"


class ProfileCreateRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    name: str = Field(default="My portfolio", min_length=1, max_length=80)
    risk_tolerance: Literal["conservative", "moderate", "aggressive"] = "moderate"


class PortfolioJsonIngestRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    profile_id: str = Field(min_length=36, max_length=36)
    portfolio: Union[Dict[str, Any], List[Any]]


class AdvisorRunRequest(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    profile_id: str = Field(min_length=36, max_length=36)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    with_ai: bool = True


class TaAnalyzeRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    force_refresh: bool = False


class GenaiResearchRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    provider: Optional[str] = Field(default=None, description="ollama | cursor | openai | openai_compatible | anthropic")
    model: Optional[str] = Field(default=None, description="Model id for the chosen provider")
    market_provider: Literal["auto", "yfinance", "nse"] = "auto"
    force_refresh: bool = False
    execute_trades: bool = Field(default=False, description="Agent hook: paper/live MIS order if autopilot rules pass")
    trade_quantity: int = Field(default=1, ge=1, le=1000)
    autonomous_picks: bool = Field(
        default=False,
        description="Agent scans watchlist/universe and picks top bullish names (trend + composite + news)",
    )
    max_autonomous_picks: int = Field(default=1, ge=1, le=3)


class PredictionTrackRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    name: str = Field(default="", max_length=120)
    entry_price: float = Field(gt=0)
    as_of: str = Field(default="", max_length=40)
    predicted_stance: str = Field(min_length=2, max_length=40)
    predicted_horizon: str = Field(default="1m", max_length=12)
    composite_score: Optional[float] = None
    conviction_score: Optional[float] = None
    summary: str = Field(default="", max_length=600)


class PredictionRateRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    notes: str = Field(default="", max_length=800)
    outcome_label: Optional[str] = Field(default=None, max_length=40)


class PredictionRefreshRequest(BaseModel):
    provider: Literal["auto", "yfinance", "nse"] = "auto"


class PositionSizeRequest(BaseModel):
    price: float = Field(gt=0)
    atr: Optional[float] = Field(default=None, gt=0)
    capital: float = Field(default=100_000.0, gt=1000, le=50_000_000)
    risk_pct: float = Field(default=1.0, ge=0.1, le=5.0)
    atr_stop_mult: float = Field(default=1.5, ge=0.5, le=4.0)
    reward_r: float = Field(default=2.0, ge=0.5, le=5.0)


class SwingSetupRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    force_refresh: bool = False
    with_dossier: bool = False
    capital: float = Field(default=100_000.0, gt=1000, le=50_000_000)
    risk_pct: float = Field(default=1.0, ge=0.1, le=5.0)
    atr_stop_mult: float = Field(default=1.5, ge=0.5, le=4.0)
    reward_r: float = Field(default=2.0, ge=0.5, le=5.0)


class SwingPlanRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    entry: float = Field(gt=0)
    stop: float = Field(gt=0)
    targets: list[float] = Field(default_factory=list, max_length=5)
    shares: int = Field(gt=0, le=1_000_000)
    thesis: str = Field(default="", max_length=1200)
    horizon: Literal["1w", "1m"] = "1w"
    capital: float = Field(default=100_000.0, gt=1000, le=50_000_000)
    risk_pct: float = Field(default=1.0, ge=0.1, le=5.0)
    trailing_stop: Optional[float] = Field(default=None, gt=0)
    atr_stop_mult: float = Field(default=1.5, ge=0.5, le=4.0)
    reward_r: float = Field(default=2.0, ge=0.5, le=5.0)


class SwingRecalcRequest(BaseModel):
    entry: float = Field(gt=0)
    stop: Optional[float] = Field(default=None, gt=0)
    capital: float = Field(default=100_000.0, gt=1000, le=50_000_000)
    risk_pct: float = Field(default=1.0, ge=0.1, le=5.0)
    atr: Optional[float] = Field(default=None, gt=0)
    atr_stop_mult: float = Field(default=1.5, ge=0.5, le=4.0)
    reward_r: float = Field(default=2.0, ge=0.5, le=5.0)


class SwingPnlRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=24)
    provider: Literal["auto", "yfinance", "nse"] = "auto"


class BrokerOrderRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    side: Literal["buy", "sell"]
    quantity: int = Field(gt=0, le=1_000_000)
    order_type: Literal["market", "limit", "sl", "sl-m"] = "limit"
    limit_price: Optional[float] = Field(default=None, gt=0)
    stop_price: Optional[float] = Field(default=None, gt=0)
    target_price: Optional[float] = Field(default=None, gt=0)
    broker: Literal["stub", "zerodha", "groww", "fyers"] = "stub"
    product: Literal["delivery", "intraday", "cnc", "mis"] = "delivery"
    trade_id: Optional[str] = Field(default=None, max_length=64)


class BrokerQuotesRequest(BaseModel):
    broker: Literal["stub", "zerodha", "groww", "fyers"] = "stub"
    symbols: list[str] = Field(min_length=1, max_length=48)


class PayoutAccountRequest(BaseModel):
    account_holder: str = Field(min_length=2, max_length=120)
    bank_name: str = Field(min_length=2, max_length=120)
    account_number: str = Field(min_length=4, max_length=24)
    ifsc: str = Field(min_length=11, max_length=11)
    upi_id: str = Field(default="", max_length=80)


class BrokerSellAllRequest(BaseModel):
    confirm: bool = False
    dry_run: bool = False
    include_mf: bool = False
    tax_bracket_rate_pct: float = Field(default=30.0, ge=0, le=42)


class SipRequest(BaseModel):
    monthly: float = Field(default=5000, ge=100, le=1_000_000)
    years: float = Field(default=10, ge=0.5, le=40)
    expected_annual_return_pct: float = Field(default=12.0, ge=-20, le=30)


class BacktestRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    strategy: Literal["sma_cross", "rsi_reversion", "trend_follow"] = "sma_cross"
    capital: float = Field(default=100_000.0, gt=1000, le=10_000_000)


class WatchScanRequest(BaseModel):
    symbols: list[str] = Field(default_factory=list, max_length=20)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    rules: Optional[Dict[str, Any]] = None


class OptionsPulseRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    price: Optional[float] = Field(default=None, gt=0)
    atr: Optional[float] = Field(default=None, gt=0)
    vix: Optional[float] = Field(default=None, ge=0, le=100)


class CorrelationRequest(BaseModel):
    symbols: list[str] = Field(min_length=2, max_length=12)
    provider: Literal["auto", "yfinance", "nse"] = "auto"


class NotifyRequest(BaseModel):
    alerts: list[Any] = Field(default_factory=list)
    webhook_url: Optional[str] = Field(default=None, max_length=500)
    telegram_bot_token: Optional[str] = Field(default=None, max_length=120)
    telegram_chat_id: Optional[str] = Field(default=None, max_length=40)


class ExportHtmlRequest(BaseModel):
    title: str = Field(default="ScanBhav Report", min_length=1, max_length=200)
    sections: list[Dict[str, Any]] = Field(default_factory=list)


class ExportPdfRequest(BaseModel):
    title: str = Field(default="ScanBhav Report", min_length=1, max_length=200)
    sections: list[Dict[str, Any]] = Field(default_factory=list)


class ExportCsvRequest(BaseModel):
    kind: Literal["brief", "watchlist", "journal", "holdings"] = "brief"
    rows: list[Dict[str, Any]] = Field(default_factory=list)
    symbol: Optional[str] = None


class ImportCsvRequest(BaseModel):
    kind: Literal["watchlist", "journal", "holdings"] = "watchlist"
    csv_text: str = Field(min_length=1, max_length=2_000_000)


class AccountImportRequest(BaseModel):
    version: int
    exported_at: Optional[str] = None
    payload: Dict[str, Any]


class BacktestSweepRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    strategy: Literal["sma_cross", "rsi_reversion", "trend_follow"] = "sma_cross"
    capital: float = Field(default=100_000.0, gt=1000, le=10_000_000)
    fast_periods: list[int] = Field(default_factory=lambda: [10, 20])
    slow_periods: list[int] = Field(default_factory=lambda: [50, 100])


class TaScreenRequest(BaseModel):
    limit: int = Field(default=500, ge=10, le=520)
    horizon: Literal["1d", "1w", "1m", "3m", "6m", "9m", "1y", "2y", "3y", "5y"] = "1m"
    force_refresh: bool = False
    max_workers: int = Field(default=8, ge=1, le=12)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    batch_size: int = Field(default=50, ge=5, le=100)
    batch_pause_seconds: float = Field(default=1.0, ge=0, le=60)
    retry_rounds: int = Field(default=1, ge=0, le=5)
    retry_pause_seconds: float = Field(default=20.0, ge=0, le=300)
    batch_strategy: Literal["round_robin", "sequential"] = Field(
        default="round_robin",
        description="round_robin = 50 large → 50 mid → 50 small → repeat; reduces rate limits",
    )
    bucket: Optional[Literal["large", "mid", "small"]] = Field(
        default=None,
        description="Optional cap bucket; null screens full Nifty 500",
    )


class PortfolioSettingsRequest(BaseModel):
    broker: Optional[Literal["zerodha", "groww"]] = None
    tax_bracket_id: Optional[str] = None
    tax_bracket_rate_pct: Optional[float] = Field(default=None, ge=0, le=42)


class PortfolioBuyRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    quantity: float = Field(gt=0, le=1_000_000)
    price: Optional[float] = Field(default=None, gt=0)
    asset_type: Literal["stock", "mutual_fund"] = "stock"
    name: str = Field(default="", max_length=120)
    broker: Optional[Literal["zerodha", "groww"]] = None
    bought_at: Optional[str] = None
    equity_oriented: bool = True
    provider: Literal["auto", "yfinance", "nse"] = "auto"


class PortfolioSellRequest(BaseModel):
    holding_id: str = Field(min_length=4, max_length=40)
    quantity: Optional[float] = Field(default=None, gt=0)
    price: Optional[float] = Field(default=None, gt=0)
    preview_only: bool = False
    provider: Literal["auto", "yfinance", "nse"] = "auto"


class PortfolioSellAllRequest(BaseModel):
    prices: Optional[Dict[str, float]] = None
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    preview_only: bool = True


class TradingConfigPatch(BaseModel):
    execution_mode: Optional[Literal["paper", "live"]] = None
    live_armed: Optional[bool] = None
    default_broker: Optional[Literal["stub", "zerodha", "groww", "fyers"]] = None
    default_product: Optional[Literal["delivery", "intraday", "cnc", "mis"]] = None
    risk: Optional[Dict[str, Any]] = None
    autopilot: Optional[Dict[str, Any]] = None
    watchlist: Optional[List[str]] = None


class IntradaySimConfigure(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    rules: Optional[Dict[str, Any]] = None


class IntradaySimTick(BaseModel):
    symbol: str = Field(min_length=1, max_length=40)
    price: Optional[float] = Field(default=None, gt=0)
    provider: Literal["auto", "yfinance", "nse"] = "auto"
    force_eod: bool = False


class SessionStartBody(BaseModel):
    pick_mode: Literal["curated_list", "agent_auto"] = "curated_list"
    symbols: Optional[List[str]] = Field(default=None, max_length=20)
    max_spend_inr: float = Field(default=200_000, gt=0)
    max_profit_inr: float = Field(default=30_000, gt=0)
    max_loss_inr: float = Field(default=15_000, gt=0)
    max_concurrent_picks: int = Field(default=3, ge=1, le=10)
    auto_square_orphans: bool = True

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, symbols: Optional[List[str]]) -> Optional[List[str]]:
        if symbols is None:
            return None
        from trading.symbol_validate import CURATED_SYMBOLS_MAX, normalize_symbol_list

        return normalize_symbol_list(symbols, max_count=CURATED_SYMBOLS_MAX)


class DualSessionStartBody(BaseModel):
    agent_max_spend_inr: float = Field(default=1_000_000, gt=0)
    agent_max_profit_inr: float = Field(default=100_000, gt=0)
    agent_max_loss_inr: float = Field(default=15_000, gt=0)
    agent_max_concurrent_picks: int = Field(default=5, ge=1, le=10)
    curated_symbols: List[str] = Field(min_length=1, max_length=20)
    curated_max_spend_inr: float = Field(default=1_000_000, gt=0)
    curated_max_profit_inr: float = Field(default=100_000, gt=0)
    curated_max_loss_inr: float = Field(default=15_000, gt=0)
    curated_max_concurrent_picks: int = Field(default=5, ge=1, le=10)
    auto_square_orphans: bool = True

    @field_validator("curated_symbols")
    @classmethod
    def normalize_curated_symbols(cls, symbols: List[str]) -> List[str]:
        from trading.symbol_validate import CURATED_SYMBOLS_MAX, normalize_symbol_list

        return normalize_symbol_list(symbols, max_count=CURATED_SYMBOLS_MAX, min_count=1)


class SessionStopBody(BaseModel):
    session_id: Optional[str] = Field(default=None, max_length=64)


class SessionEventsClearBody(BaseModel):
    retention: Literal["1h", "12h", "1d", "7d"] = "7d"
    session_id: Optional[str] = Field(default=None, max_length=64)
