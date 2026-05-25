"""Reddit posts via the public .json endpoints — no key required.

Two ingestion shapes:

- **Multi-ticker subs** (r/stocks, r/wallstreetbets, ...): search the sub
  for the ticker symbol, then verify the symbol appears as a whole word
  in the title or body (cheap false-positive filter).
- **Single-ticker subs** (r/intelstock -> INTC, r/uuu_stock -> UUUU):
  the sub *is* the ticker, so we just pull /new and attribute every
  post to the mapped ticker. Higher signal per request, no search cost.

Reddit asks for a descriptive User-Agent. The default is set in
.env.example (``REDDIT_USER_AGENT``); settings.yaml can override it.
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Iterable

import requests

from ..config import env, setting


def _user_agent() -> str:
    return (setting("sentiment.reddit.user_agent")
            or env("REDDIT_USER_AGENT")
            or "FIRE-Dashboard/0.1")


def _headers() -> dict:
    return {"User-Agent": _user_agent()}


def _per_sub_limit() -> int:
    try:
        return int(setting("sentiment.reddit.per_sub_limit", 25))
    except (TypeError, ValueError):
        return 25


def _multi_subs() -> list:
    subs = setting("sentiment.reddit.multi_ticker_subs", []) or []
    return [str(s).strip() for s in subs if str(s).strip()]


def _single_subs() -> dict:
    raw = setting("sentiment.reddit.single_ticker_subs", {}) or {}
    return {str(k).strip(): str(v).strip().upper()
            for k, v in raw.items() if k and v}


def _epoch_to_iso(epoch) -> str:
    try:
        return datetime.fromtimestamp(float(epoch),
                                      tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch_json(url: str, params: dict = None) -> dict:
    try:
        r = requests.get(url, params=params, headers=_headers(), timeout=15)
        if r.status_code != 200:
            return {}
        return r.json()
    except Exception:
        return {}


def _posts_from_listing(data: dict) -> list:
    return [child.get("data", {})
            for child in data.get("data", {}).get("children", [])]


def _ticker_in_text(ticker: str, text: str) -> bool:
    if not text:
        return False
    return re.search(rf"\b\$?{re.escape(ticker)}\b", text,
                     flags=re.IGNORECASE) is not None


def _to_post(ticker: str, sub: str, p: dict) -> dict:
    title = p.get("title") or ""
    body = p.get("selftext") or ""
    text = (title + "\n" + body).strip()
    score = p.get("score") or 0
    num_comments = p.get("num_comments") or 0
    # Reddit upvotes + comments → a soft influence weight; capped to keep
    # one viral post from drowning the rest.
    weight = min(5.0, 1.0 + (score / 100.0) + (num_comments / 50.0))
    permalink = p.get("permalink", "")
    return {
        "ticker": ticker.upper(),
        "source": "reddit",
        "external_id": p.get("id") or permalink,
        "created_at": _epoch_to_iso(p.get("created_utc")),
        "author": f"r/{sub}",
        "weight": weight,
        "url": f"https://www.reddit.com{permalink}" if permalink else None,
        "text": text,
    }


def _search_sub(ticker: str, sub: str, since_iso: str) -> list:
    url = f"https://www.reddit.com/r/{sub}/search.json"
    params = {"q": ticker, "restrict_sr": 1, "sort": "new",
              "t": "week", "limit": _per_sub_limit()}
    data = _fetch_json(url, params)
    out = []
    for p in _posts_from_listing(data):
        created = _epoch_to_iso(p.get("created_utc"))
        if created < since_iso:
            continue
        text = ((p.get("title") or "") + "\n" + (p.get("selftext") or ""))
        if not _ticker_in_text(ticker, text):
            continue
        out.append(_to_post(ticker, sub, p))
    return out


def _scrape_single_sub(sub: str, ticker: str, since_iso: str) -> list:
    url = f"https://www.reddit.com/r/{sub}/new.json"
    params = {"limit": _per_sub_limit()}
    data = _fetch_json(url, params)
    out = []
    for p in _posts_from_listing(data):
        created = _epoch_to_iso(p.get("created_utc"))
        if created < since_iso:
            continue
        out.append(_to_post(ticker, sub, p))
    return out


def fetch_recent(ticker: str, since: datetime) -> list:
    """All Reddit posts mentioning `ticker` since `since`."""
    ticker = ticker.upper()
    since_iso = since.astimezone(timezone.utc).isoformat(timespec="seconds")

    out: list = []

    # 1. Multi-ticker subs — search each.
    for sub in _multi_subs():
        out.extend(_search_sub(ticker, sub, since_iso))
        time.sleep(0.4)  # stay polite to Reddit

    # 2. Single-ticker subs — only scrape the one(s) mapped to this ticker.
    for sub, mapped in _single_subs().items():
        if mapped != ticker:
            continue
        out.extend(_scrape_single_sub(sub, ticker, since_iso))
        time.sleep(0.4)

    # Dedup within the run by Reddit post id.
    seen = set()
    unique = []
    for p in out:
        eid = p["external_id"]
        if eid in seen:
            continue
        seen.add(eid)
        unique.append(p)
    return unique


def fetch_for_all_single_subs(since: datetime) -> Iterable:
    """Convenience helper for the orchestrator: scrape every configured
    single-ticker sub once and attribute the posts to their mapped
    tickers. Avoids re-scraping the same sub for every ticker."""
    since_iso = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    for sub, mapped in _single_subs().items():
        yield from _scrape_single_sub(sub, mapped, since_iso)
        time.sleep(0.4)
