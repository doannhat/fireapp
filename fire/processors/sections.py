"""Per-section Claude paragraph generator.

For each of the 9 Research-tab sections we ask Claude to write one
short paragraph that *interprets* the numbers for this specific ticker
in light of the investor's strategy memory. These calls run in parallel
(see `fire.processors.deep_dive`) so the wall-clock cost is one call,
not nine.
"""
from __future__ import annotations

from ..claude_cli import Claude, ClaudeResult


# What we tell Claude each section is about. Short label only — the
# strategy memory + KPI data carry the rest of the context.
SECTION_LABELS = {
    "overview":  "snapshot (size, leadership, volatility, sector position)",
    "valuation": "valuation multiples relative to growth and quality",
    "growth":    "revenue, EPS, and margin trajectory",
    "quality":   "returns on capital and operating leverage",
    "health":    "balance-sheet strength and dilution risk",
    "ai":        "exposure to the AI super-cycle (segment, capex, customer concentration)",
    "income":    "dividend, implied volatility, and option-flow setup",
    "sentiment": "social sentiment vs the 30d baseline",
    "fine":      "structural risks (ownership concentration, short interest, SBC)",
}


PROMPT_TEMPLATE = """You are FIRE's research desk. Write ONE paragraph
(4-7 sentences, ~80-140 words) that interprets {ticker}'s {section_label}
for a long-term investor whose strategy is in the system context.

Rules:
- Use ONLY the numbers provided below. Do not invent values.
- Quote specific KPIs by their actual numbers ("ROE of 101%", not
  "elite ROE"). The user wants the connection between numbers and
  takeaway to be obvious.
- If extras blocks are present (VALUATION HISTORY, INSIDER ACTIVITY,
  FORM 4 BREAKDOWN, 13F INSTITUTIONAL HOLDERS, ACTIVIST FILINGS, EARNINGS
  CALL EXCERPT, GUIDANCE / OUTLOOK SCAN), weave the relevant numbers
  into the paragraph — these are the section's strongest evidence.
  Specifically:
    · valuation section: cite the P/B trajectory and call out the
      ** DEEP-VALUE TRIGGER ** when present.
    · growth section: when a GUIDANCE / OUTLOOK SCAN is present, quote
      one short verbatim fragment in "quotes" — management's own words
      beat your interpolation of the KPI table.
    · ai section: when an EARNINGS CALL EXCERPT is present, surface
      what management is actually saying about capex, customers, ramp.
    · fine section: lead with the FORM 4 BREAKDOWN's DISCRETIONARY NET
      (NOT the raw insider net — 10b5-1 plan sells are mechanical, not
      signal). Name the top 13F holder by value. If ACTIVIST FILINGS
      includes an SC 13D from a credible activist, that goes in the
      punchline.
- End the paragraph with the takeaway: is this section a strength, a
  weakness, or a watch-item for the thesis? Use **bold** on the punchline.
- No hedging. Terse. Skip clauses cleanly when their data isn't present.

Return ONLY JSON in this exact shape:

{{
  "paragraph": "your single paragraph here (you can use **bold** for emphasis)"
}}

Data for {ticker} — {section_label}:

{data_blob}
"""


def _humanize_money(v) -> str:
    if v is None:
        return "—"
    a = abs(v)
    sign = "−" if v < 0 else ""
    if a >= 1e12: return f"{sign}${a / 1e12:.2f}T"
    if a >= 1e9:  return f"{sign}${a / 1e9:.1f}B"
    if a >= 1e6:  return f"{sign}${a / 1e6:.0f}M"
    return f"{sign}${a:,.0f}"


# Per-section extras: which slices of the Phase 2.6/2.7 data block does each
# section's paragraph care about? Keeps prompts tight by only sending
# the relevant signals to the model that's writing each paragraph.
_EXTRAS_PER_SECTION = {
    "overview":  ("insider_summary", "form4_breakdown", "transcripts_brief"),
    "valuation": ("valuation_history",),
    "growth":    ("transcripts_guidance",),  # forward-guidance snippets
    "ai":        ("transcripts_brief",),     # capex / product / customer mix
    "fine":      ("insider_summary", "insider_recent", "form4_breakdown",
                  "institutional_holdings_db", "activist_filings"),
    "sentiment": ("sentiment_counts_breakdown",),  # synthesized inline
    # quality/health/income deliberately omitted — their KPI tiles are
    # richer signals than the extras blocks here.
}


# Per-call body trim sent to per-section prompts. Tighter than the
# thesis blob — sections only need a paragraph's worth of context.
_TRANSCRIPT_SECTION_SLICE = 1400


