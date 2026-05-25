"""X / Twitter — pluggable but dormant by default.

Returns [] unless ``X_BEARER_TOKEN`` is set in the environment. The rest
of the pipeline calls this source unconditionally; absence of a key is
just "this source had no posts today" — no warning, no crash.

If you add a token, this module hits the v2 recent-search endpoint:
    GET /2/tweets/search/recent?query=$TICKER lang:en -is:retweet
That endpoint requires a paid X API plan. The token only flows through
environment variables — it is never logged or written to disk.
"""
from __future__ import annotations

from datetime import datetime, timezone

import requests

from ..config import env


_SEARCH_URL = "https://api.twitter.com/2/tweets/search/recent"


def _enabled() -> bool:
    return bool(env("X_BEARER_TOKEN"))


def fetch_recent(ticker: str, since: datetime) -> list:
    if not _enabled():
        return []
    token = env("X_BEARER_TOKEN")
    headers = {"Authorization": f"Bearer {token}"}
    params = {
        "query": f"${ticker} lang:en -is:retweet",
        "max_results": 50,
        "start_time": since.astimezone(timezone.utc).isoformat(timespec="seconds"),
        "tweet.fields": "created_at,public_metrics,author_id",
    }
    try:
        r = requests.get(_SEARCH_URL, headers=headers, params=params, timeout=15)
        if r.status_code != 200:
            return []
        payload = r.json()
    except Exception:
        return []

    out = []
    for tw in payload.get("data", []) or []:
        metrics = tw.get("public_metrics", {}) or {}
        # Engagement-weighted: like + repost + reply count, soft-capped.
        eng = (metrics.get("like_count", 0)
               + metrics.get("retweet_count", 0)
               + metrics.get("reply_count", 0))
        weight = min(5.0, 1.0 + eng / 100.0)
        out.append({
            "ticker": ticker.upper(),
            "source": "x",
            "external_id": str(tw["id"]),
            "created_at": tw.get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "author": tw.get("author_id"),
            "weight": weight,
            "url": f"https://twitter.com/i/web/status/{tw['id']}",
            "text": tw.get("text", ""),
        })
    return out
