"""Compare tab — pin up to 4 tickers, render a grouped KPI table with
best/worst highlighting per row.

Phase 6 of the IMPLEMENTATION_PLAN. The Compare view re-uses the same
`fire.metrics.build_research_data` that powers Research, then pivots
the per-ticker KPI lists into a metric-per-row table.

Best/worst is computed per row using a hand-curated direction map
(`lower_better` for multiples, `higher_better` for margins / growth).
"""
from __future__ import annotations

import re

import streamlit as st

from .. import db, metrics
from ..config import all_tickers


# --------------------------------------------------------------------------
# Metric registry — which rows to show, and which way is "good"
# --------------------------------------------------------------------------
# Each entry: (section_key, label_substring, direction, group_title, claude_line)
# direction: 'lo' (lower is better) or 'hi' (higher is better).
METRIC_ROWS = [
    # 02 Valuation
    ("valuation", "P/E trailing",     "lo", "02 · Valuation", "Lower multiples are cheaper."),
    ("valuation", "P/E forward",      "lo", "02 · Valuation", ""),
    ("valuation", "PEG",              "lo", "02 · Valuation", ""),
    ("valuation", "P/S",              "lo", "02 · Valuation", ""),
    ("valuation", "EV/EBITDA",        "lo", "02 · Valuation", ""),
    ("valuation", "FCF yield",        "hi", "02 · Valuation", ""),

    # 03 Growth
    ("growth", "Revenue YoY",         "hi", "03 · Growth", "More growth = better, all else equal."),
    ("growth", "Revenue 3y CAGR",     "hi", "03 · Growth", ""),
    ("growth", "EPS YoY",             "hi", "03 · Growth", ""),
    ("growth", "EPS 3y CAGR",         "hi", "03 · Growth", ""),
    ("growth", "Gross margin",        "hi", "03 · Growth", ""),
    ("growth", "Operating margin",    "hi", "03 · Growth", ""),
    ("growth", "Net margin",          "hi", "03 · Growth", ""),

    # 04 Quality
    ("quality", "ROE",                "hi", "04 · Quality", "Returns on capital — higher = stronger moat."),
    ("quality", "ROA",                "hi", "04 · Quality", ""),
    ("quality", "FCF margin",         "hi", "04 · Quality", ""),
    ("quality", "Asset turnover",     "hi", "04 · Quality", ""),
    ("quality", "Inventory turns",    "hi", "04 · Quality", ""),
    ("quality", "R&D efficiency",     "hi", "04 · Quality", ""),

    # 05 Health
    ("health", "Net cash",            "hi", "05 · Health",  "Balance-sheet strength."),
    ("health", "Current ratio",       "hi", "05 · Health",  ""),
    ("health", "Quick ratio",         "hi", "05 · Health",  ""),
    ("health", "Interest coverage",   "hi", "05 · Health",  ""),
    ("health", "Debt / equity",       "lo", "05 · Health",  ""),
    ("health", "Share count YoY",     "lo", "05 · Health",  "Buybacks beat dilution."),

    # 06 AI exposure
    ("ai", "DC % of rev",             "hi", "06 · AI exposure", "Higher data-center share = more concentrated AI bet."),
    ("ai", "R&D % rev",               "hi", "06 · AI exposure", ""),
    ("ai", "R&D YoY",                 "hi", "06 · AI exposure", ""),
    ("ai", "Capex YoY",               "lo", "06 · AI exposure", "Lower capex = capital-light."),

    # 07 Income & options
    ("income", "Dividend yield",      "hi", "07 · Income & options", "Selling premium? Higher IV helps."),
    ("income", "Payout ratio",        "hi", "07 · Income & options", ""),
    ("income", "30d realized vol",    "hi", "07 · Income & options", ""),
    ("income", "Put / call ratio",    "lo", "07 · Income & options", ""),
]


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
@st.cache_data(ttl=900, show_spinner=False)
def _research_for(ticker: str) -> dict:
    return metrics.build_research_data(ticker)


def _find_kpi(kpis: list, label_substr: str) -> dict | None:
    s = label_substr.lower()
    for k in kpis:
        if s in (k.get("label") or "").lower():
            return k
    return None


_NUM_RE = re.compile(r"[-−+]?[\d,]+(?:\.\d+)?")


