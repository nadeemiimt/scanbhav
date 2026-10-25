"""Data and model connectors a user can turn on with their own key."""
from __future__ import annotations

from typing import Any

# Built-ins that already work with no key.
FREE_SOURCES = [
    {
        "id": "yahoo",
        "label": "Yahoo Finance",
        "kind": "prices",
        "needs_key": False,
        "required": False,
        "plain": "Daily prices for most NSE names. Good default. Patchy on tiny stocks.",
    },
    {
        "id": "nse",
        "label": "NSE public charts",
        "kind": "prices",
        "needs_key": False,
        "required": False,
        "plain": "Official NSE chart data. Used when Yahoo has no bars.",
    },
]

# Optional keys. The app calls them only after a key is saved in Settings.
KEYED_SOURCES = [
    {
        "id": "alphavantage",
        "label": "Alpha Vantage",
        "kind": "prices",
        "needs_key": True,
        "required": False,
        "docs": "https://www.alphavantage.co/support/#api-key",
        "plain": "Extra daily prices. Free tier is slow (about 25 calls a day).",
    },
    {
        "id": "finnhub",
        "label": "Finnhub",
        "kind": "quotes",
        "needs_key": True,
        "required": False,
        "docs": "https://finnhub.io/register",
        "plain": "Live quote and company news. Indian coverage is thinner than US.",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "kind": "genai",
        "needs_key": True,
        "required": False,
        "docs": "https://platform.openai.com/api-keys",
        "plain": "GenAI research notes and learning explanations. Optional if you use Ollama locally.",
    },
    {
        "id": "anthropic",
        "label": "Anthropic",
        "kind": "genai",
        "needs_key": True,
        "required": False,
        "docs": "https://console.anthropic.com/settings/keys",
        "plain": "Same job as OpenAI, using Claude.",
    },
    {
        "id": "cursor",
        "label": "Cursor",
        "kind": "code_learning",
        "needs_key": True,
        "required": False,
        "docs": "https://cursor.com/dashboard/integrations",
        "plain": "Lets Cursor edit recommendation code after you approve a learning gap. It does not place trades.",
    },
]

BROKER_APP_KEYS = [
    {
        "id": "zerodha_api_key",
        "broker": "zerodha",
        "label": "Zerodha API key",
        "secret": False,
        "docs": "https://developers.kite.trade/",
        "plain": "Kite Connect app key. Needed only for live ticks / live orders.",
    },
    {
        "id": "zerodha_api_secret",
        "broker": "zerodha",
        "label": "Zerodha API secret",
        "secret": True,
        "docs": "https://developers.kite.trade/",
        "plain": "Kite Connect app secret. Used once per day when you complete OAuth.",
    },
    {
        "id": "groww_api_key",
        "broker": "groww",
        "label": "Groww API key",
        "secret": False,
        "docs": "https://groww.in/trade-api",
        "plain": "Groww Trade API key. Needs a static IP whitelist for live data.",
    },
    {
        "id": "groww_api_secret",
        "broker": "groww",
        "label": "Groww API secret",
        "secret": True,
        "docs": "https://groww.in/trade-api",
        "plain": "Groww Trade API secret.",
    },
    {
        "id": "fyers_app_id",
        "broker": "fyers",
        "label": "FYERS App ID",
        "secret": False,
        "docs": "https://myapi.fyers.in/",
        "plain": "FYERS API v3 app id. Optional live broker path.",
    },
    {
        "id": "fyers_secret",
        "broker": "fyers",
        "label": "FYERS secret",
        "secret": True,
        "docs": "https://myapi.fyers.in/",
        "plain": "FYERS API v3 secret.",
    },
]


def runtime_token_guide() -> dict[str, Any]:
    """What a packaged / local install needs to run."""
    return {
        "headline": "No token is required to Analyze, Screen, Backtest, or Paper Autopilot.",
        "required": [
            {
                "id": "none",
                "label": "None for core desk",
                "plain": (
                    "Yahoo + NSE public data power Analyze, Screener, horizon picks, "
                    "paper trading, and decision desk. Install and open the app — no key."
                ),
            }
        ],
        "recommended": [
            {
                "id": "openai_or_ollama",
                "label": "OpenAI key — or install Ollama (free, local)",
                "plain": (
                    "Plain-English GenAI notes and “Ask AI what to change” after backtests. "
                    "Ollama needs no cloud key; OpenAI/Anthropic need a paid API key."
                ),
            },
        ],
        "optional": [
            {
                "id": "alphavantage",
                "label": "Alpha Vantage",
                "plain": "Backup daily prices when Yahoo/NSE are thin.",
            },
            {
                "id": "finnhub",
                "label": "Finnhub",
                "plain": "Extra news / quotes.",
            },
            {
                "id": "cursor",
                "label": "Cursor API key",
                "plain": "Only if you tick “Allow Cursor to edit recommendation code”.",
            },
            {
                "id": "broker",
                "label": "Zerodha / Groww / FYERS app keys + daily OAuth",
                "plain": (
                    "Only for live LTP ticks and live orders. Paper mode never needs a broker. "
                    "Save app key/secret here, then connect OAuth from Accounts / Autopilot."
                ),
            },
            {
                "id": "oauth_login",
                "label": "Google / GitHub OAuth (sign-in)",
                "plain": "Optional. Local packaged builds can use the built-in dev sign-in.",
            },
        ],
        "never_required_for_paper": [
            "Broker access tokens",
            "AUTH_JWT_SECRET (defaults work on a single-user desktop)",
            "Cursor / OpenAI / Anthropic keys",
        ],
        "how_to_manage": (
            "Settings → Your API keys. Keys stay on this computer in a local secrets file "
            "and are shown back only as a hint (••••last4). Clear a field and Save to remove."
        ),
    }


def integration_catalog() -> dict[str, Any]:
    return {
        "free": FREE_SOURCES,
        "keyed": KEYED_SOURCES,
        "broker_app_keys": BROKER_APP_KEYS,
        "runtime_guide": runtime_token_guide(),
        "custom": {
            "id": "custom",
            "plain": (
                "Any REST API. Set a base URL and a path with {symbol}. "
                "Example path: /quote?symbol={symbol}. The key is sent as a header."
            ),
        },
        "suggested_later": [
            "Zerodha Kite Connect — live NSE ticks and orders (needs a broker app).",
            "TrueData or Global Datafeeds — adjusted history and delivery % for backtests.",
            "NSE bhavcopy + delivery files — free, but the site blocks scrapers, so a broker feed is steadier.",
        ],
    }
