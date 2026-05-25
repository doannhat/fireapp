"""Research tab — full v2 layout.

`render_research(ticker)` is the entry point; it pulls everything via
`fire.metrics.build_research_data` and lays it out using the renderers
in `fire.ui.components`.
"""
from __future__ import annotations

import json

import streamlit as st

from .. import db, jobs, metrics
from ..config import all_tickers
from .components import (_esc, render_activity_band, render_kpi_grid,
                         render_section_header, render_section_nav,
                         render_sentiment, render_thesis_card,
                         render_ticker_bar)
from .list_picker import render_list_picker
from .thesis_mock import build_mock_thesis

try:
    from ..processors.thesis import build_thesis as _claude_thesis
except Exception:
    _claude_thesis = None

try:
    from ..processors.deep_dive import build_deep_dive as _claude_deep_dive
    from ..processors.deep_dive import SECTION_KEYS as DEEP_DIVE_SECTIONS
except Exception:
    _claude_deep_dive = None
    DEEP_DIVE_SECTIONS = ()


SECTION_NAV = [
    ("overview",  "Overview"),
    ("valuation", "Valuation"),
    ("growth",    "Growth"),
    ("quality",   "Quality"),
    ("health",    "Health"),
    ("ai",        "AI exposure"),
    ("income",    "Options"),
    ("signals",   "Signals"),
    ("sentiment", "Sentiment"),
    ("fine",      "Fine print"),
]


# --------------------------------------------------------------------------
# Signals section — insider activity + institutional positioning + P/B history
# Reads from the Phase 2.6 tables populated by collect_ticker().
# --------------------------------------------------------------------------
def _humanize_money(v) -> str:
    if v is None:
        return "—"
    sign = "-" if v < 0 else ""
    a = abs(v)
    if a >= 1e9:
        return f"{sign}${a / 1e9:.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:.1f}M"
    if a >= 1e3:
        return f"{sign}${a / 1e3:.0f}K"
    return f"{sign}${a:,.0f}"


def _humanize_shares(v) -> str:
    if v is None:
        return "—"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    if v >= 1e3:
        return f"{v / 1e3:.0f}K"
    return f"{v:,.0f}"


