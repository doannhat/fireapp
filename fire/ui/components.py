"""Shared HTML renderers used by Research / Compare / Watchlist views.

Each function returns an HTML string. The caller wraps the result in
`st.markdown(..., unsafe_allow_html=True)`. Keeping the HTML pure lets us
compose larger sections without Streamlit getting in the way.
"""
from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable


# --------------------------------------------------------------------------
# Small primitives
# --------------------------------------------------------------------------
def _esc(s) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def _md_bold(s: str) -> str:
    """Tiny renderer: **bold** → <strong>bold</strong>. Escapes the rest."""
    if not s:
        return ""
    parts = []
    in_bold = False
    buf = ""
    i = 0
    while i < len(s):
        if s[i:i + 2] == "**":
            parts.append(_esc(buf))
            buf = ""
            parts.append("</strong>" if in_bold else "<strong>")
            in_bold = not in_bold
            i += 2
        else:
            buf += s[i]
            i += 1
    parts.append(_esc(buf))
    if in_bold:
        parts.append("</strong>")
    return "".join(parts)


def _md_em(s: str) -> str:
    """Same trick for *italic* and **bold**, with `code` left for callers."""
    if not s:
        return ""
    s = _md_bold(s)
    # Lightweight italic: _text_ → <em>text</em>
    out = []
    i = 0
    in_em = False
    while i < len(s):
        if s[i] == "_" and (i == 0 or s[i - 1] != "\\"):
            out.append("</em>" if in_em else "<em>")
            in_em = not in_em
            i += 1
        else:
            out.append(s[i])
            i += 1
    if in_em:
        out.append("</em>")
    return "".join(out)


# --------------------------------------------------------------------------
# Sparkline (inline SVG, no charting library)
# --------------------------------------------------------------------------
def sparkline_svg(values: list[float], width: int = 90, height: int = 22) -> str:
    """Render a list of floats as a 90×22 polyline SVG."""
    if not values or len(values) < 2:
        return ""
    lo = min(values)
    hi = max(values)
    rng = hi - lo if hi != lo else 1.0
    n = len(values)
    points = []
    for i, v in enumerate(values):
        x = i / (n - 1) * width
        # SVG y-axis is inverted; map high values to small y.
        y = height - ((v - lo) / rng) * height
        points.append(f"{x:.1f},{y:.1f}")
    last_x, last_y = points[-1].split(",")
    return (
        f'<svg class="spark" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none">'
        f'<polyline points="{" ".join(points)}"/>'
        f'<circle class="spark-dot" cx="{last_x}" cy="{last_y}" r="2"/>'
        f'</svg>'
    )


# --------------------------------------------------------------------------
# Ticker bar (sticky)
# --------------------------------------------------------------------------
def _fmt_price(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}"