def _to_float(kpi: dict | None) -> float | None:
    if not kpi:
        return None
    txt = (kpi.get("value") or "").replace("−", "-").replace(",", "")
    m = _NUM_RE.search(txt)
    if not m:
        return None
    try:
        v = float(m.group(0))
    except ValueError:
        return None
    unit = (kpi.get("unit") or "").upper()
    if unit == "T":
        v *= 1e12
    elif unit == "B":
        v *= 1e9
    elif unit == "M":
        v *= 1e6
    elif unit == "K":
        v *= 1e3
    return v


def _format_cell(kpi: dict | None) -> str:
    if not kpi:
        return "—"
    ccy = kpi.get("ccy") or ""
    val = kpi.get("value") or "—"
    unit = kpi.get("unit") or ""
    return f"{ccy}{val}{unit}"


# --------------------------------------------------------------------------
# Pin-row + table renderers
# --------------------------------------------------------------------------
def _render_pin_row(tickers: list, snapshots: dict, col_template: str) -> str:
    """Header row with one card per pinned ticker. Renders exactly
    `len(tickers)` cells so its column widths match the table below."""
    cells = []
    for tk in tickers:
        snap = snapshots.get(tk, {})
        price = snap.get("price")
        prev = snap.get("prev_close")
        chg = None
        if price and prev:
            chg = (price / prev - 1) * 100
        delta_cls = "up" if (chg or 0) >= 0 else "dn"
        delta_html = (
            f'<span class="delta-mini {delta_cls}">'
            f'{"▴" if (chg or 0) >= 0 else "▾"}{abs(chg):.1f}%</span>'
            if chg is not None else ""
        )
        mcap = ""
        if snap.get("market_cap"):
            v = snap["market_cap"]
            mcap = f"${v / 1e12:.2f}T" if v >= 1e12 else \
                   f"${v / 1e9:.1f}B" if v >= 1e9 else f"${v / 1e6:.0f}M"
        pe = snap.get("trailing_pe") or snap.get("forward_pe")
        pe_str = f"P/E {pe:.1f}" if pe else "P/E —"
        if price:
            cells.append(f"""
            <div class="pin-cell">
              <div class="pin-id">{tk}</div>
              <div class="pin-name">{(snap.get('name') or tk)[:32]}</div>
              <div class="pin-price">${price:,.2f} {delta_html}</div>
              <div class="pin-meta"><span>{mcap}</span><span>{pe_str}</span></div>
            </div>
            """)
        else:
            cells.append(f"""
            <div class="pin-cell">
              <div class="pin-id">{tk}</div>
              <div class="pin-name">no data — refresh collector</div>
            </div>
            """)
    return f"""
    <div class="pin-row" style="grid-template-columns: {col_template};">
      <div class="pin-cell row-lbl">
        {len(METRIC_ROWS)} METRICS<br>
        <span class="count">across 6 sections</span>
      </div>
      {"".join(cells)}
    </div>
    """


def _render_table(tickers: list, datas: dict) -> str:
    """Group metrics by their section and render the v2 grid layout."""
    if not tickers:
        return ""

    # Group rows
    groups: dict = {}
    for row in METRIC_ROWS:
        groups.setdefault(row[3], []).append(row)

    # Use the same column template the pin row was built with so the
    # widths line up exactly above + below the divider.
    n = len(tickers)
    col_template = f"220px repeat({n}, minmax(0, 1fr))"

    parts = []
    parts.append(f'<div class="ct" style="grid-template-columns: {col_template};">')

    for group_title, rows in groups.items():
        num, _, name = group_title.partition(" · ")
        parts.append(f"""
        <div class="ct-group-head" style="grid-column: 1 / -1;">
          <span class="num">{num}</span><h3>{name}</h3>
        </div>
        """)
        for sec_key, label, direction, _, claude_line in rows:
            cells = []
            numerics = []
            for tk in tickers:
                kpis = datas[tk]["sections"].get(sec_key) or []
                kpi = _find_kpi(kpis, label)
                cells.append((tk, kpi))
                numerics.append(_to_float(kpi))

            valid = [n for n in numerics if n is not None]
            best_v = (max(valid) if direction == "hi" else min(valid)) if valid else None
            worst_v = (min(valid) if direction == "hi" else max(valid)) if valid else None
            row_html = [f"""
            <div class="lbl">
              <span>{label}</span>
              <span class="lbl-hint">{"lower better" if direction == "lo" else "higher better"}</span>
            </div>
            """]
            for (tk, kpi), num in zip(cells, numerics):
                disp = _format_cell(kpi)
                if num is None or best_v is None:
                    cls = ""
                    badge = ""
                elif num == best_v and num != worst_v:
                    cls = "best"
                    badge = '<span class="badge">best</span>'
                elif num == worst_v and num != best_v:
                    cls = "worst"
                    badge = ""
                else:
                    cls = ""
                    badge = ""
                row_html.append(f'<div class="cell {cls}">{disp}{badge}</div>')
            parts.append(f'<div class="ct-row" style="display:contents">{"".join(row_html)}</div>')

    parts.append("</div>")
    return "".join(parts)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
