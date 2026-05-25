"""Historical valuation ratios scraped from stockanalysis.com.

Why we have this: yfinance gives you *today's* P/B, but the deep-value
screen wants P/B *history* — has this name been below book before, and
for how long? stockanalysis.com publishes 10y of annual ratios per
ticker on a public HTML page that's easy to parse.

Pattern matches the other adapters: returns a list of dicts, never
raises. The orchestrator persists via `db.save_valuation_history`.

Page format (as of mid-2026):

    https://stockanalysis.com/stocks/<symbol>/financials/ratios/

The page renders a table whose first row is the period_end date and
subsequent rows are individual ratios (PE Ratio, PB Ratio, PS Ratio,
...). We extract the three we care about and ignore the rest.
"""
from __future__ import annotations

import re

import requests


_BASE_URL = "https://stockanalysis.com/stocks/{ticker}/financials/ratios/"
_HEADERS = {
    # stockanalysis.com 403s on unset / generic UAs. A real-browser UA is
    # fine — the page is public and they don't gate it behind a key.
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Map the row labels we care about onto our column names.
_LABELS = {
    "pb": "PB Ratio",
    "ps": "PS Ratio",
    "pe": "PE Ratio",
}


def _fetch_html(ticker: str) -> str:
    try:
        url = _BASE_URL.format(ticker=ticker.lower())
        r = requests.get(url, headers=_HEADERS, timeout=15)
        if r.status_code != 200:
            return ""
        return r.text
    except Exception:
        return ""


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def _num(s: str):
    """Parse '12.34', '1,234.5', '-' (missing), '12.3%' → float or None."""
    if not s:
        return None
    s = s.replace(",", "").replace("%", "").strip()
    if s in ("-", "—", "N/A", ""):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _extract_rows(html: str) -> dict:
    """Return {label: [cells]} for every row in the first ratios table.
    First cell of a row is the label (text), remaining cells are
    annual values left-to-right, oldest → newest (stockanalysis flips
    the table this way for desktop)."""
    if not html:
        return {}
    # Grab the first <table>…</table>.
    m = re.search(r"<table\b[^>]*>(.*?)</table>", html, flags=re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    table = m.group(1)
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", table, flags=re.DOTALL | re.IGNORECASE)
    out: dict = {}
    for row in rows:
        cells = re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>",
                           row, flags=re.DOTALL | re.IGNORECASE)
        if not cells:
            continue
        cells = [_strip_tags(c) for c in cells]
        label = cells[0]
        if not label:
            continue
        out[label] = cells[1:]
    return out


def fetch_valuation_history(ticker: str) -> list:
    """Return up to 10 years of {period_end, pb, ps, pe} rows for ticker.

    Never raises. Returns [] on any failure (page missing, parsing
    failure, ticker not covered)."""
    html = _fetch_html(ticker)
    if not html:
        return []
    rows = _extract_rows(html)
    if not rows:
        return []

    # The header row's label is typically "Fiscal Year" with cells like
    # "FY 2015", "FY 2016", ..., "FY 2025". We pull period_end from
    # whatever row holds the dates — stockanalysis labels it "Period
    # Ending" on this page.
    period_cells = (rows.get("Period Ending")
                    or rows.get("Fiscal Year")
                    or rows.get("Year"))
    if not period_cells:
        return []

    pb_cells = rows.get(_LABELS["pb"]) or []
    ps_cells = rows.get(_LABELS["ps"]) or []
    pe_cells = rows.get(_LABELS["pe"]) or []

    n = len(period_cells)
    out: list = []
    for i in range(n):
        period = period_cells[i]
        if not period:
            continue
        # Normalise "FY 2024" / "2024" / "2024-12-31" → use raw string;
        # SQLite text sort works fine for the keys we care about.
        period_end = period.strip()
        out.append({
            "period_end": period_end,
            "pb": _num(pb_cells[i]) if i < len(pb_cells) else None,
            "ps": _num(ps_cells[i]) if i < len(ps_cells) else None,
            "pe": _num(pe_cells[i]) if i < len(pe_cells) else None,
        })
    # Filter rows with absolutely no data.
    return [r for r in out
            if any(r.get(k) is not None for k in ("pb", "ps", "pe"))]
