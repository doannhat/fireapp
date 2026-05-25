"""Watchlist tab — 3-column list ladder with add-ticker + per-card picker.

Layout matches the v2 mockup's Watchlist view:

    [ Holding ]   [ Shortlist ]   [ Watchlist ]

Each cell stacks the tickers currently on that list as compact cards.
The header row above the ladder has an "Add ticker" input that:

  1. Appends the symbol to `watchlist.yaml` under the chosen layer.
  2. Writes the chosen list to `watchlist_meta` in SQLite.
  3. Fetches a one-shot snapshot so the Research tab has data when the
     user clicks through (no need to wait for the next collector run).

Clicking a ticker card switches the Research tab to that ticker via
`st.session_state["active_ticker"]`.
"""
from __future__ import annotations

import streamlit as st

from .. import db
from ..config import LIST_LABEL, LISTS, ticker_layers
from ..edgar import search_filings
from ..market import fetch_snapshot
from .list_picker import add_ticker as _add_ticker_shared
from .list_picker import render_list_picker


LIST_ACCENT_CLASS = {
    "holding":   "is-holding",
    "shortlist": "is-shortlist",
    "watchlist": "is-watchlist",
}


# --------------------------------------------------------------------------
# Cached snapshots — fast loads for the cards
# --------------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def _all_snapshots() -> dict:
    """Map of ticker → latest snapshot row. Hits SQLite, not yfinance."""
    with db.connect() as conn:
        rows = db.latest_snapshots(conn)
    return {r["ticker"]: dict(r) for r in rows}


# --------------------------------------------------------------------------
# Card renderer
# --------------------------------------------------------------------------
def _humanize_cap(v):
    if not v:
        return ""
    if v >= 1e12:
        return f"${v / 1e12:.2f}T"
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.0f}M"
    return f"${v:,.0f}"


def _render_card(ticker: str, list_name: str, snap: dict):
    """One compact card. Uses Streamlit columns to lay out: open button on
    the left, picker on the right, snapshot details in between."""
    accent = LIST_ACCENT_CLASS.get(list_name, "")
    price = snap.get("price")
    prev = snap.get("prev_close")
    day_chg = None
    if price and prev:
        day_chg = (price / prev - 1) * 100
    delta_cls = "up" if (day_chg or 0) >= 0 else "dn"
    delta_str = (
        f'<span class="delta-mini {delta_cls}">'
        f'{"▴" if (day_chg or 0) >= 0 else "▾"}{abs(day_chg):.1f}%</span>'
        if day_chg is not None else ""
    )
    mcap = _humanize_cap(snap.get("market_cap"))
    pe = snap.get("forward_pe") or snap.get("trailing_pe")
    pe_str = f"P/E {pe:.1f}" if pe else "P/E —"

    name = snap.get("name") or ticker
    name = name if len(name) <= 32 else name[:30] + "…"

    # Use a single Streamlit container per card with HTML for the body.
    with st.container(border=False):
        st.html(
            f"""
            <div class="watch-card {accent}">
              <div class="wc-top">
                <span class="wc-id">{ticker}</span>
                <span class="wc-list">{LIST_LABEL[list_name].upper()}</span>
              </div>
              <div class="wc-name">{name}</div>
              <div class="wc-price">
                {'$' + f'{price:,.2f}' if price else '—'} {delta_str}
              </div>
              <div class="wc-meta">{mcap} · {pe_str}</div>
            </div>
            """
        )
        action_cols = st.columns([2, 3])
        with action_cols[0]:
            if st.button("◇ open", key=f"open_{list_name}_{ticker}",
                         use_container_width=True):
                st.session_state["active_ticker"] = ticker
                # Best-effort: jump back to Research tab.
                st.session_state["_target_tab"] = "research"
                st.rerun()
        with action_cols[1]:
            render_list_picker(
                ticker,
                key_prefix=f"wl_picker_{list_name}",
            )


# --------------------------------------------------------------------------
# Refresh prices — lightweight per-ticker yfinance pull
# --------------------------------------------------------------------------
def _refresh_prices(tickers: list[str]) -> tuple[int, list[str]]:
    """Pull a fresh snapshot for each ticker and persist. Returns (ok, failed)."""
    ok = 0
    failed: list[str] = []
    progress = st.progress(0.0, text="Refreshing prices…")
    total = max(len(tickers), 1)
    with db.connect() as conn:
        for i, tk in enumerate(tickers, start=1):
            progress.progress(i / total, text=f"Refreshing {tk} ({i}/{total})")
            try:
                snap = fetch_snapshot(tk)
                if snap.get("price") is not None:
                    db.save_snapshot(conn, snap)
                    ok += 1
                else:
                    failed.append(tk)
            except Exception:
                failed.append(tk)
    progress.empty()
    return ok, failed