def _render_extras_for_section(section_name: str, extras: dict) -> str:
    """Render only the Phase 2.6 slices relevant to a given section."""
    if not extras:
        return ""
    wanted = _EXTRAS_PER_SECTION.get(section_name, ())
    if not wanted:
        return ""
    out: list = []

    if "valuation_history" in wanted:
        vh = extras.get("valuation_history") or []
        if vh:
            ordered = list(reversed(vh[:8]))
            out.append("\n[VALUATION HISTORY · annual · stockanalysis.com]")
            for r in ordered:
                period = (r.get("period_end") or "")[:25]
                pb = r.get("pb")
                ps = r.get("ps")
                pe = r.get("pe")
                pb_s = f"P/B={pb:.2f}" if isinstance(pb, (int, float)) else "P/B=—"
                ps_s = f"P/S={ps:.2f}" if isinstance(ps, (int, float)) else "P/S=—"
                pe_s = f"P/E={pe:.2f}" if isinstance(pe, (int, float)) else "P/E=—"
                out.append(f"  {period:25} {pb_s}  {ps_s}  {pe_s}")
            latest = vh[0]
            if isinstance(latest.get("pb"), (int, float)) and latest["pb"] <= 1.0:
                out.append(
                    f"  ** DEEP-VALUE TRIGGER: P/B {latest['pb']:.2f} ≤ 1.0 — "
                    f"Intel-2025-template starting condition."
                )

    if "insider_summary" in wanted:
        ins = extras.get("insider_summary") or {}
        n_total = (ins.get("buy_n") or 0) + (ins.get("sell_n") or 0)
        if n_total > 0:
            net = ins.get("net_value") or 0.0
            out.append("\n[INSIDER ACTIVITY · last 180 days]")
            out.append(
                f"  NET: {_humanize_money(abs(net))} "
                f"{'NET BOUGHT' if net >= 0 else 'NET SOLD'}"
            )
            out.append(
                f"  BUYS: {ins.get('buy_n', 0)} txns ({_humanize_money(ins.get('buy_value', 0))})"
                f" · SELLS: {ins.get('sell_n', 0)} txns ({_humanize_money(ins.get('sell_value', 0))})"
            )

    if "insider_recent" in wanted:
        recent = extras.get("insider_recent") or []
        if recent:
            out.append("\n[RECENT INSIDER TXNS]")
            for r in recent[:5]:
                act = (r.get("action") or "").upper()
                side = "BUY" if act == "P" else ("SELL" if act == "S" else act or "—")
                v = r.get("value")
                v_str = _humanize_money(abs(v)) if v is not None else "—"
                name = (r.get("insider") or "—")[:28]
                role = (r.get("role") or "")[:24]
                fdate = r.get("filing_date") or ""
                out.append(f"  {fdate} · {side} · {name} ({role}) · {v_str}")

    if "institutional_holdings_db" in wanted:
        holders = extras.get("institutional_holdings_db") or []
        if holders:
            period = holders[0].get("period_end") or "—"
            out.append(f"\n[13F INSTITUTIONAL HOLDERS · {period}]")
            for h in holders[:6]:
                name = (h.get("holder_name") or "—")[:35]
                v = h.get("value")
                v_str = _humanize_money(v) if v is not None else "—"
                out.append(f"  {name}: {v_str}")

    if "form4_breakdown" in wanted:
        f4 = extras.get("form4_breakdown") or {}
        total = ((f4.get("discretionary_buy_n") or 0)
                 + (f4.get("discretionary_sell_n") or 0)
                 + (f4.get("plan_sell_n") or 0))
        if total > 0:
            net = f4.get("discretionary_net_value") or 0
            out.append("\n[FORM 4 BREAKDOWN · 180d · signal vs noise]")
            out.append(
                f"  DISCRETIONARY NET: {_humanize_money(abs(net))} "
                f"{'NET BOUGHT' if net >= 0 else 'NET SOLD'} "
                f"({f4.get('discretionary_buy_n', 0)} buys · "
                f"{f4.get('discretionary_sell_n', 0)} sells)"
            )
            if f4.get("plan_sell_n") or 0:
                out.append(
                    f"  10b5-1 PLAN SELLS: {f4.get('plan_sell_n', 0)} txns · "
                    f"{_humanize_money(f4.get('plan_sell_value', 0))} "
                    f"(mechanical — NOT a directional signal)"
                )

    if "activist_filings" in wanted:
        acts = extras.get("activist_filings") or []
        if acts:
            out.append("\n[ACTIVIST FILINGS · SC 13D / 13G]")
            for a in acts[:5]:
                form = a.get("form") or ""
                filer = (a.get("filer_name") or "—")[:40]
                pct = a.get("pct_owned")
                pct_str = f"{pct:.1f}%" if isinstance(pct, (int, float)) else "—"
                fdate = a.get("filing_date") or ""
                kind = ("ACTIVIST INTENT" if "13D" in form
                        else "passive 5%+")
                out.append(f"  {fdate} · {form} · {filer} · {pct_str}  ({kind})")

    if "transcripts_brief" in wanted:
        ts = extras.get("transcripts") or []
        if ts:
            out.append("\n[EARNINGS CALL EXCERPT · most recent]")
            t = ts[0]
            cd = t.get("call_date") or "—"
            period = t.get("period") or ""
            label = f"{cd}" + (f" · {period}" if period else "")
            out.append(f"  CALL: {label}")
            body = (t.get("body") or "")[:_TRANSCRIPT_SECTION_SLICE]
            for ln in body.split("\n"):
                ln = ln.strip()
                if not ln:
                    continue
                out.append(f"  | {ln}")

    if "transcripts_guidance" in wanted:
        # Heuristic guidance scan: pull lines that look forward-looking.
        ts = extras.get("transcripts") or []
        if ts:
            t = ts[0]
            body = t.get("body") or ""
            keywords = (
                "guidance", "outlook", "expect", "guide ", "guide.",
                "next quarter", "next year", "fiscal ", "FY", "raise",
                "raised", "lowered", "capex", "capacity", "ramp",
            )
            picks: list = []
            for ln in body.split("\n"):
                line = ln.strip()
                if not line or len(line) < 30:
                    continue
                low = line.lower()
                if any(k in low for k in keywords):
                    picks.append(line[:300])
                    if len(picks) >= 8:
                        break
            if picks:
                cd = t.get("call_date") or "—"
                out.append(f"\n[GUIDANCE / OUTLOOK SCAN · {cd}]")
                for p in picks:
                    out.append(f"  | {p}")

    return "\n".join(out)


