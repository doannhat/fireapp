"""Claude-built investment thesis card.

`build_thesis(ticker, snap, sections, sentiment)` returns a structured
dict the renderer turns into the thesis card. Sole producer for the
real (non-mock) thesis payload.

Schema is split into 3 partials (`core` / `deep` / `forward`) and
`build_thesis` fans out 3 parallel Claude calls via ThreadPoolExecutor,
then merges + strict-validates. Wall-clock is bounded by the slowest
partial (~60s on Sonnet) instead of the ~160s a single monolithic call
would take. Each partial caches independently.

Strict validation: any missing required field marks the result
ok=False so the renderer falls back to the heuristic mock in
`fire.ui.thesis_mock`.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import yfinance as yf

from .. import db
from ..claude_cli import Claude, ClaudeResult
from ..strategy import load_strategy

# Per-call body trim sent to the prompt. Storage keeps ~12KB; the
# prompt blob keeps only the densest leading slice of each transcript.
_TRANSCRIPT_PROMPT_SLICE = 2500


# ----------------------------------------------------------------------
# Parallel build — split the v2 schema into 3 self-contained partials
# so `build_thesis` can fan out 3 Claude calls instead of one big one.
# Wall-clock drops from ~160s (single Sonnet call against the full
# schema) to ~60s (max of 3 Sonnet calls running concurrently). Each
# partial is independently cached.
# ----------------------------------------------------------------------
SCHEMA_CORE = r"""
{
  "headline": {
    "call": "CORE | ADD | WATCH | PASS — single word",
    "one_liner": "<=18 words. The investment in one sentence.",
    "variant_view": "1-2 sentences. What does the market have wrong about this name? If genuinely consensus with no variant view, say 'Consensus — no variant edge' and the `call` should be WATCH or PASS."
  },
  "verdict": "EXECUTIVE SUMMARY — one flowing paragraph, 8-12 sentences (~200-300 words). NO line breaks, NO subheads, NO bullet lists — a single story arc that synthesises EVERY data source in the blob. Cover in order: (a) what the company does in plain English + which AI-stack layer it sits in (compute / network / power / hyperscaler / software / materials / services); (b) the durable moat — what defends the economics (switching cost / IP / scale / contracts / network effects), cite ROE / margin / market-share numbers; (c) the financial snapshot — quote AT LEAST 3-4 specific numbers spanning growth, margins, balance-sheet posture; (d) valuation context — cite current P/B (and if VALUATION HISTORY is present, name the trajectory: re-rating up / down / flat over the last 3-5 years, and call out the **deep-value trigger** if P/B ≤ 1.0); (e) positioning signals — cite the INSIDER ACTIVITY net buy/sell figure and, if 13F holders are listed, name the biggest holder and direction; (f) sentiment posture — cite the current vs 30d baseline if delta is meaningful, and call out HN sentiment separately when it diverges from retail (HN leads); (g) strategy fit — how it clears or fails the 5-10× / hidden-gem / AI super-cycle / quality-compounder bars, citing the number that drove each verdict; (h) the punchline — a single bolded sentence (wrap in **) the reader walks away with. Every clause either teaches or filters. Skip clauses cleanly when the underlying data isn't in the blob — sparse beats invented.",
  "strategy_fit": {"passes": "integer 0-4", "total": 4},
  "strategy_check": [
    {
      "status": "pass | partial | fail",
      "label": "5–10× upside in 2–3yr | Hidden gem · unloved by retail | AI super-cycle exposure | 2–3yr quality compounder",
      "verdict": "1-3 word tag",
      "evidence": "<=14 words — the specific number that drove the status"
    }
  ],
  "sizing": {
    "Suggested": "% of AI sleeve + 1-line rationale",
    "Entry":     "Explicit trigger — price level, IV range, or % drawdown",
    "Income":    "CC / CSP posture, or 'n/a'",
    "Constraint":"What would force a re-think"
  },
  "bull": ["3 bullets. Each MUST cite a specific number from the data. Use **bold** on the punchline phrase."],
  "bear": ["3 bullets, same rule as bull."]
}
"""

SCHEMA_DEEP = r"""
{
  "moat": {
    "paragraph": "3-4 sentences. The DURABLE economic moat — switching cost, network effects, IP, scale, brand, regulatory. Specific to THIS company; cite ROE / margin / market-share numbers from the data. Use **bold** for the punchline.",
    "bullets":   ["3 short bullets (<=14 words each) naming concrete moat sources"]
  },
  "positioning": {
    "paragraph": "3-4 sentences. Where in the AI super-cycle stack does this sit? Picks-and-shovels at silicon / network / optical / power / hyperscaler / downstream software / agent? Quantify exposure (segment % of revenue, capex YoY).",
    "layer":     "compute | network | power | hyperscaler | software | materials | services"
  },
  "pricing_power": {
    "verdict":   "high | moderate | low",
    "paragraph": "2-3 sentences. Can this company raise prices without losing volume? Which contracts cap it? 2-3yr elasticity story. Use **bold** on the verdict word."
  },
  "revenue_multiplier": {
    "potential": "<2× | 2-3× | 5-10× | >10×",
    "paragraph": "2-3 sentences. Quantified range with assumptions; tie to specific products / customers / contracts when possible."
  }
}
"""

SCHEMA_FORWARD = r"""
{
  "catalysts": [
    {
      "when":       "Specific date or window — 'Q2 2026 earnings', '1H 2027', 'CES 2027'",
      "event":      "<=18 words",
      "edge":       "What changes if it lands as expected vs market consensus",
      "confidence": "high | moderate | speculative"
    }
  ],
  "ownership": {
    "rows": {
      "Institutional":  {"value": "X% of float", "qoq": "+/-Y pp QoQ or null", "class": "pos|neg|flat"},
      "Insider held":   {"value": "X% (founder-led: yes/no)", "class": "pos|flat"},
      "Top holder Δ":   {"value": "Holder name +/-Y% QoQ", "class": "pos|neg|flat"},
      "Analyst stance": {"value": "N buy / N hold / N sell", "class": "pos|flat|neg"},
      "PT vs price":    {"value": "+/-X% to consensus PT $###", "class": "pos|neg|flat"}
    },
    "tag":      ["cool | warm | amber", "short label e.g. 'consensus long' / 'contrarian setup'"],
    "takeaway": "1-2 sentences. Are we crowded vs contrarian? Where are we vs sell-side consensus?"
  },
  "scenarios": {
    "bull": {"desc": "assumption chain (growth + multiple)", "multi": "1.5", "px": "$###", "vs_consensus_pt": "+X% above consensus PT"},
    "base": {"desc": "assumption chain", "multi": "1.0", "px": "$###", "vs_consensus_pt": "in-line with consensus PT"},
    "bear": {"desc": "assumption chain", "multi": "0.5", "px": "$###", "vs_consensus_pt": "-X% below consensus PT"},
    "asymmetry": "+X / -Y — bull-vs-base upside divided by base-vs-bear downside",
    "tag":       ["cool | warm | amber", "5-10× viable | misses 5-10×"],
    "takeaway":  "1-2 sentences."
  },
  "premortem": {
    "kill_switch":    "Single observable that would force you to sell. Specific (price / metric / event).",
    "ignored_risks":  ["2 bullets, <=14 words each — risks the market is shrugging off"]
  },
  "optionality": [
    "2-3 bullets, <=22 words each. Each = a call-option NOT in the base case (new product / new geo / capital-return surprise / M&A optionality)."
  ]
}
"""


# Each partial gets its own kind-key so cache entries don't collide.
_PARTS: tuple = (
    ("core",    SCHEMA_CORE,    "thesis_core_v2"),
    ("deep",    SCHEMA_DEEP,    "thesis_deep_v2"),
    ("forward", SCHEMA_FORWARD, "thesis_forward_v2"),
)


PART_RULES = {
    "core": (
        "FOCUS: the executive-summary half of the thesis — headline call, "
        "the prose verdict, the four strategy_check rows, sizing, bull, bear.\n"
        "The four strategy_check items appear in this exact order:\n"
        '  (1) "5–10× upside in 2–3yr"\n'
        '  (2) "Hidden gem · unloved by retail"\n'
        '  (3) "AI super-cycle exposure"\n'
        '  (4) "2–3yr quality compounder"\n'
        "Each MUST include an `evidence` field naming the number that drove "
        "the status. The `verdict` MUST be a SINGLE paragraph — no blank "
        "lines, no subheads, no bullets — but it MUST be SUBSTANTIVE "
        "(200-300 words) and synthesise every data source available: "
        "valuation history (P/B trajectory + deep-value trigger if ≤ 1.0), "
        "insider activity, 13F holders, HN sentiment, MANAGEMENT COMMENTARY "
        "from the EARNINGS CALL COMMENTARY block (quote a 4-8 word fragment "
        "verbatim when it captures the forward guidance), and ACTIVIST "
        "FILINGS (13D/13G) when present. Don't restate what the bullets "
        "cover — synthesise.\n"
        "INSIDER SIGNAL RULE: the FORM 4 BREAKDOWN distinguishes "
        "mechanical 10b5-1 plan sells (NOT signal) from discretionary "
        "buys/sells (signal). When evaluating insider activity, cite "
        "ONLY the DISCRETIONARY NET figure. A high-magnitude 10b5-1 "
        "plan sell stream alongside zero discretionary activity is "
        "neutral, NOT bearish.\n"
        "ACTIVIST RULE: an SC 13D filing (activist intent) by a credible "
        "investor (Pershing, Icahn, Elliott, Starboard, Third Point, "
        "Trian, JANA, ValueAct, etc.) is one of the strongest possible "
        "buy signals and MUST be called out in the verdict by filer name "
        "and date. SC 13G (passive) is materially weaker — note it but "
        "don't headline it.\n"
        "CALL COMMENTARY RULE: when EARNINGS CALL COMMENTARY is present, "
        "the verdict MUST reflect what management actually said — "
        "guidance, capex direction, customer concentration callouts, new "
        "product timelines. Quote a SHORT verbatim fragment (use "
        "\"quotation marks\") when it materially changes the take.\n"
        "When evaluating 'Hidden gem · unloved by retail', the INSIDER "
        "ACTIVITY and 13F blocks are first-class signals: heavy "
        "discretionary insider buying + low institutional concentration "
        "= strong hidden-gem fit; heavy discretionary selling + crowded "
        "13F = fails the screen.\n"
        "When evaluating valuation, treat the **DEEP-VALUE TRIGGER** flag "
        "in the blob as decisive evidence for the Intel-2025 template. "
        "`headline.variant_view` must answer 'what does the market have "
        "wrong?' If you can't honestly identify a variant view, say "
        "'Consensus — no variant edge' and downgrade `headline.call` to "
        "WATCH or PASS."
    ),
    "deep": (
        "FOCUS: the moat / positioning / pricing-power / revenue-multiplier "
        "deep-dive blocks. Quantify wherever possible — cite ROE, margin, "
        "segment %, customer contracts. Pricing-power verdict must be one "
        "of high|moderate|low. Revenue-multiplier potential must be one of "
        "<2× | 2-3× | 5-10× | >10×.\n"
        "If VALUATION HISTORY shows a multi-year compression (P/B falling "
        "for 3+ consecutive periods), that's evidence for either eroding "
        "moat OR a turnaround setup — weave the interpretation into the "
        "moat paragraph explicitly."
    ),
    "forward": (
        "FOCUS: forward-looking blocks — catalysts (2-4 dated events), "
        "ownership (institutional / insider / analyst posture), scenarios "
        "(bull/base/bear with vs_consensus_pt comparisons), premortem "
        "(single observable kill-switch + 2 ignored risks), and "
        "optionality (2-3 call options NOT in the base case).\n"
        "scenarios.bull/base/bear prices are arithmetic from the current "
        "price and your stated growth/multiple assumptions. Show your "
        "work in `desc`. `vs_consensus_pt` compares your price to the "
        "analyst target mean (ANALYST CONSENSUS in the data blob). "
        "`premortem.kill_switch` is a SINGLE observable — a price level, "
        "a leading indicator, a contract loss. Not a generic 'bad earnings'.\n"
        "For `ownership` rows: use the 13F INSTITUTIONAL HOLDERS block "
        "(EDGAR-derived) as the primary source for both Institutional % "
        "and Top holder Δ; only fall back to the TOP INSTITUTIONAL HOLDERS "
        "block (yfinance-derived) if 13F data is empty. The INSIDER "
        "ACTIVITY block drives the Insider held row's qualitative "
        "takeaway — heavy insider buying flips `class` to pos, heavy "
        "selling flips it to neg."
    ),
}


PROMPT_TEMPLATE_PART = r"""You are FIRE's research desk. Given the data below for
{ticker}, fill in ONE PARTIAL of a larger investment thesis. The full
thesis is being assembled in parallel; you are responsible only for the
keys defined in the schema below.

