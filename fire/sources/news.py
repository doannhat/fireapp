"""News headlines from two free sources: yfinance .news and Google News RSS.

Both are keyless. yfinance gives finance-tuned coverage that tends to
match the watchlist names well; Google News RSS widens to smaller
publishers. Dedup is by URL, then by lowercase title prefix.
"""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote_plus

import feedparser
import yfinance as yf


def _epoch_to_iso(epoch) -> str:
    try:
        return datetime.fromtimestamp(float(epoch),
                                      tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _struct_to_iso(struct_time) -> str:
    try:
        # feedparser returns time.struct_time in UTC for published_parsed.
        ts = datetime(*struct_time[:6], tzinfo=timezone.utc)
        return ts.isoformat(timespec="seconds")
    except Exception:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _fetch_yfinance(ticker: str, since_iso: str) -> list:
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []
    out = []
    for item in items:
        # yfinance returns a few shapes — flatten to the common one.
        if "content" in item and isinstance(item["content"], dict):
            c = item["content"]
            title = c.get("title")
            summary = c.get("summary") or c.get("description") or ""
            url = (c.get("canonicalUrl") or {}).get("url") or c.get("clickThroughUrl", {}).get("url")
            pub = c.get("pubDate")
            try:
                created = datetime.fromisoformat(pub.replace("Z", "+00:00")).isoformat(timespec="seconds") if pub else None
            except Exception:
                created = None
            publisher = (c.get("provider") or {}).get("displayName")
            ext_id = c.get("id") or url
        else:
            title = item.get("title")
            summary = item.get("summary") or ""
            url = item.get("link")
            created = _epoch_to_iso(item.get("providerPublishTime"))
            publisher = item.get("publisher")
            ext_id = item.get("uuid") or url
        if not title or not url:
            continue
        if created and created < since_iso:
            continue
        out.append({
            "ticker": ticker.upper(),
            "source": "news",
            "external_id": str(ext_id),
            "created_at": created or datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "author": publisher or "yfinance",
            "weight": 1.5,  # editorial headlines weigh slightly more than chatter
            "url": url,
            "text": (title + " — " + summary).strip(" —"),
        })
    return out


def _fetch_google_news(ticker: str, since_iso: str) -> list:
    q = quote_plus(f"{ticker} stock")
    url = f"https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(url)
    except Exception:
        return []
    out = []
    for entry in feed.entries[:25]:
        title = (entry.get("title") or "").strip()
        link = entry.get("link")
        if not title or not link:
            continue
        created = (_struct_to_iso(entry.published_parsed)
                   if getattr(entry, "published_parsed", None)
                   else datetime.now(timezone.utc).isoformat(timespec="seconds"))
        if created < since_iso:
            continue
        publisher = ""
        src = entry.get("source")
        if isinstance(src, dict):
            publisher = src.get("title", "")
        out.append({
            "ticker": ticker.upper(),
            "source": "news",
            "external_id": entry.get("id") or link,
            "created_at": created,
            "author": publisher or "Google News",
            "weight": 1.2,
            "url": link,
            "text": title,
        })
    return out


def fetch_recent(ticker: str, since: datetime) -> list:
    since_iso = since.astimezone(timezone.utc).isoformat(timespec="seconds")
    posts = _fetch_yfinance(ticker, since_iso) + _fetch_google_news(ticker, since_iso)

    # Dedup by URL first, then by lowercase title prefix.
    seen_urls = set()
    seen_titles = set()
    out = []
    for p in posts:
        u = p.get("url") or ""
        if u in seen_urls:
            continue
        prefix = p["text"][:80].lower()
        if prefix in seen_titles:
            continue
        seen_urls.add(u)
        seen_titles.add(prefix)
        out.append(p)
    return out
