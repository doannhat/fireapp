"""SEC EDGAR filings lookup — official, free, no API key required.

EDGAR asks callers to identify themselves via the User-Agent header; that
string is configured in settings.yaml under `edgar.user_agent`.

Three modes:

  1. ``recent_filings(ticker)`` — most recent 10-K/Q/8-K for a ticker.
  2. ``search_filings(query)`` — EDGAR full-text search across ALL
     filers. Use to discover *which* companies are talking about
     "HBM4", "co-packaged optics", "silicon carbide", etc.
  3. ``fetch_13f_positions(ticker)`` — reconstruct institutional
     positions in a ticker from recent 13F filings.

All three are defensive: a flaky response yields an empty list, never
raises.
"""
from __future__ import annotations

import re
from datetime import datetime

import requests

from .config import setting

_UA = setting("edgar.user_agent", "FIRE Dashboard contact@example.com")
_HEADERS = {"User-Agent": _UA, "Accept-Encoding": "gzip, deflate"}

_cik_map = None  # lazy-loaded ticker -> zero-padded CIK


def _load_cik_map() -> dict:
    global _cik_map
    if _cik_map is None:
        try:
            resp = requests.get(
                "https://www.sec.gov/files/company_tickers.json",
                headers=_HEADERS, timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
            _cik_map = {
                str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
                for row in data.values()
            }
        except Exception:
            _cik_map = {}
    return _cik_map


def recent_filings(ticker: str, forms=("8-K", "10-Q", "10-K"), limit: int = 8) -> list:
    """Most recent SEC filings for a ticker. Never raises; returns [] on failure."""
    cik = _load_cik_map().get(ticker.upper())
    if not cik:
        return []
    try:
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=_HEADERS, timeout=20,
        )
        resp.raise_for_status()
        recent = resp.json().get("filings", {}).get("recent", {})
    except Exception:
        return []

    forms_list = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])
    descs = recent.get("primaryDocDescription", [])

    out = []
    for i in range(len(forms_list)):
        form = forms_list[i]
        if forms and form not in forms:
            continue
        accession = accessions[i] if i < len(accessions) else ""
        doc = docs[i] if i < len(docs) else ""
        acc_nodash = accession.replace("-", "")
        if acc_nodash and doc:
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{int(cik)}/{acc_nodash}/{doc}")
        else:
            url = (f"https://www.sec.gov/cgi-bin/browse-edgar"
                   f"?action=getcompany&CIK={cik}&type={form}")
        out.append({
            "form": form,
            "filing_date": dates[i] if i < len(dates) else "",
            "accession": accession,
            "title": descs[i] if i < len(descs) and descs[i] else form,
            "url": url,
        })
        if len(out) >= limit:
            break
    return out


# --------------------------------------------------------------------------
# Full-text search across all EDGAR filings — theme discovery
# --------------------------------------------------------------------------
_FTS_BASE = "https://efts.sec.gov/LATEST/search-index"

# Reverse map: padded CIK → ticker. Built on demand from the same
# company_tickers.json the recent_filings code already pulls.
_cik_to_ticker = None


def _load_cik_to_ticker() -> dict:
    global _cik_to_ticker
    if _cik_to_ticker is None:
        _cik_to_ticker = {cik: tk for tk, cik in _load_cik_map().items()}
    return _cik_to_ticker