{part_rules}

CRITICAL RULES — break any of these and the response is rejected:
1. Use ONLY the data provided. Do NOT invent numbers (revenue figures,
   customer concentration, 13F flows, analyst quotes that aren't in the
   blob). If a number isn't here, omit the related bullet — sparse is
   better than wrong.
2. Output ONLY the JSON keys defined in the schema below. Do NOT include
   keys from other partials. Do NOT wrap in commentary or markdown.
3. Tone: terse, no hedging. The reader wants a verdict, not a discussion.

Output MUST match this schema exactly:

{schema}

Data:

{data_blob}
"""


# Required leaf-keys, checked by `_validate_thesis`. If any are missing
# from Claude's response, we return ok=False so the renderer falls back
# to the mock — the user opted in to strict validation.
REQUIRED_PATHS: tuple = (
    ("headline", "call"),
    ("headline", "one_liner"),
    ("headline", "variant_view"),
    ("verdict",),
    ("strategy_fit", "passes"),
    ("strategy_check",),    # list — non-empty enforced below
    ("sizing", "Suggested"),
    ("sizing", "Entry"),
    ("bull",),               # list — non-empty
    ("bear",),               # list — non-empty
    ("catalysts",),          # list — non-empty
    ("moat", "paragraph"),
    ("positioning", "paragraph"),
    ("pricing_power", "verdict"),
    ("revenue_multiplier", "potential"),
    ("ownership", "rows"),
    ("scenarios", "bull"),
    ("scenarios", "base"),
    ("scenarios", "bear"),
    ("premortem", "kill_switch"),
    ("optionality",),
)


# ----------------------------------------------------------------------
# Data blob builder
# ----------------------------------------------------------------------
def _human_money(v: float | None) -> str:
    if v is None:
        return "—"
    a = abs(v)
    sign = "−" if v < 0 else ""
    if a >= 1e12: return f"{sign}${a / 1e12:.2f}T"
    if a >= 1e9:  return f"{sign}${a / 1e9:.1f}B"
    if a >= 1e6:  return f"{sign}${a / 1e6:.0f}M"
    return f"{sign}${a:,.0f}"


def _safe_yf_info(ticker: str) -> dict:
    """Pull yfinance .info defensively. The thesis builder needs a
    handful of fields (longBusinessSummary, analyst PT, CEO context)
    that aren't carried through the metrics snapshot."""
    try:
        return yf.Ticker(ticker).info or {}
    except Exception:
        return {}