def _fmt_pct(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{v:+.{decimals}f}%"


def _humanize_cap(v: float | None) -> str:
    if v is None:
        return "—"
    a = abs(v)
    sign = "−" if v < 0 else ""
    if a >= 1e12:
        return f"{sign}${v / 1e12:.2f}T" if v >= 0 else f"−${a / 1e12:.2f}T"
    if a >= 1e9:
        return f"{sign}${v / 1e9:.1f}B" if v >= 0 else f"−${a / 1e9:.1f}B"
    if a >= 1e6:
        return f"{sign}${v / 1e6:.0f}M" if v >= 0 else f"−${a / 1e6:.0f}M"
    return f"{sign}${v:,.0f}"


def render_ticker_bar(snap: dict) -> str:
    """Render the sticky ticker context bar at the top of Research.
    The interactive list picker is overlaid onto this bar via CSS by
    `fire.ui.research` — see `.st-key-hero_picker` in the theme."""
    day_chg = snap.get("day_chg_pct")
    delta_cls = "up" if (day_chg or 0) >= 0 else "dn"
    delta_arrow = "▴" if (day_chg or 0) >= 0 else "▾"
    delta_html = (
        f'<span class="delta {delta_cls}">{delta_arrow} '
        f'{abs(day_chg):.2f}%</span>' if day_chg is not None else ""
    )

    ev_sub = ""
    if snap.get("enterprise_value"):
        ev_sub = f"EV {_humanize_cap(snap['enterprise_value'])}"

    range_str = "—"
    range_sub = ""
    if snap.get("week52_high") and snap.get("week52_low"):
        range_str = f"{snap['week52_low']:.0f} – {snap['week52_high']:.0f}"
        if snap.get("range_pos_pct") is not None:
            range_sub = f"{snap['range_pos_pct']:.0f}th pctl in range"

    ytd_str = _fmt_pct(snap.get("ytd_pct"))

    beta_val = ""
    if snap.get("beta") is not None:
        beta_val = f"β {snap['beta']:.2f}"

    next_e_str = "—"
    if snap.get("next_earnings") is not None:
        try:
            next_e_str = snap["next_earnings"].strftime("%d %b").upper()
        except Exception:
            next_e_str = str(snap["next_earnings"])

    sector_line = ""
    if snap.get("sector"):
        sub = snap.get("industry") or ""
        sector_line = (
            f'<div class="sector">{_esc(snap.get("sector"))}'
            f'{" · " + _esc(sub) if sub else ""}</div>'
        )

    refresh_block = (
        f'<div class="refresh-block">'
        f'<div class="at">Refreshed</div>'
        f'<div class="ago">{datetime.now().strftime("%H:%M:%S")} ET</div>'
        f'</div>'
    )

    return f"""
    <div class="ticker-bar">
      <div class="ticker-row">
        <div class="ticker-id">
          <div>
            <div class="ticker-symbol">
              <span class="exch">{_esc(snap.get("exchange") or "")}</span>{_esc(snap["ticker"])}
            </div>
          </div>
          <div class="ticker-name">
            {_esc(snap.get("name") or snap["ticker"])}
            {sector_line}
          </div>
        </div>
        <div class="stat-strip">
          <div class="stat-cell price-cell">
            <div class="lbl">Price</div>
            <div class="val"><span class="ccy">$</span>{_fmt_price(snap.get("price"))}{delta_html}</div>
          </div>
          <div class="stat-cell">
            <div class="lbl">Market Cap</div>
            <div class="val">{_humanize_cap(snap.get("market_cap"))}</div>
            <div class="sub">{ev_sub}</div>
          </div>
          <div class="stat-cell">
            <div class="lbl">52-week range</div>
            <div class="val">{range_str}</div>
            <div class="sub">{range_sub}</div>
          </div>
          <div class="stat-cell">
            <div class="lbl">YTD performance</div>
            <div class="val">{ytd_str}</div>
          </div>
          <div class="stat-cell">
            <div class="lbl">Volatility</div>
            <div class="val">{beta_val or "—"}</div>
          </div>
          <div class="stat-cell">
            <div class="lbl">Next earnings</div>
            <div class="val">{next_e_str}</div>
          </div>
        </div>
        {refresh_block}
      </div>
    </div>
    """


# --------------------------------------------------------------------------
# Section header + Claude one-liner
# --------------------------------------------------------------------------
def render_section_nav(sections: list[tuple[str, str]], active: str = "overview") -> str:
    """`sections` is a list of (id, label). active is the current id.

    Each link is a real anchor to `#sec-<id>` — the corresponding
    `<section id="sec-<id>">` wrapper in the rendered Research view
    catches the click and the browser scrolls to it. Sections have
    `scroll-margin-top` so the sticky topbar doesn't cover the heading.
    """
    items = []
    for i, (sid, label) in enumerate(sections, start=1):
        cls = "active" if sid == active else ""
        items.append(
            f'<a href="#sec-{_esc(sid)}" class="{cls}">'
            f'<span class="num">{i:02d}</span>{_esc(label)}</a>'
        )
    return f'<nav class="section-nav">{"".join(items)}</nav>'


def render_section_header(num: int, title: str, badge: str = "",
                          claude_line: str = "") -> str:
    """Section number + title + badge + (optional) Claude one-liner."""
    head = f"""
    <div class="section-head">
      <span class="num">{num:02d}</span>
      <h2>{_esc(title)}</h2>
      {f'<span class="badge">{_esc(badge)}</span>' if badge else ''}
    </div>
    """
    if claude_line:
        head += (
            f'<div class="claude-line"><span class="glyph">◇</span>'
            f'<span>{_md_em(claude_line)}</span></div>'
        )
    return head


# --------------------------------------------------------------------------
# KPI glossary popover — every tile gets a small `ⓘ` info button. Click
# opens a popover with WHAT (definition) + SOURCE (data attribution).
# Implemented with native <details>/<summary> so it's accessible, needs
# no JS, and keeps the popover open until the user clicks away.
# Definitions live in fire/ui/kpi_glossary.py.
# --------------------------------------------------------------------------
from .kpi_glossary import lookup as _kpi_lookup


def _render_kpi_info_popover(label: str, section: str | None) -> str:
    info = _kpi_lookup(label, section)
    # `_md_bold` markdown is permitted inside definition/source strings —
    # use plain `_esc` here so the popover stays literal-text.
    definition = _esc(info.get("definition", ""))
    source = _esc(info.get("source", ""))
    return f"""
    <details class="kpi-info">
      <summary class="kpi-info-trigger" aria-label="What is {_esc(label)}?">ⓘ</summary>
      <div class="kpi-info-popover">
        <div class="kpi-info-section">
          <span class="kpi-info-key">WHAT</span>
          <p>{definition}</p>
        </div>
        <div class="kpi-info-section">
          <span class="kpi-info-key">SOURCE</span>
          <p>{source}</p>
        </div>
      </div>
    </details>
    """


# --------------------------------------------------------------------------
# KPI grid
# --------------------------------------------------------------------------
def render_kpi_tile(kpi: dict, section: str | None = None) -> str:
    """One KPI tile from the dict produced by fire.metrics.

    `section` (when provided) selects the right glossary fallback for
    labels that aren't in the explicit glossary table. Optional —
    omitting it just degrades to the generic default."""
    tag_html = ""
    if kpi.get("tag"):
        style, text = kpi["tag"]
        tip = kpi.get("tag_tip") or ""
        # title attribute = native hover tooltip; no JS needed
        tip_attr = f' title="{_esc(tip)}"' if tip else ""
        tag_html = (
            f'<span class="kpi-tag {style}"{tip_attr}>{_esc(text)}</span>'
        )

    ccy = kpi.get("ccy") or ""
    unit = kpi.get("unit") or ""
    ccy_html = f'<span class="ccy">{_esc(ccy)}</span>' if ccy else ""
    unit_html = f'<span class="unit">{_esc(unit)}</span>' if unit else ""

    value_html = f'<div class="kpi-value">{ccy_html}{_esc(kpi.get("value", "—"))}{unit_html}</div>'

    caption_html = ""
    if kpi.get("caption"):
        caption_html = f'<div class="kpi-caption">{_md_bold(kpi["caption"])}</div>'

    spark_html = ""
    spark = kpi.get("spark")
    if spark and spark.get("data"):
        svg = sparkline_svg(spark["data"])
        if svg:
            spark_html = (
                f'<div class="spark-wrap">{svg}'
                f'<span class="spark-cap">{_esc(spark.get("label", ""))}</span>'
                f'</div>'
            )

    info_popover = _render_kpi_info_popover(kpi.get("label", ""), section)

    return f"""
    <div class="kpi">
      <div class="kpi-head">
        <span class="kpi-label">{_esc(kpi["label"])}</span>
        <div class="kpi-head-right">
          {tag_html}
          {info_popover}
        </div>
      </div>
      {value_html}
      {caption_html}
      {spark_html}
    </div>
    """


def render_kpi_grid(kpis: list, cols: int = 4, section: str | None = None) -> str:
    """Render a grid of KPI tiles. `cols` picks the css grid class;
    `section` is forwarded to each tile so the info popover can pick a
    sensible fallback definition for unknown labels."""
    tiles = "".join(render_kpi_tile(k, section=section) for k in kpis)
    return f'<div class="kpi-grid cols-{cols}">{tiles}</div>'


# --------------------------------------------------------------------------
# Thesis card
# --------------------------------------------------------------------------
def render_thesis_card(thesis: dict) -> str:
    """Render the v2 thesis card from a structured dict. Missing
    sections render as empty (e.g. an in-flight pre-merge state); only
    fields that the schema guarantees are required for layout."""
    meta = thesis.get("meta", {})
    meta_html = (
        f'Tailored to your strategy '
        f'<span class="dot">·</span> {_esc(meta.get("sources", "—"))} sources '
        f'<span class="dot">·</span> {_esc(meta.get("cost", "—"))} '
        f'<span class="dot">·</span> {_esc(meta.get("freshness", "—"))}'
    )

    # Headline ribbon (v2). At the top of the card — conviction tier +
    # variant view. Renders nothing when the field is absent.
    headline = thesis.get("headline") or {}
    headline_html = ""
    if headline:
        call = (headline.get("call") or "").strip().upper()
        call_cls = {
            "CORE": "core", "ADD": "add",
            "WATCH": "watch", "PASS": "pass",
        }.get(call, "watch")
        one_liner = headline.get("one_liner") or ""
        variant = headline.get("variant_view") or ""
        headline_html = f"""
        <div class="headline-ribbon">
          <span class="conviction-pill {call_cls}">{_esc(call or "—")}</span>
          <div class="headline-body">
            <div class="headline-line">{_md_em(one_liner)}</div>
            <div class="variant-view">
              <span class="variant-label">VARIANT VIEW</span>
              <span class="variant-text">{_md_em(variant)}</span>
            </div>
          </div>
        </div>
        """

    # Verdict
    fit = thesis.get("strategy_fit", {})
    verdict_right = (
        f'strategy fit · {fit.get("passes", "—")} / {fit.get("total", "—")} criteria'
    )
    # Verdict can be multi-paragraph (separated by blank lines).
    raw_verdict = (thesis.get("verdict") or "").strip()
    verdict_paragraphs = [p for p in raw_verdict.split("\n\n") if p.strip()]
    verdict_body = "".join(
        f'<p class="verdict-text">{_md_em(p.strip())}</p>'
        for p in verdict_paragraphs
    ) if verdict_paragraphs else (
        f'<p class="verdict-text">{_md_em(raw_verdict)}</p>'
    )
    verdict_html = f"""
    <div class="verdict-section">
      <div class="block-label">
        <span>EXECUTIVE SUMMARY</span>
        <span class="right">{_esc(verdict_right)}</span>
      </div>
      {verdict_body}
    </div>
    """

    # Strategy check (v2 adds an optional `evidence` line under each row)
    items = []
    for item in thesis.get("strategy_check", []):
        cls = item.get("status", "pass")
        check_char = {"pass": "✓", "fail": "✗", "partial": "~"}.get(cls, "·")
        evidence = item.get("evidence")
        evidence_html = (
            f'<div class="strategy-evidence">{_md_em(evidence)}</div>'
            if evidence else ""
        )
        items.append(f"""
        <div class="strategy-item {_esc(cls)}">
          <span class="check">{check_char}</span>
          <span class="label">
            {_md_bold(item.get("label", ""))}
            {evidence_html}
          </span>
          <span class="verdict">{_esc(item.get("verdict", ""))}</span>
        </div>
        """)
    strategy_html = "".join(items)

    # Sizing
    sizing_rows = []
    for k, v in thesis.get("sizing", {}).items():
        sizing_rows.append(f"""
        <div class="sizing-row">
          <span class="k">{_esc(k)}</span>
          <span class="v">{_md_em(v)}</span>
        </div>
        """)
    sizing_html = "".join(sizing_rows)

    # Bull / bear
    bull_items = "".join(f"<li>{_md_bold(item)}</li>"
                         for item in thesis.get("bull", []))
    bear_items = "".join(f"<li>{_md_bold(item)}</li>"
                         for item in thesis.get("bear", []))

    # 3 mini cards
    mini_cards = []

    # Ownership card — top-holder QoQ Δ, analyst stance distribution,
    # PT vs price. Sole producer is the v2 thesis builder.
    own = thesis.get("ownership") or {}
    own_rows = []
    for k, v in (own.get("rows") or {}).items():
        cls = v.get("class", "")
        qoq = v.get("qoq")
        qoq_html = (
            f' <span class="qoq {cls}">({_esc(qoq)})</span>'
            if qoq else ""
        )
        own_rows.append(
            f'<div class="flow-row"><span class="who">{_esc(k)}</span>'
            f'<span class="val {cls}">{_esc(v.get("value", "—"))}{qoq_html}</span></div>'
        )
    own_tag = ""
    if own.get("tag"):
        cls, text = own["tag"]
        own_tag = f'<span class="tag {cls}">{_esc(text)}</span>'
    if own.get("rows"):
        mini_cards.append(f"""
        <div class="thesis-mini">
          <h5><span>OWNERSHIP &amp; ANALYST</span>{own_tag}</h5>
          {"".join(own_rows)}
          {f'<div class="thesis-takeaway">{_md_bold(own.get("takeaway", ""))}</div>' if own.get("takeaway") else ''}
        </div>
        """)

    # Scenarios (vs_consensus_pt per row + asymmetry takeaway)
    scen = thesis.get("scenarios") or {}
    scen_rows = []
    for which in ("bull", "base", "bear"):
        s = scen.get(which) or {}
        if not s:
            continue
        vs_pt = s.get("vs_consensus_pt")
        vs_pt_html = (
            f'<span class="vs-pt">{_esc(vs_pt)}</span>'
            if vs_pt else ""
        )
        scen_rows.append(f"""
        <div class="scenario-row {which}">
          <span class="name">{which.upper()}</span>
          <span class="desc">{_esc(s.get("desc", ""))}{vs_pt_html}</span>
          <span class="multi">×{_esc(s.get("multi", "—"))}</span>
          <span class="px">{_esc(s.get("px", "—"))}</span>
        </div>
        """)
    scen_tag = ""
    if scen.get("tag"):
        cls, text = scen["tag"]
        scen_tag = f'<span class="tag {cls}">{_esc(text)}</span>'
    asymmetry = scen.get("asymmetry")
    asymmetry_html = (
        f'<div class="asymmetry-row"><span>asymmetry</span>'
        f'<span>{_esc(asymmetry)}</span></div>'
        if asymmetry else ""
    )
    if scen_rows:
        mini_cards.append(f"""
        <div class="thesis-mini">
          <h5><span>2–3Y POTENTIAL</span>{scen_tag}</h5>
          {"".join(scen_rows)}
          {asymmetry_html}
          {f'<div class="thesis-takeaway">{_md_bold(scen.get("takeaway", ""))}</div>' if scen.get("takeaway") else ''}
        </div>
        """)

    mini_cards_html = "".join(mini_cards)

    # ---- New blocks: moat / positioning / pricing / multiplier --------
    moat = thesis.get("moat") or {}
    positioning = thesis.get("positioning") or {}
    pricing = thesis.get("pricing_power") or {}
    multiplier = thesis.get("revenue_multiplier") or {}

    moat_html = ""
    if moat.get("paragraph") or moat.get("bullets"):
        bullets_html = "".join(
            f"<li>{_md_bold(b)}</li>" for b in (moat.get("bullets") or [])
        )
        moat_html = f"""
        <div class="thesis-block moat">
          <div class="block-label"><span>MOAT</span></div>
          <div class="block-paragraph">{_md_em(moat.get("paragraph", ""))}</div>
          {f'<ul class="block-bullets">{bullets_html}</ul>' if bullets_html else ''}
        </div>
        """

    positioning_html = ""
    if positioning.get("paragraph"):
        layer = (positioning.get("layer") or "").strip()
        layer_pill = (
            f'<span class="layer-pill">{_esc(layer.upper())}</span>'
            if layer else ""
        )
        positioning_html = f"""
        <div class="thesis-block positioning">
          <div class="block-label">
            <span>AI POSITIONING</span>{layer_pill}
          </div>
          <div class="block-paragraph">{_md_em(positioning.get("paragraph", ""))}</div>
        </div>
        """

    pricing_html = ""
    if pricing.get("paragraph"):
        verdict_word = (pricing.get("verdict") or "").lower()
        verdict_cls = {
            "high": "cool", "moderate": "amber", "low": "warm",
        }.get(verdict_word, "amber")
        pricing_html = f"""
        <div class="thesis-block pricing">
          <div class="block-label">
            <span>PRICING POWER</span>
            <span class="verdict-pill {verdict_cls}">
              {_esc((pricing.get("verdict") or "—").upper())}
            </span>
          </div>
          <div class="block-paragraph">{_md_em(pricing.get("paragraph", ""))}</div>
        </div>
        """

    multiplier_html = ""
    if multiplier.get("paragraph"):
        pot = (multiplier.get("potential") or "—").strip()
        # Choose tag tone: 5-10× / >10× is cool (matches user's strategy);
        # <2× is warm (misses target); rest amber.
        pot_lower = pot.lower()
        if ">10" in pot_lower or "5-10" in pot_lower or "5–10" in pot_lower:
            pot_cls = "cool"
        elif "<2" in pot_lower or "unlikely" in pot_lower:
            pot_cls = "warm"
        else:
            pot_cls = "amber"
        multiplier_html = f"""
        <div class="thesis-block multiplier">
          <div class="block-label">
            <span>REVENUE MULTIPLIER · 2–3Y</span>
            <span class="verdict-pill {pot_cls}">{_esc(pot)}</span>
          </div>
          <div class="block-paragraph">{_md_em(multiplier.get("paragraph", ""))}</div>
        </div>
        """

    deep_dive_html = (
        f'<div class="thesis-deepdive">'
        f'{moat_html}{positioning_html}{pricing_html}{multiplier_html}'
        f'</div>'
        if any([moat_html, positioning_html, pricing_html, multiplier_html])
        else ""
    )

    # ---- Catalysts (v2) --------------------------------------------
    cat_rows = []
    for c in thesis.get("catalysts") or []:
        conf = (c.get("confidence") or "moderate").lower()
        conf_cls = {
            "high": "cool", "moderate": "amber", "speculative": "warm",
        }.get(conf, "amber")
        cat_rows.append(f"""
        <div class="catalyst-row">
          <span class="when">{_esc(c.get("when", "—"))}</span>
          <span class="event">{_md_em(c.get("event", ""))}</span>
          <span class="edge">{_md_em(c.get("edge", ""))}</span>
          <span class="conf {conf_cls}">{_esc(conf.upper())}</span>
        </div>
        """)
    catalysts_html = ""
    if cat_rows:
        catalysts_html = f"""
        <div class="thesis-block catalysts-block">
          <div class="block-label"><span>CATALYSTS · NEXT 12M</span></div>
          <div class="catalyst-grid">{"".join(cat_rows)}</div>
        </div>
        """

    # ---- Pre-mortem (v2) -------------------------------------------
    pm = thesis.get("premortem") or {}
    premortem_html = ""
    if pm.get("kill_switch") or pm.get("ignored_risks"):
        ignored_items = "".join(
            f"<li>{_md_bold(b)}</li>" for b in (pm.get("ignored_risks") or [])
        )
        premortem_html = f"""
        <div class="thesis-block premortem-block">
          <div class="block-label"><span>PRE-MORTEM</span></div>
          {f'<div class="kill-switch"><span class="ks-label">KILL SWITCH</span><span class="ks-text">{_md_em(pm.get("kill_switch", ""))}</span></div>' if pm.get("kill_switch") else ''}
          {f'<div class="ignored-label">Risks the market is shrugging off</div><ul class="block-bullets">{ignored_items}</ul>' if ignored_items else ''}
        </div>
        """

    # ---- Optionality (v2) ------------------------------------------
    opt = thesis.get("optionality") or []
    optionality_html = ""
    if opt:
        opt_items = "".join(f"<li>{_md_bold(b)}</li>" for b in opt)
        optionality_html = f"""
        <div class="thesis-block optionality-block">
          <div class="block-label"><span>UPSIDE OPTIONALITY</span><span class="right">not in base case</span></div>
          <ul class="block-bullets">{opt_items}</ul>
        </div>
        """

    extras_row_html = ""
    if catalysts_html or premortem_html or optionality_html:
        extras_row_html = (
            f'<div class="thesis-extras">'
            f'{catalysts_html}{premortem_html}{optionality_html}'
            f'</div>'
        )

    return f"""
    <section class="tldr">
      <div class="tldr-head">
        <div class="label"><span class="glyph">◇</span>CLAUDE · INVESTMENT THESIS</div>
        <div class="meta">{meta_html}</div>
      </div>
      <div class="thesis-body">
        {headline_html}
        {verdict_html}

        <div class="thesis-row-1">
          <div>
            <div class="block-label"><span>By your strategy</span></div>
            <div class="strategy-check">{strategy_html}</div>
          </div>
          <div>
            <div class="block-label"><span>Position sizing</span><span class="right">conditional</span></div>
            <div class="position-sizing">{sizing_html}</div>
          </div>
        </div>

        <div class="bull-bear">
          <div class="case-col bull">
            <h4>BULL CASE</h4>
            <ul class="case-list">{bull_items}</ul>
          </div>
          <div class="case-col bear">
            <h4>BEAR CASE</h4>
            <ul class="case-list">{bear_items}</ul>
          </div>
        </div>

        {deep_dive_html}

        {extras_row_html}

        {f'<div class="thesis-cards">{mini_cards_html}</div>' if mini_cards_html else ''}
      </div>
    </section>
    """


# --------------------------------------------------------------------------
# Sentiment block
# --------------------------------------------------------------------------
def render_sentiment(sent: dict, themes: list = None) -> str:
    """Render the v2 sentiment block — meter + (optional) themes + quotes."""
    current = sent.get("current")
    baseline = sent.get("baseline")
    delta = sent.get("delta")
    counts = sent.get("counts") or {}
    trustworthy = sent.get("trustworthy", True)
    baseline_n = sent.get("baseline_n_days")
    min_n = sent.get("min_baseline_days", 5)
    last_at = sent.get("last_fetched_at")

    big = "—"
    if current is not None:
        big = f"{current:+.2f}"

    baseline_html = ""
    if baseline is not None:
        baseline_html = (
            f'vs <span class="ref">30d baseline {baseline:+.2f}</span>'
        )

    delta_html = ""
    if delta is not None and trustworthy:
        delta_html = (
            f'<span class="delta-small">{"▴" if delta >= 0 else "▾"} '
            f'{delta:+.2f} vs baseline</span>'
        )

    # Marker position 0–100% maps current in [-1, +1] to [0, 100].
    marker_pos = 50
    baseline_pos = 50
    if current is not None:
        marker_pos = max(0, min(100, (current + 1) * 50))
    if baseline is not None:
        baseline_pos = max(0, min(100, (baseline + 1) * 50))

    counts_html = ""
    for src, label in [("reddit", "Reddit"), ("stocktwits", "StockTwits"), ("news", "News")]:
        n = counts.get(src, 0)
        counts_html += f"""
        <div class="c">
          <div class="l">{label}</div>
          <div class="n">{n:,}</div>
          <div class="l" style="color:var(--text-3);font-weight:400">items · 30d</div>
        </div>
        """

    # Freshness / trust pill below the baseline line.
    last_at_str = ""
    if last_at:
        try:
            last_at_str = (last_at[:16].replace("T", " "))
        except Exception:
            last_at_str = ""
    if not trustworthy and baseline_n is not None:
        trust_html = (
            f'<div class="sent-trust untrusted">'
            f'⚠ {baseline_n}/{min_n} baseline days · interpret cautiously'
            + (f' · last refresh {_esc(last_at_str)}' if last_at_str else '')
            + '</div>'
        )
        gray_attr = ' data-untrusted="1"'
    else:
        trust_html = (
            f'<div class="sent-trust">'
            f'{baseline_n or 0} baseline days'
            + (f' · last refresh {_esc(last_at_str)}' if last_at_str else '')
            + '</div>'
        )
        gray_attr = ''

    meter_card = f"""
    <div class="sent-meter-card"{gray_attr}>
      <div class="h">
        <span>AGGREGATE SENTIMENT</span>
        {delta_html}
      </div>
      <div class="big"><span class="pos">{big}</span></div>
      <div class="baseline">{baseline_html}</div>
      {trust_html}
      <div class="sent-track">
        <div class="bar"></div>
        <div class="baseline-tick" style="left:{baseline_pos}%"></div>
        <div class="marker" style="left:{marker_pos}%"></div>
        <div class="ticks">
          <span>−1.0</span><span>0</span><span>+1.0</span>
        </div>
      </div>
      <div class="sent-counts">{counts_html}</div>
    </div>
    """

    # Themes — placeholder if Claude clustering isn't wired yet.
    themes_html = ""
    if themes:
        items = []
        for t in themes:
            items.append(f"""
            <li>
              <span class="tag {_esc(t.get('kind', 'watch'))}">{_esc(t.get('kind', 'WATCH').upper())}</span>
              <span class="text">{_md_bold(t.get('text', ''))}</span>
              <span class="vol">{_esc(t.get('vol', ''))}</span>
            </li>
            """)
        themes_html = f"""
        <div class="sent-themes">
          <div class="h">
            <span>◇ CLAUDE · THEMES</span>
            <span class="meta">{_esc((themes[0].get('meta', '') if themes else ''))}</span>
          </div>
          <ul>{"".join(items)}</ul>
        </div>
        """
    else:
        themes_html = f"""
        <div class="sent-themes">
          <div class="h">
            <span>◇ CLAUDE · THEMES</span>
            <span class="meta">awaiting cluster — run pre-warm to populate</span>
          </div>
          <ul><li><span class="tag watch">WATCH</span><span class="text">
          Theme clustering happens on the next <code>--pre-warm</code>.
          Until then, see the quote grid below for the latest social posts.
          </span><span class="vol"></span></li></ul>
        </div>
        """

    grid_html = f'<div class="sent-grid">{meter_card}{themes_html}</div>'

    # Pull quotes
    quotes = sent.get("quotes") or []
    qcards = []
    for q in quotes[:4]:
        score = q.get("score")
        score_cls = "pos" if (score or 0) > 0 else "neg" if (score or 0) < 0 else ""
        score_html = f'<span class="score {score_cls}">{score:+.2f}</span>' if score is not None else ""
        try:
            created = q["created_at"][:10] if q.get("created_at") else ""
        except Exception:
            created = ""
        qcards.append(f"""
        <div class="qcard">
          <div class="src"><span>{_esc(q.get("source", "—"))}</span>{score_html}</div>
          <p class="q">{_esc((q.get("text") or "")[:240])}</p>
          <div class="meta">{_esc(created)}</div>
        </div>
        """)
    if qcards:
        grid_html += f'<div class="quote-grid">{"".join(qcards)}</div>'

    return grid_html


# --------------------------------------------------------------------------
# Activity band
# --------------------------------------------------------------------------
def render_activity_band(rows: Iterable[dict]) -> str:
    items = []
    seen_live = False
    for r in rows:
        # Crude relative-time label: '14h' etc.
        try:
            dt = datetime.fromisoformat(r.get("created_at"))
            delta = datetime.now() - dt
            if delta.total_seconds() < 90 * 60:
                t = "NOW" if not seen_live else f"{int(delta.total_seconds() // 60)}m"
                live_cls = " live" if not seen_live else ""
                seen_live = True
            elif delta.total_seconds() < 3600 * 24:
                t = f"{int(delta.total_seconds() // 3600)}h"
                live_cls = ""
            else:
                t = f"{delta.days}d"
                live_cls = ""
        except Exception:
            t = "—"
            live_cls = ""
        items.append(
            f'<li class="{live_cls.strip()}"><span class="t">{_esc(t)}</span>'
            f'<span>{_esc(r.get("label", ""))}</span></li>'
        )
    if not items:
        items.append(
            '<li><span class="t">—</span><span>no Claude activity yet '
            '— run <code>python -m fire.collector --pre-warm</code></span></li>'
        )
    return f"""
    <section class="activity-band">
      <div class="lbl"><span class="glyph">◇</span>CLAUDE · ACTIVITY</div>
      <ul>{"".join(items)}</ul>
    </section>
    """


