"""Collect a daily snapshot of the whole watchlist into SQLite.

Run from the terminal:
    python -m fire.collector                # snapshots + sentiment
    python -m fire.collector --pre-warm     # also runs Claude thesis on
                                            # every `holding` ticker so
                                            # the dashboard is instant.

Or import and call `run_collector()` directly.
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import yfinance as yf

from . import db
from .config import LISTS, all_tickers, setting
from .edgar import (fetch_13f_positions, fetch_activist_filings,
                    fetch_form4_enrichment, recent_filings)
from .market import fetch_earnings, fetch_snapshot
from .sentiment import run_sentiment_collector
from .sources.openinsider import fetch_insider_transactions
from .sources.stockanalysis import fetch_valuation_history
from .sources.transcripts import fetch_transcripts


def _fetch_deep_extras(ticker: str) -> dict:
    """Pull the extra yfinance payloads the thesis builder consumes:
    top institutional holders and the analyst-rating distribution.

    Defensive on every call — a delisted ticker or temporary yfinance
    glitch returns an empty dict and the collector moves on. Both
    payloads serialise to JSON; the thesis builder parses them back."""
    out: dict = {}
    try:
        t = yf.Ticker(ticker)
    except Exception:
        return out

    try:
        ih = t.institutional_holders
        if ih is not None and not getattr(ih, "empty", True):
            # yfinance gives us a DataFrame; serialise to JSON records.
            out["institutional_holders"] = ih.to_json(
                orient="records", date_format="epoch"
            )
    except Exception:
        pass

    try:
        rec = t.recommendations
        if rec is not None and not getattr(rec, "empty", True):
            out["recommendations"] = rec.to_json(
                orient="records", date_format="epoch"
            )
    except Exception:
        pass

    return out


def _safe(fn, *args, **kwargs):
    """Wrapper that swallows exceptions and returns None — used so a
    failed parallel fetch can't crash the whole collector run."""
    try:
        return fn(*args, **kwargs)
    except Exception:
        return None


# Source registry for the parallel per-ticker collector. Each entry is
# (label, fetcher, persister). The persister is called from the main
# thread with the open SQLite connection — SQLite connections aren't
# thread-safe, so we serialise the writes on purpose.
def _persist_snapshot(conn, ticker, payload):
    if payload is not None:
        db.save_snapshot(conn, payload)


def _persist_earnings(conn, ticker, payload):
    if payload:
        db.save_earnings(conn, ticker, payload)


def _persist_filings(conn, ticker, payload):
    if payload:
        db.save_filings(conn, ticker, payload)


def _persist_valuation_history(conn, ticker, payload):
    if payload:
        db.save_valuation_history(conn, ticker, payload)


def _persist_insider_transactions(conn, ticker, payload):
    if payload:
        db.save_insider_transactions(conn, ticker, payload)


def _persist_institutional(conn, ticker, payload):
    if payload:
        db.save_institutional_holdings(conn, ticker, payload)


def _persist_transcripts(conn, ticker, payload):
    if payload:
        db.save_transcripts(conn, ticker, payload)


def _persist_activist(conn, ticker, payload):
    if payload:
        db.save_activist_filings(conn, ticker, payload)


def _persist_form4(conn, ticker, payload):
    if payload:
        db.enrich_insider_transactions(conn, ticker, payload)


def _persist_deep_extras(conn, ticker, payload):
    if payload:
        for kind, content in payload.items():
            db.save_deep_extra(conn, ticker, kind, content)


def _transcripts_for(ticker: str) -> list:
    """Skip dates we already have so a re-run pulls nothing new."""
    with db.connect() as conn:
        latest = db.latest_transcript_date(conn, ticker)
    skip = {latest} if latest else set()
    return fetch_transcripts(ticker, limit=3, skip_dates=skip)


# Each (label, fetcher, persister) pair. The fetcher is called from a
# worker thread; the persister runs in the main thread once the future
# resolves. Order doesn't matter — futures are awaited as_completed.
_PIPELINE = (
    ("snapshot",         lambda t: fetch_snapshot(t),
                          _persist_snapshot),
    ("earnings",         lambda t: fetch_earnings(t),
                          _persist_earnings),
    ("filings",          lambda t: recent_filings(t),
                          _persist_filings),
    ("deep_extras",      lambda t: _fetch_deep_extras(t),
                          _persist_deep_extras),
    ("valuation",        lambda t: fetch_valuation_history(t),
                          _persist_valuation_history),
    ("insider",          lambda t: fetch_insider_transactions(t),
                          _persist_insider_transactions),
    ("institutional",    lambda t: fetch_13f_positions(t),
                          _persist_institutional),
    ("transcripts",      _transcripts_for,
                          _persist_transcripts),
    ("activist",         lambda t: fetch_activist_filings(t),
                          _persist_activist),
    ("form4_enrich",     lambda t: fetch_form4_enrichment(t, limit=20),
                          _persist_form4),
)