def _earnings_streak(conn, ticker: str, n: int = 6) -> list:
    """Last `n` quarterly EPS surprise rows, most-recent first. Each row
    is {date, est, actual, surprise_pct}. Empty list if none reported."""
    rows = conn.execute(
        """SELECT earnings_date, eps_estimate, eps_actual, surprise_pct
           FROM earnings
           WHERE ticker = ? AND eps_actual IS NOT NULL
           ORDER BY earnings_date DESC LIMIT ?""",
        (ticker.upper(), n),
    ).fetchall()
    return [dict(r) for r in rows]


def _next_earnings(conn, ticker: str) -> str | None:
    today = date.today().isoformat()
    row = conn.execute(
        """SELECT earnings_date FROM earnings
           WHERE ticker = ? AND earnings_date >= ?
           ORDER BY earnings_date ASC LIMIT 1""",
        (ticker.upper(), today),
    ).fetchone()
    return row["earnings_date"] if row else None


def _recent_filings(conn, ticker: str, days: int = 90) -> list:
    """Recent 10-K/10-Q/8-K cadence — Claude uses this to anchor
    catalysts to filing windows."""
    from datetime import timedelta
    since = (date.today() - timedelta(days=days)).isoformat()
    rows = conn.execute(
        """SELECT form, filing_date, title
           FROM filings
           WHERE ticker = ? AND filing_date >= ?
           ORDER BY filing_date DESC LIMIT 8""",
        (ticker.upper(), since),
    ).fetchall()
    return [dict(r) for r in rows]


def _read_all_db_extras(ticker: str) -> dict:
    """Single-pass DB read for all the per-ticker extras. Held in one
    function so the parallel `gather_extras` thread can call it without
    holding the SQLite lock open across the slower network calls."""
    out: dict = {
        "earnings_streak": [], "next_earnings": None,
        "filings_recent": [], "extras_rows": {},
        "insider_summary": None, "insider_recent": [],
        "form4_breakdown": None,
        "institutional_holdings_db": [],
        "valuation_history": [],
        "transcripts": [],
        "activist_filings": [],
    }
    try:
        with db.connect() as conn:
            out["earnings_streak"] = _earnings_streak(conn, ticker, n=6)
            out["next_earnings"] = _next_earnings(conn, ticker)
            out["filings_recent"] = _recent_filings(conn, ticker, days=120)
            out["extras_rows"] = db.get_deep_extras(conn, ticker)
            try:
                out["insider_summary"] = db.insider_summary(conn, ticker, days=180)
            except Exception:
                pass
            try:
                out["insider_recent"] = db.get_insider_transactions(
                    conn, ticker, days=180, limit=10
                )
            except Exception:
                pass
            try:
                out["form4_breakdown"] = db.get_insider_form4_breakdown(
                    conn, ticker, days=180
                )
            except Exception:
                pass
            try:
                out["institutional_holdings_db"] = (
                    db.get_institutional_holdings(conn, ticker, limit=8)
                )
            except Exception:
                pass
            try:
                out["valuation_history"] = db.get_valuation_history(
                    conn, ticker, limit=10
                )
            except Exception:
                pass
            try:
                out["transcripts"] = db.get_transcripts(conn, ticker, limit=2)
            except Exception:
                pass
            try:
                out["activist_filings"] = db.get_activist_filings(
                    conn, ticker, days=365, limit=8
                )
            except Exception:
                pass
    except Exception:
        pass
    return out


def gather_extras(ticker: str) -> dict:
    """One-shot extras pull for the thesis prompt. Runs the network
    yfinance .info fetch in parallel with the SQLite reads — they're
    fully independent, so doing them concurrently shaves the slower
    one off the wall-clock.

    Wraps everything in try/except so a yfinance hiccup or empty DB
    row doesn't break the thesis build — just produces a sparser
    prompt."""
    out: dict = {
        "info": {}, "earnings_streak": [], "next_earnings": None,
        "filings_recent": [], "inst_holders": [], "analyst_dist": [],
        "insider_summary": None, "insider_recent": [],
        "form4_breakdown": None,
        "institutional_holdings_db": [],
        "valuation_history": [],
        "transcripts": [],
        "activist_filings": [],
    }

    # Two independent jobs, parallel:
    #   - yfinance .info (network, slow)
    #   - all SQLite reads (local, fast, but uses connection)
    extras_rows: dict = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_info = pool.submit(_safe_yf_info, ticker)
        fut_db = pool.submit(_read_all_db_extras, ticker)
        try:
            out["info"] = fut_info.result() or {}
        except Exception:
            out["info"] = {}
        try:
            db_out = fut_db.result() or {}
        except Exception:
            db_out = {}

    # Merge DB results into the top-level out dict.
    extras_rows = db_out.pop("extras_rows", {}) or {}
    for k, v in db_out.items():
        out[k] = v

    # deep_extras stores JSON blobs — parse defensively.
    try:
        ih = extras_rows.get("institutional_holders")
        if ih and ih.get("content"):
            out["inst_holders"] = json.loads(ih["content"])
    except Exception:
        pass
    try:
        rec = extras_rows.get("recommendations")
        if rec and rec.get("content"):
            out["analyst_dist"] = json.loads(rec["content"])
    except Exception:
        pass

    return out