def search_filings(query: str, forms=("10-K", "10-Q", "8-K"),
                   limit: int = 25, days: int = 365) -> list:
    """Full-text search across ALL EDGAR filings for `query`.

    Returns up to `limit` matches as
        {ticker, cik, accession, form, filing_date, company, snippet, url}

    Use this to find every company *talking about* a theme — "HBM4",
    "co-packaged optics", "silicon carbide", etc. Filters to the last
    `days` days by default so a stale corpus doesn't dominate. Never
    raises.
    """
    q = (query or "").strip()
    if not q:
        return []
    # EDGAR full-text search is case-insensitive and supports quoted
    # phrases — wrap multi-word queries in quotes so "co-packaged optics"
    # doesn't match every doc with "co" + "packaged" + "optics" separately.
    if " " in q and not (q.startswith('"') and q.endswith('"')):
        q = f'"{q}"'

    params = {
        "q": q,
        "dateRange": "custom",
        "forms": ",".join(forms),
    }
    # Date filter: last `days` days.
    try:
        from datetime import date, timedelta
        params["startdt"] = (date.today() - timedelta(days=days)).isoformat()
        params["enddt"] = date.today().isoformat()
    except Exception:
        pass

    try:
        resp = requests.get(_FTS_BASE, params=params,
                            headers=_HEADERS, timeout=20)
        resp.raise_for_status()
        payload = resp.json()
    except Exception:
        return []

    hits = (payload.get("hits") or {}).get("hits") or []
    if not hits:
        return []
    cik_to_ticker = _load_cik_to_ticker()
    out: list = []
    for h in hits[:limit]:
        src = h.get("_source") or {}
        # EDGAR returns 'adsh' = accession with dashes already, plus
        # 'ciks' = list of filers as zero-stripped ints.
        accession = src.get("adsh") or h.get("_id") or ""
        if not accession:
            continue
        ciks = src.get("ciks") or []
        cik = str(ciks[0]).zfill(10) if ciks else None
        ticker = cik_to_ticker.get(cik) if cik else None
        forms_field = src.get("form") or ""
        filing_date = src.get("file_date") or src.get("filed") or ""
        # Display names list - first one is the issuer.
        companies = src.get("display_names") or []
        company = companies[0] if companies else None
        snippet = h.get("highlight", {}).get("content")
        if isinstance(snippet, list):
            snippet = " … ".join(snippet)[:500]
        # Build a viewable URL to the document.
        acc_nodash = accession.replace("-", "")
        primary_doc = (h.get("_id") or "").split(":", 1)[-1]
        if cik and acc_nodash and primary_doc:
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{int(cik)}/{acc_nodash}/{primary_doc}")
        elif cik and accession:
            url = (f"https://www.sec.gov/cgi-bin/browse-edgar"
                   f"?action=getcompany&CIK={cik}&type={forms_field}")
        else:
            url = "https://efts.sec.gov/LATEST/search-index?q=" + q
        out.append({
            "ticker": ticker,
            "cik": cik,
            "accession": accession,
            "form": forms_field,
            "filing_date": filing_date,
            "company": company,
            "snippet": snippet,
            "url": url,
        })
    return out


# --------------------------------------------------------------------------
# 13F institutional positions for a ticker
# --------------------------------------------------------------------------

# Lazy ticker → CUSIP map. EDGAR's company_tickers.json doesn't include
# CUSIPs; we instead use the issuer's CIK + the holder's 13F XML which
# lists positions by CUSIP **and** name. We resolve "holdings of $TICKER"
# by matching the issuer's listed name in the 13F infoTable.


_company_name_by_cik: dict = {}


def _company_name_for_cik(cik: str) -> str:
    """Look up an entity's display name from EDGAR. Cached in-process —
    holder names rarely change, so we keep them per-run."""
    if not cik:
        return ""
    if cik in _company_name_by_cik:
        return _company_name_by_cik[cik]
    try:
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        name = resp.json().get("name", "") or ""
    except Exception:
        name = ""
    _company_name_by_cik[cik] = name
    return name


def _company_name_for_ticker(ticker: str) -> str:
    cik = _load_cik_map().get(ticker.upper())
    return _company_name_for_cik(cik) if cik else ""


def _recent_13f_accessions(holder_cik: str, limit: int = 4) -> list:
    """Most-recent 13F-HR accessions for an institutional holder."""
    try:
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{holder_cik}.json",
            headers=_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        recent = resp.json().get("filings", {}).get("recent", {})
    except Exception:
        return []
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    period_of_reports = recent.get("reportDate", [])
    out = []
    for i, f in enumerate(forms):
        if not f.startswith("13F-HR"):
            continue
        out.append({
            "accession": accs[i] if i < len(accs) else "",
            "filing_date": dates[i] if i < len(dates) else "",
            "period_end": period_of_reports[i] if i < len(period_of_reports) else "",
        })
        if len(out) >= limit:
            break
    return out


