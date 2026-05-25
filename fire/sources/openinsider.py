"""Insider transactions scraped from openinsider.com.

OpenInsider aggregates SEC Form 4 filings into a clean per-ticker HTML
table — much lighter than parsing raw Form 4 XML from EDGAR ourselves.
The page is public, no key required.

URL shape:
    http://openinsider.com/screener?s=<ticker>&...

The table cells we care about (left to right on the screener page):
    X · Filing Date · Trade Date · Ticker · Insider Name · Title ·
    Trade Type · Price · Qty · Owned · ΔOwn · Value

Trade Type encodes the action: "P - Purchase", "S - Sale",
"S - Sale+OE", "A - Grant", "M - Option Exercise", etc. We persist the
single-letter code (first char) as `action` so it sorts cleanly.

Pattern matches the other adapters: list-of-dicts out, never raises.
"""
from __future__ import annotations

import re

import requests


# The screener page accepts a ticker and returns most recent filings.
# fd=730 = lookback in days (we ask for ~2 years).
_BASE_URL = (
    "http://openinsider.com/screener"
    "?s={ticker}&o=&pl=&ph=&ll=&lh=&fd=730&fdr=&td=730&tdr="
    "&fdlyl=&fdlyh=&daysago=&xp=1&xs=1&xa=1&xd=1&xg=1&xf=1&xm=1&xx=1&xc=1&xw=1"
    "&vl=&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih="
    "&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=100&page=1"
)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_html(ticker: str) -> str:
    try:
        url = _BASE_URL.format(ticker=ticker.upper())
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            return ""
        return r.text
    except Exception:
        return ""


def _strip_tags(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()


def _extract_href(cell_html: str) -> str:
    m = re.search(r'href="([^"]+)"', cell_html)
    if not m:
        return ""
    href = m.group(1)
    if href.startswith("/"):
        href = "http://openinsider.com" + href
    return href


def _num(s: str):
    if not s:
        return None
    s = s.replace(",", "").replace("$", "").replace("+", "").strip()
    # Some values are wrapped in parens for negatives: (1,234) → -1234
    neg = s.startswith("(") and s.endswith(")")
    if neg:
        s = s[1:-1]
    try:
        v = float(s)
        return -v if neg else v
    except ValueError:
        return None


def _find_main_table(html: str) -> str:
    """OpenInsider wraps the results in <table class="tinytable">…</table>."""
    m = re.search(
        r'<table[^>]*class="[^"]*\btinytable\b[^"]*"[^>]*>(.*?)</table>',
        html, flags=re.DOTALL | re.IGNORECASE,
    )
    return m.group(1) if m else ""


def fetch_insider_transactions(ticker: str) -> list:
    """Return up to ~100 most recent insider transactions for a ticker.

    Each row: {filing_date, txn_date, insider, role, action, shares,
    price, value, url}. Never raises."""
    html = _fetch_html(ticker)
    if not html:
        return []
    body = _find_main_table(html)
    if not body:
        return []

    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", body,
                      flags=re.DOTALL | re.IGNORECASE)
    out: list = []
    for row in rows:
        # Match data cells only — the header row uses <th> and the
        # earlier regex was matching both, leaking column labels into
        # the results.
        cells = re.findall(r"<td\b[^>]*>(.*?)</td>",
                           row, flags=re.DOTALL | re.IGNORECASE)
        if len(cells) < 12:
            continue
        # Filing-date cell often holds an <a> linking to the SEC filing.
        filing_link = _extract_href(cells[1])
        cell_txt = [_strip_tags(c) for c in cells]
        filing_date = cell_txt[1][:10] if cell_txt[1] else None
        txn_date = cell_txt[2][:10] if cell_txt[2] else None
        # cells[3] is the ticker (always = arg); skip
        insider = cell_txt[4] or None
        role = cell_txt[5] or None
        trade_type = cell_txt[6] or ""
        action = trade_type[:1].upper() if trade_type else None
        price = _num(cell_txt[7])
        shares = _num(cell_txt[8])
        value = _num(cell_txt[11])
        if not filing_date or not insider:
            continue
        out.append({
            "filing_date": filing_date,
            "txn_date": txn_date,
            "insider": insider,
            "role": role,
            "action": action,
            "shares": shares,
            "price": price,
            "value": value,
            "url": filing_link or None,
        })
    return out
