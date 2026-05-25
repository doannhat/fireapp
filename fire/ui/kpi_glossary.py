"""Per-KPI definitions + data-source attributions for the Research tab.

Every KPI tile in the Research tab carries a small `ⓘ` info button that
opens a popover with two fields:

  - **WHAT**   : what this metric measures, in 1-2 sentences
  - **SOURCE** : where the underlying data comes from

`lookup(label)` returns the entry for a given KPI label, falling back to
a generic message keyed by the metric's section so even labels we
haven't catalogued get useful attribution.

When you add a new KPI in `fire/metrics.py`, add a matching entry here.
Unmatched labels fall through to a safe default — the popover still
renders, it just shows generic source attribution.
"""
from __future__ import annotations


# Compact reusable source strings. Keeping these as constants means a
# yfinance API change only requires editing the constant, not every row.
_YF_INFO = "yfinance `.info` — Yahoo Finance fundamentals snapshot."
_YF_BALANCE = "yfinance `.balance_sheet` / `.quarterly_balance_sheet`."
_YF_INCOME = "yfinance `.income_stmt` / `.quarterly_income_stmt`."
_YF_CASHFLOW = "yfinance `.cashflow` / `.quarterly_cashflow`."
_YF_HISTORY = "yfinance `.history(period='1y')` — daily price series."
_YF_INST = "yfinance `.institutional_holders` and `.info` ownership fields."
_YF_FAST = "yfinance `.fast_info` — fast price / market-cap snapshot."

# A few KPIs are computed *from* yfinance data in `fire/metrics.py` —
# tagged below so the user knows the multi-step path.
_COMPUTED_FROM = lambda src: f"Computed in `fire.metrics` from {src}"