def _format_inst_holders(rows: list, limit: int = 5) -> list:
    """Top-N institutional holders with QoQ Δ. Each row from yfinance has
    Holder, pctHeld, Shares, Value, pctChange."""
    if not rows:
        return []
    out = []
    for r in rows[:limit]:
        holder = r.get("Holder") or "—"
        pct = r.get("pctHeld")
        chg = r.get("pctChange")
        pct_str = f"{pct * 100:.1f}%" if isinstance(pct, (int, float)) else "—"
        chg_str = (
            f"{chg * 100:+.1f}% QoQ" if isinstance(chg, (int, float))
            else "—"
        )
        out.append(f"{holder} ({pct_str}, {chg_str})")
    return out


def _format_analyst_dist(rows: list) -> str:
    """yfinance recommendations: list of {period, strongBuy, buy, hold,
    sell, strongSell}. Period '0m' is the latest snapshot.
    Returns a human string + trend tag."""
    if not rows:
        return "—"
    latest = next((r for r in rows if r.get("period") == "0m"), rows[0])
    sb = latest.get("strongBuy") or 0
    b = latest.get("buy") or 0
    h = latest.get("hold") or 0
    s = latest.get("sell") or 0
    ss = latest.get("strongSell") or 0
    return f"{sb + b} buy / {h} hold / {s + ss} sell (latest)"


