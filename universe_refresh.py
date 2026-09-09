"""Download NSE index CSVs and rebuild Nifty 500 Large/Mid/Small buckets."""
from __future__ import annotations

import csv
import json
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any

from config import BASE_DIR

OUT = BASE_DIR / "data" / "universe"
REFRESH_META = OUT / "refresh_meta.json"

URLS = {
    "nifty500": "https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv",
    "nifty100": "https://nsearchives.nseindia.com/content/indices/ind_nifty100list.csv",
    "midcap150": "https://nsearchives.nseindia.com/content/indices/ind_niftymidcap150list.csv",
    "smallcap250": "https://nsearchives.nseindia.com/content/indices/ind_niftysmallcap250list.csv",
}

FILES = {
    "nifty500": "ind_nifty500list.csv",
    "nifty100": "ind_nifty100list.csv",
    "midcap150": "ind_niftymidcap150list.csv",
    "smallcap250": "ind_niftysmallcap250list.csv",
}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/csv,*/*",
            "Referer": "https://www.nseindia.com/",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        dest.write_bytes(resp.read())


def _load_symbols(path: Path) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            sym = (row.get("Symbol") or row.get("symbol") or "").strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            out.append(f"{sym}.NSE")
    return out


def _build_buckets() -> dict[str, Any]:
    large = _load_symbols(OUT / FILES["nifty100"])
    mid = _load_symbols(OUT / FILES["midcap150"])
    small = _load_symbols(OUT / FILES["smallcap250"])
    nifty500 = _load_symbols(OUT / FILES["nifty500"])

    large_set = set(large)
    mid = [s for s in mid if s not in large_set]
    mid_set = set(mid)
    small = [s for s in small if s not in large_set and s not in mid_set]
    known = large_set | mid_set | set(small)
    for s in nifty500:
        if s not in known:
            small.append(s)
            known.add(s)

    return {
        "as_of": date.today().isoformat(),
        "source": "NSE archives Nifty 100 / Midcap 150 / Smallcap 250 / Nifty 500",
        "urls": URLS,
        "large": large,
        "mid": mid,
        "small": small,
    }


def refresh_universe_from_nse() -> dict[str, Any]:
    """Download all four NSE CSVs and rewrite bucket files."""
    OUT.mkdir(parents=True, exist_ok=True)
    for key, filename in FILES.items():
        _download(URLS[key], OUT / filename)

    payload = _build_buckets()
    buckets_path = OUT / "nifty500_buckets.json"
    buckets_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    lines = ["symbol,bucket"]
    for bucket in ("large", "mid", "small"):
        for symbol in payload[bucket]:
            lines.append(f"{symbol},{bucket}")
    (OUT / "nifty500.csv").write_text("\n".join(lines) + "\n", encoding="utf-8")

    meta = {
        "refreshed_at": datetime.now().isoformat(timespec="seconds"),
        "as_of": payload["as_of"],
        "counts": {k: len(payload[k]) for k in ("large", "mid", "small")},
        "total": sum(len(payload[k]) for k in ("large", "mid", "small")),
    }
    REFRESH_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    from universe import reload_universe

    reload_universe()
    return meta


def refresh_meta() -> dict[str, Any]:
    if REFRESH_META.exists():
        return json.loads(REFRESH_META.read_text(encoding="utf-8"))
    buckets = OUT / "nifty500_buckets.json"
    if buckets.exists():
        data = json.loads(buckets.read_text(encoding="utf-8"))
        return {"as_of": data.get("as_of"), "refreshed_at": None}
    return {}


def ensure_universe_fresh(force: bool = False) -> dict[str, Any]:
    """
    Refresh NSE constituent lists at most once per calendar day unless force=True.
    Returns status dict for API/UI.
    """
    meta = refresh_meta()
    today = date.today().isoformat()
    as_of = meta.get("as_of")
    stale = force or as_of != today

    if not stale:
        return {
            "refreshed": False,
            "as_of": as_of,
            "message": "Universe already checked today.",
            **meta,
        }

    try:
        new_meta = refresh_universe_from_nse()
        return {
            "refreshed": True,
            "as_of": new_meta.get("as_of"),
            "message": "Universe refreshed from NSE.",
            **new_meta,
        }
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return {
            "refreshed": False,
            "as_of": as_of,
            "error": str(exc),
            "message": "Could not reach NSE — using last saved universe.",
            **meta,
        }