# --------------------------------------------------------------------------
# EDGAR theme search — discoverability for "who else talks about HBM4?"
# --------------------------------------------------------------------------
def _render_edgar_theme_search():
    """Compact full-text search across EDGAR filings. Lets the user
    type a theme ("HBM4", "co-packaged optics") and surface every
    company that's filed about it recently. Results cached in SQLite so
    a repeat lookup is instant; an explicit Refresh re-queries EDGAR."""
    st.html(
        '<div class="block-label" style="margin: 20px 0 8px; '
        'padding: 0 0 4px; border-bottom: 1px solid var(--line-soft);">'
        '<span>EDGAR THEME SEARCH</span>'
        '<span class="right" style="color:var(--text-3);">'
        'find every company mentioning a theme in recent 10-K / 10-Q / 8-K'
        '</span></div>'
    )
    with st.form("edgar_theme_form", clear_on_submit=False, border=False):
        cols = st.columns([5, 2, 2])
        with cols[0]:
            query = st.text_input(
                "Theme",
                value=st.session_state.get("edgar_theme_query", ""),
                placeholder='e.g. "HBM4", "co-packaged optics", "silicon carbide"',
                label_visibility="collapsed",
            )
        with cols[1]:
            submitted = st.form_submit_button(
                "↗ SEARCH", type="primary", use_container_width=True,
            )
        with cols[2]:
            refreshed = st.form_submit_button(
                "↻ refresh", use_container_width=True,
                help="Drop the SQLite cache for this query and re-hit EDGAR.",
            )

    if submitted or refreshed:
        q = (query or "").strip()
        if not q:
            st.warning("Enter a theme to search.")
            return
        st.session_state["edgar_theme_query"] = q
        # Cache lookup first, unless the user explicitly requested refresh.
        with db.connect() as conn:
            cached = db.get_edgar_search_hits(conn, q, limit=25) if not refreshed else []
        if not cached:
            with st.spinner(f"Searching EDGAR for {q!r}…"):
                hits = search_filings(q)
            if hits:
                with db.connect() as conn:
                    db.save_edgar_search_hits(conn, q, hits)
                cached = hits
        if not cached:
            st.info(f"No EDGAR matches found for {q!r} in the last year.")
            return
        _render_edgar_results(cached)
    elif st.session_state.get("edgar_theme_query"):
        # Re-render last results on rerun without forcing the user to
        # click Search again.
        q = st.session_state["edgar_theme_query"]
        with db.connect() as conn:
            cached = db.get_edgar_search_hits(conn, q, limit=25)
        if cached:
            _render_edgar_results(cached)


def _render_edgar_results(hits: list) -> None:
    """Compact result table. Each row links to the SEC document; the
    ticker (when known) becomes a chip the user can click to add to
    their watchlist."""
    rows_html = ""
    for h in hits[:15]:
        ticker = (h.get("ticker") or "").upper()
        company = (h.get("company") or "")[:50]
        form = h.get("form") or ""
        date_str = h.get("filing_date") or ""
        snippet = (h.get("snippet") or "")[:180]
        url = h.get("url") or ""
        ticker_chip = (
            f'<span class="kpi-tag" style="background:var(--amber-soft, #5a3a00);'
            f'color:var(--amber, #ffb74d);padding:2px 6px;border-radius:3px;'
            f'font-size:10px">{ticker}</span>'
            if ticker else
            '<span style="color:var(--text-3);font-size:10px">—</span>'
        )
        rows_html += (
            f'<tr>'
            f'<td style="white-space:nowrap">{date_str}</td>'
            f'<td>{ticker_chip}</td>'
            f'<td>{company}</td>'
            f'<td><span class="kpi-caption">{form}</span></td>'
            f'<td><a href="{url}" target="_blank" rel="noopener" '
            f'  style="color:var(--text-2);text-decoration:none">{snippet} ↗</a></td>'
            f'</tr>'
        )
    st.html(
        f'<div style="margin: 12px 0 4px;">'
        f'<table class="signal-table" style="width:100%;border-collapse:collapse;'
        f'  font-size:12px">'
        f'<thead><tr style="color:var(--text-3);font-size:11px">'
        f'  <th style="text-align:left;padding:4px 6px">Filed</th>'
        f'  <th style="text-align:left;padding:4px 6px">Ticker</th>'
        f'  <th style="text-align:left;padding:4px 6px">Company</th>'
        f'  <th style="text-align:left;padding:4px 6px">Form</th>'
        f'  <th style="text-align:left;padding:4px 6px">Snippet</th>'
        f'</tr></thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</div>'
    )