def _fetch_13f_infotable(holder_cik: str, accession: str) -> str:
    """Pull the InfoTable XML for one 13F. EDGAR doesn't expose a
    consistent filename, so we list the filing index and pick the XML
    that contains the table data."""
    acc_nodash = accession.replace("-", "")
    try:
        idx = requests.get(
            f"https://www.sec.gov/cgi-bin/browse-edgar"
            f"?action=getcompany&CIK={holder_cik}"
            f"&type=13F-HR&dateb=&owner=include&count=10",
            headers=_HEADERS, timeout=15,
        )
        # We don't actually need the human-readable page; fall through to
        # the JSON index for the filing folder.
    except Exception:
        pass
    try:
        folder_idx = requests.get(
            f"https://www.sec.gov/Archives/edgar/data/"
            f"{int(holder_cik)}/{acc_nodash}/",
            headers=_HEADERS, timeout=15,
        )
        if folder_idx.status_code != 200:
            return ""
        # Find an XML that looks like InfoTable.
        m = re.findall(r'href="([^"]+\.xml)"', folder_idx.text, flags=re.IGNORECASE)
        info_xml = None
        for href in m:
            low = href.lower()
            if "infotable" in low or "info_table" in low or "form13f" in low:
                info_xml = href
                break
            # Heuristic fallback — the smallest non-primary XML in a
            # 13F filing is almost always the info table.
            if low.endswith(".xml") and "primary_doc" not in low:
                info_xml = href
        if not info_xml:
            return ""
        if info_xml.startswith("/"):
            url = "https://www.sec.gov" + info_xml
        elif info_xml.startswith("http"):
            url = info_xml
        else:
            url = (f"https://www.sec.gov/Archives/edgar/data/"
                   f"{int(holder_cik)}/{acc_nodash}/{info_xml}")
        r = requests.get(url, headers=_HEADERS, timeout=20)
        if r.status_code != 200:
            return ""
        return r.text
    except Exception:
        return ""


_CORP_SUFFIXES = frozenset({
    "CORP", "CORPORATION", "INC", "INCORPORATED", "LTD", "LIMITED",
    "LLC", "PLC", "NV", "SA", "AG", "CO", "COMPANY", "HOLDINGS",
    "HOLDING", "GROUP", "CLASS", "THE", "ORDINARY", "SHARES",
    "COMMON", "STOCK",
})


def _issuer_match_phrase(issuer_name: str) -> str:
    """Build a robust matching phrase from the issuer's EDGAR name.

    Why this exists: the prior implementation matched on the first
    word only — but for issuers with short first words ("MP Materials",
    "AT&T", "U.S. Steel") that produces brutal false positives. A 13F
    that holds "MPLX LP" matched the "MP" prefix for MP Materials,
    contaminating the position aggregation with bogus shares.

    The fix: normalize the issuer name (strip punctuation, drop corp
    suffixes like CORP/INC/HOLDINGS) and use the first 1-2 significant
    words as the match phrase. For short first words (≤3 chars) we
    require BOTH the first and second word to be present — "MP" alone
    matches MPLX, but "MP MATERIALS" does not."""
    if not issuer_name:
        return ""
    cleaned = re.sub(r"[^\w\s]", " ", issuer_name.upper())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = [w for w in cleaned.split() if w not in _CORP_SUFFIXES]
    if not words:
        return ""
    if len(words[0]) <= 3 and len(words) >= 2:
        return f"{words[0]} {words[1]}"
    return words[0]


def _parse_infotable_positions(xml: str, issuer_name: str) -> list:
    """Pull (issuer_name, value, shares) tuples that match the target
    issuer name. Uses a length-aware first-1-or-2-word phrase matcher
    (see `_issuer_match_phrase`) to avoid false positives for short
    issuer names like 'MP'."""
    if not xml or not issuer_name:
        return []
    target = _issuer_match_phrase(issuer_name)
    if not target:
        return []
    # Each position is bounded by <infoTable>…</infoTable>; strip XML
    # namespaces to make regex tractable.
    xml_no_ns = re.sub(r"<\w+:", "<", xml)
    xml_no_ns = re.sub(r"</\w+:", "</", xml_no_ns)
    blocks = re.findall(r"<infoTable>(.*?)</infoTable>",
                        xml_no_ns, flags=re.DOTALL | re.IGNORECASE)
    out: list = []
    for b in blocks:
        name_m = re.search(r"<nameOfIssuer>(.*?)</nameOfIssuer>",
                           b, flags=re.DOTALL | re.IGNORECASE)
        if not name_m:
            continue
        name = name_m.group(1).strip()
        # Normalize the 13F's nameOfIssuer the same way so suffix /
        # punctuation differences don't break the match ("MP Materials,
        # Corp" vs "MP MATERIALS CORP").
        name_norm = re.sub(r"[^\w\s]", " ", name.upper())
        name_norm = re.sub(r"\s+", " ", name_norm).strip()
        if target not in name_norm:
            continue
        val_m = re.search(r"<value>(.*?)</value>", b,
                          flags=re.IGNORECASE)
        sh_m = re.search(r"<sshPrnamt>(.*?)</sshPrnamt>", b,
                         flags=re.IGNORECASE)
        try:
            # SEC 13F amendments (effective 2023): the `<value>` field is
            # reported in *whole dollars*. Older filings used thousands.
            # We default to dollars since the curated holder list is all
            # large managers filing under the modern rules.
            value = float(val_m.group(1).strip()) if val_m else None
        except (TypeError, ValueError):
            value = None
        try:
            shares = float(sh_m.group(1).strip()) if sh_m else None
        except (TypeError, ValueError):
            shares = None
        out.append({"name": name, "shares": shares, "value": value})
    return out