def collect_ticker(conn, ticker: str, max_workers: int = 8) -> dict:
    """Fetch everything we know about a ticker, in parallel.

    The collector previously did 10 sequential fetches per ticker — most
    of which are pure network I/O. Pre-parallelism, a 7-ticker watchlist
    took ~3-5min. Running independent fetches concurrently cuts that
    by ~5× because the slowest fetcher (Form 4 walk) caps the wall-
    clock, not the sum of all fetchers.

    SQLite connections aren't thread-safe by default, so we keep all
    DB writes serialised in this (main) thread — only the network I/O
    runs in worker threads. The futures hand back their payloads and
    persistence happens via the (label, persister) registry once each
    future resolves.

    Returns the snapshot dict (back-compat with the original signature)
    so callers like the collector CLI can show price-or-failed status."""
    snap_holder: dict = {}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_safe, fetcher, ticker): (label, persister)
            for label, fetcher, persister in _PIPELINE
        }
        # Drain as they finish — keeps the SQLite write window short
        # per source rather than batching at the end.
        from concurrent.futures import as_completed
        for fut in as_completed(futures):
            label, persister = futures[fut]
            try:
                payload = fut.result()
            except Exception:
                payload = None
            if label == "snapshot" and isinstance(payload, dict):
                snap_holder = payload
            try:
                persister(conn, ticker, payload)
            except Exception:
                # Persistence error must not abort other sources.
                pass

    return snap_holder or {"ticker": ticker.upper()}


def run_collector(progress=None, include_sentiment: bool = None) -> dict:
    """Refresh every watchlist ticker.

    `progress`, if given, is called as progress(done, total, ticker)
    during the price/filings phase, then again during the sentiment phase.
    `include_sentiment` defaults to settings.yaml sentiment.enabled (True).
    Returns a summary dict: {total, ok, failed, sentiment?}.
    """
    db.init_db()
    tickers = all_tickers()
    total = len(tickers)
    ok, failed = 0, []

    with db.connect() as conn:
        for i, ticker in enumerate(tickers, start=1):
            try:
                snap = collect_ticker(conn, ticker)
                if snap.get("price") is not None:
                    ok += 1
                else:
                    failed.append(ticker)
            except Exception:
                failed.append(ticker)
            if progress:
                progress(i, total, ticker)
            time.sleep(0.3)  # stay polite to the data sources
        db.set_meta(conn, "last_run",
                    datetime.now().isoformat(timespec="seconds"))

    summary = {"total": total, "ok": ok, "failed": failed}

    if include_sentiment is None:
        include_sentiment = bool(setting("sentiment.enabled", True))
    if include_sentiment:
        try:
            summary["sentiment"] = run_sentiment_collector(progress=progress)
        except Exception as exc:
            summary["sentiment_error"] = str(exc)

    return summary


def run_pre_warm(progress=None) -> dict:
    """Run the Claude thesis processor against every `holding` ticker so
    the Research tab is instant on next visit.

    Honours the cost cap in `settings.yaml` (claude.cost_cap_usd).
    Halts gracefully when the cap is hit. Cache-first, so re-runs against
    unchanged data are free.

    Returns {total, ok, cached, failed: [ticker], total_cost_usd}.
    """
    from .claude_cli import Claude
    from .metrics import build_research_data
    from .processors.thesis import build_thesis

    db.init_db()
    with db.connect() as conn:
        lists = db.get_lists(conn)
    holdings = sorted(t for t, l in lists.items() if l == "holding")
    total = len(holdings)
    if not total:
        return {"total": 0, "ok": 0, "cached": 0, "failed": [],
                "total_cost_usd": 0.0}

    claude = Claude()  # picks up cost cap from settings.yaml
    ok = cached = 0
    failed: list = []
    cost_total = 0.0

    for i, ticker in enumerate(holdings, start=1):
        if progress:
            progress(i, total, f"{ticker} (thesis)")
        try:
            data = build_research_data(ticker)
            result_data, result = build_thesis(
                ticker, data["snapshot"], data["sections"], data["sentiment"],
                claude=claude,
            )
        except Exception as exc:
            failed.append(ticker)
            continue
        if not result.ok:
            failed.append(ticker)
            continue
        ok += 1
        if result.cached:
            cached += 1
        elif result.cost_usd:
            cost_total += float(result.cost_usd)

    return {
        "total": total, "ok": ok, "cached": cached,
        "failed": failed, "total_cost_usd": round(cost_total, 4),
    }


def main():
    parser = argparse.ArgumentParser(description="FIRE data collector")
    parser.add_argument(
        "--pre-warm", action="store_true",
        help="After data refresh, also run Claude thesis on every `holding` "
             "ticker so the dashboard is instant.",
    )
    parser.add_argument(
        "--skip-sentiment", action="store_true",
        help="Skip the sentiment ingest pass (faster, no Reddit/StockTwits)",
    )
    args = parser.parse_args()

    print("FIRE collector — refreshing the watchlist...\n")

    def _progress(done, total, ticker):
        print(f"  [{done:>2}/{total}] {ticker}")

    result = run_collector(progress=_progress,
                           include_sentiment=not args.skip_sentiment)
    print(f"\nDone. {result['ok']}/{result['total']} tickers updated.")
    if result["failed"]:
        print(f"No price returned for: {', '.join(result['failed'])}")
    sent = result.get("sentiment")
    if sent:
        by = sent["by_source"]
        print(f"\nSentiment ({sent['scorer']}): {sent['tickers_with_data']}/"
              f"{sent['total']} tickers had new posts.")
        print(f"  reddit: {by['reddit']}   stocktwits: {by['stocktwits']}   "
              f"news: {by['news']}   x: {by['x']}")

    if args.pre_warm:
        print("\n--pre-warm: running Claude thesis on holding tickers…")
        pw = run_pre_warm(progress=_progress)
        if pw["total"]:
            print(f"Done. {pw['ok']}/{pw['total']} OK · "
                  f"{pw['cached']} cached · "
                  f"${pw['total_cost_usd']:.2f} spent.")
            if pw["failed"]:
                print(f"Failed: {', '.join(pw['failed'])}")
        else:
            print("No `holding` tickers — nothing to pre-warm.")


if __name__ == "__main__":
    main()
    sys.exit(0)