def _render_signals_section(ticker: str) -> None:
    """Render the Signals section: insider activity + institutional
    holders + P/B history. Each subsection renders nothing when its data
    table is empty — so a ticker that's never been collected just shows
    a tight placeholder."""
    with db.connect() as conn:
        ins_summary = db.insider_summary(conn, ticker, days=180)
        ins_recent = db.get_insider_transactions(conn, ticker, days=180, limit=6)
        holders = db.get_institutional_holdings(conn, ticker, limit=8)
        val_history = db.get_valuation_history(conn, ticker, limit=10)

    has_anything = (ins_summary["buy_n"] + ins_summary["sell_n"] > 0
                    or holders or val_history)
    if not has_anything:
        # Render an empty section with a hint so the user knows it's wired
        # but waiting on collector data.
        st.html(
            f'<section class="section" id="sec-signals">'
            f'{render_section_header(8, "Signals", "insider · 13F · P/B history", "Run the collector to populate insider transactions, 13F positions, and P/B history.")}'
            f'</section>'
        )
        return

    blocks: list[str] = []

    # ---- Insider activity block ----
    if ins_summary["buy_n"] + ins_summary["sell_n"] > 0:
        net = ins_summary["net_value"]
        net_cls = "up" if net >= 0 else "dn"
        net_arrow = "▴" if net >= 0 else "▾"
        buy_v = _humanize_money(ins_summary["buy_value"])
        sell_v = _humanize_money(ins_summary["sell_value"])
        rows_html = ""
        for r in ins_recent:
            act = (r.get("action") or "").upper()
            tag_cls = "up" if act == "P" else ("dn" if act == "S" else "")
            tag = "BUY" if act == "P" else ("SELL" if act == "S" else act or "—")
            insider = _esc((r.get("insider") or "—")[:30])
            role = _esc((r.get("role") or "")[:24])
            # OpenInsider encodes sales as negative; we already show side
            # via the BUY/SELL chip, so render magnitudes positively.
            value_raw = r.get("value")
            shares_raw = r.get("shares")
            value_str = _humanize_money(abs(value_raw) if value_raw is not None else None)
            shares_str = _humanize_shares(abs(shares_raw) if shares_raw is not None else None)
            fdate = _esc(r.get("filing_date") or "")
            rows_html += (
                f'<tr>'
                f'<td>{fdate}</td>'
                f'<td><span class="kpi-tag {tag_cls}">{tag}</span></td>'
                f'<td>{insider}<br><span class="kpi-caption">{role}</span></td>'
                f'<td style="text-align:right">{shares_str}</td>'
                f'<td style="text-align:right">{value_str}</td>'
                f'</tr>'
            )
        blocks.append(f"""
        <div class="signal-block">
          <div class="signal-head">INSIDER ACTIVITY · last 180 days</div>
          <div class="signal-summary">
            <span class="signal-figure {net_cls}">{net_arrow} {_humanize_money(abs(net))} net</span>
            <span class="signal-sub">{ins_summary['buy_n']} buys ({buy_v}) ·
              {ins_summary['sell_n']} sells ({sell_v})</span>
          </div>
          <table class="signal-table">
            <thead><tr>
              <th>Filed</th><th>Side</th><th>Insider</th>
              <th style="text-align:right">Shares</th>
              <th style="text-align:right">Value</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>""")

    # ---- Institutional holders block ----
    if holders:
        period = holders[0].get("period_end") or "—"
        rows_html = ""
        for h in holders:
            name = _esc((h.get("holder_name") or "—")[:32])
            value_str = _humanize_money(h.get("value"))
            shares_str = _humanize_shares(h.get("shares"))
            rows_html += (
                f'<tr>'
                f'<td>{name}</td>'
                f'<td style="text-align:right">{shares_str}</td>'
                f'<td style="text-align:right">{value_str}</td>'
                f'</tr>'
            )
        blocks.append(f"""
        <div class="signal-block">
          <div class="signal-head">INSTITUTIONAL HOLDERS · {_esc(period)}</div>
          <div class="signal-summary">
            <span class="signal-sub">From 13F-HR filings of curated managers
              (configurable in <code>settings.yaml</code>).</span>
          </div>
          <table class="signal-table">
            <thead><tr>
              <th>Holder</th>
              <th style="text-align:right">Shares</th>
              <th style="text-align:right">Value</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </div>""")

    # ---- Valuation history block ----
    if val_history:
        # Show newest 8 periods left-to-right (oldest first), with P/B
        # highlighted because that's the deep-value-screen anchor.
        vh = list(reversed(val_history[:8]))
        head_cells = "".join(
            f'<th>{_esc(r.get("period_end") or "")}</th>' for r in vh
        )
        def _fmt(v):
            return f"{v:.2f}" if isinstance(v, (int, float)) else "—"
        def _row(label, key, accent=False):
            cls = " accent" if accent else ""
            cells = "".join(
                f'<td>{_fmt(r.get(key))}</td>' for r in vh
            )
            return f'<tr class="vh-row{cls}"><th>{label}</th>{cells}</tr>'
        blocks.append(f"""
        <div class="signal-block">
          <div class="signal-head">VALUATION HISTORY · annual</div>
          <div class="signal-summary">
            <span class="signal-sub">From stockanalysis.com. P/B is the
              deep-value anchor — look for ratios at or below 1.0 as the
              Intel-2025-style starting condition.</span>
          </div>
          <table class="signal-table valuation-history">
            <thead><tr><th></th>{head_cells}</tr></thead>
            <tbody>
              {_row("P/B", "pb", accent=True)}
              {_row("P/S", "ps")}
              {_row("P/E", "pe")}
            </tbody>
          </table>
        </div>""")

    body = "".join(blocks) or "<div class='claude-line'>No signal data yet.</div>"
    st.html(
        f'<section class="section" id="sec-signals">'
        f'{render_section_header(8, "Signals", "insider · 13F · P/B history", "")}'
        f'<style>'
        f'.signal-block {{ margin: 8px 0 18px; }}'
        f'.signal-head {{ font-family: var(--mono, monospace); font-size: 11px; '
        f'  letter-spacing: 0.08em; color: var(--text-3); margin-bottom: 6px; }}'
        f'.signal-summary {{ display: flex; gap: 14px; align-items: baseline; '
        f'  margin-bottom: 10px; flex-wrap: wrap; }}'
        f'.signal-figure {{ font-size: 15px; font-weight: 600; }}'
        f'.signal-figure.up {{ color: var(--up, #4caf50); }}'
        f'.signal-figure.dn {{ color: var(--dn, #ef5350); }}'
        f'.signal-sub {{ font-size: 11.5px; color: var(--text-3); }}'
        f'.signal-table {{ width: 100%; border-collapse: collapse; '
        f'  font-size: 12px; }}'
        f'.signal-table th, .signal-table td {{ border-bottom: 1px solid '
        f'  var(--line-soft, #2a2a2a); padding: 5px 8px; text-align: left; }}'
        f'.signal-table thead th {{ font-weight: 500; color: var(--text-3); '
        f'  font-size: 11px; letter-spacing: 0.05em; }}'
        f'.valuation-history th:first-child {{ width: 50px; color: var(--text-3); }}'
        f'.vh-row.accent th, .vh-row.accent td {{ font-weight: 600; }}'
        f'</style>'
        f'{body}'
        f'</section>'
    )


