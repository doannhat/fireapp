"""Sentiment orchestrator — ingests every source, scores, persists.

The dashboard's "Refresh data now" button calls ``run_sentiment_collector``
right after the price/earnings/filings refresh.

Defensive throughout: each source is wrapped so one flaky endpoint
never aborts a whole run.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

from . import db
from .config import all_tickers, setting
from .scoring import current_scorer, score
from .sources import hn, news, reddit, stocktwits, x as x_source


_SOURCES = [
    ("reddit", reddit.fetch_recent),
    ("stocktwits", stocktwits.fetch_recent),
    ("news", news.fetch_recent),
    ("hn", hn.fetch_recent),
    ("x", x_source.fetch_recent),
]


def _ingest_window_days() -> int:
    try:
        return int(setting("sentiment.ingest_window_days", 4))
    except (TypeError, ValueError):
        return 4


def _score_posts(posts: list, scorer_name: str) -> list:
    """Fill in tone/scorer for any post that does not already have one
    (StockTwits messages with a bullish/bearish label come pre-scored)."""
    for p in posts:
        if p.get("tone") is not None:
            continue
        p["tone"] = score(p.get("text", ""))
        p["scorer"] = scorer_name
    return posts


def collect_for_ticker(conn, ticker: str, since: datetime,
                       scorer_name: str) -> dict:
    """Pull every source for one ticker, score, persist. Returns
    {source: count_inserted}."""
    counts: dict = {}
    for name, fetch in _SOURCES:
        try:
            posts = fetch(ticker, since) or []
        except Exception:
            posts = []
        if not posts:
            counts[name] = 0
            continue
        _score_posts(posts, scorer_name)
        counts[name] = db.save_sentiment_posts(conn, posts)
        time.sleep(0.2)  # gentle on the next source
    return counts


def run_sentiment_collector(progress=None) -> dict:
    """Refresh sentiment for every watchlist ticker. Mirrors the price
    collector's interface (``progress(done, total, ticker)``)."""
    db.init_db()
    scorer_name = current_scorer()
    tickers = all_tickers()
    total = len(tickers)
    since = datetime.now(timezone.utc) - timedelta(days=_ingest_window_days())

    summary = {"total": total, "scorer": scorer_name,
               "by_source": {n: 0 for n, _ in _SOURCES},
               "tickers_with_data": 0}

    with db.connect() as conn:
        for i, ticker in enumerate(tickers, start=1):
            try:
                counts = collect_for_ticker(conn, ticker, since, scorer_name)
                if any(counts.values()):
                    summary["tickers_with_data"] += 1
                for src, c in counts.items():
                    summary["by_source"][src] += c
                # Commit per ticker so the dashboard can read while we
                # continue scraping. SQLite serialises writers; long
                # transactions starve concurrent readers.
                conn.commit()
            except Exception:
                pass
            if progress:
                progress(i, total, ticker)

        # One rollup pass at the end is cheaper than per-ticker.
        db.recompute_sentiment_daily(conn)
        conn.commit()
        db.set_meta(conn, "last_sentiment_run",
                    datetime.now().isoformat(timespec="seconds"))

    return summary


def main():
    print("FIRE sentiment collector — pulling Reddit / StockTwits / news...\n")

    def _progress(done, total, ticker):
        print(f"  [{done:>2}/{total}] {ticker}")

    result = run_sentiment_collector(progress=_progress)
    by = result["by_source"]
    print(f"\nDone. Scorer: {result['scorer']}. "
          f"{result['tickers_with_data']}/{result['total']} tickers had new posts.")
    print(f"  reddit: {by['reddit']}   stocktwits: {by['stocktwits']}   "
          f"news: {by['news']}   hn: {by['hn']}   x: {by['x']}")


if __name__ == "__main__":
    main()
