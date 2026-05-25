"""SQLite storage for FIRE snapshots, earnings, filings and sentiment.

Storing a daily snapshot is what lets the tool detect *changes* over time
(valuation drifting, sentiment shifting). The longer it runs, the better.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta

from .config import (DB_PATH, DEFAULT_LIST, LISTS, STAGE_TO_LIST,
                     initial_lists)

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    name TEXT,
    price REAL,
    prev_close REAL,
    market_cap REAL,
    trailing_pe REAL,
    forward_pe REAL,
    price_to_sales REAL,
    price_to_book REAL,
    peg REAL,
    ev_to_ebitda REAL,
    profit_margin REAL,
    revenue_growth REAL,
    week52_high REAL,
    week52_low REAL,
    fifty_day_avg REAL,
    two_hundred_day_avg REAL,
    PRIMARY KEY (ticker, date)
);

CREATE TABLE IF NOT EXISTS earnings (
    ticker TEXT NOT NULL,
    earnings_date TEXT NOT NULL,
    eps_estimate REAL,
    eps_actual REAL,
    surprise_pct REAL,
    recorded_at TEXT,
    PRIMARY KEY (ticker, earnings_date)
);

CREATE TABLE IF NOT EXISTS filings (
    ticker TEXT NOT NULL,
    accession TEXT NOT NULL,
    form TEXT,
    filing_date TEXT,
    title TEXT,
    url TEXT,
    recorded_at TEXT,
    PRIMARY KEY (ticker, accession)
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS watchlist_meta (
    ticker TEXT PRIMARY KEY,
    list TEXT NOT NULL,
    note TEXT,
    added_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS sentiment_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,
    external_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    author TEXT,
    weight REAL,
    url TEXT,
    text TEXT NOT NULL,
    tone REAL,
    scorer TEXT,
    UNIQUE (source, external_id)
);
CREATE INDEX IF NOT EXISTS idx_sent_posts_ticker_time
    ON sentiment_posts(ticker, created_at);

CREATE TABLE IF NOT EXISTS sentiment_daily (
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,
    day TEXT NOT NULL,
    n INTEGER NOT NULL,
    tone_mean REAL,
    tone_vol_weighted REAL,
    PRIMARY KEY (ticker, source, day)
);

CREATE TABLE IF NOT EXISTS financial_lines (
    ticker TEXT NOT NULL,
    period_end TEXT NOT NULL,
    period_type TEXT NOT NULL,        -- 'annual' or 'quarterly'
    statement TEXT NOT NULL,          -- 'income' | 'balance' | 'cashflow'
    metric TEXT NOT NULL,
    value REAL,
    fetched_at TEXT,
    PRIMARY KEY (ticker, period_end, period_type, statement, metric)
);
CREATE INDEX IF NOT EXISTS idx_finlines_ticker
    ON financial_lines(ticker, statement, period_type, period_end);

CREATE TABLE IF NOT EXISTS thesis_notes (
    ticker TEXT PRIMARY KEY,
    content TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS deep_extras (
    ticker TEXT NOT NULL,
    kind TEXT NOT NULL,               -- 'institutional_holders' | 'recommendations' | ...
    content TEXT,                     -- JSON
    fetched_at TEXT,
    PRIMARY KEY (ticker, kind)
);

CREATE TABLE IF NOT EXISTS claude_cache (
    cache_key TEXT PRIMARY KEY,
    ticker TEXT,
    kind TEXT,
    prompt_hash TEXT,
    content_hash TEXT,
    strategy_hash TEXT,
    response_json TEXT,
    cost_usd REAL,
    latency_ms INTEGER,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_claude_cache_ticker
    ON claude_cache(ticker, kind);

CREATE TABLE IF NOT EXISTS peer_percentiles (
    ticker TEXT NOT NULL,
    cohort TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL,
    percentile REAL,
    cohort_median REAL,
    cohort_n INTEGER,
    computed_at TEXT,
    PRIMARY KEY (ticker, cohort, metric)
);

-- Phase 2.6 — extra free data sources -------------------------------------

-- Historical valuation ratios scraped from stockanalysis.com (period_end
-- is the fiscal-period date; one row per ratio per period).
CREATE TABLE IF NOT EXISTS valuation_history (
    ticker TEXT NOT NULL,
    period_end TEXT NOT NULL,
    pb REAL,
    ps REAL,
    pe REAL,
    fetched_at TEXT,
    PRIMARY KEY (ticker, period_end)
);

-- Insider buys / sells from OpenInsider. We dedupe on the natural key
-- (ticker, filing_date, insider, txn_date, shares) since the same row
-- can appear on multiple pages.
CREATE TABLE IF NOT EXISTS insider_transactions (
    ticker TEXT NOT NULL,
    filing_date TEXT,
    txn_date TEXT,
    insider TEXT,
    role TEXT,
    action TEXT,       -- 'P' (purchase), 'S' (sale), 'A' (award), etc.
    shares REAL,
    price REAL,
    value REAL,        -- USD notional
    url TEXT,
    fetched_at TEXT,
    PRIMARY KEY (ticker, filing_date, insider, txn_date, shares)
);
CREATE INDEX IF NOT EXISTS idx_insider_ticker_date
    ON insider_transactions(ticker, filing_date);

-- Institutional positions reconstructed from 13F filings. One row per
-- (ticker, holder, period_end). We only keep the latest few periods so
-- the table stays small.
CREATE TABLE IF NOT EXISTS institutional_holdings (
    ticker TEXT NOT NULL,
    holder_cik TEXT NOT NULL,
    holder_name TEXT,
    period_end TEXT NOT NULL,
    shares REAL,
    value REAL,        -- USD as of period_end
    fetched_at TEXT,
    PRIMARY KEY (ticker, holder_cik, period_end)
);
CREATE INDEX IF NOT EXISTS idx_inst_ticker_period
    ON institutional_holdings(ticker, period_end);

-- Earnings call transcripts (Motley Fool / Yahoo). Body is trimmed
-- before storage to keep the table small — full transcripts are
-- 50-100KB each and we don't need the whole prepared script.
CREATE TABLE IF NOT EXISTS transcripts (
    ticker TEXT NOT NULL,
    call_date TEXT NOT NULL,         -- earnings call date (YYYY-MM-DD)
    period TEXT,                     -- "Q1 2026", "FY 2025", etc.
    source TEXT NOT NULL,            -- 'fool' | 'yahoo'
    url TEXT,
    body TEXT,                       -- trimmed prepared remarks + Q&A snippets
    body_len INTEGER,
    fetched_at TEXT,
    PRIMARY KEY (ticker, call_date)
);
CREATE INDEX IF NOT EXISTS idx_transcripts_ticker_date
    ON transcripts(ticker, call_date DESC);

-- Activist filings (SC 13D / 13G + amendments). 13D = activist intent;
-- 13G = passive 5%+ stake. We persist both because both move stocks.
CREATE TABLE IF NOT EXISTS activist_filings (
    ticker TEXT NOT NULL,
    filer_cik TEXT NOT NULL,
    filer_name TEXT,
    form TEXT NOT NULL,              -- 'SC 13D' | 'SC 13G' | 'SC 13D/A' | 'SC 13G/A'
    accession TEXT NOT NULL,
    filing_date TEXT,
    pct_owned REAL,                  -- aggregate % owned per cover page
    url TEXT,
    fetched_at TEXT,
    PRIMARY KEY (ticker, filer_cik, accession)
);
CREATE INDEX IF NOT EXISTS idx_activist_ticker_date
    ON activist_filings(ticker, filing_date DESC);

-- Cached EDGAR full-text search results. Lets a theme search ("HBM4",
-- "co-packaged optics") show up instantly next time without re-hitting
-- the EDGAR API. We re-query whenever the user explicitly refreshes.
CREATE TABLE IF NOT EXISTS edgar_search_hits (
    query TEXT NOT NULL,
    ticker TEXT,
    cik TEXT,
    accession TEXT NOT NULL,
    form TEXT,
    filing_date TEXT,
    company TEXT,
    snippet TEXT,
    url TEXT,
    fetched_at TEXT,
    PRIMARY KEY (query, accession)
);
CREATE INDEX IF NOT EXISTS idx_edgar_search_query
    ON edgar_search_hits(query, filing_date DESC);
"""