SECTION_CLAUDE_LINES = {
    "overview":  "Snapshot data straight from yfinance — sector, employees, "
                 "founder/CEO, beta, volume.",
    "valuation": "Multiples vs PEG. PEG below 1 flatters growth even when "
                 "absolute multiples look rich. Hover any tag to see the "
                 "threshold rule.",
    "growth":    "YoY and 3y/5y CAGR for revenue + EPS, plus margin trend "
                 "deltas. Watch where **margin** does more work than **volume**.",
    "quality":   "Profit per dollar of capital. **ROIC** and **FCF margin** "
                 "are the cleanest moat statistics.",
    "health":    "Balance sheet snapshot. Net cash + interest coverage + "
                 "share count YoY tells you about dilution risk.",
    "ai":        "**Pure-AI infra exposure** for compute names; R&D % and "
                 "capex YoY for the broader value chain. Data-center % from "
                 "hand-curated settings.yaml.",
    "income":    "Dividend is usually symbolic in this cohort. **30d "
                 "realized vol** stands in for IV until we wire the options "
                 "scanner in Phase 3.",
    "sentiment": "VADER aggregate + Reddit/StockTwits/news counts. Theme "
                 "clustering arrives once Phase 3 runs Claude pre-warm.",
    "fine":      "Things that don't fit elsewhere — ownership concentration, "
                 "insider holdings, short interest.",
}


SECTION_COL_GRID = {
    "overview":  6,
    "valuation": 3,
    "growth":    4,
    "quality":   4,
    "health":    4,
    "ai":        4,
    "income":    4,
    "fine":      4,
}


# --------------------------------------------------------------------------
# Cached data fetch — keeps the Research tab snappy on repeated reruns.
# --------------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def _load(ticker: str) -> dict:
    return metrics.build_research_data(ticker)


# --------------------------------------------------------------------------
# Thesis hydration — restore from claude_cache if session_state is empty.
# --------------------------------------------------------------------------
def _hydrate_thesis_from_cache(ticker: str, state_key: str, meta_key: str) -> None:
    """If session_state has no thesis for this ticker but the Claude cache
    does, copy the freshest one in. Means navigating tabs / reloading the
    page doesn't drop the user back to the heuristic mock."""
    if st.session_state.get(state_key):
        return
    with db.connect() as conn:
        row = conn.execute(
            """SELECT response_json, cost_usd, latency_ms, created_at
               FROM claude_cache
               WHERE ticker = ? AND kind = 'thesis'
               ORDER BY created_at DESC LIMIT 1""",
            (ticker.upper(),),
        ).fetchone()
    if not row or not row["response_json"]:
        return
    try:
        data = json.loads(row["response_json"])
    except (TypeError, ValueError):
        return
    if not isinstance(data, dict):
        return
    st.session_state[state_key] = data
    cost = row["cost_usd"]
    st.session_state[meta_key] = {
        "sources": "cached",
        "cost": f"${cost:.2f}" if cost is not None else "cached",
        "freshness": f"cached · {(row['created_at'] or '')[:16].replace('T', ' ')}",
    }