# label -> {definition, source}.
# Keys match the `label` field on each KPI dict produced by metrics.py.
GLOSSARY: dict[str, dict[str, str]] = {
    # =============================================================
    # OVERVIEW
    # =============================================================
    "Sector": {
        "definition": "GICS sector and industry classification — the broad "
                      "and specific industry buckets the company sits in.",
        "source": _YF_INFO + " Fields: `sector`, `industry`.",
    },
    "Employees": {
        "definition": "Full-time headcount as last reported by the company "
                      "in its 10-K / 10-Q.",
        "source": _YF_INFO + " Field: `fullTimeEmployees`.",
    },
    "CEO": {
        "definition": "Current chief executive officer plus tenure context "
                      "where available.",
        "source": _YF_INFO + " Field: `companyOfficers[]` (filtered to CEO).",
    },
    "Beta": {
        "definition": "5-year volatility relative to the S&P 500. >1 means "
                      "the stock historically swings more than the market; "
                      "<1 means less. Pure historical regression — not a "
                      "forecast.",
        "source": _YF_INFO + " Field: `beta`.",
    },
    "Float": {
        "definition": "Shares available to the public for trading (total "
                      "shares minus insider / restricted holdings). Lower "
                      "float can mean higher volatility per dollar of flow.",
        "source": _YF_INFO + " Field: `floatShares`.",
    },
    "Avg vol": {
        "definition": "30-day average daily trading volume — a liquidity "
                      "measure. Larger positions need higher avg vol to "
                      "enter/exit without slipping the price.",
        "source": _YF_FAST + " Field: `threeMonthAverageVolume` (≈30d).",
    },

    # =============================================================
    # VALUATION
    # =============================================================
    "P/E trailing": {
        "definition": "Price divided by trailing-twelve-month EPS. The "
                      "classic earnings multiple. High P/E = market pricing "
                      "in growth; low P/E = either cheap or a value trap.",
        "source": _YF_INFO + " Field: `trailingPE`.",
    },
    "P/E forward": {
        "definition": "Price divided by analyst-consensus next-twelve-month "
                      "EPS. More forward-looking than trailing — but only "
                      "as good as the consensus estimate.",
        "source": _YF_INFO + " Field: `forwardPE`.",
    },
    "P/S": {
        "definition": "Price-to-Sales — market cap divided by trailing "
                      "revenue. Useful for unprofitable / pre-margin "
                      "growth companies where P/E is meaningless.",
        "source": _YF_INFO + " Field: `priceToSalesTrailing12Months`.",
    },
    "PEG": {
        "definition": "P/E divided by projected EPS growth rate. PEG ≤ 1 "
                      "is the classic 'growth at a reasonable price' "
                      "threshold (Peter Lynch).",
        "source": _YF_INFO + " Field: `pegRatio` (forward 5y growth).",
    },
    "EV/EBITDA": {
        "definition": "Enterprise value divided by trailing EBITDA. "
                      "Capital-structure-neutral — useful for comparing "
                      "across leverage levels (acquirers' favorite multiple).",
        "source": _YF_INFO + " Field: `enterpriseToEbitda`.",
    },
    "FCF yield": {
        "definition": "Trailing-twelve-month free cash flow as a percent "
                      "of market cap. The cash-economic version of "
                      "earnings yield — harder to manipulate than EPS.",
        "source": _COMPUTED_FROM("yfinance `freeCashflow` and `marketCap`."),
    },

    # =============================================================
    # GROWTH
    # =============================================================
    "Revenue YoY": {
        "definition": "Trailing-twelve-month revenue growth vs the prior "
                      "TTM period. The primary top-line momentum signal.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "Revenue 3y CAGR": {
        "definition": "Compound annual revenue growth over the last 3 "
                      "fiscal years. Smooths single-year volatility.",
        "source": _COMPUTED_FROM(_YF_INCOME + " (last 3 annual periods)"),
    },
    "EPS YoY": {
        "definition": "Trailing earnings-per-share growth vs the prior "
                      "TTM period. Margin expansion + revenue growth "
                      "+ buybacks all flow through here.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "EPS 3y CAGR": {
        "definition": "Compound annual EPS growth over the last 3 fiscal "
                      "years. The cleanest single growth metric — but "
                      "watch the buyback contribution.",
        "source": _COMPUTED_FROM(_YF_INCOME + " (last 3 annual periods)"),
    },
    "Gross margin": {
        "definition": "Gross profit divided by revenue. Measures the "
                      "pricing power baked into the product before any "
                      "operating expense.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "Operating margin": {
        "definition": "Operating income divided by revenue. Captures both "
                      "pricing power AND operating leverage / discipline.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "Net margin": {
        "definition": "Net income divided by revenue. After interest, "
                      "taxes, everything. The cleanest 'how much of every "
                      "$ of revenue ends up as profit' number.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },

    # =============================================================
    # QUALITY
    # =============================================================
    "ROE": {
        "definition": "Return on Equity — net income divided by "
                      "shareholders' equity. Measures profit per dollar "
                      "of book capital. Elite > 30%. Caveat: heavily "
                      "leveraged businesses can inflate ROE.",
        "source": _COMPUTED_FROM(_YF_INCOME + " + " + _YF_BALANCE),
    },
    "ROA (proxy ROIC)": {
        "definition": "Return on Assets — net income / total assets. "
                      "Used here as a proxy for ROIC (true ROIC needs "
                      "operating capital + tax-adjusted operating "
                      "income, which yfinance doesn't expose cleanly).",
        "source": _COMPUTED_FROM(_YF_INCOME + " + " + _YF_BALANCE),
    },
    "FCF margin": {
        "definition": "Free cash flow as a percent of revenue. Tells you "
                      "how much of every revenue dollar converts to cash "
                      "the business can deploy.",
        "source": _COMPUTED_FROM(_YF_CASHFLOW + " + " + _YF_INCOME),
    },
    "Asset turnover": {
        "definition": "Revenue divided by total assets. Higher = the "
                      "business produces more sales per dollar of capital "
                      "tied up. Combined with margin → ROA.",
        "source": _COMPUTED_FROM(_YF_INCOME + " + " + _YF_BALANCE),
    },
    "Inventory turns": {
        "definition": "Cost of goods sold divided by average inventory. "
                      "Higher = faster inventory cycling = better working "
                      "capital efficiency. Critical for semis and retail.",
        "source": _COMPUTED_FROM(_YF_INCOME + " (COGS) + " + _YF_BALANCE),
    },
    "R&D efficiency": {
        "definition": "Revenue generated per dollar of R&D spending. "
                      "Higher = R&D is being effectively monetized.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },

    # =============================================================
    # HEALTH
    # =============================================================
    "Net cash": {
        "definition": "Cash and short-term investments minus total debt. "
                      "Positive = net cash position (financial flexibility); "
                      "negative = net debt (financial leverage).",
        "source": _COMPUTED_FROM(_YF_BALANCE),
    },
    "Debt / equity": {
        "definition": "Total debt divided by shareholders' equity. "
                      "Measures leverage. >1 = more debt than equity capital. "
                      "Tech companies typically run <0.5; utilities >1.",
        "source": _COMPUTED_FROM(_YF_BALANCE),
    },
    "Current ratio": {
        "definition": "Current assets / current liabilities. Liquidity "
                      "measure — can the company cover near-term obligations? "
                      "≥ 1.5 generally considered safe.",
        "source": _COMPUTED_FROM(_YF_BALANCE),
    },
    "Quick ratio": {
        "definition": "(Current assets minus inventory) / current "
                      "liabilities. Stricter liquidity test — assumes "
                      "inventory can't be liquidated quickly.",
        "source": _COMPUTED_FROM(_YF_BALANCE),
    },
    "Interest coverage": {
        "definition": "Operating income (EBIT) divided by interest expense. "
                      "Times-the-company-can-pay-its-interest. < 2 is a "
                      "yellow flag, < 1 means EBIT doesn't even cover interest.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "Cash conversion": {
        "definition": "Operating cash flow divided by net income. >1 "
                      "means the company is converting more cash than it "
                      "books in earnings — typically high quality. "
                      "<1 persistently can indicate aggressive accounting.",
        "source": _COMPUTED_FROM(_YF_CASHFLOW + " + " + _YF_INCOME),
    },
    "Days sales out": {
        "definition": "Average days between booking a sale and collecting "
                      "the cash (DSO). Rising DSO can signal customers "
                      "stretching payment terms — early warning sign.",
        "source": _COMPUTED_FROM(_YF_INCOME + " (revenue) + " + _YF_BALANCE +
                                 " (accounts receivable)"),
    },
    "Share count YoY": {
        "definition": "Year-over-year change in diluted share count. "
                      "Negative = net buybacks (returning capital). "
                      "Positive = net dilution (issuance > buybacks).",
        "source": _COMPUTED_FROM(_YF_INCOME + " (diluted weighted avg shares)"),
    },

    # =============================================================
    # AI EXPOSURE
    # =============================================================
    "R&D % rev": {
        "definition": "Research & development spending as a percent of "
                      "revenue. Proxy for innovation intensity. AI / "
                      "semi names typically run >15%; mature industrials <2%.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "R&D YoY": {
        "definition": "Year-over-year change in absolute R&D spending. "
                      "Rapid R&D ramp often precedes product cycles "
                      "(e.g. HBM4, CPO, SiC).",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "Capex YoY": {
        "definition": "Year-over-year change in capital expenditure. "
                      "For the AI value chain: capex YoY tracks how much "
                      "physical capacity (fabs, data centers) the business "
                      "is building.",
        "source": _COMPUTED_FROM(_YF_CASHFLOW),
    },
    "Inventory": {
        "definition": "Total inventory on the balance sheet — relevant "
                      "for semi cycles where rising inventory often "
                      "precedes a price-and-margin reset.",
        "source": _YF_BALANCE + " — inventory line.",
    },

    # =============================================================
    # INCOME / OPTIONS
    # =============================================================
    "Dividend yield": {
        "definition": "Annualised dividend per share divided by current "
                      "price. Long-term holders care about yield-on-cost "
                      "compounding from re-invested dividends.",
        "source": _YF_INFO + " Field: `dividendYield`.",
    },
    "Payout ratio": {
        "definition": "Dividends paid divided by net income. >100% means "
                      "the company is paying out more than it earns — "
                      "either drawing from cash or unsustainable.",
        "source": _YF_INFO + " Field: `payoutRatio`.",
    },
    "30d realized vol": {
        "definition": "Annualised standard deviation of the last 30 daily "
                      "log returns. Stand-in for implied volatility until "
                      "the options scanner is wired (Phase 3).",
        "source": _COMPUTED_FROM(_YF_HISTORY + " (last 30 close prices)"),
    },
    "Put / call ratio": {
        "definition": "Total put open-interest divided by total call "
                      "open-interest across the front-month chain. >1 "
                      "= net bearish positioning; <1 = net bullish.",
        "source": _COMPUTED_FROM("yfinance `.option_chain()` for the "
                                 "nearest expiration."),
    },

    # =============================================================
    # FINE PRINT
    # =============================================================
    "Institutional own": {
        "definition": "Percentage of shares held by institutional "
                      "investors (mutual funds, pensions, hedge funds). "
                      "Very high (>80%) signals consensus crowding; "
                      "very low (<20%) signals 'undiscovered' status.",
        "source": _YF_INFO + " Field: `heldPercentInstitutions`. "
                  "Cross-referenced with EDGAR 13F holdings in the "
                  "Signals section.",
    },
    "Insider own": {
        "definition": "Percentage of shares held by company insiders "
                      "(officers, directors, 10%+ holders). Founder-led "
                      "companies often run high (>10%).",
        "source": _YF_INFO + " Field: `heldPercentInsiders`.",
    },
    "Short interest": {
        "definition": "Percentage of float currently sold short. "
                      "High short interest (>10%) can fuel squeezes; can "
                      "also signal a bear thesis to investigate.",
        "source": _YF_INFO + " Field: `shortPercentOfFloat`.",
    },
    "Days to cover": {
        "definition": "Short interest divided by average daily volume — "
                      "how many trading days it would take shorts to "
                      "cover. High = potential squeeze fuel.",
        "source": _YF_INFO + " Field: `shortRatio`.",
    },
    "SBC % rev": {
        "definition": "Stock-based compensation as a percent of revenue. "
                      "Tech companies typically run 5-15%. Persistently "
                      "high SBC dilutes existing shareholders.",
        "source": _COMPUTED_FROM(_YF_CASHFLOW + " (stock-based "
                                 "compensation line) + " + _YF_INCOME),
    },
}


# Per-section fallback when a label isn't in the explicit table.
# Means new KPIs added without glossary entries still show useful
# attribution; the user gets generic-but-honest information instead
# of a broken popover.
_DEFAULTS_BY_SECTION = {
    "overview": {
        "definition": "Company overview field.",
        "source": _YF_INFO,
    },
    "valuation": {
        "definition": "Valuation multiple.",
        "source": _YF_INFO + " or computed from yfinance fundamentals.",
    },
    "growth": {
        "definition": "Growth metric.",
        "source": _COMPUTED_FROM(_YF_INCOME),
    },
    "quality": {
        "definition": "Quality / returns-on-capital metric.",
        "source": _COMPUTED_FROM(_YF_INCOME + " + " + _YF_BALANCE),
    },
    "health": {
        "definition": "Balance-sheet health metric.",
        "source": _COMPUTED_FROM(_YF_BALANCE),
    },
    "ai": {
        "definition": "AI-cycle exposure / capex intensity metric.",
        "source": _COMPUTED_FROM(_YF_INCOME + " + " + _YF_CASHFLOW),
    },
    "income": {
        "definition": "Income / volatility / options-positioning metric.",
        "source": _YF_INFO + " and " + _YF_HISTORY,
    },
    "fine": {
        "definition": "Ownership / short interest / structural fine print.",
        "source": _YF_INFO + " ownership fields.",
    },
}


_GENERIC_DEFAULT = {
    "definition": "Financial metric for this ticker.",
    "source": _YF_INFO + " or computed from yfinance statements.",
}


def lookup(label: str, section: str | None = None) -> dict:
    """Return {definition, source} for a KPI label.

    Falls back to a section-specific default when the label isn't
    catalogued, and to a generic default when even the section is
    unknown. Never raises — every call yields a renderable popover."""
    if label in GLOSSARY:
        return GLOSSARY[label]
    if section and section in _DEFAULTS_BY_SECTION:
        return _DEFAULTS_BY_SECTION[section]
    return _GENERIC_DEFAULT