def _data_blob(section_name: str, kpis: list, snap: dict,
               sentiment: dict | None = None,
               extras: dict | None = None) -> str:
    """Compact text dump of the section's KPIs plus enough snapshot
    context that Claude knows which company we're talking about. When
    `extras` is given, the Phase 2.6 slices relevant to this section
    are appended."""
    lines = [
        f"TICKER: {snap.get('ticker', '—')}",
        f"NAME:   {snap.get('name', '—')}",
    ]
    if snap.get("sector"):
        ind = snap.get("industry") or ""
        lines.append(f"SECTOR: {snap.get('sector')}"
                     + (f" / {ind}" if ind else ""))
    if snap.get("market_cap"):
        v = snap["market_cap"]
        lines.append(
            f"MARKET CAP: ${v / 1e12:.2f}T" if v >= 1e12 else
            f"MARKET CAP: ${v / 1e9:.1f}B"
        )
    if snap.get("price") is not None:
        lines.append(f"PRICE: ${snap['price']:.2f}")
    if snap.get("ytd_pct") is not None:
        lines.append(f"YTD: {snap['ytd_pct']:+.1f}%")

    lines.append(f"\n[{section_name.upper()} KPIs]")
    if not kpis:
        lines.append("  (no KPIs computed for this section)")
    for k in kpis or []:
        val = k.get("value", "")
        unit = k.get("unit", "")
        ccy = k.get("ccy", "")
        cap = k.get("caption", "")
        tag = k.get("tag") or [None, None]
        tag_label = tag[1] if isinstance(tag, (list, tuple)) and len(tag) > 1 else ""
        lines.append(
            f"  {k.get('label', '—')}: {ccy}{val}{unit}"
            + (f" ({tag_label})" if tag_label else "")
            + (f" — {cap}" if cap else "")
        )

    if section_name == "sentiment" and sentiment:
        lines.append("\n[SENTIMENT]")
        if sentiment.get("current") is not None:
            lines.append(f"  Current: {sentiment['current']:+.2f}")
        if sentiment.get("baseline") is not None:
            lines.append(f"  30d baseline: {sentiment['baseline']:+.2f}")
        if sentiment.get("delta") is not None:
            lines.append(f"  Δ: {sentiment['delta']:+.2f}")
        if sentiment.get("baseline_n_days") is not None:
            lines.append(f"  Baseline days: {sentiment['baseline_n_days']}")
        c = sentiment.get("counts") or {}
        lines.append(
            f"  COUNTS by source: reddit={c.get('reddit', 0)}, "
            f"stocktwits={c.get('stocktwits', 0)}, news={c.get('news', 0)}, "
            f"hn={c.get('hn', 0)}  (HN often leads retail on infra topics)"
        )
        if sentiment.get("trustworthy") is False:
            lines.append("  (baseline thin — interpret cautiously)")

    # Phase 2.6 extras, narrowed to the slices each section cares about.
    extras_blob = _render_extras_for_section(section_name, extras or {})
    if extras_blob:
        lines.append(extras_blob)

    return "\n".join(lines)


def build_section_summary(
    ticker: str,
    section_name: str,
    kpis: list,
    snap: dict,
    sentiment: dict | None = None,
    *,
    extras: dict | None = None,
    force: bool = False,
    claude: Claude | None = None,
    handle=None,
) -> tuple[dict | None, ClaudeResult]:
    """Single Claude call returning `{"paragraph": "..."}`.

    `extras` is the Phase 2.6 envelope produced by
    `fire.processors.thesis.gather_extras`. When passed, the relevant
    slice for this section (P/B history for valuation, insider/13F for
    fine, etc.) is woven into the data blob. Optional — paragraphs
    still work fine without it."""
    c = claude or Claude()
    prompt = PROMPT_TEMPLATE.format(
        ticker=ticker.upper(),
        section_label=SECTION_LABELS.get(section_name, section_name),
        data_blob=_data_blob(section_name, kpis, snap, sentiment, extras),
    )
    result = c.call(
        kind=f"section.{section_name}",
        ticker=ticker,
        prompt=prompt,
        content="",
        force=force,
        handle=handle,
    )
    return result.data, result