def _data_blob(snapshot: dict, sections: dict, sentiment: dict,
               extras: dict) -> str:
    """Compact text dump of the metrics we have, so Claude doesn't
    waste tokens parsing JSON. Skip None values; nothing here is ever
    invented."""
    lines: list = []
    snap = snapshot or {}
    info = extras.get("info") or {}

    # ---- IDENTITY + PRICE CONTEXT ------------------------------------
    lines.append(f"TICKER: {snap.get('ticker')}")
    lines.append(f"NAME:   {snap.get('name')}")
    if snap.get("sector"):
        lines.append(f"SECTOR: {snap.get('sector')} / {snap.get('industry') or '—'}")
    if info.get("country"):
        lines.append(f"HQ:     {info.get('city') or ''}, {info.get('state') or ''} {info.get('country') or ''}".strip())
    if snap.get("price") is not None:
        lines.append(f"PRICE:  ${snap['price']:.2f}")
    if snap.get("market_cap") is not None:
        lines.append(f"MKT CAP: {_human_money(snap['market_cap'])}")
    if snap.get("enterprise_value") is not None:
        lines.append(f"EV:     {_human_money(snap['enterprise_value'])}")
    if snap.get("week52_high") and snap.get("week52_low"):
        lines.append(f"52W RANGE: {snap['week52_low']:.0f} – {snap['week52_high']:.0f}")
    if snap.get("range_pos_pct") is not None:
        lines.append(f"52W RANGE POSITION: {snap['range_pos_pct']:.0f}th pctl")
    if snap.get("ytd_pct") is not None:
        lines.append(f"YTD:    {snap['ytd_pct']:+.1f}%")
    if snap.get("beta") is not None:
        lines.append(f"BETA:   {snap['beta']:.2f}")

    # ---- BUSINESS DESCRIPTION ----------------------------------------
    biz = info.get("longBusinessSummary") or info.get("businessSummary")
    if biz:
        # Cap at 600 chars to keep prompt budget tight.
        biz = " ".join(biz.split())  # collapse whitespace
        lines.append(f"\n[BUSINESS DESCRIPTION]\n{biz[:600]}")

    # ---- LEADERSHIP --------------------------------------------------
    officers = info.get("companyOfficers") or []
    if officers:
        lines.append("\n[LEADERSHIP]")
        for o in officers[:3]:
            name = o.get("name") or "—"
            title = o.get("title") or "—"
            age = (
                f", age {date.today().year - int(o['yearBorn'])}"
                if o.get("yearBorn") else ""
            )
            lines.append(f"  {title}: {name}{age}")

    # ---- ANALYST CONSENSUS -------------------------------------------
    pt_mean = info.get("targetMeanPrice")
    pt_low = info.get("targetLowPrice")
    pt_high = info.get("targetHighPrice")
    rec_key = info.get("recommendationKey")
    n_analysts = info.get("numberOfAnalystOpinions")
    if pt_mean or rec_key:
        lines.append("\n[ANALYST CONSENSUS]")
        if pt_mean:
            lines.append(f"  PRICE TARGET MEAN: ${pt_mean:.2f}")
            if snap.get("price"):
                gap = (pt_mean / snap["price"] - 1) * 100
                lines.append(f"  PT vs PRICE: {gap:+.1f}%")
        if pt_low and pt_high:
            lines.append(f"  PT RANGE: ${pt_low:.2f} – ${pt_high:.2f}")
        if rec_key:
            lines.append(f"  CONSENSUS: {rec_key}")
        if n_analysts:
            lines.append(f"  ANALYSTS COVERING: {n_analysts}")
        dist = _format_analyst_dist(extras.get("analyst_dist") or [])
        if dist != "—":
            lines.append(f"  RATING DIST: {dist}")

    # ---- KPI SECTIONS (existing payload) -----------------------------
    for sec_name, kpis in (sections or {}).items():
        lines.append(f"\n[{sec_name.upper()}]")
        for k in kpis or []:
            val = k.get("value", "")
            unit = k.get("unit", "")
            ccy = k.get("ccy", "")
            cap = k.get("caption", "")
            tag = k.get("tag") or [None, None]
            tag_label = tag[1] if isinstance(tag, (list, tuple)) and len(tag) > 1 else ""
            lines.append(
                f"  {k.get('label', '—')}: {ccy}{val}{unit}"
                f"{f' ({tag_label})' if tag_label else ''}"
                f"{f' — {cap}' if cap else ''}"
            )
            # If a KPI carries a sparkline series, expose the trajectory.
            spark = k.get("spark")
            if spark and spark.get("data") and len(spark["data"]) >= 3:
                series = ", ".join(f"{v:.2f}" for v in spark["data"][:8])
                lines.append(f"    └── series ({spark.get('label', '')}): {series}")

    # ---- INSTITUTIONAL HOLDERS (top-5 + QoQ Δ) -----------------------
    ih = _format_inst_holders(extras.get("inst_holders") or [])
    if ih:
        lines.append("\n[TOP INSTITUTIONAL HOLDERS]")
        for row in ih:
            lines.append(f"  {row}")

    # ---- EARNINGS STREAK ---------------------------------------------
    streak = extras.get("earnings_streak") or []
    if streak:
        lines.append("\n[EARNINGS HISTORY]")
        beats = 0
        misses = 0
        for r in streak:
            sp = r.get("surprise_pct")
            tag = ""
            if sp is not None:
                if sp > 0:
                    beats += 1
                elif sp < 0:
                    misses += 1
                tag = f" surprise {sp:+.1f}%"
            est = r.get("eps_estimate")
            act = r.get("eps_actual")
            lines.append(
                f"  {r.get('earnings_date')}: est {est}, actual {act}{tag}"
            )
        lines.append(f"  STREAK: {beats} beats / {misses} misses in last {len(streak)} quarters")

    if extras.get("next_earnings"):
        lines.append(f"\nNEXT EARNINGS: {extras['next_earnings']}")

    # ---- RECENT FILINGS ----------------------------------------------
    filings = extras.get("filings_recent") or []
    if filings:
        lines.append("\n[RECENT SEC FILINGS]")
        for f in filings[:6]:
            lines.append(f"  {f.get('filing_date')} {f.get('form')}: {f.get('title', '')[:80]}")

    # ---- SENTIMENT ---------------------------------------------------
    if sentiment:
        lines.append("\n[SENTIMENT]")
        if sentiment.get("current") is not None:
            lines.append(f"  CURRENT MEAN: {sentiment['current']:+.2f}")
        if sentiment.get("baseline") is not None:
            lines.append(f"  30D BASELINE: {sentiment['baseline']:+.2f}")
        if sentiment.get("delta") is not None:
            lines.append(f"  SHIFT: {sentiment['delta']:+.2f}")
        c = sentiment.get("counts") or {}
        lines.append(
            f"  COUNTS: reddit={c.get('reddit', 0)}, "
            f"stocktwits={c.get('stocktwits', 0)}, news={c.get('news', 0)}, "
            f"hn={c.get('hn', 0)}  (HN = leading-indicator tech sentiment)"
        )

    # ---- PHASE 2.6 SIGNALS — insider, 13F-derived holders, P/B history -
    # These are direct conviction signals for the deep-value / hidden-gem
    # screen. Claude is instructed (in prompt rules) to cite specific
    # values from these blocks when they materially change the verdict.

    ins_sum = extras.get("insider_summary") or {}
    if ins_sum.get("buy_n", 0) + ins_sum.get("sell_n", 0) > 0:
        net = ins_sum.get("net_value") or 0.0
        lines.append("\n[INSIDER ACTIVITY · last 180 days · OpenInsider]")
        lines.append(
            f"  NET: {_human_money(abs(net))} "
            f"{'NET BOUGHT' if net >= 0 else 'NET SOLD'}"
        )
        lines.append(
            f"  BUYS:  {ins_sum.get('buy_n', 0)} txns · "
            f"{_human_money(ins_sum.get('buy_value', 0))}"
        )
        lines.append(
            f"  SELLS: {ins_sum.get('sell_n', 0)} txns · "
            f"{_human_money(ins_sum.get('sell_value', 0))}"
        )
        recent = extras.get("insider_recent") or []
        # Show up to 5 freshest rows so Claude can quote a specific name.
        for r in recent[:5]:
            act = (r.get("action") or "").upper()
            side = "BUY" if act == "P" else ("SELL" if act == "S" else act or "—")
            v = r.get("value")
            v_str = _human_money(abs(v)) if v is not None else "—"
            name = (r.get("insider") or "—")[:30]
            role = (r.get("role") or "")[:24]
            fdate = r.get("filing_date") or ""
            lines.append(
                f"    {fdate} · {side} · {name} ({role}) · {v_str}"
            )

    db_holders = extras.get("institutional_holdings_db") or []
    if db_holders:
        period = db_holders[0].get("period_end") or "—"
        lines.append(f"\n[13F INSTITUTIONAL HOLDERS · {period} · from EDGAR]")
        for h in db_holders[:8]:
            name = (h.get("holder_name") or h.get("holder_cik") or "—")[:35]
            value = h.get("value")
            shares = h.get("shares")
            v_str = _human_money(value) if value is not None else "—"
            sh_str = (
                f"{shares / 1e6:.1f}M sh"
                if isinstance(shares, (int, float)) and shares >= 1e6
                else f"{shares:,.0f} sh"
                if isinstance(shares, (int, float)) else "— sh"
            )
            lines.append(f"  {name}: {v_str} · {sh_str}")

    vh = extras.get("valuation_history") or []
    if vh:
        # Show oldest → newest so the trajectory reads left-to-right.
        ordered = list(reversed(vh[:10]))
        lines.append(
            "\n[VALUATION HISTORY · annual · stockanalysis.com]"
        )
        for r in ordered:
            period = (r.get("period_end") or "")[:25]
            pb = r.get("pb")
            ps = r.get("ps")
            pe = r.get("pe")
            pb_s = f"P/B={pb:.2f}" if isinstance(pb, (int, float)) else "P/B=—"
            ps_s = f"P/S={ps:.2f}" if isinstance(ps, (int, float)) else "P/S=—"
            pe_s = f"P/E={pe:.2f}" if isinstance(pe, (int, float)) else "P/E=—"
            lines.append(f"  {period:25} {pb_s}  {ps_s}  {pe_s}")
        # Flag the deep-value condition explicitly when current P/B ≤ 1.0.
        latest = vh[0]
        if isinstance(latest.get("pb"), (int, float)) and latest["pb"] <= 1.0:
            lines.append(
                f"  ** DEEP-VALUE TRIGGER: latest P/B {latest['pb']:.2f} ≤ 1.0 — "
                f"meets the Intel-2025-template starting condition."
            )

    # ---- FORM 4 BREAKDOWN — split mechanical vs discretionary -----------
    f4 = extras.get("form4_breakdown") or {}
    f4_total_n = (
        (f4.get("discretionary_buy_n") or 0)
        + (f4.get("discretionary_sell_n") or 0)
        + (f4.get("plan_sell_n") or 0)
    )
    if f4_total_n > 0:
        lines.append("\n[FORM 4 BREAKDOWN · 180d · mechanical vs discretionary]")
        lines.append(
            f"  DISCRETIONARY BUYS:  "
            f"{f4.get('discretionary_buy_n', 0)} txns · "
            f"{_human_money(f4.get('discretionary_buy_value', 0))}"
        )
        lines.append(
            f"  DISCRETIONARY SELLS: "
            f"{f4.get('discretionary_sell_n', 0)} txns · "
            f"{_human_money(f4.get('discretionary_sell_value', 0))}"
        )
        lines.append(
            f"  10b5-1 PLAN SELLS:   "
            f"{f4.get('plan_sell_n', 0)} txns · "
            f"{_human_money(f4.get('plan_sell_value', 0))}  "
            f"(pre-scheduled — NOT a directional signal)"
        )
        lines.append(
            f"  DERIVATIVE TXNS:     "
            f"{f4.get('derivative_n', 0)} txns · "
            f"{_human_money(f4.get('derivative_value', 0))}  "
            f"(option exercises / awards)"
        )
        net = f4.get("discretionary_net_value") or 0
        lines.append(
            f"  DISCRETIONARY NET:   {_human_money(abs(net))} "
            f"{'NET BOUGHT' if net >= 0 else 'NET SOLD'}  "
            f"** this is the signal — discretionary only **"
        )

    # ---- ACTIVIST FILINGS — SC 13D / 13G ---------------------------------
    activists = extras.get("activist_filings") or []
    if activists:
        lines.append("\n[ACTIVIST FILINGS · SC 13D / 13G · last 365d]")
        for a in activists[:6]:
            form = a.get("form") or ""
            filer = (a.get("filer_name") or "—")[:40]
            pct = a.get("pct_owned")
            pct_str = f"{pct:.1f}%" if isinstance(pct, (int, float)) else "—"
            fdate = a.get("filing_date") or ""
            kind = "ACTIVIST INTENT" if "13D" in form else "passive 5%+"
            lines.append(
                f"  {fdate} · {form} · {filer} · {pct_str}  ({kind})"
            )

    # ---- EARNINGS CALL COMMENTARY — last 2 calls, trimmed --------------
    transcripts = extras.get("transcripts") or []
    if transcripts:
        lines.append(
            "\n[EARNINGS CALL COMMENTARY · prepared remarks excerpt · most recent first]"
        )
        for t in transcripts[:2]:
            cd = t.get("call_date") or "—"
            period = t.get("period") or ""
            label = f"{cd}" + (f" · {period}" if period else "")
            lines.append(f"  --- CALL: {label} ---")
            body = (t.get("body") or "")[:_TRANSCRIPT_PROMPT_SLICE]
            # Indent every line so the model treats it as quoted content,
            # not as instructions.
            for ln in body.split("\n"):
                ln = ln.strip()
                if not ln:
                    continue
                lines.append(f"  | {ln}")

    return "\n".join(lines)