# Columns written by save_snapshot, in order (ticker + date are added separately).
SNAPSHOT_COLS = [
    "name", "price", "prev_close", "market_cap", "trailing_pe", "forward_pe",
    "price_to_sales", "price_to_book", "peg", "ev_to_ebitda", "profit_margin",
    "revenue_growth", "week52_high", "week52_low", "fifty_day_avg",
    "two_hundred_day_avg",
]


@contextmanager
def connect():
    """Context-managed SQLite connection; commits on clean exit.

    WAL mode is set once at init_db() and persists in the file header;
    busy_timeout is per-connection. Together they let the dashboard read
    while the collector is writing, instead of erroring on a held lock.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout=30000")
    except sqlite3.OperationalError:
        pass
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with connect() as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        _migrate_watchlist_meta(conn)
        conn.executescript(SCHEMA)
        _migrate_insider_form4_columns(conn)
        _seed_lists(conn)


def _migrate_insider_form4_columns(conn):
    """Phase 2.7 — add Form-4-derived columns to insider_transactions.

    The OpenInsider adapter populated the original columns; Form 4 XML
    parsing adds 10b5-1 (pre-scheduled plan), is_derivative (option
    exercise vs open-market), and ownership_form (D=direct/I=indirect).
    Idempotent: skips if columns already exist."""
    cols = _table_columns(conn, "insider_transactions")
    if not cols:
        return
    if "plan_10b5_1" not in cols:
        conn.execute(
            "ALTER TABLE insider_transactions ADD COLUMN plan_10b5_1 INTEGER"
        )
    if "is_derivative" not in cols:
        conn.execute(
            "ALTER TABLE insider_transactions ADD COLUMN is_derivative INTEGER"
        )
    if "ownership_form" not in cols:
        conn.execute(
            "ALTER TABLE insider_transactions ADD COLUMN ownership_form TEXT"
        )


def _table_columns(conn, table: str) -> set:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate_watchlist_meta(conn):
    """Move legacy `stage` column to `list`; drop `passed` rows.

    Idempotent: skips if `watchlist_meta` doesn't exist (fresh install) or
    already has a `list` column.
    """
    exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' "
        "AND name='watchlist_meta'"
    ).fetchone()
    if not exists:
        return
    cols = _table_columns(conn, "watchlist_meta")
    if "list" in cols:
        return
    if "stage" not in cols:
        return  # malformed; let CREATE IF NOT EXISTS handle it

    # Build the new shape and copy rows, translating stage→list and
    # dropping 'passed' rows along the way.
    conn.execute("""
        CREATE TABLE watchlist_meta_new (
            ticker TEXT PRIMARY KEY,
            list TEXT NOT NULL,
            note TEXT,
            added_at TEXT,
            updated_at TEXT
        )
    """)
    rows = conn.execute(
        "SELECT ticker, stage, note, added_at, updated_at FROM watchlist_meta"
    ).fetchall()
    for r in rows:
        stage = (r["stage"] or "").lower()
        if stage == "passed":
            continue
        lst = STAGE_TO_LIST.get(stage, DEFAULT_LIST)
        conn.execute(
            "INSERT OR REPLACE INTO watchlist_meta_new "
            "(ticker, list, note, added_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (r["ticker"], lst, r["note"], r["added_at"], r["updated_at"]),
        )
    conn.execute("DROP TABLE watchlist_meta")
    conn.execute("ALTER TABLE watchlist_meta_new RENAME TO watchlist_meta")


def _seed_lists(conn):
    """Insert any first-time list hints from watchlist.yaml. Never
    overwrites a row that already exists — once the user edits a list
    in the UI, the DB is the source of truth."""
    hints = initial_lists()
    if not hints:
        return
    existing = conn.execute(
        "SELECT COUNT(*) AS c FROM watchlist_meta"
    ).fetchone()
    if existing and existing["c"] >= len(hints):
        return
    now = datetime.now().isoformat(timespec="seconds")
    for ticker, lst in hints.items():
        conn.execute(
            "INSERT OR IGNORE INTO watchlist_meta "
            "(ticker, list, added_at, updated_at) VALUES (?, ?, ?, ?)",
            (ticker, lst, now, now),
        )


def save_snapshot(conn, snap: dict, on_date: str = None):
    on_date = on_date or date.today().isoformat()
    cols = ["ticker", "date"] + SNAPSHOT_COLS
    placeholders = ", ".join("?" for _ in cols)
    values = [snap.get("ticker"), on_date] + [snap.get(c) for c in SNAPSHOT_COLS]
    conn.execute(
        f"INSERT OR REPLACE INTO snapshots ({', '.join(cols)}) VALUES ({placeholders})",
        values,
    )


def save_earnings(conn, ticker: str, rows: list):
    now = datetime.now().isoformat(timespec="seconds")
    for r in rows:
        conn.execute(
            """INSERT OR REPLACE INTO earnings
               (ticker, earnings_date, eps_estimate, eps_actual, surprise_pct, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ticker, r.get("earnings_date"), r.get("eps_estimate"),
             r.get("eps_actual"), r.get("surprise_pct"), now),
        )