# --------------------------------------------------------------------------
# Activist filings — SC 13D / 13G targeting a given ticker
# --------------------------------------------------------------------------
_BROWSE_EDGAR = "https://www.sec.gov/cgi-bin/browse-edgar"


def fetch_activist_filings(ticker: str, days: int = 365) -> list:
    """Return SC 13D / 13G / 13D-A / 13G-A filings targeting `ticker`.

    Approach: EDGAR's legacy `browse-edgar` endpoint, when queried with
    the ISSUER's CIK, returns 13D/G filings where that issuer is the
    SUBJECT (i.e. the company being held). This is the canonical
    discovery path — the FTS approach we tried first matched too much
    tangential text (e.g. a 13G filing that footnotes the issuer's
    name elsewhere).

    The endpoint returns an HTML index page; we parse the filing rows.
    Each row exposes form / filing date / accession + a link to the
    filing folder where the cover page is. From the cover page we
    can later extract % ownership and filer name — but to keep the
    collector wall-clock tight, we lazily resolve filer names from a
    second hit when the index doesn't carry them.

    Each return row: {filer_cik, filer_name, form, accession,
    filing_date, pct_owned, url}. Never raises."""
    cik = _load_cik_map().get(ticker.upper())
    if not cik:
        return []
    params = {
        "action": "getcompany",
        "CIK": cik,
        "type": "SC 13",
        "dateb": "",
        "owner": "include",
        "count": "40",
    }
    try:
        resp = requests.get(_BROWSE_EDGAR, params=params,
                            headers=_HEADERS, timeout=20)
        if resp.status_code != 200:
            return []
        html = resp.text
    except Exception:
        return []

    # The filings results live inside a <table class="tableFile2"> block.
    # Each row contains: form-type td, link td, description td (which
    # carries `Acc-no: 0001234-56-789012`), and a date td.
    from datetime import date as _date, timedelta as _td
    cutoff = (_date.today() - _td(days=days)).isoformat()

    tbl_m = re.search(
        r'<table[^>]*class="tableFile2"[^>]*>(.*?)</table>',
        html, flags=re.DOTALL | re.IGNORECASE,
    )
    if not tbl_m:
        return []
    table_body = tbl_m.group(1)

    out: list = []
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table_body,
                      flags=re.DOTALL | re.IGNORECASE)
    for row in rows:
        cells = re.findall(r"<td[^>]*>(.*?)</td>",
                           row, flags=re.DOTALL | re.IGNORECASE)
        if len(cells) < 4:
            continue
        form = re.sub(r"<[^>]+>", "", cells[0]).strip()
        if not form.startswith("SC 13"):
            continue
        # Pull href + accession from the link cell (cells[1]).
        href_m = re.search(
            r'href="(/Archives/edgar/data/(\d+)/(\d+)/'
            r'([\d-]+)-index\.htm[^"]*)"',
            cells[1], flags=re.IGNORECASE,
        )
        if not href_m:
            continue
        href = href_m.group(1)
        filer_cik_path = href_m.group(2)
        acc_nodash = href_m.group(3)
        accession_dashed = href_m.group(4)
        # Date cell is typically cells[3] (after form / link / desc).
        # CAREFUL: the description cell contains an "Acc-no:
        # 0001234567-24-001394" string whose last 8 digits also match
        # \d{4}-\d{2}-\d{2} — so we anchor the year to 19xx/20xx and
        # explicitly skip cells that contain 'Acc-no'.
        date_text = ""
        for c in cells[2:]:
            t = re.sub(r"<[^>]+>", "", c)
            if "Acc-no" in t:
                continue
            t = t.strip()
            m_d = re.search(r"\b((?:19|20)\d{2}-\d{2}-\d{2})\b", t)
            if m_d:
                date_text = m_d.group(1)
                break
        if not date_text:
            continue
        if date_text < cutoff:
            continue
        folder_url = (f"https://www.sec.gov/Archives/edgar/data/"
                      f"{filer_cik_path}/{acc_nodash}/")
        out.append({
            "filer_cik": filer_cik_path.zfill(10),
            "filer_name": "",   # populated on demand below
            "form": form,
            "accession": accession_dashed,
            "filing_date": date_text,
            "pct_owned": None,
            "url": folder_url,
        })

    # Resolve filer names + % ownership for up to the first 6 rows. Each
    # fetch is a single HTTP request; we keep the cap low so a ticker
    # with many filings doesn't blow up the collector wall-clock.
    import time as _t
    for row in out[:6]:
        try:
            r = requests.get(row["url"], headers=_HEADERS, timeout=12)
            if r.status_code != 200:
                continue
            body = r.text
        except Exception:
            continue
        _t.sleep(0.2)
        # Filer name appears in the index page header.
        nm = re.search(
            r"<span class=\"companyName\">\s*([^<(]+)",
            body, flags=re.IGNORECASE,
        )
        if nm:
            row["filer_name"] = nm.group(1).strip()
        else:
            # Fallback: <title>SEC.gov | XYZ Corp - 13G</title>
            nm = re.search(r"<title>SEC\.gov\s*\|\s*([^<]+)</title>",
                           body, flags=re.IGNORECASE)
            if nm:
                row["filer_name"] = nm.group(1).split("-")[0].strip()
        # % ownership on the cover page — try a few common patterns.
        m_pct = re.search(
            r"PERCENT\s+OF\s+CLASS[^0-9]{1,80}(\d+\.?\d*)\s*%",
            body, flags=re.DOTALL | re.IGNORECASE,
        )
        if m_pct:
            try:
                row["pct_owned"] = float(m_pct.group(1))
            except ValueError:
                pass
    return out


