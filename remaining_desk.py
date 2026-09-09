"""Remaining ScanBhav desk helpers — educational, no live NFO feed required."""
from __future__ import annotations

import html as html_lib
import json
import math
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

try:
    import requests as _requests
except ImportError:  # pragma: no cover
    _requests = None

ACCOUNT_BUNDLE_VERSION = 1


def options_pulse(
    symbol: str,
    vix_level: Optional[float] = None,
    *,
    atr: Optional[float] = None,
    price: Optional[float] = None,
    spot: Optional[float] = None,
) -> dict[str, Any]:
    """Educational options desk context without paid NFO feed."""
    sym = symbol.upper()
    ref = spot or price
    vix = float(vix_level) if vix_level is not None else None

    if vix is None:
        vix_context = "India VIX not supplied — treat implied volatility as unknown."
        stance = "neutral"
        stance_note = "Without VIX, size option risk conservatively and prefer defined-risk structures for learning."
    elif vix >= 22:
        vix_context = f"India VIX ~{vix:.1f} — elevated fear; premiums tend to be wider."
        stance = "caution"
        stance_note = "High VIX often favors premium sellers (with margin awareness) but whipsaws are common — reduce size."
    elif vix <= 13:
        vix_context = f"India VIX ~{vix:.1f} — subdued; premiums may be thinner."
        stance = "calm"
        stance_note = "Low VIX can make long premium expensive relative to move — consider spreads for education."
    else:
        vix_context = f"India VIX ~{vix:.1f} — moderate regime."
        stance = "neutral"
        stance_note = "Moderate VIX — straddles/strangles can be used to study theta vs movement trade-offs."

    straddle = None
    if ref and ref > 0:
        move = atr if atr and atr > 0 else ref * 0.015
        half = move * 0.85
        straddle = {
            "atm_strike_proxy": round(ref, 2),
            "conceptual_call_premium_range": [round(half * 0.45, 2), round(half * 0.75, 2)],
            "conceptual_put_premium_range": [round(half * 0.45, 2), round(half * 0.75, 2)],
            "conceptual_straddle_range": [round(half * 0.9, 2), round(half * 1.5, 2)],
            "basis": "ATR-scaled educational proxy" if atr else "~1.5% of spot proxy (no ATR)",
        }

    return {
        "symbol": sym,
        "spot": round(ref, 4) if ref else None,
        "india_vix": vix,
        "vix_context": vix_context,
        "suggested_stance": stance,
        "stance_note": stance_note,
        "atm_straddle_concept": straddle,
        "missing_live_data": ["PCR", "open_interest", "IV_skew", "live_option_chain"],
        "disclaimer": (
            "Educational options context only — not live NFO data. "
            "PCR/OI/IV require a paid derivatives feed. Do not trade on these ranges."
        ),
    }


def earnings_calendar_from_yahoo(symbol: str) -> dict[str, Any]:
    """Best-effort earnings dates from yfinance; empty list on failure."""
    events: list[dict[str, Any]] = []
    note = ""
    try:
        import yfinance as yf
        from fetch_stock_data import yahoo_symbol

        ticker = yf.Ticker(yahoo_symbol(symbol))

        cal = getattr(ticker, "calendar", None)
        if cal is not None:
            if hasattr(cal, "to_dict"):
                raw = cal.to_dict(orient="index") if hasattr(cal, "to_dict") else {}
                for key, val in (raw or {}).items():
                    if hasattr(key, "strftime"):
                        d = key.strftime("%Y-%m-%d")
                    else:
                        d = str(key)[:10]
                    events.append({"date": d, "event": "earnings", "estimate": _scalar(val)})
            elif isinstance(cal, dict):
                for k, v in cal.items():
                    events.append({"date": str(k)[:10], "event": "earnings", "estimate": _scalar(v)})

        if not events and hasattr(ticker, "get_earnings_dates"):
            try:
                edf = ticker.get_earnings_dates(limit=12)
                if edf is not None and not getattr(edf, "empty", True):
                    for idx, row in edf.iterrows():
                        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
                        est = None
                        for col in ("EPS Estimate", "eps_estimate", "Estimate"):
                            if col in row.index and row[col] is not None:
                                est = _scalar(row[col])
                                break
                        events.append({"date": d, "event": "earnings", "estimate": est})
            except Exception:
                pass

        if not events:
            note = "No earnings calendar returned by Yahoo for this symbol."
    except Exception as exc:
        note = f"Earnings lookup failed: {exc}"

    events.sort(key=lambda x: x.get("date") or "")
    return {
        "symbol": symbol.upper(),
        "events": events[:24],
        "count": len(events),
        "note": note,
        "disclaimer": "Unofficial Yahoo calendar — verify on exchange/NSE before acting.",
    }


