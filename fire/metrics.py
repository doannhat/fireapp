"""Section-by-section KPI assembly for the Research tab.

Pure-data functions: each one takes a ticker and returns a dict of values
that the renderer turns into KPI tiles. yfinance is the source of truth;
when a value is missing we leave it out of the dict so the renderer
shows nothing rather than a fake number.

Honest-data philosophy (see IMPLEMENTATION_PLAN.md):

  - yfinance / SEC: ✓ shown
  - synthetic peer medians, smart-money flows, top-4 customer
    concentration: skipped unless we have a real source

`build_research_data(ticker)` is the top-level entry point; it fetches
the ticker once and assembles every section.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import yfinance as yf

from . import db
from .config import setting


# --------------------------------------------------------------------------
# yfinance bundle — one fetch per ticker
# --------------------------------------------------------------------------
@dataclass
class TickerBundle:
    """All the yfinance data the renderer needs, fetched once."""
    ticker: str
    info: dict
    fast_info: dict
    income_a: pd.DataFrame | None
    income_q: pd.DataFrame | None
    balance_a: pd.DataFrame | None
    balance_q: pd.DataFrame | None
    cashflow_a: pd.DataFrame | None
    cashflow_q: pd.DataFrame | None
    recommendations: pd.DataFrame | None
    inst_holders: pd.DataFrame | None
    price_history: pd.Series | None
    earnings_dates: pd.DataFrame | None
    options_expirations: tuple


def _safe(getter):
    try:
        v = getter()
    except Exception:
        return None
    if isinstance(v, pd.DataFrame) and v.empty:
        return None
    return v


def fetch_bundle(ticker: str) -> TickerBundle:
    """Fetch everything yfinance can give us in one go. Defensive on each call."""
    t = yf.Ticker(ticker)
    info = _safe(lambda: t.info) or {}
    fi_raw = _safe(lambda: t.fast_info)
    fast_info = {}
    if fi_raw is not None:
        for k in ("lastPrice", "previousClose", "marketCap",
                 "yearHigh", "yearLow", "fiftyDayAverage",
                 "twoHundredDayAverage", "tenDayAverageVolume",
                 "threeMonthAverageVolume", "shares"):
            try:
                fast_info[k] = fi_raw[k]
            except Exception:
                fast_info[k] = None
    options = _safe(lambda: t.options) or ()
    return TickerBundle(
        ticker=ticker.upper(),
        info=info,
        fast_info=fast_info,
        income_a=_safe(lambda: t.income_stmt),
        income_q=_safe(lambda: t.quarterly_income_stmt),
        balance_a=_safe(lambda: t.balance_sheet),
        balance_q=_safe(lambda: t.quarterly_balance_sheet),
        cashflow_a=_safe(lambda: t.cashflow),
        cashflow_q=_safe(lambda: t.quarterly_cashflow),
        recommendations=_safe(lambda: t.recommendations),
        inst_holders=_safe(lambda: t.institutional_holders),
        price_history=_safe(lambda: t.history(period="1y")["Close"]),
        earnings_dates=_safe(lambda: t.get_earnings_dates(limit=12)),
        options_expirations=options,
    )


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
def _num(x):
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def _row(df: pd.DataFrame | None, *candidates: str):
    """Return the first matching row from a yfinance statement (case-insensitive,
    partial match) as a Series indexed by period_end. None if not found."""
    if df is None or df.empty:
        return None
    lower_idx = {str(idx).lower(): idx for idx in df.index}
    for cand in candidates:
        c = cand.lower()
        for key, real in lower_idx.items():
            if key == c:
                return df.loc[real]
        for key, real in lower_idx.items():
            if c in key:
                return df.loc[real]
    return None


def _val(series: pd.Series | None, idx: int = 0):
    """Pull value at column index `idx` (0 = most recent in yfinance frames)."""
    if series is None or len(series) <= idx:
        return None
    try:
        return _num(series.iloc[idx])
    except Exception:
        return None


def _yoy(series: pd.Series | None) -> float | None:
    """% change from period -1 to period 0 (most recent vs year prior)."""
    cur = _val(series, 0)
    prior = _val(series, 1)
    if cur is None or prior is None or prior == 0:
        return None
    return (cur - prior) / abs(prior) * 100.0


def _cagr(series: pd.Series | None, years: int) -> float | None:
    """Annualised growth from period -years to period 0."""
    if series is None or len(series) <= years:
        return None
    end = _val(series, 0)
    start = _val(series, years)
    if end is None or start is None or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1.0 / years) - 1.0) * 100.0


def _fmt_value(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    if abs(v) >= 100:
        return f"{v:,.0f}"
    return f"{v:.{decimals}f}"


def _signed(v: float | None, decimals: int = 1) -> str:
    if v is None:
        return "—"
    return f"{'+' if v >= 0 else '−'}{abs(v):.{decimals}f}"


def _humanize_cap(v: float | None) -> tuple[str, str, str]:
    """Return (ccy_prefix, value, unit) for a dollar amount."""
    if v is None:
        return ("$", "—", "")
    a = abs(v)
    sign = "−" if v < 0 else ""
    if a >= 1e12:
        return (f"{sign}$", f"{v / 1e12:.2f}", "T")
    if a >= 1e9:
        return (f"{sign}$", f"{v / 1e9:.1f}", "B")
    if a >= 1e6:
        return (f"{sign}$", f"{v / 1e6:.0f}", "M")
    return (f"{sign}$", f"{v:,.0f}", "")


def _kpi(label, value, unit="", tag=None, caption="", spark=None, ccy="",
         tag_tip=""):
    """Build a KPI dict. `tag_tip` is the threshold rule that triggered the
    tag — surfaced as a tooltip so the heuristic is transparent."""
    return {
        "label": label,
        "value": value,
        "unit": unit,
        "ccy": ccy,
        "tag": tag,
        "tag_tip": tag_tip,
        "caption": caption,
        "spark": spark,
    }


def _t(key: str, default):
    """Tag-threshold lookup. Reads settings.yaml `tags.<key>` with a fallback."""
    return setting(f"tags.{key}", default)


def _v(key: str, default):
    """Valuation-threshold lookup. Reads settings.yaml `valuation.<key>`."""
    return setting(f"valuation.{key}", default)


def _compute_fcf(bundle: "TickerBundle") -> float | None:
    """Pull free cash flow once, with consistent fallback rules.

    Order of preference:
      1. yfinance info.freeCashflow
      2. yfinance cashflow statement "Free Cash Flow" row
      3. Operating Cash Flow + Capital Expenditure (capex is negative in
         yfinance, so addition is correct)
    """
    cf = _num(bundle.info.get("freeCashflow"))
    if cf:
        return cf
    fcf_row = _row(bundle.cashflow_a, "Free Cash Flow")
    if fcf_row is not None:
        v = _val(fcf_row)
        if v is not None:
            return v
    ocf = _val(_row(bundle.cashflow_a, "Operating Cash Flow",
                    "Total Cash From Operating Activities"))
    cx = _val(_row(bundle.cashflow_a, "Capital Expenditure",
                   "Capital Expenditures"))
    if ocf is not None and cx is not None:
        return ocf + cx
    return None


# --------------------------------------------------------------------------
# Sparkline data extraction
# --------------------------------------------------------------------------
def _series_as_spark(series: pd.Series | None,
                     label: str = "8q", reverse=True) -> dict | None:
    """yfinance series → list of recent floats (oldest→newest), as a spark dict.

    yfinance returns columns in newest-first order; we reverse so the
    sparkline reads left-to-right chronologically.
    """
    if series is None or series.empty:
        return None
    vals = []
    for v in series.dropna():
        f = _num(v)
        if f is not None:
            vals.append(f)
    if reverse:
        vals = list(reversed(vals))
    if len(vals) < 2:
        return None
    return {"data": vals[:8], "label": label}


# --------------------------------------------------------------------------
# Snapshot (ticker bar)
# --------------------------------------------------------------------------
def snapshot(bundle: TickerBundle) -> dict:
    info = bundle.info
    fi = bundle.fast_info
    price = _num(fi.get("lastPrice")) or _num(info.get("currentPrice"))
    prev = _num(fi.get("previousClose")) or _num(info.get("previousClose"))
    market_cap = _num(fi.get("marketCap")) or _num(info.get("marketCap"))
    enterprise = _num(info.get("enterpriseValue"))
    week_hi = _num(fi.get("yearHigh")) or _num(info.get("fiftyTwoWeekHigh"))
    week_lo = _num(fi.get("yearLow")) or _num(info.get("fiftyTwoWeekLow"))
    range_pos = None
    if price is not None and week_hi and week_lo and week_hi != week_lo:
        range_pos = (price - week_lo) / (week_hi - week_lo) * 100

    day_chg = None
    if price is not None and prev:
        day_chg = (price / prev - 1) * 100

    # YTD performance
    ytd = None
    if bundle.price_history is not None and len(bundle.price_history) > 1:
        try:
            jan1 = pd.Timestamp(date(date.today().year, 1, 1), tz=bundle.price_history.index.tz)
            base = bundle.price_history[bundle.price_history.index >= jan1]
            if len(base) > 1 and base.iloc[0]:
                ytd = (base.iloc[-1] / base.iloc[0] - 1) * 100
        except Exception:
            ytd = None

    beta = _num(info.get("beta"))

    # Next earnings
    next_e = None
    if bundle.earnings_dates is not None and not bundle.earnings_dates.empty:
        today = pd.Timestamp.now(tz=bundle.earnings_dates.index.tz)
        future = bundle.earnings_dates[bundle.earnings_dates.index >= today]
        if not future.empty:
            next_e = future.index.min()

    return {
        "ticker": bundle.ticker,
        "name": info.get("longName") or info.get("shortName") or bundle.ticker,
        "exchange": (info.get("exchange") or "").upper(),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "price": price,
        "prev_close": prev,
        "day_chg_pct": day_chg,
        "market_cap": market_cap,
        "enterprise_value": enterprise,
        "week52_high": week_hi,
        "week52_low": week_lo,
        "range_pos_pct": range_pos,
        "ytd_pct": ytd,
        "beta": beta,
        "next_earnings": next_e,
    }


# --------------------------------------------------------------------------
# 01 Overview
# --------------------------------------------------------------------------
def section_overview(bundle: TickerBundle) -> list:
    info = bundle.info
    out = []

    employees = _num(info.get("fullTimeEmployees"))
    if employees is not None:
        out.append(_kpi(
            "Employees",
            f"{employees / 1000:.1f}" if employees >= 1000 else f"{employees:.0f}",
            unit="K" if employees >= 1000 else "",
            caption="Full-time per latest filing.",
        ))

    officers = info.get("companyOfficers") or []
    ceo = None
    for o in officers:
        title = (o.get("title") or "").lower()
        if "ceo" in title or "chief executive" in title:
            ceo = o
            break
    if ceo:
        name = ceo.get("name") or ""
        # Drop honorifics (Mr., Ms., Dr.) for the headline so the name reads cleanly.
        clean = name
        for prefix in ("Mr.", "Ms.", "Mrs.", "Dr.", "Mr ", "Ms ", "Dr "):
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()
                break
        # Use last-name-first family for the headline (e.g. "Jen-Hsun Huang");
        # fall back to the first 24 chars if the name is unusually long.
        headline = clean[:24]
        caption = ""
        if ceo.get("yearBorn"):
            try:
                age = date.today().year - int(ceo["yearBorn"])
                caption = f"Age {age}"
            except (TypeError, ValueError):
                caption = f"Born {ceo['yearBorn']}"
        if ceo.get("title"):
            caption = f"{ceo['title']}" + (f" · {caption}" if caption else "")
        out.append(_kpi(
            "CEO", headline, caption=caption,
        ))

    float_sh = _num(info.get("floatShares"))
    shares_out = _num(info.get("sharesOutstanding"))
    if float_sh:
        ccy, val, unit = _humanize_cap(float_sh)
        # Strip the $ since this is share count, not dollars.
        out.append(_kpi(
            "Float", f"{float_sh / 1e9:.1f}" if float_sh >= 1e9 else f"{float_sh / 1e6:.0f}",
            unit="B" if float_sh >= 1e9 else "M",
            caption=(
                f"of {shares_out / 1e9:.1f}B outstanding"
                if shares_out and shares_out >= 1e9 else "shares freely tradable"
            ),
        ))

    beta = _num(info.get("beta"))
    if beta is not None:
        descriptor = ""
        if beta > 1.0:
            descriptor = f"{(beta - 1) * 100:.0f}% more volatile than market"
        elif beta < 1.0:
            descriptor = f"{(1 - beta) * 100:.0f}% less volatile than market"
        else:
            descriptor = "in line with market"
        out.append(_kpi(
            "Beta", f"{beta:.2f}", caption=descriptor,
        ))

    avg_vol = _num(bundle.fast_info.get("threeMonthAverageVolume")) or \
              _num(bundle.fast_info.get("tenDayAverageVolume")) or \
              _num(info.get("averageVolume"))
    if avg_vol:
        out.append(_kpi(
            "Avg vol", f"{avg_vol / 1e6:.0f}" if avg_vol >= 1e6 else f"{avg_vol / 1e3:.0f}",
            unit="M" if avg_vol >= 1e6 else "K",
            caption="3-month average daily volume.",
        ))

    industry = info.get("industry")
    sector = info.get("sector")
    if industry or sector:
        out.append(_kpi(
            "Sector", industry or sector or "—",
            caption=sector or "",
        ))

    return out


# --------------------------------------------------------------------------
# 02 Valuation
# --------------------------------------------------------------------------
def _val_tag(v, cheap, rich, lower_better=True):
    """Return (style, label, tip) for a value vs (cheap, rich) thresholds.
    `tip` is a one-line explanation surfaced as a tooltip."""
    if v is None:
        return None, ""
    if lower_better:
        if v <= cheap:
            return ("cool", "cheap"), f"value ≤ {cheap} = cheap"
        if v >= rich:
            return ("warm", "rich"), f"value ≥ {rich} = rich"
        return ("neutral", "fair"), f"between {cheap} (cheap) and {rich} (rich)"
    if v >= rich:
        return ("cool", "high"), f"value ≥ {rich} = high"
    if v <= cheap:
        return ("warm", "low"), f"value ≤ {cheap} = low"
    return ("neutral", "fair"), f"between {cheap} (low) and {rich} (high)"


def section_valuation(bundle: TickerBundle) -> list:
    info = bundle.info
    out = []

    pe = _num(info.get("trailingPE"))
    if pe is not None:
        tag, tip = _val_tag(pe, _v("pe_trailing_cheap", 15), _v("pe_trailing_rich", 35))
        out.append(_kpi(
            "P/E trailing", f"{pe:.1f}", unit="×", tag=tag, tag_tip=tip,
            caption="Trailing 12-month earnings multiple.",
        ))

    fwd_pe = _num(info.get("forwardPE"))
    if fwd_pe is not None:
        tag, tip = _val_tag(fwd_pe, _v("pe_forward_cheap", 15), _v("pe_forward_rich", 30))
        out.append(_kpi(
            "P/E forward", f"{fwd_pe:.1f}", unit="×", tag=tag, tag_tip=tip,
            caption="Compresses on next year's EPS estimate.",
        ))

    peg = _num(info.get("trailingPegRatio") or info.get("pegRatio"))
    if peg is not None:
        tag, tip = _val_tag(peg, _v("peg_cheap", 1.0), _v("peg_rich", 2.5))
        out.append(_kpi(
            "PEG", f"{peg:.2f}", tag=tag, tag_tip=tip,
            caption="P/E divided by EPS growth. Below 1.0 flatters growth.",
        ))

    ps = _num(info.get("priceToSalesTrailing12Months"))
    if ps is not None:
        tag, tip = _val_tag(ps, _v("ps_cheap", 4), _v("ps_rich", 12))
        out.append(_kpi(
            "P/S", f"{ps:.1f}", unit="×", tag=tag, tag_tip=tip,
            caption="Price relative to revenue.",
        ))

    ev_ebitda = _num(info.get("enterpriseToEbitda"))
    if ev_ebitda is not None:
        tag, tip = _val_tag(ev_ebitda, _v("ev_ebitda_cheap", 10), _v("ev_ebitda_rich", 25))
        out.append(_kpi(
            "EV/EBITDA", f"{ev_ebitda:.1f}", unit="×", tag=tag, tag_tip=tip,
            caption="Capital-structure-neutral multiple.",
        ))

    market_cap = _num(info.get("marketCap"))
    free_cf = _compute_fcf(bundle)
    if free_cf and market_cap:
        fcf_yield = free_cf / market_cap * 100
        tag, tip = _val_tag(fcf_yield,
                            _v("fcf_yield_low", 2), _v("fcf_yield_high", 6),
                            lower_better=False)
        out.append(_kpi(
            "FCF yield", f"{fcf_yield:.1f}", unit="%", tag=tag, tag_tip=tip,
            caption="Free cash flow as % of market cap.",
        ))

    return out


# --------------------------------------------------------------------------
# 03 Growth
# --------------------------------------------------------------------------
def section_growth(bundle: TickerBundle) -> list:
    info = bundle.info
    out = []

    revenue_q = _row(bundle.income_q, "Total Revenue", "Revenue")
    revenue_a = _row(bundle.income_a, "Total Revenue", "Revenue")
    eps_q = _row(bundle.income_q, "Diluted EPS", "Basic EPS")
    eps_a = _row(bundle.income_a, "Diluted EPS", "Basic EPS")
    gross_profit_a = _row(bundle.income_a, "Gross Profit")
    operating_income_a = _row(bundle.income_a, "Operating Income")
    net_income_a = _row(bundle.income_a, "Net Income")

    rev_yoy = _num(info.get("revenueGrowth"))
    if rev_yoy is not None:
        rev_yoy *= 100
        spark = _series_as_spark(revenue_q, label=f"{len(revenue_q) if revenue_q is not None else 0}q") \
            if revenue_q is not None else None
        top = _t("rev_yoy_top_decile", 50)
        exp = _t("rev_yoy_expanding", 15)
        tag, tip = None, ""
        if rev_yoy > top:
            tag, tip = ("cool", "top decile"), f"revenue YoY > {top}%"
        elif rev_yoy < 0:
            tag, tip = ("warm", "shrinking"), "revenue YoY < 0%"
        elif rev_yoy > exp:
            tag, tip = ("amber", "expanding"), f"revenue YoY > {exp}%"
        out.append(_kpi(
            "Revenue YoY", _signed(rev_yoy), unit="%", tag=tag, tag_tip=tip,
            caption="Most recent quarter vs prior year.",
            spark=spark,
        ))

    rev_3y = _cagr(revenue_a, 3)
    if rev_3y is not None:
        out.append(_kpi(
            "Revenue 3y CAGR", _signed(rev_3y, 0), unit="%",
            caption="Annualised over the trailing 3 years.",
        ))

    rev_5y = _cagr(revenue_a, 5)
    if rev_5y is not None:
        out.append(_kpi(
            "Revenue 5y CAGR", _signed(rev_5y, 0), unit="%",
            caption="Smoothed long-term trend.",
        ))

    eps_yoy = _num(info.get("earningsGrowth"))
    if eps_yoy is not None:
        eps_yoy *= 100
        spark = _series_as_spark(eps_q,
                                 label=f"{len(eps_q) if eps_q is not None else 0}q") \
            if eps_q is not None else None
        leverage = bool(eps_yoy and rev_yoy and eps_yoy > rev_yoy)
        tag = ("cool", "leverage") if leverage else None
        tip = (f"EPS YoY ({eps_yoy:+.0f}%) > Revenue YoY ({rev_yoy:+.0f}%)"
               if leverage else "")
        out.append(_kpi(
            "EPS YoY", _signed(eps_yoy), unit="%", tag=tag, tag_tip=tip,
            caption=(
                "EPS > revenue = textbook operating leverage."
                if leverage else "Quarterly EPS vs prior-year quarter."
            ),
            spark=spark,
        ))

    eps_3y = _cagr(eps_a, 3)
    if eps_3y is not None:
        out.append(_kpi(
            "EPS 3y CAGR", _signed(eps_3y, 0), unit="%",
            caption="Compounded EPS growth.",
        ))

    # Margins
    gm = _num(info.get("grossMargins"))
    if gm is not None:
        gm_pct = gm * 100
        # YoY pp change
        pp = None
        if gross_profit_a is not None and revenue_a is not None:
            prior_gm = None
            cur_rev = _val(revenue_a, 0)
            prior_rev = _val(revenue_a, 1)
            cur_gp = _val(gross_profit_a, 0)
            prior_gp = _val(gross_profit_a, 1)
            if cur_rev and prior_rev and cur_gp and prior_gp:
                pp = (cur_gp / cur_rev - prior_gp / prior_rev) * 100
        tag = None
        tip = ""
        if pp is not None and abs(pp) > 1:
            tag = ("amber", f"{'+' if pp >= 0 else '−'}{abs(pp):.1f}pp YoY")
            tip = f"current gross margin {gm_pct:.1f}% vs prior-year {gm_pct - pp:.1f}%"
        out.append(_kpi(
            "Gross margin", f"{gm_pct:.1f}", unit="%", tag=tag, tag_tip=tip,
            caption="Gross profit as % of revenue.",
        ))

    op_m = _num(info.get("operatingMargins"))
    if op_m is not None:
        op_pct = op_m * 100
        pp = None
        if operating_income_a is not None and revenue_a is not None:
            cur_rev = _val(revenue_a, 0)
            prior_rev = _val(revenue_a, 1)
            cur_oi = _val(operating_income_a, 0)
            prior_oi = _val(operating_income_a, 1)
            if cur_rev and prior_rev and cur_oi is not None and prior_oi is not None:
                pp = (cur_oi / cur_rev - prior_oi / prior_rev) * 100
        tag = None
        tip = ""
        margin_pp = _t("margin_pp_change", 2)
        if pp is not None and abs(pp) > margin_pp:
            tag = ("amber", f"{'+' if pp >= 0 else '−'}{abs(pp):.1f}pp YoY")
            tip = f"|YoY pp change| > {margin_pp}pp"
        out.append(_kpi(
            "Operating margin", f"{op_pct:.1f}", unit="%", tag=tag, tag_tip=tip,
            caption="Operating income as % of revenue.",
        ))

    net_m = _num(info.get("profitMargins"))
    if net_m is not None:
        out.append(_kpi(
            "Net margin", f"{net_m * 100:.1f}", unit="%",
            caption="Net income drop-through.",
        ))

    return out


# --------------------------------------------------------------------------
# 04 Quality & moat
# --------------------------------------------------------------------------
def section_quality(bundle: TickerBundle) -> list:
    info = bundle.info
    out = []

    roe = _num(info.get("returnOnEquity"))
    if roe is not None:
        roe_pct = roe * 100
        roe_elite = _t("roe_elite", 30)
        tag = ("cool", "elite") if roe_pct >= roe_elite else None
        tip = f"ROE ≥ {roe_elite}%" if tag else ""
        out.append(_kpi(
            "ROE", f"{roe_pct:.0f}", unit="%", tag=tag, tag_tip=tip,
            caption="Net income per $ of shareholder equity.",
        ))

    # ROIC ≈ NOPAT / invested capital. yfinance doesn't expose it, so use a
    # proxy: returnOnAssets is close enough for the AI cohort.
    roa = _num(info.get("returnOnAssets"))
    if roa is not None:
        roa_pct = roa * 100
        roa_elite = _t("roa_elite", 20)
        tag = ("cool", "elite") if roa_pct >= roa_elite else None
        tip = f"ROA ≥ {roa_elite}%" if tag else ""
        out.append(_kpi(
            "ROA (proxy ROIC)", f"{roa_pct:.0f}", unit="%", tag=tag, tag_tip=tip,
            caption="Return on assets; close proxy for ROIC.",
        ))

    # FCF margin (shares the same `_compute_fcf` helper as the Valuation
    # section so the two numbers never drift apart).
    rev = _val(_row(bundle.income_a, "Total Revenue", "Revenue"))
    free_cf = _compute_fcf(bundle)
    if rev and free_cf is not None:
        fcf_m = free_cf / rev * 100
        out.append(_kpi(
            "FCF margin", f"{fcf_m:.0f}", unit="%",
            caption="Free cash flow as % of revenue.",
        ))

    # Operating margin is rendered in the Growth section already (with its
    # YoY pp tag). Don't show it twice.

    # Asset turnover = revenue / total assets
    total_assets = _val(_row(bundle.balance_a, "Total Assets"))
    if rev and total_assets:
        at = rev / total_assets
        out.append(_kpi(
            "Asset turnover", f"{at:.2f}", unit="×",
            caption="Revenue generated per $ of assets.",
        ))

    # Inventory turns = COGS / inventory
    cogs = _val(_row(bundle.income_a, "Cost Of Revenue",
                     "Cost of Goods Sold", "Reconciled Cost Of Revenue"))
    inv = _val(_row(bundle.balance_a, "Inventory"))
    if cogs and inv:
        turns = cogs / inv
        out.append(_kpi(
            "Inventory turns", f"{turns:.1f}", unit="×",
            caption="COGS divided by inventory.",
        ))

    # R&D efficiency = revenue / R&D
    rd = _val(_row(bundle.income_a, "Research And Development",
                   "Research Development"))
    if rev and rd:
        eff = rev / rd
        out.append(_kpi(
            "R&D efficiency", f"{eff:.1f}", unit="×",
            caption="Revenue per $ of R&D spend.",
        ))

    return out


# --------------------------------------------------------------------------
# 05 Financial health
# --------------------------------------------------------------------------
def section_health(bundle: TickerBundle) -> list:
    info = bundle.info
    out = []

    total_cash = _num(info.get("totalCash"))
    total_debt = _num(info.get("totalDebt"))
    if total_cash is not None and total_debt is not None:
        net = total_cash - total_debt
        ccy, val, unit = _humanize_cap(net)
        tag = ("cool", "strong") if net > 0 else ("warm", "leveraged")
        tip = "net cash > 0" if net > 0 else "net debt position"
        out.append(_kpi(
            "Net cash", val, unit=unit, ccy=ccy, tag=tag, tag_tip=tip,
            caption=(
                f"{_humanize_cap(total_cash)[0]}{_humanize_cap(total_cash)[1]}"
                f"{_humanize_cap(total_cash)[2]} cash · "
                f"{_humanize_cap(total_debt)[0]}{_humanize_cap(total_debt)[1]}"
                f"{_humanize_cap(total_debt)[2]} debt."
            ),
        ))

    cur = _num(info.get("currentRatio"))
    if cur is not None:
        out.append(_kpi(
            "Current ratio", f"{cur:.1f}", unit="×",
            caption="Short-term assets cover short-term debt.",
        ))

    quick = _num(info.get("quickRatio"))
    if quick is not None:
        out.append(_kpi(
            "Quick ratio", f"{quick:.1f}", unit="×",
            caption="Cash + AR cover ST debt.",
        ))

    # Interest coverage = operating income / interest expense
    op_inc = _val(_row(bundle.income_a, "Operating Income",
                       "EBIT", "Total Operating Income"))
    int_exp = _val(_row(bundle.income_a, "Interest Expense"))
    if op_inc and int_exp:
        ic = abs(op_inc / int_exp)
        out.append(_kpi(
            "Interest coverage", f"{ic:.0f}", unit="×",
            caption="Operating income ÷ interest expense.",
        ))

    de = _num(info.get("debtToEquity"))
    if de is not None:
        # yfinance returns this as a multiplier × 100; normalize.
        de_norm = de / 100 if de > 5 else de
        out.append(_kpi(
            "Debt / equity", f"{de_norm:.2f}",
            caption="Debt per $ of equity.",
        ))

    # Share count YoY
    shares_q = _row(bundle.income_q, "Diluted Average Shares",
                    "Basic Average Shares", "Share Issued")
    if shares_q is not None and len(shares_q) >= 5:
        cur = _val(shares_q, 0)
        prior = _val(shares_q, 4)  # 4 quarters back ≈ 1 yr
        if cur and prior:
            chg = (cur / prior - 1) * 100
            buy = _t("buyback_threshold", -0.5)
            dil = _t("dilution_threshold", 1.5)
            tag, tip = None, ""
            if chg < buy:
                tag, tip = ("cool", "buyback"), f"share count YoY < {buy:+.1f}%"
            elif chg > dil:
                tag, tip = ("warm", "dilution"), f"share count YoY > {dil:+.1f}%"
            out.append(_kpi(
                "Share count YoY", _signed(chg, 1), unit="%",
                tag=tag, tag_tip=tip,
                caption="Net change in diluted shares outstanding.",
            ))

    # Cash conversion = FCF / NI
    ni = _val(_row(bundle.income_a, "Net Income"))
    free_cf = _compute_fcf(bundle)
    if free_cf and ni and ni > 0:
        cc = free_cf / ni * 100
        out.append(_kpi(
            "Cash conversion", f"{cc:.0f}", unit="%",
            caption="FCF as % of net income.",
        ))

    # DSO = AR / revenue × 365
    ar = _val(_row(bundle.balance_a, "Accounts Receivable", "Receivables"))
    rev = _val(_row(bundle.income_a, "Total Revenue", "Revenue"))
    if ar and rev:
        dso = ar / rev * 365
        out.append(_kpi(
            "Days sales out", f"{dso:.0f}", unit="d",
            caption="Average collection period.",
        ))

    return out


# --------------------------------------------------------------------------
# 06 AI exposure
# --------------------------------------------------------------------------
def section_ai(bundle: TickerBundle) -> list:
    out = []
    info = bundle.info
    ticker = bundle.ticker

    # Data-center % of revenue — pulled from a hand-curated map in settings.yaml.
    dc_map = setting("ai_segments", {}) or {}
    dc_share = dc_map.get(ticker)
    if dc_share is not None:
        out.append(_kpi(
            "DC % of rev", f"{dc_share:.0f}", unit="%",
            tag=("amber", "curated"),
            caption="From settings.yaml ai_segments map.",
        ))

    # R&D as % of revenue
    rev = _val(_row(bundle.income_a, "Total Revenue", "Revenue"))
    rd = _val(_row(bundle.income_a, "Research And Development",
                   "Research Development"))
    if rev and rd:
        out.append(_kpi(
            "R&D % rev", f"{rd / rev * 100:.0f}", unit="%",
            caption="Research spend as share of revenue.",
        ))
        rd_prior = _val(_row(bundle.income_a, "Research And Development",
                             "Research Development"), 1)
        if rd_prior:
            chg = (rd / rd_prior - 1) * 100
            out.append(_kpi(
                "R&D YoY", _signed(chg, 0), unit="%",
                caption="$ R&D spend growth.",
            ))

    # Capex YoY
    capex_a = _row(bundle.cashflow_a, "Capital Expenditure",
                   "Capital Expenditures")
    if capex_a is not None and len(capex_a) >= 2:
        cur = abs(_val(capex_a, 0) or 0)
        prior = abs(_val(capex_a, 1) or 0)
        if cur and prior:
            chg = (cur / prior - 1) * 100
            ccy, val, unit = _humanize_cap(cur)
            out.append(_kpi(
                "Capex YoY", _signed(chg, 0), unit="%",
                caption=f"Run-rate {ccy}{val}{unit}.",
            ))

    # Inventory + purchase commitments — inventory only since commits aren't in yfinance.
    inv = _val(_row(bundle.balance_a, "Inventory"))
    if inv:
        ccy, val, unit = _humanize_cap(inv)
        out.append(_kpi(
            "Inventory", val, unit=unit, ccy=ccy,
            caption="Balance-sheet inventory only (no purchase commits).",
        ))

    return out


# --------------------------------------------------------------------------
# 07 Income & options
# --------------------------------------------------------------------------
def section_income(bundle: TickerBundle) -> list:
    info = bundle.info
    out = []

    div_yield = _num(info.get("dividendYield"))
    if div_yield is not None:
        # yfinance >= 0.2.40 returns this as a percent number already
        # (e.g. 2.0 == 2%). Trust the spec — the old "scale up if < 0.2"
        # heuristic mis-read NVDA's 0.02% as 2%.
        yld = div_yield
        token = _t("div_yield_token", 0.5)
        high = _t("div_yield_high", 3.0)
        tag, tip = None, ""
        if yld < token:
            tag, tip = ("warm", "token"), f"yield < {token}%"
        elif yld > high:
            tag, tip = ("cool", "high"), f"yield > {high}%"
        out.append(_kpi(
            "Dividend yield", f"{yld:.2f}", unit="%", tag=tag, tag_tip=tip,
            caption="Annual dividend / price (per yfinance).",
        ))

    payout = _num(info.get("payoutRatio"))
    if payout is not None:
        out.append(_kpi(
            "Payout ratio", f"{payout * 100:.0f}", unit="%",
            caption="Dividends as % of earnings.",
        ))

    # Implied volatility — best available proxy is historical 30d vol on price.
    if bundle.price_history is not None and len(bundle.price_history) > 30:
        rets = bundle.price_history.pct_change().dropna()
        last30 = rets.iloc[-30:]
        if not last30.empty:
            iv = last30.std() * (252 ** 0.5) * 100
            elev = _t("iv_elevated", 40)
            tag = ("amber", "elevated") if iv > elev else None
            tip = f"30d realized vol > {elev}%" if tag else ""
            out.append(_kpi(
                "30d realized vol", f"{iv:.0f}", unit="%", tag=tag, tag_tip=tip,
                caption="Annualised stdev of daily returns (proxy for IV).",
            ))

    # Put/call ratio from options chain — pull next expiry only
    if bundle.options_expirations:
        try:
            t = yf.Ticker(bundle.ticker)
            chain = t.option_chain(bundle.options_expirations[0])
            calls_vol = chain.calls["volume"].sum() if "volume" in chain.calls else 0
            puts_vol = chain.puts["volume"].sum() if "volume" in chain.puts else 0
            if calls_vol and not pd.isna(calls_vol):
                pcr = (puts_vol or 0) / calls_vol
                bull = _t("pcr_bullish", 0.70)
                bear = _t("pcr_bearish", 1.30)
                tag, tip = None, ""
                if pcr < bull:
                    tag, tip = ("cool", "bullish"), f"put/call < {bull}"
                elif pcr > bear:
                    tag, tip = ("warm", "bearish"), f"put/call > {bear}"
                out.append(_kpi(
                    "Put / call ratio", f"{pcr:.2f}", tag=tag, tag_tip=tip,
                    caption=f"Next expiry: {bundle.options_expirations[0]}.",
                ))
        except Exception:
            pass

    return out


# --------------------------------------------------------------------------
# 08 Sentiment (DB-backed)
# --------------------------------------------------------------------------
def section_sentiment(ticker: str) -> dict:
    """Reads sentiment_daily + sentiment_posts for the meter and quotes.

    Also returns `baseline_n_days` (number of daily rows that fed the
    30d baseline) and `last_post_at` so the UI can show whether the
    numbers are recent enough to trust.
    """
    with db.connect() as conn:
        daily = db.sentiment_daily(conn, ticker, days=30)
        posts = db.recent_sentiment_posts(conn, ticker, days=14, limit=4)
        shifts = db.sentiment_shifts(conn, baseline_days=30, current_days=3)
        # Pull the most-recent sentiment row for freshness.
        last_row = conn.execute(
            "SELECT MAX(fetched_at) AS f FROM sentiment_posts WHERE ticker = ?",
            (ticker.upper(),),
        ).fetchone()
        last_fetched_at = last_row["f"] if last_row else None

    counts = {"reddit": 0, "stocktwits": 0, "news": 0, "hn": 0}
    distinct_days = set()
    for r in daily:
        counts[r["source"]] = counts.get(r["source"], 0) + r["n"]
        distinct_days.add(r["day"])

    shift_row = next((s for s in shifts if s["ticker"] == ticker.upper()), None)
    current = shift_row["current_mean"] if shift_row else None
    baseline = shift_row["baseline_mean"] if shift_row else None
    delta = shift_row["shift"] if shift_row else None
    n_current = shift_row["n_current"] if shift_row else 0

    quotes = []
    for p in posts:
        quotes.append({
            "source": p["source"].title() if p["source"] else "—",
            "score": p["tone"],
            "text": p["text"],
            "url": p["url"],
            "created_at": p["created_at"],
        })

    min_baseline_days = setting("sentiment_min_baseline_days", 5)
    return {
        "current": current,
        "baseline": baseline,
        "delta": delta,
        "counts": counts,
        "quotes": quotes,
        "baseline_n_days": len(distinct_days),
        "n_current": n_current,
        "last_fetched_at": last_fetched_at,
        "min_baseline_days": min_baseline_days,
        "trustworthy": len(distinct_days) >= min_baseline_days,
    }


# --------------------------------------------------------------------------
# 09 Fine print
# --------------------------------------------------------------------------
def section_fine_print(bundle: TickerBundle) -> list:
    info = bundle.info
    out = []

    inst_pct = _num(info.get("heldPercentInstitutions"))
    if inst_pct is not None:
        pct = inst_pct * 100
        crowded = _t("inst_crowded", 75)
        tag = ("warm", "crowded") if pct > crowded else None
        tip = f"institutional ownership > {crowded}%" if tag else ""
        out.append(_kpi(
            "Institutional own", f"{pct:.0f}", unit="%", tag=tag, tag_tip=tip,
            caption="Per yfinance ownership data.",
        ))

    insider_pct = _num(info.get("heldPercentInsiders"))
    if insider_pct is not None:
        out.append(_kpi(
            "Insider own", f"{insider_pct * 100:.1f}", unit="%",
            caption="Founder/officer/director holdings.",
        ))

    short_pct = _num(info.get("shortPercentOfFloat"))
    if short_pct is not None:
        out.append(_kpi(
            "Short interest", f"{short_pct * 100:.1f}", unit="%",
            caption="Shares shorted as % of float.",
        ))

    short_ratio = _num(info.get("shortRatio"))
    if short_ratio is not None:
        out.append(_kpi(
            "Days to cover", f"{short_ratio:.1f}", unit="d",
            caption="Short interest ÷ avg daily volume.",
        ))

    # Stock-based comp as % of revenue
    sbc = _val(_row(bundle.cashflow_a, "Stock Based Compensation",
                    "Stock-Based Compensation"))
    rev = _val(_row(bundle.income_a, "Total Revenue", "Revenue"))
    if sbc and rev:
        out.append(_kpi(
            "SBC % rev", f"{sbc / rev * 100:.1f}", unit="%",
            caption="Stock-based compensation drag.",
        ))

    return out


# --------------------------------------------------------------------------
# Top-level assembly
# --------------------------------------------------------------------------
def build_research_data(ticker: str) -> dict:
    """One-shot fetch + assemble for the Research tab."""
    bundle = fetch_bundle(ticker)
    return {
        "ticker": ticker.upper(),
        "snapshot": snapshot(bundle),
        "sections": {
            "overview":  section_overview(bundle),
            "valuation": section_valuation(bundle),
            "growth":    section_growth(bundle),
            "quality":   section_quality(bundle),
            "health":    section_health(bundle),
            "ai":        section_ai(bundle),
            "income":    section_income(bundle),
            "fine":      section_fine_print(bundle),
        },
        "sentiment": section_sentiment(ticker),
    }


if __name__ == "__main__":
    import json
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "NVDA"
    data = build_research_data(tk)
    # Strip non-serializable items for the smoke print
    snap = data["snapshot"]
    if snap.get("next_earnings") is not None:
        snap["next_earnings"] = str(snap["next_earnings"])
    print(json.dumps(data, indent=2, default=str))