# ----------------------------------------------------------------------
# Source-audit accessor — what Claude actually saw.
#
# `gather_source_rows()` returns a structured list of every data source
# fed into the thesis prompt, paired with the EXACT raw lines that
# source contributed to the blob. The Research-tab "Sources" section
# renders this so the user can verify Claude isn't fabricating numbers
# in the executive summary.
#
# NOTE: this MUST stay in lock-step with `_data_blob()` above. The raw
# lines come from re-parsing the blob, so adding a new block in
# `_data_blob` without adding a matching row here will surface as a
# silently missing source in the UI.
# ----------------------------------------------------------------------
@dataclass
class SourceRow:
    """One data source fed to Claude when building the thesis.

    `raw_lines` is the EXACT slice of `_data_blob()` output that this
    source contributed — so the user can see byte-for-byte what
    Claude was given for this category.
    """
    id: str
    label: str
    provider: str
    present: bool
    summary: str
    raw_lines: list = field(default_factory=list)


def _split_data_blob_into_blocks(blob: str) -> dict:
    """Parse `_data_blob()` output into `{header: [lines]}`.

    Each `[BLOCK NAME ...]` line opens a new block. Everything before
    the first bracketed header lands in `"__preamble__"`. The header
    key is the uppercased first token before ` · ` (so
    `[INSIDER ACTIVITY · last 180 days · OpenInsider]` -> `INSIDER
    ACTIVITY`).
    """
    blocks: dict = {"__preamble__": []}
    current = "__preamble__"
    for line in blob.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("[") and "]" in stripped:
            inner = stripped[1:stripped.index("]")]
            current = inner.split(" · ")[0].strip().upper()
            blocks.setdefault(current, [])
        blocks.setdefault(current, []).append(line)
    return blocks