def save_filings(conn, ticker: str, rows: list):
    now = datetime.now().isoformat(timespec="seconds")
    for r in rows:
        conn.execute(
            """INSERT OR REPLACE INTO filings
               (ticker, accession, form, filing_date, title, url, recorded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ticker, r.get("accession"), r.get("form"), r.get("filing_date"),
             r.get("title"), r.get("url"), now),
        )


def set_meta(conn, key: str, value: str):
    conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)", (key, value))


def get_meta(conn, key: str, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def latest_snapshots(conn) -> list:
    """Most recent snapshot row for every ticker."""
    return conn.execute(
        """SELECT s.* FROM snapshots s
           JOIN (SELECT ticker, MAX(date) AS d FROM snapshots GROUP BY ticker) m
             ON s.ticker = m.ticker AND s.date = m.d
           ORDER BY s.ticker"""
    ).fetchall()


def snapshot_history(conn, ticker: str) -> list:
    return conn.execute(
        "SELECT * FROM snapshots WHERE ticker = ? ORDER BY date", (ticker,)
    ).fetchall()


def get_earnings(conn, ticker: str) -> list:
    return conn.execute(
        "SELECT * FROM earnings WHERE ticker = ? ORDER BY earnings_date DESC",
        (ticker,),
    ).fetchall()


def upcoming_earnings(conn, days: int = 14) -> list:
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=days)).isoformat()
    return conn.execute(
        """SELECT * FROM earnings
           WHERE earnings_date >= ? AND earnings_date <= ?
           ORDER BY earnings_date""",
        (today, horizon),
    ).fetchall()


def recent_surprises(conn, days: int = 30) -> list:
    since = (date.today() - timedelta(days=days)).isoformat()
    today = date.today().isoformat()
    return conn.execute(
        """SELECT * FROM earnings
           WHERE earnings_date >= ? AND earnings_date <= ?
             AND eps_actual IS NOT NULL
           ORDER BY earnings_date DESC""",
        (since, today),
    ).fetchall()


def get_filings(conn, ticker: str, limit: int = 10) -> list:
    return conn.execute(
        "SELECT * FROM filings WHERE ticker = ? ORDER BY filing_date DESC LIMIT ?",
        (ticker, limit),
    ).fetchall()


def recent_filings(conn, days: int = 7) -> list:
    since = (date.today() - timedelta(days=days)).isoformat()
    return conn.execute(
        "SELECT * FROM filings WHERE filing_date >= ? ORDER BY filing_date DESC",
        (since,),
    ).fetchall()


# --------------------------------------------------------------------------
# Lists (per-ticker workflow state: holding / shortlist / watchlist)
# --------------------------------------------------------------------------
def get_lists(conn) -> dict:
    """ticker -> list. Tickers without a row default to DEFAULT_LIST."""
    rows = conn.execute(
        "SELECT ticker, list FROM watchlist_meta"
    ).fetchall()
    return {r["ticker"]: r["list"] for r in rows}


def get_list(conn, ticker: str) -> str:
    row = conn.execute(
        "SELECT list FROM watchlist_meta WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    return row["list"] if row else DEFAULT_LIST


def is_on_list(conn, ticker: str) -> bool:
    """True iff the ticker has an explicit row in watchlist_meta.
    `get_list` returns DEFAULT_LIST as a fallback for unknown tickers —
    callers that need to distinguish 'actually on a list' vs 'just being
    researched' should use this."""
    row = conn.execute(
        "SELECT 1 FROM watchlist_meta WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    return row is not None


def set_list(conn, ticker: str, list_name: str):
    if list_name not in LISTS:
        raise ValueError(f"Unknown list: {list_name}")
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO watchlist_meta (ticker, list, added_at, updated_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(ticker) DO UPDATE SET list=excluded.list,
                                             updated_at=excluded.updated_at""",
        (ticker.upper(), list_name, now, now),
    )


def remove_ticker_meta(conn, ticker: str):
    conn.execute("DELETE FROM watchlist_meta WHERE ticker = ?",
                 (ticker.upper(),))


def bulk_set_list(conn, list_name: str, tickers: list = None):
    """Set every (or a given list of) ticker's list in one statement."""
    if list_name not in LISTS:
        raise ValueError(f"Unknown list: {list_name}")
    now = datetime.now().isoformat(timespec="seconds")
    if tickers:
        placeholders = ",".join("?" for _ in tickers)
        conn.execute(
            f"UPDATE watchlist_meta SET list = ?, updated_at = ? "
            f"WHERE ticker IN ({placeholders})",
            [list_name, now, *[t.upper() for t in tickers]],
        )
    else:
        conn.execute(
            "UPDATE watchlist_meta SET list = ?, updated_at = ?",
            (list_name, now),
        )


def list_counts(conn) -> dict:
    """Map of list_name -> count of tickers currently on that list."""
    counts = {k: 0 for k in LISTS}
    rows = conn.execute(
        "SELECT list, COUNT(*) AS c FROM watchlist_meta GROUP BY list"
    ).fetchall()
    for r in rows:
        if r["list"] in counts:
            counts[r["list"]] = r["c"]
    return counts


def clear_watchlist_meta(conn):
    """Drop every row in watchlist_meta. Snapshots/sentiment stay so
    re-adding a ticker keeps its history."""
    conn.execute("DELETE FROM watchlist_meta")


# --------------------------------------------------------------------------
# Sentiment — raw posts + daily aggregates
# --------------------------------------------------------------------------
def save_sentiment_posts(conn, posts: list) -> int:
    """Insert posts, deduping by (source, external_id). Returns new-row count."""
    if not posts:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for p in posts:
        try:
            cur = conn.execute(
                """INSERT OR IGNORE INTO sentiment_posts
                   (ticker, source, external_id, created_at, fetched_at,
                    author, weight, url, text, tone, scorer)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (p["ticker"].upper(), p["source"], str(p["external_id"]),
                 p["created_at"], now,
                 p.get("author"), p.get("weight", 1.0), p.get("url"),
                 p["text"], p.get("tone"), p.get("scorer")),
            )
            if cur.rowcount:
                n += 1
        except (KeyError, sqlite3.IntegrityError):
            continue
    return n


def recompute_sentiment_daily(conn, ticker: str = None, days: int = 35):
    """Refresh the per-day rollup over the last `days` days. If a ticker
    is given, only that ticker is recomputed; otherwise all tickers.

    tone_mean = weighted mean (by `weight`) of tone over posts that day.
    tone_vol_weighted = tone_mean * ln(1 + n). Lets a day with five
    aligned posts outweigh a day with one outlier.
    """
    import math
    since = (date.today() - timedelta(days=days)).isoformat()
    params: list = [since]
    where = "WHERE date(created_at) >= ? AND tone IS NOT NULL"
    if ticker:
        where += " AND ticker = ?"
        params.append(ticker.upper())
    rows = conn.execute(
        f"""SELECT ticker, source, date(created_at) AS day,
                   COUNT(*) AS n,
                   SUM(COALESCE(weight, 1.0) * tone) AS wsum,
                   SUM(COALESCE(weight, 1.0)) AS wtot
            FROM sentiment_posts {where}
            GROUP BY ticker, source, day""",
        params,
    ).fetchall()

    if ticker:
        conn.execute(
            "DELETE FROM sentiment_daily WHERE ticker = ? AND day >= ?",
            (ticker.upper(), since),
        )
    else:
        conn.execute(
            "DELETE FROM sentiment_daily WHERE day >= ?", (since,)
        )

    for r in rows:
        mean = r["wsum"] / r["wtot"] if r["wtot"] else None
        vol = mean * math.log(1 + r["n"]) if mean is not None else None
        conn.execute(
            """INSERT INTO sentiment_daily
               (ticker, source, day, n, tone_mean, tone_vol_weighted)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (r["ticker"], r["source"], r["day"], r["n"], mean, vol),
        )


def sentiment_daily(conn, ticker: str, days: int = 30) -> list:
    """Daily aggregate rows for a ticker over the last `days` days."""
    since = (date.today() - timedelta(days=days)).isoformat()
    return conn.execute(
        """SELECT * FROM sentiment_daily
           WHERE ticker = ? AND day >= ?
           ORDER BY source, day""",
        (ticker.upper(), since),
    ).fetchall()


def recent_sentiment_posts(conn, ticker: str, days: int = 3,
                           limit: int = 10) -> list:
    """Most recent scored posts for a ticker — used to show the
    headlines driving a sentiment shift."""
    since = (date.today() - timedelta(days=days)).isoformat()
    return conn.execute(
        """SELECT * FROM sentiment_posts
           WHERE ticker = ? AND date(created_at) >= ?
             AND tone IS NOT NULL
           ORDER BY created_at DESC LIMIT ?""",
        (ticker.upper(), since, limit),
    ).fetchall()


# --------------------------------------------------------------------------
# Deep research — financial statements (long-form) and thesis notes
# --------------------------------------------------------------------------
def save_financial_lines(conn, ticker: str, period_type: str,
                         statement: str, rows: list) -> int:
    """Upsert long-form financial rows."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        try:
            conn.execute(
                """INSERT INTO financial_lines
                   (ticker, period_end, period_type, statement,
                    metric, value, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, period_end, period_type, statement, metric)
                   DO UPDATE SET value = excluded.value,
                                 fetched_at = excluded.fetched_at""",
                (ticker.upper(), r["period_end"], period_type, statement,
                 r["metric"], r.get("value"), now),
            )
            n += 1
        except (KeyError, sqlite3.IntegrityError):
            continue
    return n


def get_financial_lines(conn, ticker: str, statement: str = None,
                        period_type: str = "annual") -> list:
    """Return rows for a ticker, optionally scoped to one statement."""
    where = "WHERE ticker = ? AND period_type = ?"
    params: list = [ticker.upper(), period_type]
    if statement:
        where += " AND statement = ?"
        params.append(statement)
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM financial_lines {where} "
        f"ORDER BY statement, period_end DESC, metric",
        params,
    ).fetchall()]


def financial_freshness(conn, ticker: str) -> str:
    """Latest fetched_at across all financial lines for a ticker, or None."""
    row = conn.execute(
        "SELECT MAX(fetched_at) AS f FROM financial_lines WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    return row["f"] if row else None


def get_thesis_note(conn, ticker: str) -> dict:
    row = conn.execute(
        "SELECT * FROM thesis_notes WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    return dict(row) if row else {"ticker": ticker.upper(), "content": "",
                                  "updated_at": None}


def save_thesis_note(conn, ticker: str, content: str):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO thesis_notes (ticker, content, updated_at)
           VALUES (?, ?, ?)
           ON CONFLICT(ticker) DO UPDATE SET content = excluded.content,
                                             updated_at = excluded.updated_at""",
        (ticker.upper(), content, now),
    )


def save_deep_extra(conn, ticker: str, kind: str, content: str):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT INTO deep_extras (ticker, kind, content, fetched_at)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(ticker, kind) DO UPDATE SET content = excluded.content,
                                                    fetched_at = excluded.fetched_at""",
        (ticker.upper(), kind, content, now),
    )


def get_deep_extras(conn, ticker: str) -> dict:
    rows = conn.execute(
        "SELECT * FROM deep_extras WHERE ticker = ?", (ticker.upper(),)
    ).fetchall()
    return {r["kind"]: dict(r) for r in rows}


def snapshot_freshness(conn, ticker: str) -> str:
    row = conn.execute(
        "SELECT MAX(date) AS d FROM snapshots WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    return row["d"] if row else None


def sentiment_shifts(conn, baseline_days: int = 30, current_days: int = 3,
                     abs_floor: float = 0.15,
                     std_factor: float = 0.5) -> list:
    """Per-ticker combined shift across sources."""
    import math
    today = date.today()
    cur_since = (today - timedelta(days=current_days)).isoformat()
    base_since = (today - timedelta(days=baseline_days)).isoformat()
    base_until = cur_since

    cur_raw = conn.execute(
        """SELECT ticker, n, tone_mean
           FROM sentiment_daily
           WHERE day >= ? AND tone_mean IS NOT NULL""",
        (cur_since,),
    ).fetchall()

    cur_acc: dict = {}
    for r in cur_raw:
        w = math.log(1.0 + (r["n"] or 0))
        a = cur_acc.setdefault(r["ticker"],
                               {"wsum": 0.0, "wtot": 0.0, "n": 0})
        a["wsum"] += w * r["tone_mean"]
        a["wtot"] += w
        a["n"] += r["n"] or 0
    cur_rows = [dict(ticker=t, **v) for t, v in cur_acc.items()]

    base_rows = conn.execute(
        """SELECT ticker, tone_mean
           FROM sentiment_daily
           WHERE day >= ? AND day < ?""",
        (base_since, base_until),
    ).fetchall()

    base_by_t: dict = {}
    for r in base_rows:
        if r["tone_mean"] is None:
            continue
        base_by_t.setdefault(r["ticker"], []).append(r["tone_mean"])

    out = []
    for c in cur_rows:
        t = c["ticker"]
        if not c["wtot"]:
            continue
        current = c["wsum"] / c["wtot"]
        means = base_by_t.get(t, [])
        if not means:
            baseline = None
            std = None
            shift = None
            meaningful = False
        else:
            baseline = sum(means) / len(means)
            if len(means) > 1:
                m = baseline
                var = sum((x - m) ** 2 for x in means) / (len(means) - 1)
                std = math.sqrt(var)
            else:
                std = 0.0
            shift = current - baseline
            threshold = max(abs_floor, std_factor * std)
            meaningful = abs(shift) > threshold
        out.append({
            "ticker": t,
            "current_mean": current,
            "baseline_mean": baseline,
            "baseline_std": std,
            "shift": shift,
            "n_current": c["n"],
            "meaningful": meaningful,
        })
    return sorted(out, key=lambda r: abs(r.get("shift") or 0), reverse=True)


# --------------------------------------------------------------------------
# Claude CLI cache
# --------------------------------------------------------------------------
def get_claude_cache(conn, cache_key: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM claude_cache WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    return dict(row) if row else None


def save_claude_cache(conn, cache_key: str, ticker: str, kind: str,
                      prompt_hash: str, content_hash: str,
                      strategy_hash: str, response_json: str,
                      cost_usd: float | None,
                      latency_ms: int | None):
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """INSERT OR REPLACE INTO claude_cache
           (cache_key, ticker, kind, prompt_hash, content_hash,
            strategy_hash, response_json, cost_usd, latency_ms, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (cache_key, ticker, kind, prompt_hash, content_hash,
         strategy_hash, response_json, cost_usd, latency_ms, now),
    )


def recent_claude_activity(conn, ticker: str = None, limit: int = 8) -> list:
    where = ""
    params: list = []
    if ticker:
        where = "WHERE ticker = ?"
        params.append(ticker.upper())
    rows = conn.execute(
        f"""SELECT ticker, kind, created_at, cost_usd, latency_ms
            FROM claude_cache {where}
            ORDER BY created_at DESC LIMIT ?""",
        params + [limit],
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Valuation history (Stockanalysis.com scrape)
# --------------------------------------------------------------------------
def save_valuation_history(conn, ticker: str, rows: list) -> int:
    """Upsert P/B, P/S, P/E history rows. Each row: {period_end, pb, ps, pe}."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        try:
            conn.execute(
                """INSERT INTO valuation_history
                   (ticker, period_end, pb, ps, pe, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, period_end) DO UPDATE SET
                     pb = excluded.pb, ps = excluded.ps, pe = excluded.pe,
                     fetched_at = excluded.fetched_at""",
                (ticker.upper(), r["period_end"], r.get("pb"),
                 r.get("ps"), r.get("pe"), now),
            )
            n += 1
        except (KeyError, sqlite3.IntegrityError):
            continue
    return n


def get_valuation_history(conn, ticker: str, limit: int = 12) -> list:
    """Most recent N annual periods of P/B, P/S, P/E for a ticker."""
    rows = conn.execute(
        """SELECT * FROM valuation_history
           WHERE ticker = ? ORDER BY period_end DESC LIMIT ?""",
        (ticker.upper(), limit),
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Insider transactions (OpenInsider scrape)
# --------------------------------------------------------------------------
def save_insider_transactions(conn, ticker: str, rows: list) -> int:
    """Upsert insider rows. Each row: {filing_date, txn_date, insider,
    role, action, shares, price, value, url}."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        try:
            conn.execute(
                """INSERT OR IGNORE INTO insider_transactions
                   (ticker, filing_date, txn_date, insider, role, action,
                    shares, price, value, url, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (ticker.upper(), r.get("filing_date"), r.get("txn_date"),
                 r.get("insider"), r.get("role"), r.get("action"),
                 r.get("shares"), r.get("price"), r.get("value"),
                 r.get("url"), now),
            )
            n += 1
        except sqlite3.IntegrityError:
            continue
    return n


def get_insider_transactions(conn, ticker: str, days: int = 180,
                             limit: int = 20) -> list:
    """Recent insider transactions for a ticker, newest first."""
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT * FROM insider_transactions
           WHERE ticker = ? AND filing_date >= ?
           ORDER BY filing_date DESC LIMIT ?""",
        (ticker.upper(), since, limit),
    ).fetchall()
    return [dict(r) for r in rows]


def insider_summary(conn, ticker: str, days: int = 180) -> dict:
    """Aggregate buy/sell pressure over the last `days` days. Useful for
    a single 'insiders bought $X net' card.

    OpenInsider returns sale values as negatives (parenthesised in the
    source HTML); we sum ABS(value) so the buy/sell totals are both
    positive magnitudes, and the action field carries direction."""
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT action, COALESCE(SUM(ABS(value)), 0) AS sum_value,
                  COUNT(*) AS n
           FROM insider_transactions
           WHERE ticker = ? AND filing_date >= ?
           GROUP BY action""",
        (ticker.upper(), since),
    ).fetchall()
    out = {"buy_value": 0.0, "sell_value": 0.0, "buy_n": 0, "sell_n": 0}
    for r in rows:
        act = (r["action"] or "").upper()
        if act.startswith("P"):    # purchase
            out["buy_value"] += r["sum_value"] or 0.0
            out["buy_n"] += r["n"]
        elif act.startswith("S"):  # sale
            out["sell_value"] += r["sum_value"] or 0.0
            out["sell_n"] += r["n"]
    out["net_value"] = out["buy_value"] - out["sell_value"]
    return out


# --------------------------------------------------------------------------
# Institutional holdings (13F aggregation)
# --------------------------------------------------------------------------
def save_institutional_holdings(conn, ticker: str, rows: list) -> int:
    """Upsert institutional holdings rows. Each row: {holder_cik,
    holder_name, period_end, shares, value}."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        try:
            conn.execute(
                """INSERT INTO institutional_holdings
                   (ticker, holder_cik, holder_name, period_end, shares,
                    value, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, holder_cik, period_end) DO UPDATE SET
                     holder_name = excluded.holder_name,
                     shares = excluded.shares,
                     value = excluded.value,
                     fetched_at = excluded.fetched_at""",
                (ticker.upper(), str(r["holder_cik"]), r.get("holder_name"),
                 r["period_end"], r.get("shares"), r.get("value"), now),
            )
            n += 1
        except (KeyError, sqlite3.IntegrityError):
            continue
    return n


def get_institutional_holdings(conn, ticker: str, limit: int = 15) -> list:
    """Top institutional holders for a ticker, latest period, by value."""
    # Find latest period first.
    latest = conn.execute(
        """SELECT MAX(period_end) AS p FROM institutional_holdings
           WHERE ticker = ?""",
        (ticker.upper(),),
    ).fetchone()
    if not latest or not latest["p"]:
        return []
    rows = conn.execute(
        """SELECT * FROM institutional_holdings
           WHERE ticker = ? AND period_end = ?
           ORDER BY COALESCE(value, 0) DESC LIMIT ?""",
        (ticker.upper(), latest["p"], limit),
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Earnings call transcripts
# --------------------------------------------------------------------------
def save_transcripts(conn, ticker: str, rows: list) -> int:
    """Upsert transcript rows. Each row: {call_date, period, source,
    url, body}. body is trimmed before storage by the adapter."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        try:
            body = r.get("body") or ""
            conn.execute(
                """INSERT INTO transcripts
                   (ticker, call_date, period, source, url, body,
                    body_len, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, call_date) DO UPDATE SET
                     period = excluded.period,
                     source = excluded.source,
                     url = excluded.url,
                     body = excluded.body,
                     body_len = excluded.body_len,
                     fetched_at = excluded.fetched_at""",
                (ticker.upper(), r["call_date"], r.get("period"),
                 r.get("source") or "fool", r.get("url"), body,
                 len(body), now),
            )
            n += 1
        except (KeyError, sqlite3.IntegrityError):
            continue
    return n


def get_transcripts(conn, ticker: str, limit: int = 3) -> list:
    """Most recent N call transcripts for a ticker."""
    rows = conn.execute(
        """SELECT * FROM transcripts
           WHERE ticker = ? ORDER BY call_date DESC LIMIT ?""",
        (ticker.upper(), limit),
    ).fetchall()
    return [dict(r) for r in rows]


def latest_transcript_date(conn, ticker: str) -> str | None:
    """Most recent call_date for a ticker, or None. Used by the
    transcripts adapter to skip already-fetched calls."""
    row = conn.execute(
        "SELECT MAX(call_date) AS d FROM transcripts WHERE ticker = ?",
        (ticker.upper(),),
    ).fetchone()
    return row["d"] if row and row["d"] else None


# --------------------------------------------------------------------------
# Activist filings (SC 13D / 13G)
# --------------------------------------------------------------------------
def save_activist_filings(conn, ticker: str, rows: list) -> int:
    """Upsert activist filings. Each row: {filer_cik, filer_name, form,
    accession, filing_date, pct_owned, url}."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        try:
            conn.execute(
                """INSERT INTO activist_filings
                   (ticker, filer_cik, filer_name, form, accession,
                    filing_date, pct_owned, url, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(ticker, filer_cik, accession) DO UPDATE SET
                     filer_name = excluded.filer_name,
                     form = excluded.form,
                     filing_date = excluded.filing_date,
                     pct_owned = excluded.pct_owned,
                     url = excluded.url,
                     fetched_at = excluded.fetched_at""",
                (ticker.upper(), str(r["filer_cik"]),
                 r.get("filer_name"), r["form"], r["accession"],
                 r.get("filing_date"), r.get("pct_owned"),
                 r.get("url"), now),
            )
            n += 1
        except (KeyError, sqlite3.IntegrityError):
            continue
    return n


def get_activist_filings(conn, ticker: str, days: int = 365,
                         limit: int = 10) -> list:
    """Recent activist filings for a ticker, newest first."""
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT * FROM activist_filings
           WHERE ticker = ? AND filing_date >= ?
           ORDER BY filing_date DESC LIMIT ?""",
        (ticker.upper(), since, limit),
    ).fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Form 4 XML enrichment — merges plan_10b5_1/is_derivative/ownership_form
# onto existing insider_transactions rows by (filing_date, insider).
# --------------------------------------------------------------------------
def enrich_insider_transactions(conn, ticker: str, rows: list) -> int:
    """Merge Form-4-derived flags onto existing insider rows. Matches by
    (ticker, filing_date, insider) — the OpenInsider rows already
    populate those three fields. Rows without an OpenInsider match are
    inserted as NEW rows so we don't lose data."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    for r in rows:
        try:
            # Try UPDATE first (the common case — OpenInsider already
            # has the row).
            cur = conn.execute(
                """UPDATE insider_transactions
                   SET plan_10b5_1 = ?, is_derivative = ?,
                       ownership_form = ?, fetched_at = ?
                   WHERE ticker = ? AND filing_date = ? AND insider = ?""",
                (1 if r.get("plan_10b5_1") else 0,
                 1 if r.get("is_derivative") else 0,
                 r.get("ownership_form"), now,
                 ticker.upper(), r.get("filing_date"), r.get("insider")),
            )
            if cur.rowcount == 0:
                # No matching OpenInsider row — insert a new one with
                # whatever Form 4 gave us. Some discretionary fields will
                # be NULL but the action/insider/value triple is enough
                # to make the row useful downstream.
                conn.execute(
                    """INSERT OR IGNORE INTO insider_transactions
                       (ticker, filing_date, txn_date, insider, role,
                        action, shares, price, value, url, fetched_at,
                        plan_10b5_1, is_derivative, ownership_form)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (ticker.upper(), r.get("filing_date"),
                     r.get("txn_date"), r.get("insider"), r.get("role"),
                     r.get("action"), r.get("shares"), r.get("price"),
                     r.get("value"), r.get("url"), now,
                     1 if r.get("plan_10b5_1") else 0,
                     1 if r.get("is_derivative") else 0,
                     r.get("ownership_form")),
                )
            n += 1
        except sqlite3.Error:
            continue
    return n


def get_insider_form4_breakdown(conn, ticker: str, days: int = 180) -> dict:
    """Split insider activity into discretionary vs 10b5-1 vs derivative
    so the thesis prompt can flag the *signal* (discretionary) and
    discount the *noise* (10b5-1 pre-scheduled sales)."""
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT action, plan_10b5_1, is_derivative,
                  COALESCE(SUM(ABS(value)), 0) AS sum_value,
                  COUNT(*) AS n
           FROM insider_transactions
           WHERE ticker = ? AND filing_date >= ?
           GROUP BY action, plan_10b5_1, is_derivative""",
        (ticker.upper(), since),
    ).fetchall()
    out = {
        "discretionary_buy_value": 0.0, "discretionary_buy_n": 0,
        "discretionary_sell_value": 0.0, "discretionary_sell_n": 0,
        "plan_sell_value": 0.0, "plan_sell_n": 0,
        "derivative_value": 0.0, "derivative_n": 0,
    }
    for r in rows:
        act = (r["action"] or "").upper()
        is_plan = bool(r["plan_10b5_1"])
        is_deriv = bool(r["is_derivative"])
        v = r["sum_value"] or 0.0
        n = r["n"] or 0
        if is_deriv:
            out["derivative_value"] += v
            out["derivative_n"] += n
            continue
        if act.startswith("P"):
            out["discretionary_buy_value"] += v
            out["discretionary_buy_n"] += n
        elif act.startswith("S"):
            if is_plan:
                out["plan_sell_value"] += v
                out["plan_sell_n"] += n
            else:
                out["discretionary_sell_value"] += v
                out["discretionary_sell_n"] += n
    out["discretionary_net_value"] = (
        out["discretionary_buy_value"] - out["discretionary_sell_value"]
    )
    return out


# --------------------------------------------------------------------------
# EDGAR full-text search cache
# --------------------------------------------------------------------------
def save_edgar_search_hits(conn, query: str, rows: list) -> int:
    """Upsert search hits for a query. Each row: {ticker, cik, accession,
    form, filing_date, company, snippet, url}."""
    if not rows:
        return 0
    now = datetime.now().isoformat(timespec="seconds")
    n = 0
    q = query.strip()
    for r in rows:
        try:
            conn.execute(
                """INSERT INTO edgar_search_hits
                   (query, ticker, cik, accession, form, filing_date,
                    company, snippet, url, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(query, accession) DO UPDATE SET
                     ticker = excluded.ticker,
                     cik = excluded.cik,
                     form = excluded.form,
                     filing_date = excluded.filing_date,
                     company = excluded.company,
                     snippet = excluded.snippet,
                     url = excluded.url,
                     fetched_at = excluded.fetched_at""",
                (q, r.get("ticker"), r.get("cik"), r["accession"],
                 r.get("form"), r.get("filing_date"), r.get("company"),
                 r.get("snippet"), r.get("url"), now),
            )
            n += 1
        except (KeyError, sqlite3.IntegrityError):
            continue
    return n


def get_edgar_search_hits(conn, query: str, limit: int = 25) -> list:
    """Cached hits for an EDGAR full-text query, newest filings first."""
    rows = conn.execute(
        """SELECT * FROM edgar_search_hits
           WHERE query = ? ORDER BY filing_date DESC LIMIT ?""",
        (query.strip(), limit),
    ).fetchall()
    return [dict(r) for r in rows]
