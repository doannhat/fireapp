"""FIRE — a long-term AI-stock research dashboard (v2).

Run with:   streamlit run app.py
Or just double-click  start_dashboard.command
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from fire import db
from fire.config import all_tickers
from fire.ui.compare import render_compare
from fire.ui.fonts import inject_fonts
from fire.ui.research import render_research
from fire.ui.strategy import render_strategy
from fire.ui.theme import inject_theme
from fire.ui.watchlist import render_watchlist


st.set_page_config(
    page_title="FIRE · terminal",
    page_icon="🔥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

inject_fonts()
inject_theme()

# Ensure schema is up to date (idempotent migration on every load).
db.init_db()


# --------------------------------------------------------------------------
# Top bar
# --------------------------------------------------------------------------
def _topbar():
    now = datetime.now()
    st.html(
        f"""
        <header class="topbar">
          <div class="brand">FIRE<span class="slash">/</span>terminal<span class="sub">v0.4</span></div>
          <span class="spacer"></span>
          <div class="meta">
            <span>{now.strftime('%d %b %y · %a').upper()}</span>
            <span class="live">{now.strftime('%H:%M ET')}</span>
          </div>
        </header>
        """
    )


_topbar()


# --------------------------------------------------------------------------
# Three tabs
# --------------------------------------------------------------------------
tab_research, tab_compare, tab_watchlist, tab_strategy = st.tabs(
    ["  RESEARCH  ", "  COMPARE  ", "  WATCHLIST  ", "  STRATEGY  "]
)

# Default ticker for first load — favor an explicit holding, fall back to
# whatever's on the watchlist.
def _default_ticker() -> str | None:
    with db.connect() as conn:
        lists = db.get_lists(conn)
    holdings = [t for t, l in lists.items() if l == "holding"]
    if holdings:
        return sorted(holdings)[0]
    if lists:
        return sorted(lists.keys())[0]
    universe = all_tickers()
    return universe[0] if universe else None


if "active_ticker" not in st.session_state:
    st.session_state["active_ticker"] = _default_ticker()


with tab_research:
    ticker = st.session_state.get("active_ticker")
    if not ticker:
        st.markdown(
            "<div class='claude-line' style='margin-top:32px'>"
            "<span class='glyph'>◇</span><span>No tickers yet. Add one to "
            "<code>watchlist.yaml</code> or via the Watchlist tab.</span></div>",
            unsafe_allow_html=True,
        )
    else:
        render_research(ticker)


with tab_compare:
    render_compare()


with tab_watchlist:
    render_watchlist()


with tab_strategy:
    render_strategy()


st.markdown(
    "<p class='footer-note'><strong>FIRE</strong> · research only · "
    "doesn't place trades · long-term investor scope · derivatives for "
    "hedging &amp; income only</p>",
    unsafe_allow_html=True,
)