def _scalar(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
        return None
    try:
        if hasattr(val, "item"):
            val = val.item()
    except Exception:
        pass
    if isinstance(val, float):
        return round(val, 4)
    return val


def intraday_levels_from_rows(
    intraday_rows: list[dict[str, Any]],
    *,
    prior_close: Optional[float] = None,
    orb_bars: int = 6,
) -> dict[str, Any]:
    """Opening range, session VWAP, gap vs prior close from intraday OHLCV rows."""
    rows = [r for r in (intraday_rows or []) if _row_close(r) > 0]
    if not rows:
        return {"available": False, "plain": "No intraday bars supplied."}

    rows = sorted(rows, key=lambda r: str(r.get("datetime") or r.get("date") or ""))
    opens, highs, lows, closes, vols = [], [], [], [], []
    for r in rows:
        o = float(r.get("open") or r.get("1. open") or r.get("close") or 0)
        h = float(r.get("high") or r.get("2. high") or o)
        l = float(r.get("low") or r.get("3. low") or o)
        c = _row_close(r)
        v = float(r.get("volume") or r.get("6. volume") or 0)
        opens.append(o)
        highs.append(h)
        lows.append(l)
        closes.append(c)
        vols.append(v)

    n_orb = min(orb_bars, len(rows))
    orb_slice = slice(0, n_orb)
    orb_high = max(highs[orb_slice])
    orb_low = min(lows[orb_slice])
    session_open = opens[0]

    # VWAP
    pv = tv = 0.0
    for h, l, c, v in zip(highs, lows, closes, vols):
        tp = (h + l + c) / 3.0
        pv += tp * v
        tv += v
    vwap = round(pv / tv, 4) if tv > 0 else round(sum(closes) / len(closes), 4)

    gap_pct = None
    gap_filled = None
    if prior_close and prior_close > 0:
        gap_pct = round((session_open / prior_close - 1) * 100, 3)
        last = closes[-1]
        gap_filled = bool((gap_pct > 0 and last <= prior_close) or (gap_pct < 0 and last >= prior_close))

    return {
        "available": True,
        "bar_count": len(rows),
        "session_open": round(session_open, 4),
        "session_high": round(max(highs), 4),
        "session_low": round(min(lows), 4),
        "last_close": round(closes[-1], 4),
        "opening_range": {
            "bars_used": n_orb,
            "high": round(orb_high, 4),
            "low": round(orb_low, 4),
            "note": "First 6 bars (~30m on 5m data) or fewer if session is young.",
        },
        "session_vwap": vwap,
        "prior_close": round(prior_close, 4) if prior_close else None,
        "gap_pct": gap_pct,
        "gap_filled": gap_filled,
        "plain": (
            f"ORB {orb_low:.2f}–{orb_high:.2f} · VWAP {vwap:.2f}"
            + (f" · gap {gap_pct:+.2f}%" if gap_pct is not None else "")
        ),
        "disclaimer": "Intraday levels are educational — not a broker ORB feed.",
    }


def _row_close(r: dict[str, Any]) -> float:
    return float(
        r.get("close")
        or r.get("4. close")
        or r.get("5. adjusted close")
        or r.get("open")
        or 0
    )


def portfolio_correlation(series_map: dict[str, list[float]]) -> dict[str, Any]:
    """Pairwise Pearson correlation from symbol -> daily closes."""
    symbols = [s for s, vals in (series_map or {}).items() if len(vals or []) >= 5]
    pairs: list[dict[str, Any]] = []
    labels: list[str] = []

    for i, a in enumerate(symbols):
        for b in symbols[i + 1 :]:
            corr = _pearson(series_map[a], series_map[b])
            if corr is not None:
                pairs.append({"a": a, "b": b, "corr": round(corr, 4)})
                labels.append(_heat_label(corr))

    pairs.sort(key=lambda p: abs(p["corr"]), reverse=True)
    return {
        "symbols": symbols,
        "pairs": pairs,
        "heat_labels": labels[: len(pairs)],
        "matrix_hint": "Pair list only — use pairs for heatmap wiring in UI.",
        "disclaimer": "Historical correlation is not a forecast of future co-movement.",
    }


def _pearson(x: list[float], y: list[float]) -> Optional[float]:
    n = min(len(x), len(y))
    if n < 5:
        return None
    xs = [float(v) for v in x[-n:] if v is not None]
    ys = [float(v) for v in y[-n:] if v is not None]
    n = min(len(xs), len(ys))
    if n < 5:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    den_x = math.sqrt(sum((a - mx) ** 2 for a in xs))
    den_y = math.sqrt(sum((b - my) ** 2 for b in ys))
    if den_x == 0 or den_y == 0:
        return None
    return num / (den_x * den_y)


def _heat_label(corr: float) -> str:
    c = abs(corr)
    if c >= 0.8:
        return "very_high"
    if c >= 0.6:
        return "high"
    if c >= 0.35:
        return "moderate"
    if c >= 0.15:
        return "low"
    return "negligible"


def sector_relative_strength(
    rows: list[dict[str, Any]],
    bench_return_1m: Optional[float] = None,
) -> dict[str, Any]:
    """Bucket screener rows by sector; rank average horizon return vs bench."""
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows or []:
        sector = row.get("sector") or row.get("industry") or "Other"
        ret = row.get("horizon_return_pct")
        if not isinstance(ret, (int, float)):
            continue
        b = buckets.setdefault(sector, {"sector": sector, "count": 0, "sum_return": 0.0, "names": []})
        b["count"] += 1
        b["sum_return"] += float(ret)
        sym = row.get("symbol") or row.get("ticker")
        if sym:
            b["names"].append(sym)

    ranked = []
    for b in buckets.values():
        avg = b["sum_return"] / b["count"] if b["count"] else 0.0
        vs_bench = round(avg - bench_return_1m, 3) if bench_return_1m is not None else None
        ranked.append({
            "sector": b["sector"],
            "count": b["count"],
            "avg_return_pct": round(avg, 3),
            "vs_bench_pct": vs_bench,
            "leading": vs_bench is not None and vs_bench > 0.5,
            "lagging": vs_bench is not None and vs_bench < -0.5,
            "sample_symbols": b["names"][:5],
        })

    ranked.sort(key=lambda x: x["avg_return_pct"], reverse=True)
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i

    headline = None
    if ranked:
        top = ranked[0]
        headline = f"Strongest sector: {top['sector']} ({top['avg_return_pct']:+.1f}% avg)"
        if bench_return_1m is not None:
            headline += f" vs bench {bench_return_1m:+.1f}%"

    return {
        "bench_return_1m_pct": bench_return_1m,
        "sectors": ranked,
        "count": len(ranked),
        "headline": headline,
        "disclaimer": "Sector RS from last screener snapshot — not a live sector index feed.",
    }


def notify_dispatch(
    alerts: list[Any],
    webhook_url: Optional[str] = None,
    telegram_bot_token: Optional[str] = None,
    telegram_chat_id: Optional[str] = None,
) -> dict[str, Any]:
    """POST alerts to webhook and/or Telegram; never raises."""
    sent: list[str] = []
    errors: list[str] = []
    payload = {"alerts": alerts, "ts": datetime.now(timezone.utc).isoformat()}

    if webhook_url:
        try:
            body = json.dumps(payload).encode("utf-8")
            if _requests is not None:
                resp = _requests.post(webhook_url, json=payload, timeout=8)
                if resp.status_code >= 400:
                    errors.append(f"webhook HTTP {resp.status_code}")
                else:
                    sent.append("webhook")
            else:
                req = urllib.request.Request(
                    webhook_url,
                    data=body,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    if resp.status >= 400:
                        errors.append(f"webhook HTTP {resp.status}")
                    else:
                        sent.append("webhook")
        except Exception as exc:
            errors.append(f"webhook: {exc}")

    if telegram_bot_token and telegram_chat_id:
        try:
            text = _format_telegram(alerts)
            tg_url = f"https://api.telegram.org/bot{telegram_bot_token}/sendMessage"
            tg_body = {"chat_id": telegram_chat_id, "text": text, "disable_web_page_preview": True}
            if _requests is not None:
                resp = _requests.post(tg_url, json=tg_body, timeout=8)
                data = resp.json() if resp.content else {}
                if not data.get("ok"):
                    errors.append(f"telegram: {data.get('description', resp.status_code)}")
                else:
                    sent.append("telegram")
            else:
                req = urllib.request.Request(
                    tg_url,
                    data=json.dumps(tg_body).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=8) as resp:
                    raw = resp.read().decode("utf-8")
                    data = json.loads(raw) if raw else {}
                    if not data.get("ok"):
                        errors.append(f"telegram: {data.get('description', 'failed')}")
                    else:
                        sent.append("telegram")
        except Exception as exc:
            errors.append(f"telegram: {exc}")

    if not webhook_url and not (telegram_bot_token and telegram_chat_id):
        errors.append("No webhook_url or telegram credentials configured.")

    return {"sent": sent, "errors": errors, "alert_count": len(alerts or [])}


def _format_telegram(alerts: list[Any]) -> str:
    lines = ["ScanBhav desk alerts"]
    for a in alerts or []:
        if isinstance(a, str):
            lines.append(f"• {a}")
        elif isinstance(a, dict):
            lines.append(f"• {a.get('message') or a.get('title') or json.dumps(a, default=str)[:200]}")
        else:
            lines.append(f"• {a}")
    return "\n".join(lines)[:4000]


def export_pdf_html(title: str, sections: list[dict[str, Any]]) -> str:
    """Return print-friendly HTML for browser print-to-PDF."""
    safe_title = html_lib.escape(title or "ScanBhav Report")
    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        f"<title>{safe_title}</title>",
        "<style>",
        "body{font-family:system-ui,-apple-system,sans-serif;max-width:800px;margin:2rem auto;color:#111;line-height:1.5;}",
        "h1{font-size:1.6rem;border-bottom:2px solid #e8b84a;padding-bottom:.4rem;}",
        "h2{font-size:1.15rem;margin-top:1.5rem;color:#333;}",
        "p,li{font-size:.95rem;}",
        ".meta{color:#666;font-size:.85rem;margin-bottom:1.5rem;}",
        ".disclaimer{margin-top:2rem;padding:1rem;background:#f8f4e8;border-left:4px solid #e8b84a;font-size:.85rem;}",
        "@media print{body{margin:1cm;}}",
        "</style></head><body>",
        f"<h1>{safe_title}</h1>",
        f"<p class='meta'>Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}</p>",
    ]
    for sec in sections or []:
        heading = html_lib.escape(str(sec.get("heading") or sec.get("title") or "Section"))
        body = sec.get("body") or sec.get("content") or ""
        if isinstance(body, list):
            body_html = "<ul>" + "".join(f"<li>{html_lib.escape(str(x))}</li>" for x in body) + "</ul>"
        else:
            body_html = f"<p>{html_lib.escape(str(body))}</p>"
        parts.append(f"<h2>{heading}</h2>{body_html}")
    parts.append(
        "<p class='disclaimer'>Educational research export — not investment advice. "
        "Verify all figures independently before trading.</p></body></html>"
    )
    return "".join(parts)


def _pdf_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
    )


