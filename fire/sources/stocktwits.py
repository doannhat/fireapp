"""StockTwits — the public stream per symbol. No key, ~200 req/hour.

Each message carries an optional user-declared sentiment ("Bullish" /
"Bearish"). When that label is present we short-circuit the tone scorer
and use ±0.6 — a strong but not extreme signal, since these self-labels
are noisy. Without a label, the body falls through to the scorer.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

import requests


_STREAM_URL = "https://api.stocktwits.com/api/2/streams/symbol/{ticker}.json"
_LABEL_TONE = {"bullish": 0.6, "bearish": -0.6}

# StockTwits sits behind Cloudflare and rejects bare Python UAs with 403.
# A normal browser UA is sufficient; no key needed.
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}


def _parse_time(s: str) -> str:
    try:
        # StockTwits returns ISO-ish strings sometimes with trailing Z.
        s = (s or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _follower_weight(followers) -> float:
    try:
        f = int(followers or 0)
    except (TypeError, ValueError):
        f = 0
    # log10-scaled, capped: 0 followers -> 1.0, 1000 -> 4.0, 1M -> 7.0.
    return min(7.0, 1.0 + math.log10(max(1, f + 1)))


def fetch_recent(ticker: str, since: datetime) -> list:
    ticker = ticker.upper()
    since_iso = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    try:
        r = requests.get(_STREAM_URL.format(ticker=ticker),
                         headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        payload = r.json()
    except Exception:
        return []

    if payload.get("response", {}).get("status") != 200:
        return []

    out = []
    for m in payload.get("messages", []) or []:
        created = _parse_time(m.get("created_at"))
        if created < since_iso:
            continue
        body = (m.get("body") or "").strip()
        if not body:
            continue
        user = m.get("user", {}) or {}
        entities = m.get("entities", {}) or {}
        label = ((entities.get("sentiment") or {}).get("basic") or "").lower()
        post = {
            "ticker": ticker,
            "source": "stocktwits",
            "external_id": str(m.get("id")),
            "created_at": created,
            "author": user.get("username"),
            "weight": _follower_weight(user.get("followers")),
            "url": f"https://stocktwits.com/{user.get('username')}/message/{m.get('id')}"
                   if user.get("username") and m.get("id") else None,
            "text": body,
        }
        if label in _LABEL_TONE:
            post["tone"] = _LABEL_TONE[label]
            post["scorer"] = "stocktwits_label"
        out.append(post)
    return out
