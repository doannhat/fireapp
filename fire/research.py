"""Deep-research fetchers — full financial statements via yfinance.

yfinance returns each statement as a DataFrame whose rows are metric
names ("Total Revenue", "Net Income", ...) and whose columns are
period-end dates. We melt that to long form so SQLite can store it
cheaply and the UI can pivot per-statement.

Each fetcher is defensive: an empty or missing frame returns 0 rows
written, never raises.
"""
from __future__ import annotations

import json

import pandas as pd
import yfinance as yf

from . import db


def _melt_frame(df) -> list:
    """yfinance frame → list of {period_end, metric, value} rows."""
    if df is None or getattr(df, "empty", True):
        return []
    out = []
    for col in df.columns:
        try:
            period_end = pd.Timestamp(col).date().isoformat()
        except Exception:
            continue
        for metric, value in df[col].items():
            if pd.isna(value):
                continue
            try:
                v = float(value)
            except (TypeError, ValueError):
                continue
            out.append({
                "period_end": period_end,
                "metric": str(metric),
                "value": v,
            })
    return out


def _safe_attr(ticker_obj, attr: str):
    """Pull an attribute from yfinance.Ticker without letting it raise."""
    try:
        return getattr(ticker_obj, attr)
    except Exception:
        return None


def _fetch_pair(ticker: str, annual_attr: str, quarterly_attr: str,
                statement: str) -> int:
    """Pull annual + quarterly variants of a statement, save both."""
    t = yf.Ticker(ticker)
    n = 0
    annual = _safe_attr(t, annual_attr)
    quarterly = _safe_attr(t, quarterly_attr)
    with db.connect() as c:
        n += db.save_financial_lines(c, ticker, "annual", statement,
                                     _melt_frame(annual))
        n += db.save_financial_lines(c, ticker, "quarterly", statement,
                                     _melt_frame(quarterly))
    return n


def fetch_and_save_income(ticker: str) -> int:
    return _fetch_pair(ticker, "income_stmt", "quarterly_income_stmt",
                       "income")


def fetch_and_save_balance(ticker: str) -> int:
    return _fetch_pair(ticker, "balance_sheet", "quarterly_balance_sheet",
                       "balance")


def fetch_and_save_cashflow(ticker: str) -> int:
    return _fetch_pair(ticker, "cashflow", "quarterly_cashflow", "cashflow")


def fetch_and_save_extras(ticker: str):
    """Institutional holders and analyst recommendations. Stored as JSON
    blobs in `deep_extras` since the row shape varies."""
    t = yf.Ticker(ticker)
    with db.connect() as c:
        holders = _safe_attr(t, "institutional_holders")
        if isinstance(holders, pd.DataFrame) and not holders.empty:
            db.save_deep_extra(
                c, ticker, "institutional_holders",
                holders.head(10).to_json(orient="records"),
            )
        recs = _safe_attr(t, "recommendations")
        if isinstance(recs, pd.DataFrame) and not recs.empty:
            db.save_deep_extra(
                c, ticker, "recommendations",
                recs.tail(20).to_json(orient="records", date_format="iso"),
            )


def ensure_thesis_row(ticker: str):
    """Seed an empty thesis-notes row so the UI has somewhere to write."""
    with db.connect() as c:
        existing = db.get_thesis_note(c, ticker)
        if not existing.get("updated_at"):
            db.save_thesis_note(c, ticker, existing.get("content") or "")


def pivot_statement(rows: list) -> "pd.DataFrame":
    """Helper for the UI — pivot long-form rows into metric × period."""
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    out = df.pivot_table(index="metric", columns="period_end",
                         values="value", aggfunc="first")
    # Most recent period first.
    out = out[sorted(out.columns, reverse=True)]
    return out
