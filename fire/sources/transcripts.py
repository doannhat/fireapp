"""Earnings-call transcripts from AlphaStreet — free, public, complete.

Why AlphaStreet:

- Google News RSS wraps publisher URLs in base64 protobufs that don't
  resolve via HTTP redirect (tested — returns "Google News" stub).
- yfinance's .news pool has ~10 items at a time, none of which are
  call transcripts (general financial headlines only).
- Seeking Alpha aggressively bot-detects after the first request and
  the transcript bodies are gated client-side in SSR_DATA.
- Motley Fool's per-ticker page is client-rendered; transcript URLs
  aren't in the static HTML.
- AlphaStreet (news.alphastreet.com) — publishes the FULL transcripts
  for free, plain HTML, no rate-limit issues observed. The URL pattern
  is `/<ticker-slug>-q<N>-<YYYY>-earnings-call-transcript/` and a
  per-ticker search with `?post_type=transcript` returns just the
  transcripts.

Performance:
- One search request to discover up to ~10 candidates per ticker.
- One body fetch per candidate (skipping any call_date already in DB).
- Body trimmed to ~12KB on storage (prompt slice trims further at
  send-time, see processors/thesis.py).
- Defensive throughout — never raises.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

import requests


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_6) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_SEARCH_URL = "https://news.alphastreet.com/"

# Per-call body cap on persistence. Big enough to hold prepared remarks
# + the most info-dense Q&A; small enough that 3 calls per ticker fit
# comfortably under the deep-dive prompt budget.
_BODY_CAP = 12_000


_DATE_PATTERNS = (
    # "Apr 23, 2026" / "April 23, 2026"
    (re.compile(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"[a-z]{0,7}\s+(\d{1,2}),?\s+(\d{4})\b"
    ), "month_day"),
    # ISO "2026-04-23"
    (re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"), "iso"),
)

_MONTH = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}


def _parse_date_anywhere(text: str) -> str | None:
    if not text:
        return None
    for pat, fmt in _DATE_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        try:
            if fmt == "iso":
                y, mo, d = (int(x) for x in m.groups())
            else:
                mon, day, year = m.groups()
                mon = _MONTH.get(mon[:3])
                if not mon:
                    continue
                y, mo, d = int(year), mon, int(day)
            return f"{y:04d}-{mo:02d}-{d:02d}"
        except (ValueError, KeyError):
            continue
    return None


def _extract_period(text: str) -> str | None:
    """Pull 'Q1 2026' / 'FY 2025' from text."""
    if not text:
        return None
    m = re.search(r"\b(Q[1-4])[\s-]+(\d{4})\b", text)
    if m:
        return f"{m.group(1)} {m.group(2)}"
    m = re.search(r"\b(FY|Fiscal\s+Year)\s+(\d{4})\b", text, re.IGNORECASE)
    if m:
        return f"FY {m.group(2)}"
    return None


def _strip_tags(html: str) -> str:
    """Convert article HTML to plain text while preserving paragraph
    breaks. Scripts and styles are dropped entirely."""
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ",
                  html, flags=re.DOTALL | re.IGNORECASE)
    # Convert block-level tags to newlines.
    html = re.sub(r"</?(p|div|br|h\d|li|tr|table)\b[^>]*>", "\n", html,
                  flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", html)
    # Decode the few HTML entities that matter for readability.
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&#x27;", "'").replace("&#39;", "'")
                .replace("&quot;", '"').replace("&lt;", "<")
                .replace("&gt;", ">").replace("&#8217;", "'")
                .replace("&#8220;", '"').replace("&#8221;", '"'))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _discover(ticker: str, limit: int) -> list:
    """Hit AlphaStreet's search with `post_type=transcript`. Returns
    candidate articles whose slugs reference this ticker."""
    out: list = []
    seen: set = set()
    # AlphaStreet slugs sometimes use the company name, sometimes the
    # ticker. Try ticker first (more specific), then ticker again as a
    # broader keyword search.
    queries = [ticker.upper(), f"({ticker.upper()})"]
    for q in queries:
        try:
            r = requests.get(
                _SEARCH_URL,
                params={"s": q, "post_type": "transcript"},
                headers=_HEADERS, timeout=15,
            )
            if r.status_code != 200:
                continue
            html = r.text
        except Exception:
            continue
        # Article URLs are clean slugs: /<slug>/  where slug typically
        # contains the ticker and the word 'transcript'.
        links = re.findall(
            r'href="(https://news\.alphastreet\.com/[a-z0-9-]+/?)"', html
        )
        tk_low = ticker.lower()
        for link in links:
            low = link.lower()
            if link in seen:
                continue
            # Slug must mention the ticker AND look like a transcript.
            if tk_low not in low:
                continue
            if "transcript" not in low:
                continue
            seen.add(link)
            out.append(link)
            if len(out) >= limit:
                return out
    return out


def _fetch_article(url: str) -> dict | None:
    """Fetch one transcript article and return {call_date, period,
    url, body}. Returns None on any failure."""
    try:
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        text = _strip_tags(r.text)
    except Exception:
        return None
    if not text or len(text) < 2000:
        # Too short — probably a stub / error page, not a real transcript.
        return None

    # Headline carries the period: "NVIDIA Corporation (NVDA) Q1 2027 …"
    head_m = re.search(r"<h1[^>]*>(.*?)</h1>",
                       r.text, flags=re.DOTALL | re.IGNORECASE)
    headline = ""
    if head_m:
        headline = re.sub(r"<[^>]+>", "", head_m.group(1)).strip()
    period = _extract_period(headline) or _extract_period(text[:1200])

    # Date is on the article — usually near the top, as "Apr. 23, 2026"
    # or similar. Pull from the first 4KB of plain text to keep
    # detection cheap.
    call_date = _parse_date_anywhere(text[:4000])

    # Anchor the body to the SUBSTANTIVE call content. AlphaStreet's
    # article layout is:
    #   1. Title / date
    #   2. "Operator" -> speaker list (analysts + execs)
    #   3. "Related Coverage" sidebar nav (preview articles)
    #   4. "Presentation" or "Sarah — Operator" → actual call begins
    #   5. Prepared remarks, then Q&A
    #
    # We want (4) onward. Anchor on the first prose-shaped opening
    # ("Good morning / afternoon / day everyone" or "Thank you,
    # operator") — that's where management actually starts speaking.
    # Fall back to "Presentation" then to the raw "Operator" if no
    # prose marker is found.
    prose_anchor = re.search(
        r"(Good\s+(?:morning|afternoon|day)[, ]+(?:everyone|ladies)|"
        r"Thank you,?\s+(?:operator|you,?\s+operator)|"
        r"Thank you and good\s+(?:morning|afternoon))",
        text, flags=re.IGNORECASE,
    )
    if prose_anchor:
        body = text[prose_anchor.start():]
    else:
        # Fallback chain: 'Presentation' heading → first 'Operator'.
        pres_anchor = re.search(r"\bPresentation\b\s*\n", text)
        if pres_anchor:
            body = text[pres_anchor.end():]
        else:
            op_anchor = re.search(r"\bOperator\b", text)
            body = text[op_anchor.start():] if op_anchor else text

    # Strip sidebar nav fragments AlphaStreet leaks into the body
    # ("Related Coverage", "Deep Dive", "Preview", date-only lines).
    body = re.sub(r"^\s*(Related Coverage|Deep Dive|Preview|Advertisement)\s*$",
                  "", body, flags=re.MULTILINE | re.IGNORECASE)
    body = re.sub(r"\n{3,}", "\n\n", body)
    body = body[:_BODY_CAP].strip()

    if not call_date:
        return None
    return {
        "call_date": call_date,
        "period": period,
        "source": "alphastreet",
        "url": url,
        "body": body,
    }


def fetch_transcripts(ticker: str, limit: int = 3,
                      skip_dates: set | None = None) -> list:
    """Fetch up to `limit` recent earnings transcripts for `ticker`.
    Skips any `call_date` already present in `skip_dates` so a re-run
    against a fresh DB pulls zero new pages.

    Returns rows {call_date, period, source, url, body}. Never raises."""
    skip_dates = skip_dates or set()
    candidates = _discover(ticker, limit * 3)
    if not candidates:
        return []

    out: list = []
    seen_dates: set = set()
    for url in candidates:
        if len(out) >= limit:
            break
        article = _fetch_article(url)
        if not article:
            continue
        cd = article["call_date"]
        if cd in skip_dates or cd in seen_dates:
            continue
        seen_dates.add(cd)
        out.append(article)
    return out