def _wrap_pdf_line(text: str, width: int = 90) -> list[str]:
    raw = (text or "").replace("\r", "").split("\n")
    out: list[str] = []
    for paragraph in raw:
        words = paragraph.split(" ")
        line = ""
        for word in words:
            candidate = f"{line} {word}".strip()
            if len(candidate) > width and line:
                out.append(line)
                line = word
            else:
                line = candidate
        out.append(line)
    return out or [""]


def build_pdf_bytes(title: str, sections: list[dict[str, Any]]) -> bytes:
    """Build a simple multi-page PDF (Helvetica) with no extra dependencies."""
    lines: list[str] = [str(title or "ScanBhav Report"), ""]
    lines.append(f"Generated {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("")
    for sec in sections or []:
        heading = str(sec.get("heading") or sec.get("title") or "Section")
        lines.append(heading)
        body = sec.get("body") or sec.get("content") or ""
        if isinstance(body, list):
            for item in body:
                lines.extend(_wrap_pdf_line(f"- {item}"))
        else:
            lines.extend(_wrap_pdf_line(str(body)))
        lines.append("")
    lines.append("Educational research export — not investment advice.")

    # Paginate ~48 lines per page
    per_page = 48
    pages = [lines[i : i + per_page] for i in range(0, len(lines), per_page)] or [[]]

    objects: list[bytes] = []
    # 1: Catalog, 2: Pages, then per page: Page + Content
    # We'll assemble object numbers dynamically.

    def obj(n: int, body: bytes) -> bytes:
        return f"{n} 0 obj\n".encode() + body + b"\nendobj\n"

    page_obj_nums: list[int] = []
    content_obj_nums: list[int] = []
    next_num = 3
    content_bodies: list[bytes] = []

    for page_lines in pages:
        y = 800
        stream_parts = ["BT", "/F1 11 Tf", "14 TL", "50 800 Td"]
        first = True
        for line in page_lines:
            safe = _pdf_escape(line[:200])
            if not first:
                stream_parts.append("T*")
            stream_parts.append(f"({safe}) Tj")
            first = False
            y -= 14
        stream_parts.append("ET")
        stream = "\n".join(stream_parts).encode("latin-1", errors="replace")
        content_bodies.append(stream)
        page_obj_nums.append(next_num)
        content_obj_nums.append(next_num + 1)
        next_num += 2

    font_num = next_num
    next_num += 1

    kids = " ".join(f"{n} 0 R" for n in page_obj_nums)
    objects.append(obj(1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objects.append(
        obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(page_obj_nums)} >>".encode())
    )

    for page_n, content_n, stream in zip(page_obj_nums, content_obj_nums, content_bodies):
        objects.append(
            obj(
                page_n,
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Contents {content_n} 0 R /Resources << /Font << /F1 {font_num} 0 R >> >> >>"
                ).encode(),
            )
        )
        objects.append(
            obj(
                content_n,
                f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream",
            )
        )

    objects.append(
        obj(font_num, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    )

    # Re-order objects by number for xref (currently appended in creation order but numbers vary)
    by_num: dict[int, bytes] = {}
    for blob in objects:
        num = int(blob.split(b" ", 1)[0])
        by_num[num] = blob
    ordered = [by_num[i] for i in sorted(by_num)]

    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for blob in ordered:
        offsets.append(len(out))
        out.extend(blob)
    xref_pos = len(out)
    count = len(ordered) + 1
    out.extend(f"xref\n0 {count}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {count} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


def csv_export(kind: str, rows: list[dict[str, Any]], symbol: Optional[str] = None) -> str:
    """Serialize desk data to CSV text."""
    import csv
    from io import StringIO

    buf = StringIO()
    kind = (kind or "brief").lower()

    if kind == "watchlist":
        writer = csv.writer(buf)
        writer.writerow(["symbol"])
        for row in rows or []:
            sym = row.get("symbol") if isinstance(row, dict) else row
            if sym:
                writer.writerow([str(sym).strip().upper()])
        return buf.getvalue()

    if kind == "journal":
        fieldnames = ["date", "symbol", "tags", "entry", "exit", "thesis", "postmortem", "id"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows or []:
            writer.writerow({
                "date": row.get("date") or "",
                "symbol": row.get("symbol") or symbol or "",
                "tags": ",".join(row.get("tags") or []) if isinstance(row.get("tags"), list) else (row.get("tags") or ""),
                "entry": row.get("entry") or "",
                "exit": row.get("exit") or "",
                "thesis": row.get("thesis") or "",
                "postmortem": row.get("postmortem") or "",
                "id": row.get("id") or "",
            })
        return buf.getvalue()

    if kind == "holdings":
        fieldnames = ["symbol", "quantity", "avg_price", "asset_type", "broker", "id"]
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows or []:
            writer.writerow({
                "symbol": row.get("symbol") or "",
                "quantity": row.get("quantity") if row.get("quantity") is not None else row.get("qty") or "",
                "avg_price": row.get("avg_price") if row.get("avg_price") is not None else row.get("buy_price") or "",
                "asset_type": row.get("asset_type") or "stock",
                "broker": row.get("broker") or "",
                "id": row.get("id") or "",
            })
        return buf.getvalue()

    # brief — flat metrics rows
    fieldnames = ["metric", "value", "symbol"]
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    if rows:
        for row in rows:
            writer.writerow({
                "metric": row.get("metric") or row.get("key") or "",
                "value": row.get("value") if row.get("value") is not None else "",
                "symbol": row.get("symbol") or symbol or "",
            })
    return buf.getvalue()


def csv_import(kind: str, csv_text: str) -> dict[str, Any]:
    """Parse CSV into desk structures for client merge."""
    import csv
    from io import StringIO

    kind = (kind or "watchlist").lower()
    text = (csv_text or "").strip()
    if not text:
        raise ValueError("CSV is empty")

    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        # maybe a bare list of symbols
        syms = []
        for line in text.splitlines():
            s = line.strip().strip(",").upper()
            if s and s.lower() != "symbol":
                syms.append(s)
        if kind == "watchlist" and syms:
            return {"ok": True, "kind": kind, "symbols": list(dict.fromkeys(syms)), "count": len(syms)}
        raise ValueError("CSV has no header row")

    fields = [f.strip().lower() for f in reader.fieldnames]

    if kind == "watchlist":
        sym_key = "symbol" if "symbol" in fields else fields[0]
        symbols: list[str] = []
        for row in reader:
            raw = (row.get(sym_key) or row.get(reader.fieldnames[0]) or "").strip().upper()
            if raw:
                symbols.append(raw)
        symbols = list(dict.fromkeys(symbols))
        return {"ok": True, "kind": kind, "symbols": symbols, "count": len(symbols)}

    if kind == "journal":
        entries = []
        for i, row in enumerate(reader):
            tags_raw = row.get("tags") or row.get("Tags") or ""
            tags = [t.strip() for t in str(tags_raw).split(",") if t.strip()]
            entries.append({
                "id": row.get("id") or f"import-{i}-{int(datetime.now(timezone.utc).timestamp())}",
                "date": row.get("date") or datetime.now(timezone.utc).isoformat(),
                "symbol": (row.get("symbol") or "").strip().upper() or "—",
                "tags": tags,
                "entry": row.get("entry") or "",
                "exit": row.get("exit") or "",
                "thesis": row.get("thesis") or "",
                "postmortem": row.get("postmortem") or "",
            })
        return {"ok": True, "kind": kind, "entries": entries, "count": len(entries)}

    if kind == "holdings":
        holdings = []
        for row in reader:
            sym = (row.get("symbol") or "").strip().upper()
            if not sym:
                continue
            try:
                qty = float(row.get("quantity") or row.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0
            try:
                price = float(row.get("avg_price") or row.get("buy_price") or row.get("price") or 0)
            except (TypeError, ValueError):
                price = 0
            holdings.append({
                "symbol": sym,
                "quantity": qty,
                "avg_price": price,
                "asset_type": (row.get("asset_type") or "stock").strip().lower(),
                "broker": row.get("broker") or "",
                "id": row.get("id") or "",
            })
        return {
            "ok": True,
            "kind": kind,
            "holdings": holdings,
            "count": len(holdings),
            "note": "Holdings CSV is a preview/import list — use Portfolio Purchase to add live paper lots.",
        }

    raise ValueError(f"Unsupported CSV kind: {kind}")


def extract_pdf_import(raw: bytes) -> dict[str, Any]:
    """Extract text + likely NSE symbols from an uploaded PDF."""
    text_parts: list[str] = []
    try:
        from pypdf import PdfReader
        from io import BytesIO

        reader = PdfReader(BytesIO(raw))
        for page in reader.pages[:40]:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                continue
    except Exception as exc:
        raise ValueError(f"Could not read PDF: {exc}") from exc

    text = "\n".join(text_parts).strip()
    # Prefer explicit exchange suffixes from our own exports
    with_exch = re.findall(r"\b([A-Z][A-Z0-9]{1,14})\.(NSE|BSE)\b", text.upper())
    symbols: list[str] = []
    for name, exch in with_exch:
        symbols.append(f"{name}.{exch}")

    # Also pick "Symbol: XYZ" / "symbol,XYZ" style lines
    for m in re.finditer(r"(?:symbol|ticker)\s*[:=,]?\s*([A-Z][A-Z0-9.]{1,20})", text, flags=re.I):
        raw = m.group(1).strip().upper()
        if "." not in raw:
            raw = f"{raw}.NSE"
        if re.match(r"^[A-Z][A-Z0-9]{1,14}\.(NSE|BSE)$", raw):
            symbols.append(raw)

    skip = {
        "STOCK", "ADDA", "REPORT", "GENERATED", "EDUCATIONAL", "RESEARCH", "EXPORT",
        "NOT", "INVESTMENT", "ADVICE", "VERDICT", "TECHNICALS", "PRICE", "COMPOSITE",
        "UTC", "SECTION", "JOURNAL", "WATCHLIST", "HOLDINGS", "SUMMARY", "METRIC",
        "VALUE", "SYMBOL", "ENTRY", "EXIT", "THESIS", "PDF", "HTML", "CSV", "WAIT",
        "METRICS", "FLAGS", "GENAI", "DISCLAIMER", "KEY", "BRIEF", "ACTION",
    }
    cleaned: list[str] = []
    for sym in symbols:
        name = sym.split(".", 1)[0]
        if name in skip or len(name) < 2:
            continue
        cleaned.append(sym)
    symbols = list(dict.fromkeys(cleaned))[:50]
    return {
        "ok": True,
        "text_preview": text[:2000],
        "symbols": symbols,
        "symbol_count": len(symbols),
        "page_hint": "Imported symbols can be merged into your watchlist.",
    }


def mf_universe() -> dict[str, Any]:
    """Curated India MF list for education (static, not live NAV)."""
    funds = [
        {"symbol": "PARAGPARIKH", "name": "Parag Parikh Flexi Cap", "category": "Flexi Cap", "risk": "Very High", "sip_tag": "₹500+ SIP", "amc": "PPFAS"},
        {"symbol": "AXISBLUECHIP", "name": "Axis Bluechip Fund", "category": "Large Cap", "risk": "Moderately High", "sip_tag": "₹500 SIP", "amc": "Axis"},
        {"symbol": "MIRAEEMERGING", "name": "Mirae Asset Emerging Bluechip", "category": "Large & Mid Cap", "risk": "Very High", "sip_tag": "₹1,000 SIP", "amc": "Mirae"},
        {"symbol": "KOTAKFLEXICAP", "name": "Kotak Flexicap Fund", "category": "Flexi Cap", "risk": "Very High", "sip_tag": "₹500 SIP", "amc": "Kotak"},
        {"symbol": "HDFCMIDCAP", "name": "HDFC Mid-Cap Opportunities", "category": "Mid Cap", "risk": "Very High", "sip_tag": "₹500 SIP", "amc": "HDFC"},
        {"symbol": "NIPPONSMALL", "name": "Nippon India Small Cap", "category": "Small Cap", "risk": "Very High", "sip_tag": "₹500 SIP", "amc": "Nippon"},
        {"symbol": "ICICITECH", "name": "ICICI Pru Technology", "category": "Sectoral — IT", "risk": "Very High", "sip_tag": "Lump/SIP", "amc": "ICICI Pru"},
        {"symbol": "SBIBLUECHIP", "name": "SBI Bluechip Fund", "category": "Large Cap", "risk": "Moderately High", "sip_tag": "₹500 SIP", "amc": "SBI"},
        {"symbol": "UTINIFTY", "name": "UTI Nifty 50 Index", "category": "Index", "risk": "Moderately High", "sip_tag": "₹500 SIP", "amc": "UTI"},
        {"symbol": "HDFCBALANCED", "name": "HDFC Balanced Advantage", "category": "Dynamic Asset", "risk": "Moderately High", "sip_tag": "₹500 SIP", "amc": "HDFC"},
        {"symbol": "ICICIPRUD", "name": "ICICI Pru Corporate Bond", "category": "Debt — Corporate Bond", "risk": "Moderate", "sip_tag": "₹1,000 SIP", "amc": "ICICI Pru"},
        {"symbol": "SBIMAGNUM", "name": "SBI Magnum Gilt Fund", "category": "Debt — Gilt", "risk": "Moderate", "sip_tag": "₹500 SIP", "amc": "SBI"},
    ]
    return {
        "count": len(funds),
        "funds": funds,
        "disclaimer": "Static educational list — check latest NAV, TER, and factsheet on AMC/AMFI before investing.",
    }


def curriculum() -> dict[str, Any]:
    """Three mini-courses × three lessons for the desk learning tab."""
    courses = [
        {
            "id": "trend",
            "title": "Trend & Moving Averages",
            "lessons": [
                {
                    "id": "trend-1",
                    "title": "What is a trend?",
                    "minutes": 8,
                    "body": "A trend is a sustained direction in price. Uptrends make higher highs and higher lows; downtrends do the opposite. Your job is to align with the dominant direction on your chosen horizon.",
                },
                {
                    "id": "trend-2",
                    "title": "SMA crossovers (educational)",
                    "minutes": 10,
                    "body": "When a faster simple moving average crosses above a slower one, it can signal improving momentum. Crosses are noisy on daily charts — combine with structure and risk limits.",
                },
                {
                    "id": "trend-3",
                    "title": "Supertrend & trailing context",
                    "minutes": 12,
                    "body": "Supertrend overlays ATR-based stops on price. Use it to study when trends persist vs when volatility expands and flips the line. Not a standalone buy/sell system.",
                },
            ],
        },
        {
            "id": "rsi",
            "title": "RSI & Mean Reversion",
            "lessons": [
                {
                    "id": "rsi-1",
                    "title": "RSI basics",
                    "minutes": 7,
                    "body": "RSI measures recent up vs down closes on a 0–100 scale. Above ~70 is often called overbought; below ~30 oversold — but strong trends can stay stretched.",
                },
                {
                    "id": "rsi-2",
                    "title": "Divergence (concept)",
                    "minutes": 11,
                    "body": "Bullish divergence: price makes a lower low while RSI makes a higher low. It hints at fading downside momentum — confirm with price action before acting.",
                },
                {
                    "id": "rsi-3",
                    "title": "RSI in ranges vs trends",
                    "minutes": 9,
                    "body": "Mean reversion works better in sideways markets. In strong trends, waiting for RSI to normalize can mean missing the move — match tool to regime.",
                },
            ],
        },
        {
            "id": "diversification",
            "title": "Diversification & Risk",
            "lessons": [
                {
                    "id": "div-1",
                    "title": "Why diversify?",
                    "minutes": 6,
                    "body": "Concentrated bets amplify both gains and losses. Spreading across sectors, caps, and asset classes reduces idiosyncratic shock from a single name.",
                },
                {
                    "id": "div-2",
                    "title": "Correlation awareness",
                    "minutes": 10,
                    "body": "Holdings that move together provide less diversification than they appear. Review pairwise correlation on your watchlist — especially in drawdowns when correlations rise.",
                },
                {
                    "id": "div-3",
                    "title": "Position sizing & heat",
                    "minutes": 12,
                    "body": "Risk per trade (e.g. 1% of capital) and portfolio heat (weight per name) matter more than picking the perfect entry. Size so a stop-out is survivable.",
                },
            ],
        },
    ]
    return {
        "course_count": len(courses),
        "lesson_count": sum(len(c["lessons"]) for c in courses),
        "courses": courses,
        "disclaimer": "Educational curriculum only — not SEBI-registered advice.",
    }


def account_bundle_export(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap arbitrary account dict for local sync export."""
    data = dict(payload or {})
    return {
        "version": ACCOUNT_BUNDLE_VERSION,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "payload": data,
    }


def account_bundle_import(bundle: dict[str, Any]) -> dict[str, Any]:
    """Validate imported account bundle; return payload or errors."""
    if not isinstance(bundle, dict):
        return {"ok": False, "errors": ["Bundle must be a JSON object."], "payload": None}
    version = bundle.get("version")
    if version != ACCOUNT_BUNDLE_VERSION:
        return {
            "ok": False,
            "errors": [f"Unsupported version {version!r}; expected {ACCOUNT_BUNDLE_VERSION}."],
            "payload": None,
        }
    payload = bundle.get("payload")
    if payload is None:
        return {"ok": False, "errors": ["Missing payload key."], "payload": None}
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["payload must be an object."], "payload": None}
    return {
        "ok": True,
        "errors": [],
        "payload": payload,
        "exported_at": bundle.get("exported_at"),
        "version": version,
    }