MAX_PINS = 4


def render_compare() -> None:
    # Default to whatever is on the watchlist; cap at 4.
    if "compare_tickers" not in st.session_state:
        with db.connect() as conn:
            lists = db.get_lists(conn)
        ordered = (
            [t for t, l in lists.items() if l == "holding"]
            + [t for t, l in lists.items() if l == "shortlist"]
            + [t for t, l in lists.items() if l == "watchlist"]
        )
        st.session_state["compare_tickers"] = ordered[:MAX_PINS]

    universe = sorted(set(all_tickers()) |
                      set(st.session_state["compare_tickers"]))

    st.html(
        f"""
        <div class="section-head">
          <span class="num">—</span>
          <h2>Compare</h2>
          <span class="badge">up to {MAX_PINS} tickers · side-by-side · best/worst per metric</span>
        </div>
        <div class="claude-line">
          <span class="glyph">◇</span>
          <span>Pick the tickers to compare. Best in row is cool (teal), worst is warm (brick).
          Direction is inferred — lower for multiples, higher for margins and growth.</span>
        </div>
        """
    )

    selected = st.multiselect(
        "Pinned tickers",
        universe,
        default=st.session_state["compare_tickers"],
        max_selections=MAX_PINS,
        label_visibility="collapsed",
        placeholder="Pick up to 4 tickers from your watchlist",
    )
    st.session_state["compare_tickers"] = selected

    if not selected:
        st.html(
            '<div class="claude-line" style="margin-top:24px">'
            '<span class="glyph">◇</span>'
            '<span>Pin some tickers above to begin comparing.</span></div>'
        )
        return

    if len(selected) < 2:
        # "Best in row" is meaningless with a cohort of one. Render an
        # explanation instead of a misleading single-column table.
        st.html(
            f'<div class="claude-line" style="margin-top:24px">'
            f'<span class="glyph">◇</span>'
            f'<span>Pin at least 2 tickers to compare. Currently pinned: '
            f'<strong>{selected[0]}</strong>.</span></div>'
        )
        return

    # Fetch data per ticker (cached).
    datas = {}
    snapshots = {}
    with st.spinner(f"Loading {len(selected)} ticker{'s' if len(selected) != 1 else ''}…"):
        for tk in selected:
            try:
                d = _research_for(tk)
                datas[tk] = d
                snapshots[tk] = d["snapshot"]
            except Exception as exc:
                st.warning(f"{tk}: {exc}")

    if not datas:
        return

    col_template = f"220px repeat({len(selected)}, minmax(0, 1fr))"
    st.html(_render_pin_row(selected, snapshots, col_template))
    st.html(_render_table(selected, datas))

    st.html(
        """
        <div class="legend" style="display:flex; gap:28px; margin-top:20px;
        padding:12px 16px; background:var(--bg-1); border:1px solid var(--line);
        font-family:JetBrains Mono,monospace; font-size:10.5px;
        color:var(--text-2); text-transform:uppercase; letter-spacing:1.4px;">
          <span><span style="display:inline-block; width:14px; height:14px;
            background:var(--cool-bg); border:1px solid var(--cool-line);
            vertical-align:-3px; margin-right:6px;"></span>Best in row</span>
          <span><span style="display:inline-block; width:14px; height:14px;
            background:var(--warm-bg); border:1px solid var(--warm-line);
            vertical-align:-3px; margin-right:6px;"></span>Worst in row</span>
          <span style="margin-left:auto; color:var(--text-3); text-transform:none;
            letter-spacing:0; font-size:11px;">
            Cohort-relative only — small N (≤4) means "best" is descriptive, not benchmark-grade.
          </span>
        </div>
        """
    )
