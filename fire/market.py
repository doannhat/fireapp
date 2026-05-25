"""Market data via yfinance: snapshots, fundamentals, earnings, price history.

Every function is defensive — a bad or delisted ticker returns empty data
rather than raising, so one failure never aborts a whole collection run.
"""
from __future__ import annotations

import math

import pandas as pd
import yfinance as yf


def _num(value):
    """Coerce to float; return None for NaN / inf / missing / junk."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _fast_get(fast_info, key):
    try:
        return fast_info[key]
    except Exception:
        return None


def fetch_snapshot(ticker: str) -> dict:
    """Pull a current valuation snapshot for one ticker. Never raises."""
    ticker = ticker.upper()
    snap = {"ticker": ticker, "name": ticker}
    t = yf.Ticker(ticker)

    # fast_info is quick and reliable for price / range data.
    try:
        fi = t.fast_info
        snap["price"] = _num(_fast_get(fi, "lastPrice"))
        snap["prev_close"] = _num(_fast_get(fi, "previousClose"))
        snap["market_cap"] = _num(_fast_get(fi, "marketCap"))
        snap["week52_high"] = _num(_fast_get(fi, "yearHigh"))
        snap["week52_low"] = _num(_fast_get(fi, "yearLow"))
        snap["fifty_day_avg"] = _num(_fast_get(fi, "fiftyDayAverage"))
        snap["two_hundred_day_avg"] = _num(_fast_get(fi, "twoHundredDayAverage"))
    except Exception:
        pass

    # .info carries the valuation ratios; it is slower and sometimes partial.
    info = {}
    try:
        info = t.info or {}
    except Exception:
        info = {}

    if info:
        snap["name"] = info.get("shortName") or info.get("longName") or snap["name"]
        snap["industry"] = info.get("industry")
        snap["sector"] = info.get("sector")
        snap["trailing_pe"] = _num(info.get("trailingPE"))
        snap["forward_pe"] = _num(info.get("forwardPE"))
        snap["price_to_sales"] = _num(info.get("priceToSalesTrailing12Months"))
        snap["price_to_book"] = _num(info.get("priceToBook"))
        snap["peg"] = _num(info.get("trailingPegRatio") or info.get("pegRatio"))
        snap["ev_to_ebitda"] = _num(info.get("enterpriseToEbitda"))
        snap["profit_margin"] = _num(info.get("profitMargins"))
        snap["revenue_growth"] = _num(info.get("revenueGrowth"))
        # Backfill anything fast_info could not provide.
        if snap.get("price") is None:
            snap["price"] = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
        if snap.get("prev_close") is None:
            snap["prev_close"] = _num(info.get("previousClose"))
        if snap.get("market_cap") is None:
            snap["market_cap"] = _num(info.get("marketCap"))
        if snap.get("week52_high") is None:
            snap["week52_high"] = _num(info.get("fiftyTwoWeekHigh"))
        if snap.get("week52_low") is None:
            snap["week52_low"] = _num(info.get("fiftyTwoWeekLow"))

    return snap


def fetch_earnings(ticker: str, limit: int = 12) -> list:
    """Past + scheduled earnings dates with EPS estimate, actual and surprise %.

    Surprise is computed here rather than read from yfinance, so the units
    are always a clean percentage.
    """
    t = yf.Ticker(ticker)
    try:
        df = t.get_earnings_dates(limit=limit)
    except Exception:
        return []
    if df is None or getattr(df, "empty", True):
        return []

    rows = []
    for idx, row in df.iterrows():
        try:
            edate = pd.Timestamp(idx).date().isoformat()
        except Exception:
            continue
        est = _num(row.get("EPS Estimate"))
        act = _num(row.get("Reported EPS"))
        surprise = None
        if est is not None and act is not None and est != 0:
            surprise = (act - est) / abs(est) * 100.0
        rows.append({
            "earnings_date": edate,
            "eps_estimate": est,
            "eps_actual": act,
            "surprise_pct": surprise,
        })
    return rows


def price_history(ticker: str, period: str = "1y"):
    """Daily close history as a pandas Series indexed by date, or None."""
    t = yf.Ticker(ticker)
    try:
        hist = t.history(period=period, interval="1d")
    except Exception:
        return None
    if hist is None or hist.empty or "Close" not in hist:
        return None
    return hist["Close"]