# --------------------------------------------------------------------------
# Form 4 XML enrichment — pulls 10b5-1 / derivative / direct vs indirect
# --------------------------------------------------------------------------
def fetch_form4_enrichment(ticker: str, limit: int = 30) -> list:
    """Pull Form 4 XML for the most recent insider transactions and
    extract the fields OpenInsider doesn't surface:

      - `plan_10b5_1`  — whether the txn is under a pre-scheduled plan
                          (a "10b5-1" sale is mechanical, not signal)
      - `is_derivative` — option exercises / awards vs open-market trades
      - `ownership_form` — 'D' (direct) / 'I' (indirect — through trust etc.)

    Returns rows {filing_date, insider, action, plan_10b5_1,
    is_derivative, ownership_form, url}. Merged onto existing
    insider_transactions rows via `db.enrich_insider_transactions`.

    Defensive: never raises. SEC has a Fair Access bot rule — we sleep
    250ms between filings to stay polite."""
    cik = _load_cik_map().get(ticker.upper())
    if not cik:
        return []
    # Find the most recent Form 4 filings for the issuer.
    try:
        resp = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        recent = resp.json().get("filings", {}).get("recent", {})
    except Exception:
        return []

    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accs = recent.get("accessionNumber", [])
    docs = recent.get("primaryDocument", [])

    out: list = []
    import time as _t
    pulled = 0
    for i, form in enumerate(forms):
        if pulled >= limit:
            break
        if form != "4":
            continue
        accession = accs[i] if i < len(accs) else ""
        doc = docs[i] if i < len(docs) else ""
        if not accession or not doc:
            continue
        filing_date = dates[i] if i < len(dates) else ""
        acc_nodash = accession.replace("-", "")
        # The primary doc on a Form 4 is HTML; the underlying XML lives
        # alongside it as `xslF345X<version>/<file>.xml` or similar.
        # We pull the folder index and grep for the .xml.
        folder_url = (f"https://www.sec.gov/Archives/edgar/data/"
                      f"{int(cik)}/{acc_nodash}/")
        try:
            idx = requests.get(folder_url, headers=_HEADERS, timeout=10)
            if idx.status_code != 200:
                continue
            xml_files = re.findall(
                r'href="([^"]+\.xml)"', idx.text, flags=re.IGNORECASE
            )
            # Skip the SEC's XSLT wrappers (they end in xslF345X*.xml as
            # directories not files — the actual XML is a sibling).
            xml_files = [
                f for f in xml_files
                if "xslf345x" not in f.lower() and not f.endswith("/")
            ]
            if not xml_files:
                continue
            xml_href = xml_files[0]
            if xml_href.startswith("/"):
                xml_url = "https://www.sec.gov" + xml_href
            elif xml_href.startswith("http"):
                xml_url = xml_href
            else:
                xml_url = folder_url + xml_href
            xr = requests.get(xml_url, headers=_HEADERS, timeout=15)
            if xr.status_code != 200:
                continue
            xml = xr.text
        except Exception:
            continue
        pulled += 1
        _t.sleep(0.25)

        # Strip namespaces for tractable regex.
        xml = re.sub(r"<\w+:", "<", xml)
        xml = re.sub(r"</\w+:", "</", xml)

        # Reporter (insider) name.
        name_m = re.search(
            r"<rptOwnerName>(.*?)</rptOwnerName>", xml,
            flags=re.DOTALL | re.IGNORECASE,
        )
        insider = (name_m.group(1).strip() if name_m else "").strip()
        if not insider:
            continue

        # Plan 10b5-1 flag.
        plan = bool(re.search(
            r"<aff10b5One>\s*(1|true)\s*</aff10b5One>", xml,
            flags=re.IGNORECASE,
        ))
        # Footnote-encoded 10b5-1 mentions (companies often disclose
        # the plan via a footnote rather than the structured field).
        if not plan:
            plan = bool(re.search(r"10b5-?1", xml, flags=re.IGNORECASE))

        # Derivative section presence.
        is_derivative = bool(re.search(
            r"<derivativeTable>.*<transactionAcquiredDisposedCode>",
            xml, flags=re.DOTALL | re.IGNORECASE,
        ))

        # Ownership form (D / I) — first occurrence wins; rows with
        # mixed direct+indirect get tagged with whichever appears first.
        own_m = re.search(
            r"<directOrIndirectOwnership>\s*<value>\s*([DI])\s*</value>",
            xml, flags=re.DOTALL | re.IGNORECASE,
        )
        ownership_form = own_m.group(1).upper() if own_m else None

        # Action code (P/S/A/etc).
        action_m = re.search(
            r"<transactionCode>\s*([A-Z])\s*</transactionCode>", xml,
            flags=re.IGNORECASE,
        )
        action = action_m.group(1).upper() if action_m else None

        out.append({
            "filing_date": filing_date,
            "insider": insider,
            "action": action,
            "plan_10b5_1": plan,
            "is_derivative": is_derivative,
            "ownership_form": ownership_form,
            "url": xml_url,
        })
    return out