def _hydrate_sections_from_cache(ticker: str, state_key: str) -> None:
    """Pull the most-recent section.<name> paragraph for each Research
    section so a page reload doesn't drop them."""
    if st.session_state.get(state_key):
        return
    paragraphs: dict = {}
    with db.connect() as conn:
        for name in DEEP_DIVE_SECTIONS:
            row = conn.execute(
                """SELECT response_json FROM claude_cache
                   WHERE ticker = ? AND kind = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (ticker.upper(), f"section.{name}"),
            ).fetchone()
            if not row or not row["response_json"]:
                continue
            try:
                data = json.loads(row["response_json"])
            except (TypeError, ValueError):
                continue
            if isinstance(data, dict) and data.get("paragraph"):
                paragraphs[name] = data["paragraph"].strip()
    if paragraphs:
        st.session_state[state_key] = paragraphs


# --------------------------------------------------------------------------
# Ticker switcher — single combobox with free-text input
# --------------------------------------------------------------------------
@st.fragment(run_every=2)
def _render_other_jobs_banner(current_ticker: str) -> None:
    """If there are deep-dive jobs running on OTHER tickers, show a
    compact banner. Click a chip to jump back to that ticker. Refreshes
    every 2s so the elapsed-time counter ticks even while the user is
    browsing a different ticker — that's how progress stays visible.
    """
    others = [
        j for j in jobs.list_running("deep_dive::")
        if j.id.split("::", 1)[-1] != current_ticker
    ]
    if not others:
        return

    chips = []
    for j in others:
        tk = j.id.split("::", 1)[-1]
        prog = (j.progress or "thinking…")
        chips.append((tk, int(j.elapsed), prog))

    label = ("◇ Deep dive still running on "
             + ", ".join(f"{tk} ({s}s · {p})" for tk, s, p in chips))
    cols = st.columns([6] + [1] * len(chips) + [3])
    with cols[0]:
        st.markdown(
            f'<div style="font-family:JetBrains Mono,monospace;font-size:11.5px;'
            f'color:var(--amber);padding-top:6px">{label}</div>',
            unsafe_allow_html=True,
        )
    for col, (tk, _, _) in zip(cols[1:-1], chips):
        with col:
            if st.button(f"→ {tk}", key=f"jump_running_{tk}",
                         use_container_width=True,
                         help=f"Switch to {tk} to monitor or stop its deep dive."):
                st.session_state["active_ticker"] = tk
                st.rerun()


def _render_ticker_input(current: str) -> None:
    """One combobox at the top of Research: pick from the watchlist OR
    type a new symbol. `accept_new_options=True` (Streamlit 1.36+) lets
    the user enter a ticker that isn't currently on any list.

    The universe is ONLY the watchlist — a ticker removed from all
    lists drops out of the dropdown on the next rerun. If the user is
    actively researching a non-listed ticker, the free-text mode keeps
    the page reachable via typing.
    """
    universe = sorted(all_tickers())
    # Pre-select the current ticker if it's on the list; otherwise
    # leave the box empty so the user sees the placeholder and the
    # dropdown still shows clean watchlist names without the orphan.
    if current in universe:
        index = universe.index(current)
    else:
        index = None
    cols = st.columns([3, 1, 8])
    with cols[0]:
        try:
            picked = st.selectbox(
                "Research ticker",
                options=universe,
                index=index,
                key=f"research_combo_{current}",
                label_visibility="collapsed",
                accept_new_options=True,
                placeholder="Type a ticker or pick from your watchlist",
            )
        except TypeError:
            # Older Streamlit: no `accept_new_options` and no None index.
            # Fall back to a plain selectbox over the universe.
            picked = st.selectbox(
                "Research ticker",
                options=universe or [current],
                index=index if index is not None else 0,
                key=f"research_combo_{current}",
                label_visibility="collapsed",
            )
    with cols[1]:
        if st.button("⟳ Refresh", key=f"refresh_data_{current}",
                     use_container_width=True,
                     help="Drop the 15-min cache and pull fresh yfinance data."):
            _load.clear()
            st.toast(f"Refreshing {current}…")
            st.rerun()

    if picked and picked.strip().upper() != current:
        st.session_state["active_ticker"] = picked.strip().upper()
        st.rerun()


# --------------------------------------------------------------------------
# Thesis controls — Generate button (idle) + polling fragment (running)
# --------------------------------------------------------------------------
DEEP_DIVE_HELP = (
    "Runs ~10 Claude calls in parallel (3-way split thesis + every section · "
    "≈60–90s cold, free on cached refresh). Keeps the app responsive — use "
    "the Stop button to abort."
)


def _render_generate_button(ticker, job_id, thesis_key, sections_key,
                            snap, sections, sentiment):
    """Idle-state Deep-Dive button. Renders ONLY the button so the caller
    can place it in a column next to the list picker. The longer
    explainer is on the button as a `help=` tooltip."""
    has_thesis = bool(st.session_state.get(thesis_key))
    has_paras = bool(st.session_state.get(sections_key))
    has_any = has_thesis or has_paras
    label = "◇ Refresh Claude deep dive" if has_any else "◇ Run Claude deep dive"
    clicked = st.button(
        label, key=f"run_claude_{ticker}", type="primary",
        use_container_width=True,
        help=DEEP_DIVE_HELP,
    )
    if clicked:
        if _claude_deep_dive is None:
            st.error("`claude` CLI not available — install it to use this.")
            return
        cap_snap, cap_sec, cap_sent = snap, sections, sentiment
        force = has_any  # explicit Refresh → force regenerate everything
        def _runner(handle):
            return _claude_deep_dive(
                ticker, cap_snap, cap_sec, cap_sent,
                force=force, handle=handle,
            )
        jobs.submit(job_id, _runner)
        st.rerun()


@st.fragment(run_every=2)
def _render_running_strip(ticker, job_id, thesis_key, meta_key, sections_key):
    """Polling fragment that owns the spinner + Stop button while a
    deep-dive job is in flight. Consumes the result (thesis +
    per-section paragraphs) when the job finishes and triggers an
    app-wide rerun so everything renders with the fresh data."""
    job = jobs.get(job_id)
    if not job:
        return

    if job.status == "done":
        deep = job.result or {}
        if isinstance(deep, dict):
            if deep.get("thesis"):
                st.session_state[thesis_key] = deep["thesis"]
                meta = deep.get("thesis_meta") or {}
                st.session_state[meta_key] = {
                    "sources": "data + strategy",
                    "cost": (
                        f"${deep.get('total_cost_usd', 0):.2f}"
                        if deep.get("total_cost_usd") is not None else "—"
                    ),
                    "freshness": (
                        f"{job.elapsed:.1f}s" if job.elapsed else "cached"
                    ),
                }
            if deep.get("sections"):
                st.session_state[sections_key] = deep["sections"]
            if deep.get("errors"):
                # Surface non-fatal errors quietly — the partial result is
                # still usable.
                err_count = len(deep["errors"])
                if err_count:
                    st.toast(
                        f"Deep dive finished with {err_count} "
                        f"section(s) failing — see logs."
                    )
        jobs.clear(job_id)
        st.rerun()
        return

    if job.status == "error":
        st.error(f"Claude error: {job.error}")
        jobs.clear(job_id)
        return

    if job.status == "cancelled":
        st.caption("◇ Stopped.")
        jobs.clear(job_id)
        return

    # Still running. Caller places this inside a column next to the
    # picker pill; render the Stop button with the elapsed time in
    # the label and the per-step progress as a small caption below.
    progress = job.progress or ""
    if st.button(
            f"■ Stop deep dive · {int(job.elapsed)}s",
            key=f"stop_claude_{ticker}",
            type="secondary",
            use_container_width=True,
            help="Claude deep-diving in the background. Keep using the app.",
    ):
        jobs.cancel(job_id)
        st.rerun()
    if progress:
        st.caption(f"◇ {progress}")


# --------------------------------------------------------------------------
# Render entry
# --------------------------------------------------------------------------
def render_research(ticker: str) -> None:
    ticker = ticker.upper()
    thesis_state_key = f"thesis::{ticker}"
    thesis_meta_key = f"thesis_meta::{ticker}"
    sections_state_key = f"thesis_sections::{ticker}"
    job_id = f"deep_dive::{ticker}"

    # Hydrate from the Claude cache before rendering anything else — this
    # is why a tab switch / reload doesn't drop you back to the mock.
    _hydrate_thesis_from_cache(ticker, thesis_state_key, thesis_meta_key)
    _hydrate_sections_from_cache(ticker, sections_state_key)

    # Top: ticker switcher + refresh.
    _render_ticker_input(ticker)

    # Banner for any deep-dive jobs running on OTHER tickers (so the
    # user doesn't lose track of work they kicked off elsewhere).
    _render_other_jobs_banner(ticker)

    with st.spinner(f"Pulling {ticker}…"):
        try:
            data = _load(ticker)
        except Exception as exc:
            st.error(f"Could not load {ticker}: {exc}")
            return

    snap = data["snapshot"]
    sections = data["sections"]
    sentiment = data["sentiment"]

    # Hero card.
    st.html(render_ticker_bar(snap))

    # Compact control strip directly below the hero — list picker (the
    # popover button is styled to read like an amber pill) sits to the
    # left, the Claude deep-dive control to its right. Both occupy a
    # single row so we don't burn vertical space on two near-empty
    # rows of UI chrome.
    is_running = bool(jobs.get(job_id))
    ctrl_cols = st.columns([2, 3, 7])
    with ctrl_cols[0]:
        with st.container(key="hero_picker"):
            render_list_picker(ticker, key_prefix="research_picker")
    with ctrl_cols[1]:
        if is_running:
            _render_running_strip(ticker, job_id, thesis_state_key,
                                  thesis_meta_key, sections_state_key)
        else:
            _render_generate_button(ticker, job_id, thesis_state_key,
                                    sections_state_key, snap, sections, sentiment)
    with ctrl_cols[2]:
        # The explainer doubles as the button's tooltip; render a
        # compact version inline so the user sees cost/latency without
        # hovering. Hidden while a job is running — the Stop button
        # carries its own progress text.
        if not is_running:
            st.caption(
                "Thesis + every section in parallel · ≈60–90s cold, free on "
                "cached refresh."
            )

    st.html(render_section_nav(SECTION_NAV, active="overview"))

    # Thesis card — Claude when available, mock otherwise.
    if st.session_state.get(thesis_state_key):
        thesis = st.session_state[thesis_state_key]
        thesis.setdefault("meta", st.session_state.get(thesis_meta_key, {}))
    else:
        thesis = build_mock_thesis(snap, sections, sentiment)
    st.html(render_thesis_card(thesis))

    # Nine sections
    section_order = ["overview", "valuation", "growth", "quality", "health",
                     "ai", "income"]
    section_titles = {
        "overview":  ("Overview", "snapshot"),
        "valuation": ("Valuation", "multiples"),
        "growth":    ("Growth", "trends"),
        "quality":   ("Quality & moat", "returns on capital"),
        "health":    ("Financial health", "balance sheet"),
        "ai":        ("AI exposure", "segment · capex · concentration"),
        "income":    ("Income & options", "dividend · IV · option-flow"),
    }
    section_paragraphs = st.session_state.get(sections_state_key) or {}

    def _para_html(key: str) -> str:
        """Render the Claude paragraph for a section, or empty string."""
        para = (section_paragraphs.get(key) or "").strip()
        if not para:
            return ""
        from .components import _md_bold, _esc
        # Multi-paragraph support
        ps = [p.strip() for p in para.split("\n\n") if p.strip()]
        body = "".join(
            f'<p style="margin:0 0 6px">{_md_bold(p)}</p>' for p in ps
        )
        return (
            f'<div class="section-paragraph">'
            f'<span class="glyph">◇</span>{body}</div>'
        )

    for i, key in enumerate(section_order, start=1):
        kpis = sections.get(key) or []
        if not kpis:
            continue
        title, badge_hint = section_titles[key]
        badge = f"{len(kpis)} field{'s' if len(kpis) != 1 else ''} · {badge_hint}"
        # Skip the static SECTION_CLAUDE_LINES one-liner when we have a
        # real Claude paragraph for this section — the paragraph carries
        # all the context the one-liner used to.
        static_line = (SECTION_CLAUDE_LINES.get(key, "")
                       if not section_paragraphs.get(key) else "")
        st.html(
            f'<section class="section" id="sec-{key}">'
            f'{render_section_header(i, title, badge, static_line)}'
            f'{_para_html(key)}'
            f'{render_kpi_grid(kpis, cols=SECTION_COL_GRID.get(key, 4), section=key)}'
            f'</section>'
        )

    # Phase 2.6 — Signals section (insiders, institutional, P/B history).
    # Renders silently if the collector hasn't pulled the data yet.
    _render_signals_section(ticker)

    sent_static = (SECTION_CLAUDE_LINES["sentiment"]
                   if not section_paragraphs.get("sentiment") else "")
    st.html(
        f'<section class="section" id="sec-sentiment">'
        f'{render_section_header(9, "Sentiment", "Reddit · StockTwits · news · HN · 30d", sent_static)}'
        f'{_para_html("sentiment")}'
        f'{render_sentiment(sentiment)}'
        f'</section>'
    )

    fine = sections.get("fine") or []
    if fine:
        fine_static = (SECTION_CLAUDE_LINES["fine"]
                       if not section_paragraphs.get("fine") else "")
        st.html(
            f'<section class="section" id="sec-fine">'
            f'{render_section_header(10, "Fine print", "ownership · short · SBC", fine_static)}'
            f'{_para_html("fine")}'
            f'{render_kpi_grid(fine, cols=4, section="fine")}'
            f'</section>'
        )

    with db.connect() as conn:
        activity = db.recent_claude_activity(conn, ticker=ticker, limit=6)
    activity_rows = [
        {"created_at": r["created_at"], "label": f"{r['kind']} · {ticker}"}
        for r in activity
    ]
    st.html(render_activity_band(activity_rows))
