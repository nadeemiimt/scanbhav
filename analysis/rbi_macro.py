"""Dynamic RBI / India macro fetch with local cache (free public sources)."""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from config import BASE_DIR, DATA_GOV_IN_API_KEY, FRED_API_KEY

CACHE_PATH = BASE_DIR / "data" / "macro" / "rbi_cache.json"
CACHE_TTL_SECONDS = 6 * 3600
RBI_HOME = "https://www.rbi.org.in/"


def _pct(raw: Optional[str]) -> Optional[float]:
    if not raw:
        return None
    try:
        return round(float(str(raw).replace("%", "").strip()), 2)
    except (TypeError, ValueError):
        return None


def _load_cache() -> Optional[dict[str, Any]]:
    if not CACHE_PATH.exists():
        return None
    try:
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if time.time() - float(data.get("fetched_at_epoch") or 0) < CACHE_TTL_SECONDS:
            return data
    except (json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _save_cache(payload: dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["fetched_at_epoch"] = time.time()
    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _scrape_rbi_homepage() -> dict[str, Any]:
    try:
        r = requests.get(RBI_HOME, timeout=20, headers={"User-Agent": "Mozilla/5.0 (compatible; ScanBhav/1.0)"})
        if r.status_code != 200:
            return {"status": "error", "http_status": r.status_code}
        text = r.text

        def _rate(label: str) -> Optional[float]:
            m = re.search(rf"{re.escape(label)}[^0-9]*</th>\s*<td>\s*:\s*([0-9.]+)\s*%?", text, re.I | re.S)
            return _pct(m.group(1)) if m else None

        return {
            "status": "ok",
            "source": "rbi_homepage",
            "rbi_repo_pct": _rate("Policy Repo Rate"),
            "standing_deposit_pct": _rate("Standing Deposit Facility Rate"),
            "msf_pct": _rate("Marginal Standing Facility Rate"),
            "reverse_repo_pct": _rate("Fixed Reverse Repo Rate"),
            "slr_pct": _rate("SLR"),
            "as_of": datetime.now(timezone.utc).date().isoformat(),
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


def _fetch_worldbank_cpi() -> dict[str, Any]:
    try:
        r = requests.get(
            "https://api.worldbank.org/v2/country/IND/indicator/FP.CPI.TOTL.ZG?format=json&per_page=3",
            timeout=20,
        )
        if r.status_code != 200:
            return {"status": "error"}
        rows = r.json()[1] if isinstance(r.json(), list) and len(r.json()) > 1 else []
        latest = rows[0] if rows else {}
        val = latest.get("value")
        return {
            "status": "ok" if val is not None else "empty",
            "source": "worldbank",
            "cpi_yoy_pct": round(float(val), 2) if val is not None else None,
            "cpi_period": latest.get("date"),
            "cpi_frequency": "annual",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


def _fetch_datagov_cpi() -> dict[str, Any]:
    if not DATA_GOV_IN_API_KEY:
        return {"status": "unconfigured"}
    # MOSPI CPI general index YoY — resource id may vary; best-effort parse.
    try:
        r = requests.get(
            "https://api.data.gov.in/resource/69ddfdac-2b33-4a75-8b79-040a7ca64e38",
            params={"api-key": DATA_GOV_IN_API_KEY, "format": "json", "limit": 12, "offset": 0},
            timeout=25,
        )
        if r.status_code != 200:
            return {"status": "error", "http_status": r.status_code}
        records = (r.json().get("records") or [])[:1]
        if not records:
            return {"status": "empty"}
        row = records[0]
        val = row.get("Inflation_Rate") or row.get("inflation_rate") or row.get("value")
        period = row.get("Month") or row.get("month") or row.get("date")
        return {
            "status": "ok",
            "source": "data_gov_in",
            "cpi_yoy_pct": _pct(str(val)) if val is not None else None,
            "cpi_period": period,
            "cpi_frequency": "monthly",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


def _fetch_fred_cpi() -> dict[str, Any]:
    if not FRED_API_KEY:
        return {"status": "unconfigured"}
    try:
        r = requests.get(
            "https://api.stlouisfed.org/fred/series/observations",
            params={
                "series_id": "FPCPITOTLZGIND",
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            },
            timeout=20,
        )
        if r.status_code != 200:
            return {"status": "error", "http_status": r.status_code}
        obs = (r.json().get("observations") or [{}])[0]
        val = obs.get("value")
        if val in (None, "."):
            return {"status": "empty"}
        return {
            "status": "ok",
            "source": "fred",
            "cpi_yoy_pct": round(float(val), 2),
            "cpi_period": obs.get("date"),
            "cpi_frequency": "annual",
        }
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


def fetch_dynamic_rbi_macro(*, force_refresh: bool = False) -> dict[str, Any]:
    """Repo rate from RBI.gov.in; CPI from data.gov.in / FRED / World Bank (best available)."""
    import os

    manual_repo = os.environ.get("RBI_REPO_RATE")
    manual_cpi = os.environ.get("INDIA_CPI_YOY")
    manual_gs10 = os.environ.get("INDIA_GSEC_10Y")
    if manual_repo or manual_cpi:
        return {
            "status": "ok",
            "source": "env_manual",
            "rbi_repo_pct": float(manual_repo) if manual_repo else None,
            "cpi_yoy_pct": float(manual_cpi) if manual_cpi else None,
            "gsec_10y_pct": float(manual_gs10) if manual_gs10 else None,
            "note": "Manual env overrides in use.",
        }

    if not force_refresh:
        cached = _load_cache()
        if cached:
            cached["from_cache"] = True
            return cached

    rbi = _scrape_rbi_homepage()
    cpi_sources = [_fetch_datagov_cpi(), _fetch_fred_cpi(), _fetch_worldbank_cpi()]
    cpi_yoy: Optional[float] = None
    cpi_period: Optional[str] = None
    cpi_source: Optional[str] = None
    cpi_frequency: Optional[str] = None
    for src in cpi_sources:
        if src.get("status") == "ok" and src.get("cpi_yoy_pct") is not None:
            cpi_yoy = src["cpi_yoy_pct"]
            cpi_period = src.get("cpi_period")
            cpi_source = src.get("source")
            cpi_frequency = src.get("cpi_frequency")
            if cpi_frequency == "monthly":
                break

    out = {
        "status": "ok" if rbi.get("status") == "ok" else "partial",
        "source": "dynamic",
        "rbi_repo_pct": rbi.get("rbi_repo_pct"),
        "standing_deposit_pct": rbi.get("standing_deposit_pct"),
        "msf_pct": rbi.get("msf_pct"),
        "reverse_repo_pct": rbi.get("reverse_repo_pct"),
        "slr_pct": rbi.get("slr_pct"),
        "cpi_yoy_pct": cpi_yoy,
        "cpi_period": cpi_period,
        "cpi_source": cpi_source,
        "cpi_frequency": cpi_frequency,
        "gsec_10y_pct": float(manual_gs10) if manual_gs10 else None,
        "as_of": rbi.get("as_of"),
        "providers": {"rbi": rbi, "cpi_chain": cpi_sources},
        "note": "Repo from RBI.gov.in; CPI from monthly data.gov.in when keyed, else FRED/World Bank annual.",
    }
    if rbi.get("status") != "ok":
        out["status"] = "partial"
        out["error"] = rbi.get("error")
    _save_cache(out)
    return out