# --------------------------------------------------------------------------
# Add-ticker form
# --------------------------------------------------------------------------
def _render_add_form():
    st.html(
        '<div class="block-label" style="margin: 20px 0 8px; '
        'padding: 0 0 4px; border-bottom: 1px solid var(--line-soft);">'
        '<span>ADD TICKER</span>'
        '<span class="right" style="color:var(--text-3);">'
        'layer is auto-detected from yfinance industry</span></div>'
    )

    with st.form("add_ticker_form", clear_on_submit=True, border=False):
        cols = st.columns([3, 3, 2])
        with cols[0]:
            ticker = st.text_input(
                "Ticker", max_chars=10, placeholder="e.g. AVGO",
                label_visibility="collapsed",
            )
        with cols[1]:
            list_choice = st.selectbox(
                "List", LISTS, index=LISTS.index("watchlist"),
                format_func=lambda l: LIST_LABEL[l],
                label_visibility="collapsed",
            )
        with cols[2]:
            submitted = st.form_submit_button(
                "+ ADD", type="primary", use_container_width=True,
            )

        if submitted:
            tk = (ticker or "").strip().upper()
            if not tk:
                st.warning("Enter a ticker symbol.")
                return
            with st.spinner(f"Validating {tk} via yfinance…"):
                ok, msg = _add_ticker_shared(tk, list_choice)
            if ok:
                _all_snapshots.clear()
                st.toast(msg)
                st.rerun()
            else:
                st.error(msg)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def render_watchlist() -> None:
    with db.connect() as conn:
        lists = db.get_lists(conn)
        counts = db.list_counts(conn)
    snapshots = _all_snapshots()
    layer_map = ticker_layers()

    # Header strip with counts.
    total = sum(counts.values())
    st.html(
        f"""
        <div class="section-head">
          <span class="num">—</span>
          <h2>Watchlist</h2>
          <span class="badge">{total} ticker{'s' if total != 1 else ''} ·
          {counts['holding']} holding · {counts['shortlist']} shortlist ·
          {counts['watchlist']} watchlist</span>
        </div>
        <div class="claude-line">
          <span class="glyph">◇</span>
          <span>Move tickers across lists with the picker on each card,
          or add a new ticker below. Lists persist to <code>watchlist.yaml</code>
          + SQLite — they survive restarts.</span>
        </div>
        """
    )

    # Refresh-prices control. Pulls a fresh snapshot for every ticker on
    # the watchlist (across all three lists). Lightweight: snapshot only,
    # no earnings/filings/sentiment — that's what `python -m fire.collector`
    # is for. Useful for a quick price check after adding a name.
    all_watchlist_tickers = sorted(lists.keys())
    refresh_cols = st.columns([2, 6])
    with refresh_cols[0]:
        refresh_clicked = st.button(
            "↻ refresh prices",
            key="watchlist_refresh_prices",
            use_container_width=True,
            disabled=not all_watchlist_tickers,
            help="Pull latest prices from yfinance for every ticker on the watchlist.",
        )
    if refresh_clicked:
        ok, failed = _refresh_prices(all_watchlist_tickers)
        _all_snapshots.clear()
        if failed:
            st.warning(
                f"Refreshed {ok}/{len(all_watchlist_tickers)} · "
                f"no price for: {', '.join(failed)}"
            )
        else:
            st.toast(f"Refreshed prices for {ok} ticker{'s' if ok != 1 else ''}.")
        st.rerun()

    _render_add_form()

    _render_edgar_theme_search()

    st.html(
        '<div style="height: 12px;"></div>'
        '<div style="border-top: 1px solid var(--line); margin-bottom: 16px;"></div>'
    )

    # Three-column ladder.
    cols = st.columns(3)
    headers = {
        "holding":   ("HOLDING",   "amber",  counts["holding"]),
        "shortlist": ("SHORTLIST", "warm",   counts["shortlist"]),
        "watchlist": ("WATCHLIST", "cool",   counts["watchlist"]),
    }
    for col, list_name in zip(cols, LISTS):
        label, accent, n = headers[list_name]
        with col:
            st.html(
                f"""
                <div class="wl-col-head wl-{accent}">
                  <span class="wl-col-name">{label}</span>
                  <span class="wl-col-count">{n}</span>
                </div>
                """
            )
            tickers_in = sorted(t for t, l in lists.items() if l == list_name)
            if not tickers_in:
                st.html(
                    '<div class="wl-empty">— empty —</div>'
                )
                continue
            for tk in tickers_in:
                snap = snapshots.get(tk, {"ticker": tk, "name": tk})
                _render_card(tk, list_name, snap)
