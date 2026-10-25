"""Auto top stocks by planning horizon (7d / 15d / 30d / 6m / 1y).

Uses the last Nifty screen cache. New screens store per-horizon scores; older
caches are backfilled from local daily price files so the desk still fills.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from config import BASE_DIR
from horizon_rank import rate_all_horizons
from screener import SCREEN_CACHE
from technicals import compute_technicals

PICKS_CACHE = BASE_DIR / "data" / "screen_cache" / "horizon_picks.json"
PICKS_TTL_SEC = 30 * 60

# User-facing planning windows → internal rating horizons
PLAN_HORIZONS: list[dict[str, Any]] = [
    {"id": "7d", "label": "Next 7 days", "hint": "Short swing / plan exit window", "source": "1w"},
    {"id": "15d", "label": "Next 15 days", "hint": "Pullback entry → target (plan_15d)", "source": "blend_1w_1m"},
    {"id": "30d", "label": "Next 30 days", "hint": "1-month hold / staged sell", "source": "1m"},
    {"id": "6m", "label": "Next 6 months", "hint": "Positional hold", "source": "6m"},
    {"id": "1y", "label": "Next 1 year", "hint": "Long-term plan sell", "source": "1y"},
]


def _load_json(path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_json(path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _score_for_plan(row: dict[str, Any], plan: dict[str, Any]) -> Optional[dict[str, Any]]:
    scores = row.get("horizon_scores") or {}
    source = plan["source"]
    if source == "blend_1w_1m":
        a = scores.get("1w") or {}
        b = scores.get("1m") or {}
        if a.get("score") is None and b.get("score") is None:
            return None
        sa = float(a.get("score") or b.get("score") or 0)
        sb = float(b.get("score") or a.get("score") or 0)
        score = round((sa + sb) / 2, 1)
        reasons = list(a.get("reasons") or [])[:2] + list(b.get("reasons") or [])[:2]
        stance = a.get("stance") or b.get("stance")
        grade = a.get("grade") or b.get("grade")
        return {
            "score": score,
            "grade": grade,
            "stance": stance,
            "reasons": reasons[:4],
            "horizon_return_pct": b.get("horizon_return_pct") if b.get("horizon_return_pct") is not None else a.get("horizon_return_pct"),
        }
    hit = scores.get(source)
    if not hit or hit.get("score") is None:
        # Legacy cache: only the ranked horizon score exists
        if row.get("score") is not None and source in {None, ""}:
            return {
                "score": row.get("score"),
                "grade": row.get("grade"),
                "stance": row.get("stance"),
                "reasons": [],
                "horizon_return_pct": row.get("horizon_return_pct"),
            }
        return None
    return {
        "score": hit.get("score"),
        "grade": hit.get("grade"),
        "stance": hit.get("stance"),
        "reasons": list(hit.get("reasons") or [])[:4],
        "horizon_return_pct": hit.get("horizon_return_pct"),
    }


def _load_screen_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = _load_json(SCREEN_CACHE)
    rows = list(payload.get("top") or payload.get("results") or [])
    meta = {
        "run_at": payload.get("run_at"),
        "scored": payload.get("scored"),
        "horizon": payload.get("horizon"),
        "has_horizon_scores": bool(rows and (rows[0].get("horizon_scores") or {})),
    }
    return rows, meta


def _backfill_horizon_scores(rows: list[dict[str, Any]], *, max_symbols: int = 120) -> list[dict[str, Any]]:
    """Fill horizon_scores from local daily cache for rows that lack them."""
    from routes.helpers import fetch_prices_light, rows_from_payload

    need = [r for r in rows if not (r.get("horizon_scores") or {})][:max_symbols]
    if not need:
        return rows

    by_sym = {r["symbol"]: r for r in rows if r.get("symbol")}

    def one(symbol: str) -> tuple[str, dict[str, Any]]:
        try:
            payload = fetch_prices_light(symbol, force_refresh=False, provider="auto", allow_nse_fallback=True)
            history = rows_from_payload(payload)
            if len(history) < 60:
                return symbol, {}
            tech = compute_technicals(history)
            ratings = rate_all_horizons(tech)
            scores = {}
            for hid, row in (ratings.get("horizons") or {}).items():
                scores[hid] = {
                    "score": row.get("score"),
                    "grade": row.get("grade"),
                    "stance": row.get("stance"),
                    "horizon_return_pct": row.get("horizon_return_pct"),
                    "reasons": list(row.get("reasons") or [])[:4],
                }
            return symbol, scores
        except Exception:
            return symbol, {}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futs = [pool.submit(one, r["symbol"]) for r in need]
        for fut in as_completed(futs):
            symbol, scores = fut.result()
            if scores and symbol in by_sym:
                by_sym[symbol]["horizon_scores"] = scores
    return list(by_sym.values()) if by_sym else rows


def _why_line(row: dict[str, Any], scored: dict[str, Any], plan: dict[str, Any]) -> str:
    stance = str(scored.get("stance") or row.get("stance") or "neutral").replace("_", " ")
    score = scored.get("score")
    reasons = scored.get("reasons") or []
    head = f"{row.get('symbol')}: {stance} for {plan['label'].lower()} (score {score})."
    if reasons:
        return f"{head} {reasons[0]}"
    ret = scored.get("horizon_return_pct")
    if ret is not None:
        return f"{head} Horizon return {ret:+.1f}%."
    return head


def build_horizon_picks(*, top_n: int = 8, force_backfill: bool = False) -> dict[str, Any]:
    cached = _load_json(PICKS_CACHE)
    fetched_at = float(cached.get("fetched_at") or 0)
    if (
        not force_backfill
        and cached.get("boards")
        and (time.time() - fetched_at) < PICKS_TTL_SEC
    ):
        return cached

    rows, screen_meta = _load_screen_rows()
    if not rows:
        return {
            "ok": False,
            "message": "No screen cache yet. Open Screener and click Run screen once.",
            "boards": [],
            "plan_horizons": PLAN_HORIZONS,
        }

    if force_backfill or not screen_meta.get("has_horizon_scores"):
        rows = _backfill_horizon_scores(rows)

    boards = []
    for plan in PLAN_HORIZONS:
        ranked: list[dict[str, Any]] = []
        for row in rows:
            scored = _score_for_plan(row, plan)
            if not scored:
                continue
            ranked.append({
                "symbol": row.get("symbol"),
                "price": row.get("price"),
                "bucket": row.get("bucket"),
                "score": scored.get("score"),
                "grade": scored.get("grade"),
                "stance": scored.get("stance"),
                "horizon_return_pct": scored.get("horizon_return_pct"),
                "reasons": scored.get("reasons") or [],
                "why": _why_line(row, scored, plan),
                "entry_15d": row.get("entry_15d"),
                "exit_15d": row.get("exit_15d"),
                "stop_15d": row.get("stop_15d"),
                "plan_target_day": row.get("plan_target_day"),
                "quality_ok": row.get("quality_ok"),
            })
        ranked.sort(key=lambda r: float(r.get("score") or 0), reverse=True)
        buy = [r for r in ranked if str(r.get("stance") or "").endswith("favorable")][:top_n]
        if len(buy) < top_n:
            buy = ranked[:top_n]
        sell_plan = sorted(
            [r for r in ranked if str(r.get("stance") or "") in {"cautious", "unfavorable"}],
            key=lambda r: float(r.get("score") or 0),
        )[: max(3, top_n // 2)]
        boards.append({
            "id": plan["id"],
            "label": plan["label"],
            "hint": plan["hint"],
            "buy": buy,
            "watch_sell": sell_plan,
            "count": len(ranked),
        })

    payload = {
        "ok": True,
        "fetched_at": time.time(),
        "screen": screen_meta,
        "top_n": top_n,
        "plan_horizons": PLAN_HORIZONS,
        "boards": boards,
        "message": (
            "Top names by technical horizon score from your last screen. "
            "Educational ranks for buy / plan-sell windows — not advice."
        ),
        "disclaimer": (
            "Scores are educational technical ranks. Re-run Screener for a fresh universe. "
            "Not investment advice."
        ),
    }
    _save_json(PICKS_CACHE, payload)
    return payload


def analysis_verdict_summary(analysis: dict[str, Any]) -> dict[str, Any]:
    """Plain good/bad summary + daywise path for Analyze desk."""
    ratings = analysis.get("ratings") or {}
    tech = analysis.get("technicals") or analysis.get("tech") or {}
    plan_7d = analysis.get("plan_7d") or {}
    plan_15d = analysis.get("plan_15d") or {}
    dossier = analysis.get("dossier") or {}
    composite = ratings.get("composite_score")
    stance = str(ratings.get("composite_stance") or "neutral")
    grade = ratings.get("composite_grade")
    best = ratings.get("best_horizon")
    worst = ratings.get("worst_horizon")
    horizons = ratings.get("horizons") or {}

    good: list[str] = []
    bad: list[str] = []
    for hid in ("1w", "1m", "6m", "1y"):
        row = horizons.get(hid) or {}
        for reason in (row.get("reasons") or [])[:2]:
            score = float(row.get("score") or 50)
            (good if score >= 55 else bad).append(f"{hid.upper()}: {reason}")

    conviction = (dossier.get("conviction") or {}).get("plain_english")
    if conviction:
        good.append(conviction)

    radar = dossier.get("signal_radar") or {}
    for flag in (radar.get("red_flags") or [])[:2]:
        text = flag if isinstance(flag, str) else (flag.get("text") or flag.get("title") or "")
        if text:
            bad.append(text)

    if stance in {"strong_favorable", "favorable"}:
        verdict = "good"
        headline = f"Technically constructive ({grade or '—'}, score {composite})."
    elif stance in {"cautious", "unfavorable"}:
        verdict = "bad"
        headline = f"Technically weak or risky ({grade or '—'}, score {composite})."
    else:
        verdict = "mixed"
        headline = f"Mixed setup ({grade or '—'}, score {composite}). Wait for a clearer edge."

    daywise = []
    fc = plan_7d.get("forecast_7d") if isinstance(plan_7d, dict) else None
    if isinstance(fc, dict):
        try:
            from forecast_tracker import build_forward_path

            daywise = build_forward_path(fc)
        except Exception:
            daywise = []

    sell_plan = None
    if plan_15d.get("ok"):
        sell_plan = {
            "entry": plan_15d.get("entry_price"),
            "exit": plan_15d.get("exit_price"),
            "stop": plan_15d.get("stop_price"),
            "plain": plan_15d.get("plain"),
        }
    elif plan_7d.get("ok"):
        sell_plan = {
            "entry": (plan_7d.get("plan_15d_ref") or {}).get("entry"),
            "exit": (plan_7d.get("plan_15d_ref") or {}).get("exit"),
            "stop": (plan_7d.get("plan_15d_ref") or {}).get("stop"),
            "plain": plan_7d.get("plain"),
        }

    return {
        "verdict": verdict,
        "headline": headline,
        "stance": stance,
        "grade": grade,
        "composite_score": composite,
        "best_horizon": best,
        "worst_horizon": worst,
        "why_good": good[:6],
        "why_bad": bad[:6],
        "daywise_prediction": daywise,
        "plan_7d_plain": plan_7d.get("plain") if isinstance(plan_7d, dict) else None,
        "buy_sell_plan": sell_plan,
        "price": tech.get("price") or analysis.get("quote", {}).get("summary", {}).get("close"),
        "disclaimer": "Educational technical summary — not investment advice.",
    }
