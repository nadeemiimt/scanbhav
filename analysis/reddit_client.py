"""Reddit OAuth search for Indian equity subs (credentials in .env only)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import requests

from config import BASE_DIR, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_PASSWORD, REDDIT_USER_AGENT, REDDIT_USERNAME

TOKEN_PATH = BASE_DIR / "data" / "reddit" / "oauth_token.json"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API_BASE = "https://oauth.reddit.com"

INDIA_SUBREDDITS = ("IndianStreetBets", "IndiaInvestments", "StockMarketIndia")


def reddit_configured() -> bool:
    return bool(REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET and REDDIT_USERNAME and REDDIT_PASSWORD and REDDIT_USER_AGENT)


def _save_token(payload: dict[str, Any]) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload["saved_at"] = datetime.now(timezone.utc).isoformat()
    TOKEN_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _load_token() -> Optional[dict[str, Any]]:
    if not TOKEN_PATH.exists():
        return None
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _fetch_token() -> dict[str, Any]:
    if not reddit_configured():
        return {"status": "unconfigured"}
    resp = requests.post(
        TOKEN_URL,
        auth=(REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET),
        data={"grant_type": "password", "username": REDDIT_USERNAME, "password": REDDIT_PASSWORD},
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=20,
    )
    if resp.status_code != 200:
        return {"status": "error", "http_status": resp.status_code, "body": resp.text[:200]}
    data = resp.json()
    data["expires_at"] = time.time() + float(data.get("expires_in") or 3600) - 60
    _save_token(data)
    return {"status": "ok", **data}


def _access_token() -> Optional[str]:
    cached = _load_token()
    if cached and cached.get("access_token") and float(cached.get("expires_at") or 0) > time.time():
        return cached["access_token"]
    fresh = _fetch_token()
    return fresh.get("access_token") if fresh.get("status") == "ok" else None


def _api_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    token = _access_token()
    if not token:
        return {"status": "unauthorized", "note": "Reddit OAuth token unavailable — check REDDIT_* env vars."}
    try:
        r = requests.get(
            f"{API_BASE}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {token}", "User-Agent": REDDIT_USER_AGENT},
            timeout=20,
        )
        if r.status_code == 401:
            _fetch_token()
            return {"status": "unauthorized", "http_status": 401}
        if r.status_code != 200:
            return {"status": "error", "http_status": r.status_code, "body": r.text[:200]}
        return {"status": "ok", "data": r.json()}
    except Exception as exc:
        return {"status": "error", "error": str(exc)[:120]}


def search_subreddit(subreddit: str, query: str, limit: int = 8) -> list[dict[str, Any]]:
    resp = _api_get(
        f"/r/{subreddit}/search",
        {"q": query, "restrict_sr": "on", "sort": "new", "limit": min(limit, 25), "t": "month"},
    )
    if resp.get("status") != "ok":
        return []
    children = (resp.get("data") or {}).get("data", {}).get("children") or []
    out: list[dict[str, Any]] = []
    for child in children:
        post = child.get("data") or {}
        title = post.get("title")
        if not title:
            continue
        out.append({
            "title": title,
            "url": f"https://www.reddit.com{post.get('permalink', '')}",
            "published_at": datetime.fromtimestamp(post.get("created_utc") or 0, tz=timezone.utc).isoformat(),
            "publisher": f"reddit/r/{subreddit}",
            "score": post.get("score"),
            "num_comments": post.get("num_comments"),
            "subreddit": subreddit,
            "source": "reddit_oauth",
        })
    return out


def search_symbol_posts(symbol: str, limit_per_sub: int = 6) -> dict[str, Any]:
    if not reddit_configured():
        return {"status": "unconfigured", "posts": [], "note": "Set REDDIT_CLIENT_ID, SECRET, USERNAME, PASSWORD, USER_AGENT in .env"}
    base = symbol.upper().split(".")[0]
    query = f"{base} stock OR {base} NSE OR {base} share"
    posts: list[dict[str, Any]] = []
    for sub in INDIA_SUBREDDITS:
        posts.extend(search_subreddit(sub, query, limit=limit_per_sub))
    # Dedupe by title
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for p in posts:
        key = p["title"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    if not unique:
        return {"status": "empty", "source": "reddit", "posts": []}
    return {
        "status": "ok",
        "source": "reddit",
        "symbol": base,
        "post_count": len(unique),
        "posts": unique[:limit_per_sub * 2],
    }
