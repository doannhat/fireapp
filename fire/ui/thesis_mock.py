"""Hardcoded thesis card structure.

Lets Phase 5 ship before Phase 3 wires the real Claude CLI. The mocked
structure is deliberately conservative — strategy criteria reflect the
user's investment-memory file, and the math (sizing, scenarios) is
filled by simple heuristics on the real data.

Once Phase 3 lands, swap `build_mock_thesis` for
`fire.processors.thesis.build_thesis`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def _find_kpi(kpis: list, label_substr: str) -> dict | None:
    for k in kpis:
        if label_substr.lower() in k.get("label", "").lower():
            return k
    return None


def _kpi_number(kpis: list, label_substr: str) -> float | None:
    """Pull a KPI's value as a float, stripping signs/percents."""
    kpi = _find_kpi(kpis, label_substr)
    if not kpi:
        return None
    raw = (kpi.get("value") or "").replace("−", "-").replace("+", "").replace(",", "")
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_mock_thesis(snap: dict, sections: dict, sentiment: dict) -> dict:
    """Build a thesis dict from real metrics — the *prose* is hardcoded but
    the *numbers* and *strategy fit* are derived from actual data.

    This is intentionally a starter — Phase 3 replaces it with Claude.
    """
    ticker = snap.get("ticker", "—")
    name = snap.get("name", ticker)
    price = snap.get("price")
    market_cap = snap.get("market_cap") or 0

    valuation = sections.get("valuation") or []
    growth = sections.get("growth") or []
    quality = sections.get("quality") or []
    fine = sections.get("fine") or []

    pe = _kpi_number(valuation, "P/E trailing")
    peg = _kpi_number(valuation, "PEG")
    rev_yoy = _kpi_number(growth, "Revenue YoY")
    eps_yoy = _kpi_number(growth, "EPS YoY")
    roe = _kpi_number(quality, "ROE")
    inst = _kpi_number(fine, "Institutional")

    # Strategy checks — wired to user_investment_strategy memory.
    # v2: each row carries `evidence` — the specific number that drove it.
    strategy = []

    # 5-10x in 2-3yr: heuristic on size + recent revenue trajectory
    large_cap = market_cap and market_cap > 1e12  # >$1T
    moonshot = (rev_yoy or 0) > 40
    if large_cap:
        strategy.append({
            "status": "fail",
            "label": "5–10× upside in 2–3yr",
            "verdict": "LOW",
            "evidence": f"Mkt cap _{market_cap / 1e12:.1f}T_ — 5× requires +${market_cap * 4 / 1e12:.0f}T new value.",
        })
    elif moonshot:
        strategy.append({
            "status": "pass",
            "label": "5–10× upside in 2–3yr",
            "verdict": "PLAUSIBLE",
            "evidence": f"Revenue +_{rev_yoy:.0f}%_ YoY off a still-small base.",
        })
    else:
        strategy.append({
            "status": "partial",
            "label": "5–10× upside in 2–3yr",
            "verdict": "DEPENDS",
            "evidence": "Growth + multiple expansion both required.",
        })

    # Hidden gem: large institutional ownership = not hidden
    if inst is not None and inst > 60:
        strategy.append({
            "status": "fail",
            "label": "Hidden gem · unloved by retail",
            "verdict": "NO",
            "evidence": f"Institutional own _{inst:.0f}%_ — crowded.",
        })
    elif inst is not None and inst < 30:
        strategy.append({
            "status": "pass",
            "label": "Hidden gem · unloved by retail",
            "verdict": "YES",
            "evidence": f"Institutional own only _{inst:.0f}%_ — room for new buyers.",
        })
    else:
        strategy.append({
            "status": "partial",
            "label": "Hidden gem · unloved by retail",
            "verdict": "MAYBE",
            "evidence": (
                f"Institutional own _{inst:.0f}%_ — mid-cohort." if inst is not None
                else "Ownership data missing — unclassified."
            ),
        })

    # AI super-cycle exposure: always pass for a watchlist ticker (curation)
    strategy.append({
        "status": "pass",
        "label": "AI super-cycle exposure",
        "verdict": "ON-THESIS",
        "evidence": "Curated into FIRE watchlist on AI-value-chain criteria.",
    })

    # 2-3yr quality compounder: ROE proxy
    if roe and roe > 25:
        strategy.append({
            "status": "pass",
            "label": "2–3yr quality compounder",
            "verdict": "GOOD",
            "evidence": f"ROE _{roe:.0f}%_ — compounds faster than hurdle rate.",
        })
    elif roe and roe > 12:
        strategy.append({
            "status": "partial",
            "label": "2–3yr quality compounder",
            "verdict": "OK",
            "evidence": f"ROE _{roe:.0f}%_ — solid but below 25% elite bar.",
        })
    else:
        strategy.append({
            "status": "fail",
            "label": "2–3yr quality compounder",
            "verdict": "WEAK",
            "evidence": f"ROE _{roe:.0f}%_ — below quality threshold." if roe else "ROE missing — quality unverified.",
        })

    passes = sum(1 for s in strategy if s["status"] == "pass")
    total = len(strategy)

    # Verdict — one flowing paragraph that walks the same arc the
    # real Claude pass produces: description → moat hint → financial
    # snapshot → strategy fit → punchline. The mock can't author novel
    # moat language, so we fall back on sector + KPI cues; once Claude
    # runs, this is replaced wholesale.
    sector = (snap.get("sector") or "").lower()
    industry = (snap.get("industry") or "").lower()

    # (a) Description + AI-stack layer (best-effort from sector text).
    if "semiconductor" in industry or "semiconductor" in sector:
        layer_phrase = "picks-and-shovels at the compute / silicon layer of the AI stack"
    elif "communication" in industry or "network" in industry:
        layer_phrase = "at the network and connectivity layer of the AI stack"
    elif "utilities" in sector or "energy" in sector:
        layer_phrase = "at the power / electrification layer feeding AI data centers"
    elif "software" in industry or "technology" in sector:
        layer_phrase = "at the software / application layer riding the AI super-cycle"
    elif "materials" in sector or "metals" in industry:
        layer_phrase = "at the materials layer supplying the AI build-out"
    else:
        layer_phrase = "exposed to the AI super-cycle through its core business"
    desc = (
        f"{name} ({ticker}) operates in {snap.get('industry') or snap.get('sector') or 'the broader market'} — "
        f"{layer_phrase}."
    )

    # (b) Moat hint — heuristic from ROE / margins / size.
    if roe and roe > 30:
        moat_hint = (
            f"Operating economics screen elite — _{roe:.0f}%_ ROE points to a "
            f"durable moat (scale, IP, or pricing power)."
        )
    elif large_cap:
        moat_hint = (
            "Mega-cap scale itself functions as the moat — distribution, "
            "balance-sheet, and ecosystem lock-in compound."
        )
    else:
        moat_hint = (
            "Moat strength is the open question — confirm via the deep-dive "
            "moat block once Claude runs."
        )

    # (c) Financial snapshot — quote concrete numbers we have.
    fin_parts = []
    if rev_yoy is not None:
        fin_parts.append(f"revenue _{rev_yoy:+.0f}%_ YoY")
    if eps_yoy is not None:
        fin_parts.append(f"EPS _{eps_yoy:+.0f}%_")
    if roe is not None:
        fin_parts.append(f"ROE _{roe:.0f}%_")
    fin = (
        "On the numbers, " + ", ".join(fin_parts) + "."
        if fin_parts else
        "Financial trajectory pending fresh fundamentals."
    )

    # (d) Strategy fit — compact version of the four checks.
    fit_parts = []
    if large_cap:
        fit_parts.append("5-10× is mathematically capped at this size")
    elif moonshot:
        fit_parts.append("5-10× is plausible off this growth base")
    if inst is not None and inst > 60:
        fit_parts.append(f"hidden-gem _fails_ at {inst:.0f}% institutional")
    elif inst is not None and inst < 30:
        fit_parts.append(f"hidden-gem _clears_ at {inst:.0f}% institutional")
    if roe and roe > 25:
        fit_parts.append(f"quality-compounder clears at {roe:.0f}% ROE")
    fit = (
        "Against the strategy, " + "; ".join(fit_parts) + "."
        if fit_parts else
        "Against the strategy, signals are mixed — see the four checks below."
    )

    # (e) Punchline — bolded, single sentence.
    if passes >= 3:
        punch = (
            f"**Strong fit — {ticker} earns conviction sizing in the AI sleeve.**"
        )
    elif passes == 2 and large_cap:
        punch = (
            f"**Defensive AI anchor, not a 5-10× hunt — {ticker} is a core "
            f"holding, not an alpha bet.**"
        )
    elif passes <= 1:
        punch = (
            f"**Limited fit — {ticker} stays on the watchlist until more "
            f"criteria pass.**"
        )
    else:
        punch = (
            f"**Mixed signals — size {ticker} as an exploratory position, "
            f"not full-conviction.**"
        )

    verdict = " ".join([desc, moat_hint, fin, fit, punch])

    # Sizing recommendations — defaults sized to risk
    if large_cap:
        sizing = {
            "Suggested": "_2–3%_ of AI sleeve · defensive anchor, not alpha",
            "Entry": f"scale in below current; full size on 15%+ pullback",
            "Income": "30-day 5% OTM covered calls when IV is elevated",
            "Constraint": "do not pyramid — keep AI sleeve for hidden gems",
        }
    elif passes >= 3:
        sizing = {
            "Suggested": "_4–6%_ of AI sleeve · conviction position",
            "Entry": "DCA over 6–8 weeks, no single-shot entry",
            "Income": "selective CCs only on extended runs",
            "Constraint": "earnings hedges via long-dated OTM puts",
        }
    else:
        sizing = {
            "Suggested": "_1–2%_ of AI sleeve · exploratory only",
            "Entry": "wait for a 20%+ drawdown before initial buy",
            "Income": "n/a — too small to bother",
            "Constraint": "re-evaluate at next earnings",
        }

    # Bull / bear — hardcoded for now; Phase 3 replaces with extracted themes.
    bull = []
    bear = []
    if peg and peg < 1.0:
        bull.append(f"**PEG of {peg:.2f}** — growth doing more than half "
                    f"the work justifying the multiple.")
    if eps_yoy and rev_yoy and eps_yoy > rev_yoy * 1.2:
        bull.append(f"**EPS growing faster than revenue ({eps_yoy:.0f}% vs "
                    f"{rev_yoy:.0f}%)** — textbook operating leverage.")
    if roe and roe > 50:
        bull.append(f"**ROE of {roe:.0f}%** on a normal cost of capital. "
                    f"Cash compounds faster than the hurdle rate.")
    if not bull:
        bull.append("Catalysts pending — Phase 3 Claude pre-warm will "
                    "extract bull themes from filings and transcripts.")

    if pe and pe > 30:
        bear.append(f"**Trailing P/E of {pe:.0f}** — priced for continued "
                    f"blistering growth. Multiple compression is the "
                    f"asymmetric risk.")
    if inst and inst > 70:
        bear.append(f"**{inst:.0f}% institutional ownership** — retail "
                    f"saturated. Underperformance forces selling cascade.")
    if large_cap and (rev_yoy or 0) > 50:
        bear.append("**Mean-reverting growth** at this revenue base — "
                    "history says +50%+ YoY rarely lasts beyond 4 quarters.")
    if not bear:
        bear.append("Bear case pending — Phase 3 Claude pre-warm will "
                    "extract risk factors from the 10-K.")

    # Ownership card — pure data, no fabricated 13F flow numbers.
    # Institutional %, insider %, short interest from the snapshot.
    insider = _kpi_number(fine, "Insider own")
    ownership = None
    if inst is not None or insider is not None:
        rows = {}
        if inst is not None:
            cls = "neg" if inst > 75 else "flat" if inst < 30 else "pos"
            rows["Institutional"] = {
                "value": f"{inst:.0f}% of float",
                "class": cls,
            }
        if insider is not None:
            rows["Insider held"] = {
                "value": f"{insider:.1f}%",
                "class": "flat",
            }
        short = _kpi_number(fine, "Short interest")
        if short is not None:
            rows["Short interest"] = {
                "value": f"{short:.1f}%",
                "class": "neg" if short > 5 else "flat",
            }
        if inst and inst > 70:
            takeaway = ("Crowded ownership — **retail saturation is priced in**. "
                        "Marginal-buyer thesis matters more than flow.")
            tag = ("amber", "consensus long")
        else:
            takeaway = "Ownership profile keeps room for new buyers."
            tag = ("cool", "uncrowded")
        ownership = {"rows": rows, "tag": tag, "takeaway": takeaway}

    # 2-3y scenarios — bull / base / bear from price and revenue trajectory
    scenarios = None
    if price and rev_yoy is not None:
        # Crude scenarios — Phase 3 will replace with proper Claude reasoning
        bull_mult = max(1.5, 1 + (rev_yoy / 100) * 1.5)
        base_mult = max(1.0, 1 + (rev_yoy / 100) * 0.7)
        bear_mult = 0.6
        scenarios = {
            "bull": {
                "desc": f"+{rev_yoy:.0f}% rev CAGR holds, mult flat",
                "multi": f"{bull_mult:.1f}",
                "px": f"${price * bull_mult:.0f}",
            },
            "base": {
                "desc": "growth decays, mult compresses",
                "multi": f"{base_mult:.1f}",
                "px": f"${price * base_mult:.0f}",
            },
            "bear": {
                "desc": "demand pause + margin revert",
                "multi": f"{bear_mult:.1f}",
                "px": f"${price * bear_mult:.0f}",
            },
        }
        if bull_mult < 5:
            scenarios["tag"] = ("warm", "misses 5–10×")
            scenarios["takeaway"] = (
                "Asymmetry stays within a normal-distribution band — "
                "**falls short of 5–10×** from this base. Look downstream "
                "for the moonshot bucket."
            )
        else:
            scenarios["tag"] = ("cool", "5–10× viable")
            scenarios["takeaway"] = (
                "Bull-case math actually clears your 5–10× bar — "
                "**this is the rare moonshot in the cohort**."
            )
        # Asymmetry — bull / bear ratio relative to current price.
        upside_pct = (bull_mult - 1) * 100
        downside_pct = (1 - bear_mult) * 100
        if downside_pct > 0:
            scenarios["asymmetry"] = f"+{upside_pct:.0f}% / −{downside_pct:.0f}%"

    # Headline (v2) — conviction tier follows passes; variant-view is
    # deliberately blank in the heuristic mock so the user sees the
    # gap and is nudged to run the real Claude pass.
    if passes >= 3:
        call = "ADD"
        one_liner = f"{ticker} clears 3+ strategy bars by the numbers."
        variant = "_Heuristic mock — run Claude pre-warm for an authored variant view._"
    elif passes == 2:
        call = "WATCH"
        one_liner = f"{ticker} clears half the strategy bars — partial fit."
        variant = "_Heuristic mock — run Claude pre-warm for an authored variant view._"
    elif passes <= 1:
        call = "PASS"
        one_liner = f"{ticker} clears one or fewer bars — weak fit."
        variant = "_Heuristic mock — run Claude pre-warm for an authored variant view._"
    else:
        call = "WATCH"
        one_liner = f"{ticker} mixed signals."
        variant = "_Heuristic mock — run Claude pre-warm for an authored variant view._"
    headline = {"call": call, "one_liner": one_liner, "variant_view": variant}

    # Catalysts (v2) — only items derivable from snapshot data. The
    # mock cannot author novel events, so we offer date anchors the
    # user can interpret.
    catalysts = []
    if snap.get("next_earnings"):
        try:
            ne = snap["next_earnings"]
            ne_str = ne.strftime("%d %b %Y").upper() if hasattr(ne, "strftime") else str(ne)
        except Exception:
            ne_str = str(snap["next_earnings"])
        catalysts.append({
            "when": ne_str,
            "event": f"{ticker} next earnings print",
            "edge": "AI-segment growth + margin trajectory either confirm or break the trend.",
            "confidence": "high",
        })
    catalysts.append({
        "when": "rolling",
        "event": "Hyperscaler capex prints (META / MSFT / GOOGL / AMZN)",
        "edge": "Direct read-through on AI-infra demand cadence.",
        "confidence": "moderate",
    })

    # Pre-mortem (v2) — kill-switch tied to a concrete observable.
    if rev_yoy is not None:
        kill_threshold = max(0, rev_yoy * 0.5)
        kill_switch = (
            f"Two consecutive quarters of revenue YoY <{kill_threshold:.0f}% "
            f"(half today's _{rev_yoy:.0f}%_ run-rate)."
        )
    else:
        kill_switch = "Two consecutive quarters where the AI-segment narrative breaks."
    premortem = {
        "kill_switch": kill_switch,
        "ignored_risks": [
            "**Hyperscaler capex** is the binding constraint, not chip supply.",
            "**Multiple compression** if 10Y rates re-rate higher.",
        ],
    }

    # Optionality (v2) — heuristic options-not-in-base-case. The mock
    # offers categories; Claude will fill specifics.
    optionality = [
        "**Sovereign AI** demand — non-US gov / enterprise deployments not modeled.",
        "**Capital-return surprise** — buyback acceleration or special div would re-rate.",
    ]

    return {
        "headline": headline,
        "verdict": verdict,
        "strategy_fit": {"passes": passes, "total": total},
        "strategy_check": strategy,
        "sizing": sizing,
        "bull": bull,
        "bear": bear,
        "catalysts": catalysts,
        "premortem": premortem,
        "optionality": optionality,
        "ownership": ownership,
        "scenarios": scenarios,
        "meta": {
            "sources": "data-only · heuristic mock",
            "cost": "$0.00",
            "freshness": datetime.now().strftime("%H:%M"),
        },
    }
