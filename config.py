"""Centralized configuration for the local-only stock analyzer."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from runtime_paths import bundle_dir, ensure_first_run, frontend_dist_path, is_frozen, user_data_dir

ensure_first_run()

BASE_DIR = user_data_dir()
BUNDLE_DIR = bundle_dir()
FRONTEND_DIST = frontend_dist_path()

_env_file = BASE_DIR / ".env"
if _env_file.is_file():
    load_dotenv(_env_file)
elif is_frozen() and (BUNDLE_DIR / ".env.example").is_file():
    load_dotenv(BUNDLE_DIR / ".env.example")
else:
    load_dotenv(BASE_DIR / ".env")


def setting(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _resolve_path(raw: str, default: Path) -> Path:
    text = (raw or "").strip()
    if not text:
        return default.resolve()
    path = Path(text)
    if not path.is_absolute():
        return (BASE_DIR / path).resolve()
    return path.resolve()


OLLAMA_HOST = setting("OLLAMA_HOST", "http://localhost:11434")
EMBEDDING_MODEL = setting("EMBEDDING_MODEL", "mxbai-embed-large:latest")
LLM_MODEL = setting("LLM_MODEL", "llama3.2:3b")
OLLAMA_KEEP_ALIVE = setting("OLLAMA_KEEP_ALIVE", "30m")
CHROMA_PATH = _resolve_path(setting("CHROMA_PATH", ""), BASE_DIR / "data" / "chroma")
COLLECTION_NAME = setting("COLLECTION_NAME", "stock_books")
CHUNK_SIZE = int(setting("CHUNK_SIZE", "3200"))
CHUNK_OVERLAP = int(setting("CHUNK_OVERLAP", "400"))
TOP_K = int(setting("TOP_K", "4"))
ALPHAVANTAGE_API_KEY = setting("ALPHAVANTAGE_API_KEY", "")
ALPHAVANTAGE_REQUEST_DELAY_SECONDS = float(setting("ALPHAVANTAGE_REQUEST_DELAY_SECONDS", "12"))
FINNHUB_API_KEY = setting("FINNHUB_API_KEY", "") or setting("STOCK_ADDA_FINNHUB_API_KEY", "")
FINNHUB_WEBHOOK_SECRET = setting("FINNHUB_WEBHOOK_SECRET", "") or setting("STOCK_ADDA_FINNHUB_WEBHOOK_SECRET", "")
FINNHUB_WEBHOOK_PUBLIC_URL = setting("FINNHUB_WEBHOOK_PUBLIC_URL", "")

STOCKTWITS_USERNAME = setting("STOCKTWITS_USERNAME", "") or setting("STOCK_ADDA_STOCKTWITS_USERNAME", "")
STOCKTWITS_PASSWORD = setting("STOCKTWITS_PASSWORD", "") or setting("STOCK_ADDA_STOCKTWITS_PASSWORD", "")
STOCKTWITS_API_BASE = setting("STOCKTWITS_API_BASE", "https://api-gw-prd.stocktwits.com")

# Optional India macro (monthly CPI via data.gov.in; FRED annual CPI backup)
DATA_GOV_IN_API_KEY = setting("DATA_GOV_IN_API_KEY", "")
FRED_API_KEY = setting("FRED_API_KEY", "")
INSIGHTS_CACHE_TTL_SECONDS = int(setting("INSIGHTS_CACHE_TTL_SECONDS", "3600"))

# Logging (see utils/logging_config.py)
LOG_LEVEL = setting("LOG_LEVEL", "INFO")
LOG_FORMAT = setting(
    "LOG_FORMAT",
    "%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

# Personal Advisor vision / screenshot extraction
# VISION_PROVIDER: openai | openai_compatible | cursor | ollama
VISION_PROVIDER = setting("VISION_PROVIDER", "openai")
VISION_MODEL = setting("VISION_MODEL", "gpt-4o-mini")
VISION_API_KEY = setting("VISION_API_KEY", "") or setting("OPENAI_API_KEY", "")
VISION_BASE_URL = setting("VISION_BASE_URL", "https://api.openai.com/v1")

# OAuth / session (Google, Yahoo, GitHub, Microsoft)
AUTH_JWT_SECRET = setting("AUTH_JWT_SECRET", "dev-change-me-stock-adda")
AUTH_JWT_TTL_SECONDS = int(setting("AUTH_JWT_TTL_SECONDS", str(7 * 24 * 3600)))
FRONTEND_URL = setting("FRONTEND_URL", "http://localhost:5173")
AUTH_CALLBACK_BASE = setting("AUTH_CALLBACK_BASE", "http://127.0.0.1:8000")
AUTH_ALLOW_DEV = setting("AUTH_ALLOW_DEV", "true")
GOOGLE_CLIENT_ID = setting("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = setting("GOOGLE_CLIENT_SECRET", "")
YAHOO_CLIENT_ID = setting("YAHOO_CLIENT_ID", "")
YAHOO_CLIENT_SECRET = setting("YAHOO_CLIENT_SECRET", "")
GITHUB_CLIENT_ID = setting("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = setting("GITHUB_CLIENT_SECRET", "")
MICROSOFT_CLIENT_ID = setting("MICROSOFT_CLIENT_ID", "")
MICROSOFT_CLIENT_SECRET = setting("MICROSOFT_CLIENT_SECRET", "")