def fetch_13f_positions(ticker: str, holder_ciks: list = None,
                        limit_holders: int = 25) -> list:
    """Pull recent 13F positions in `ticker` from a set of known
    institutional holders.

    Because EDGAR doesn't expose a "show me all holders of $TICKER"
    endpoint, the caller passes in a list of holder CIKs to scan. The
    default list (held in settings.yaml under
    `edgar.thirteenf_holders`) ships with the biggest brand-name
    institutional managers — Vanguard, BlackRock, State Street, Fidelity,
    Capital Research, etc. Add the ones that matter to your strategy.

    Each return row: {holder_cik, holder_name, period_end, shares,
    value}. Never raises.
    """
    issuer = _company_name_for_ticker(ticker)
    if not issuer:
        return []
    if not holder_ciks:
        holder_ciks = setting("edgar.thirteenf_holders", []) or []
    if not holder_ciks:
        return []

    out: list = []
    seen = set()
    for raw_cik in holder_ciks[:limit_holders]:
        cik = str(raw_cik).zfill(10)
        for filing in _recent_13f_accessions(cik, limit=1):
            xml = _fetch_13f_infotable(cik, filing["accession"])
            if not xml:
                continue
            positions = _parse_infotable_positions(xml, issuer)
            if not positions:
                continue
            # Aggregate multiple lines (different share classes etc.)
            # under the same holder.
            total_shares = sum(p.get("shares") or 0 for p in positions)
            total_value = sum(p.get("value") or 0 for p in positions)
            # holder_name is the *holder's* entity name (Vanguard,
            # BlackRock...), NOT the issuer name from the position row.
            holder_name = _company_name_for_cik(cik) or cik
            key = (cik, filing["period_end"])
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "holder_cik": cik,
                "holder_name": holder_name,
                "period_end": filing["period_end"],
                "shares": total_shares or None,
                "value": total_value or None,
            })
    return out