def gather_source_rows(snapshot: dict, sections: dict, sentiment: dict,
                       extras: dict) -> list:
    """Structured roster of every data source Claude was given for this
    thesis, paired with the exact lines each source put into the prompt
    blob. Empty sources still appear in the list (with `present=False`
    and `raw_lines=[]`) so the UI can show what was missing.
    """
    blob = _data_blob(snapshot, sections, sentiment, extras)
    blocks = _split_data_blob_into_blocks(blob)

    def lines_for(*headers: str) -> list:
        """Concatenate lines for one or more block headers, dropping
        leading blanks that come from the `\\n[HEADER]` joiner."""
        out: list = []
        for h in headers:
            chunk = list(blocks.get(h) or [])
            if not out:
                while chunk and chunk[0].strip() == "":
                    chunk.pop(0)
            out.extend(chunk)
        return out

    snap = snapshot or {}
    info = extras.get("info") or {}
    rows: list = []

    # 1. Market snapshot — price, sector, business desc, leadership.
    snap_lines = lines_for("__preamble__", "BUSINESS DESCRIPTION",
                           "LEADERSHIP")
    parts: list = []
    if snap.get("name"):
        parts.append(str(snap["name"]))
    if snap.get("sector"):
        parts.append(str(snap["sector"]))
    if snap.get("price") is not None:
        parts.append(f"${snap['price']:.2f}")
    rows.append(SourceRow(
        id="snapshot",
        label="Market snapshot",
        provider="yfinance · .info",
        present=bool(snap.get("ticker") or snap.get("name")),
        summary=" · ".join(parts) if parts else "empty",
        raw_lines=snap_lines,
    ))

    # 2. Analyst consensus — price targets, rating distribution.
    pt = info.get("targetMeanPrice")
    n_an = info.get("numberOfAnalystOpinions")
    if pt and n_an:
        analyst_summary = f"PT ${pt:.0f} · {n_an} analysts"
    elif pt:
        analyst_summary = f"PT ${pt:.0f}"
    elif info.get("recommendationKey"):
        analyst_summary = info["recommendationKey"]
    else:
        analyst_summary = "empty"
    rows.append(SourceRow(
        id="analysts",
        label="Analyst consensus",
        provider="yfinance · .info (analyst targets + rating dist)",
        present=bool(pt or info.get("recommendationKey")),
        summary=analyst_summary,
        raw_lines=lines_for("ANALYST CONSENSUS"),
    ))

    # 3. KPI sections — local computation from yfinance fundamentals.
    kpi_headers = ("OVERVIEW", "VALUATION", "GROWTH", "QUALITY", "HEALTH",
                   "AI", "INCOME", "FINE")
    n_kpi_sections = sum(1 for h in kpi_headers if blocks.get(h))
    rows.append(SourceRow(
        id="kpis",
        label="KPI sections",
        provider="computed locally · yfinance fundamentals",
        present=n_kpi_sections > 0,
        summary=(f"{n_kpi_sections} sections" if n_kpi_sections
                 else "empty"),
        raw_lines=lines_for(*kpi_headers),
    ))

    # 4. Top institutional holders (yfinance Holders endpoint).
    ih = extras.get("inst_holders") or []
    rows.append(SourceRow(
        id="yf_holders",
        label="Top institutional holders",
        provider="yfinance · Holders",
        present=bool(ih),
        summary=f"{len(ih)} holders" if ih else "empty",
        raw_lines=lines_for("TOP INSTITUTIONAL HOLDERS"),
    ))

    # 5. Earnings history (beats / misses streak, next earnings date).
    streak = extras.get("earnings_streak") or []
    if streak:
        beats = sum(1 for r in streak
                    if isinstance(r.get("surprise_pct"), (int, float))
                    and r["surprise_pct"] > 0)
        misses = sum(1 for r in streak
                     if isinstance(r.get("surprise_pct"), (int, float))
                     and r["surprise_pct"] < 0)
        earnings_summary = (f"{len(streak)}Q · {beats} beats / "
                            f"{misses} misses")
    else:
        earnings_summary = "empty"
    rows.append(SourceRow(
        id="earnings",
        label="Earnings history",
        provider="yfinance · SQLite earnings table",
        present=bool(streak),
        summary=earnings_summary,
        raw_lines=lines_for("EARNINGS HISTORY"),
    ))

    # 6. Recent SEC filings (EDGAR full-text-indexed).
    filings = extras.get("filings_recent") or []
    rows.append(SourceRow(
        id="filings",
        label="Recent SEC filings",
        provider="EDGAR · SQLite filings table · last 120d",
        present=bool(filings),
        summary=(f"{len(filings)} filings" if filings else "empty"),
        raw_lines=lines_for("RECENT SEC FILINGS"),
    ))

    # 7. Sentiment aggregate (Reddit + StockTwits + news + HN).
    sent = sentiment or {}
    counts = sent.get("counts") or {}
    total_posts = sum(int(v or 0) for v in counts.values())
    sent_present = bool(total_posts or sent.get("current") is not None)
    if sent_present:
        sent_summary = f"{total_posts} posts · 30d window"
        if sent.get("delta") is not None:
            sent_summary += f" · shift {sent['delta']:+.2f}"
    else:
        sent_summary = "empty"
    rows.append(SourceRow(
        id="sentiment",
        label="Sentiment aggregate",
        provider="Reddit · StockTwits · news · HN · 30d",
        present=sent_present,
        summary=sent_summary,
        raw_lines=lines_for("SENTIMENT"),
    ))

    # 8. Insider activity (OpenInsider) + Form 4 mechanical/discretionary
    # breakdown (EDGAR Form 4 parsing).
    ins_sum = extras.get("insider_summary") or {}
    ins_count = (ins_sum.get("buy_n") or 0) + (ins_sum.get("sell_n") or 0)
    f4 = extras.get("form4_breakdown") or {}
    f4_present = (
        (f4.get("discretionary_buy_n") or 0)
        + (f4.get("discretionary_sell_n") or 0)
        + (f4.get("plan_sell_n") or 0)
    ) > 0
    if ins_count and f4_present:
        ins_summary = f"{ins_count} txns · Form 4 breakdown · 180d"
    elif ins_count:
        ins_summary = f"{ins_count} txns · 180d"
    elif f4_present:
        ins_summary = "Form 4 breakdown only · 180d"
    else:
        ins_summary = "empty"
    rows.append(SourceRow(
        id="insider",
        label="Insider activity",
        provider="OpenInsider · EDGAR Form 4 · last 180d",
        present=bool(ins_count) or f4_present,
        summary=ins_summary,
        raw_lines=lines_for("INSIDER ACTIVITY", "FORM 4 BREAKDOWN"),
    ))

    # 9. 13F institutional holders (EDGAR, curated holder CIK list).
    db_holders = extras.get("institutional_holdings_db") or []
    period = (db_holders[0].get("period_end") if db_holders else None) or ""
    rows.append(SourceRow(
        id="thirteenf",
        label="13F institutional holders",
        provider="EDGAR · curated holder CIK list",
        present=bool(db_holders),
        summary=(f"{len(db_holders)} holders · {period}"
                 if db_holders else "empty"),
        raw_lines=lines_for("13F INSTITUTIONAL HOLDERS"),
    ))

    # 10. Valuation history (P/B, P/S, P/E by year).
    vh = extras.get("valuation_history") or []
    rows.append(SourceRow(
        id="val_history",
        label="Valuation history",
        provider="stockanalysis.com · annual",
        present=bool(vh),
        summary=f"{len(vh)} years" if vh else "empty",
        raw_lines=lines_for("VALUATION HISTORY"),
    ))

    # 11. Activist filings (SC 13D / 13G, last 365d).
    activists = extras.get("activist_filings") or []
    rows.append(SourceRow(
        id="activists",
        label="Activist filings",
        provider="EDGAR · SC 13D / 13G · last 365d",
        present=bool(activists),
        summary=(f"{len(activists)} filings" if activists else "empty"),
        raw_lines=lines_for("ACTIVIST FILINGS"),
    ))

    # 12. Earnings call transcripts (prepared remarks, ~2500 chars each).
    transcripts = extras.get("transcripts") or []
    rows.append(SourceRow(
        id="transcripts",
        label="Earnings call transcripts",
        provider=(f"transcripts source · prepared remarks "
                  f"(~{_TRANSCRIPT_PROMPT_SLICE} chars/call)"),
        present=bool(transcripts),
        summary=(f"{len(transcripts)} calls" if transcripts
                 else "empty"),
        raw_lines=lines_for("EARNINGS CALL COMMENTARY"),
    ))

    # 13. Investor strategy (STRATEGY.md). Not in the data blob —
    # prepended to every Claude prompt as a `<investor-strategy>` block.
    strategy_text = ""
    try:
        strategy_text = load_strategy().as_prompt()
    except Exception:
        strategy_text = ""
    strategy_lines = (strategy_text.split("\n") if strategy_text else [])
    rows.append(SourceRow(
        id="strategy",
        label="Investor strategy",
        provider="STRATEGY.md · system prompt for every Claude call",
        present=bool(strategy_text),
        summary=(f"{len(strategy_lines)} lines"
                 if strategy_text else "empty"),
        raw_lines=strategy_lines,
    ))

    return rows


