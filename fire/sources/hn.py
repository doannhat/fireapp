"""Hacker News posts via the public Algolia search API — no key required.

HN is a *leading indicator* for infra-AI sentiment: discussions of HBM
yield, photonics startups, foundry capacity and SiC reliability surface
on HN weeks before they hit the mainstream investing subs. That's where
the edge is for an investor with this strategy.

API docs: https://hn.algolia.com/api

Search shape:
    GET https://hn.algolia.com/api/v1/search_by_date?query={q}&...

Returns up to `hitsPerPage` items, each with title, url, story_text,
created_at, num_comments, points, objectID.

We attribute each hit to the queried ticker. To keep false positives
low we still require the ticker to appear as a whole word in the
title/text (the same defensive pattern the Reddit adapter uses).
"""
from __future__ import annotations

import re
import time
from datetime import datetime, timezone

import requests


_API = "https://hn.algolia.com/api/v1/search_by_date"


def _ticker_in_text(ticker: str, text: str) -> bool:
    if not text:
        return False
    return re.search(rf"\b\$?{re.escape(ticker)}\b", text,
                     flags=re.IGNORECASE) is not None


def _to_post(ticker: str, hit: dict) -> dict:
    title = hit.get("title") or hit.get("story_title") or ""
    body = hit.get("story_text") or hit.get("comment_text") or ""
    text = (title + "\n" + body).strip()
    points = hit.get("points") or 0
    comments = hit.get("num_comments") or 0
    # HN upvotes weight similarly to Reddit upvotes, capped.
    weight = min(5.0, 1.0 + (points / 100.0) + (comments / 50.0))
    object_id = hit.get("objectID") or ""
    url = hit.get("url") or (
        f"https://news.ycombinator.com/item?id={object_id}" if object_id else None
    )
    return {
        "ticker": ticker.upper(),
        "source": "hn",
        "external_id": str(object_id) or url,
        "created_at": hit.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "author": hit.get("author") or "hn",
        "weight": weight,
        "url": url,
        "text": text,
    }


def fetch_recent(ticker: str, since: datetime) -> list:
    """All HN stories/comments mentioning `ticker` since `since`.

    We hit the search_by_date endpoint with a numeric filter on
    created_at_i so we only get fresh items. Whole-word filter applies
    on our side too — tickers like "ON" or "IT" would otherwise match
    too much."""
    ticker = ticker.upper()
    since_ts = int(since.timestamp())
    params = {
        "query": ticker,
        "tags": "(story,comment)",
        "numericFilters": f"created_at_i>{since_ts}",
        "hitsPerPage": 30,
    }
    try:
        r = requests.get(_API, params=params, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
    except Exception:
        return []

    hits = data.get("hits") or []
    out: list = []
    for h in hits:
        text = ((h.get("title") or "")
                + "\n" + (h.get("story_text") or "")
                + "\n" + (h.get("comment_text") or ""))
        if not _ticker_in_text(ticker, text):
            continue
        out.append(_to_post(ticker, h))

    # Dedup within the run by objectID.
    seen = set()
    unique = []
    for p in out:
        eid = p["external_id"]
        if eid in seen:
            continue
        seen.add(eid)
        unique.append(p)
    time.sleep(0.2)
    return unique