# ----------------------------------------------------------------------
# Validation
# ----------------------------------------------------------------------
_NONEMPTY_LIST_PATHS: frozenset = frozenset({
    ("strategy_check",),
    ("bull",),
    ("bear",),
    ("catalysts",),
    ("optionality",),
})


def _validate_thesis(data: Any) -> list:
    """Return a list of missing required paths. Empty list = valid.

    Strict mode (user opted in): any missing required field makes the
    whole response invalid. Top-level list fields must also be
    non-empty (see `_NONEMPTY_LIST_PATHS`).
    """
    if not isinstance(data, dict):
        return ["<root is not a dict>"]

    missing: list = []
    for path in REQUIRED_PATHS:
        node: Any = data
        for key in path:
            if not isinstance(node, dict) or key not in node:
                missing.append(".".join(path))
                break
            node = node[key]
        else:
            # Reached the leaf.
            if path in _NONEMPTY_LIST_PATHS:
                if not isinstance(node, list) or not node:
                    missing.append(".".join(path) + " (empty)")
            elif isinstance(node, str) and not node.strip():
                missing.append(".".join(path) + " (blank)")
    return missing


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------
def _build_part(part_name: str, schema: str, kind: str,
                ticker: str, data_blob: str, *,
                claude: Claude, force: bool, handle) -> ClaudeResult:
    """One sub-call for one schema partial. Returns the raw ClaudeResult;
    `build_thesis` merges the .data dicts and aggregates cost/latency."""
    prompt = PROMPT_TEMPLATE_PART.format(
        ticker=ticker.upper(),
        part_rules=PART_RULES[part_name],
        schema=schema.strip(),
        data_blob=data_blob,
    )
    return claude.call(kind, ticker, prompt, content="",
                       force=force, handle=handle)


def build_thesis(ticker: str,
                 snapshot: dict,
                 sections: dict,
                 sentiment: dict,
                 *,
                 force: bool = False,
                 claude: Claude | None = None,
                 handle=None,
                 extras: dict | None = None) -> tuple[dict | None, ClaudeResult]:
    """Build the full v2 thesis dict by fanning out 3 parallel Claude
    calls (core / deep / forward) and merging the results.

    Wall-clock is dominated by the slowest of the three calls (~60s on
    Sonnet) instead of a single 160s monolithic call. Each partial is
    independently cached so re-runs that touch only one slice can hit
    cache for the other two.

    `extras` (optional) can be pre-computed; otherwise gathered here.
    `handle` is a `fire.jobs.JobHandle` for cancellation.

    Strict validation runs on the MERGED dict — if any required field
    is missing across all three partials, the result is marked
    ok=False and the renderer falls back to the heuristic mock.

    Returns the same `(data, result)` shape as before so existing
    callers (deep_dive, pre-warm) are unchanged. The returned
    `ClaudeResult.cost_usd` is the sum of the three partial costs;
    `latency_ms` is the MAX (the wall-clock).
    """
    c = claude or Claude()
    extras = extras if extras is not None else gather_extras(ticker)
    blob = _data_blob(snapshot, sections, sentiment, extras)

    # Fan out the 3 partials. Pool of 3 — each spawns a `claude` CLI
    # subprocess; the subprocesses run concurrently regardless of GIL
    # because the Python threads block on I/O (subprocess.communicate).
    results: dict = {}
    with ThreadPoolExecutor(max_workers=len(_PARTS)) as pool:
        future_to_part = {
            pool.submit(_build_part, name, schema, kind, ticker, blob,
                        claude=c, force=force, handle=handle): name
            for (name, schema, kind) in _PARTS
        }
        for fut in future_to_part:
            name = future_to_part[fut]
            try:
                results[name] = fut.result()
            except Exception as exc:
                # Synthesize a failed ClaudeResult so the merge below
                # can attribute the error to a specific partial.
                results[name] = ClaudeResult(
                    ok=False, text="", data=None,
                    cost_usd=None, latency_ms=0,
                    error=f"{name}: {exc}"[:240], cached=False,
                )

    # Bail fast if any sub-call failed at the transport layer (CLI
    # error, timeout, bad JSON). Strict mode — partial successes don't
    # help the user because validation requires the whole payload.
    failures = [r for r in results.values() if not r.ok]
    if failures:
        any_first = failures[0]
        err = "; ".join(
            f"{name}: {r.error or 'unknown'}"
            for name, r in results.items() if not r.ok
        )
        return None, ClaudeResult(
            ok=False, text=any_first.text or "", data=None,
            cost_usd=sum((r.cost_usd or 0.0) for r in results.values()) or None,
            latency_ms=max((r.latency_ms or 0) for r in results.values()),
            error=err[:600], cached=False,
        )

    # Merge the 3 partial dicts. Each one owns disjoint top-level keys,
    # so a simple dict-update preserves everything. (If Claude ever
    # bleeds keys across partials, the later partial wins — order is
    # core → deep → forward, so forward wins ties.)
    merged: dict = {}
    for name, _, _ in _PARTS:
        data = results[name].data
        if isinstance(data, dict):
            merged.update(data)

    # Compose an aggregate ClaudeResult: cost = sum, latency = max,
    # cached = True only if ALL three were cache hits.
    total_cost = sum((r.cost_usd or 0.0) for r in results.values())
    max_latency = max((r.latency_ms or 0) for r in results.values())
    all_cached = all(r.cached for r in results.values())
    agg = ClaudeResult(
        ok=True,
        text=json.dumps(merged),
        data=merged,
        cost_usd=total_cost if total_cost > 0 else None,
        latency_ms=max_latency,
        error=None,
        cached=all_cached,
    )

    missing = _validate_thesis(merged)
    if missing:
        err = "thesis_v2 missing required fields: " + ", ".join(missing[:8])
        return None, ClaudeResult(
            ok=False, text=agg.text, data=merged,
            cost_usd=agg.cost_usd, latency_ms=agg.latency_ms,
            error=err, cached=agg.cached,
        )

    return merged, agg
