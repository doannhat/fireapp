"""Auto-classify a ticker into one of the AI-value-chain layers defined
in `watchlist.yaml`.

Rule-based + explainable. The user added "AVGO" expecting it to land in
"Compute & Semiconductors" automatically; the classifier does that work
by looking at:

  1. A hand-curated override list (highest priority — covers tickers
     whose Yahoo industry is misleading or where business model is the
     real signal, e.g. SMCI/COHR/LITE).
  2. The yfinance `industry` field, matched against a keyword table.
  3. The yfinance `sector` field as a fallback.
  4. The first available layer in `watchlist.yaml` as a last resort.

Returns `(layer_key, reason)` — the reason is a short human-readable
string that the UI shows in the toast so the user can verify the pick.
"""
from __future__ import annotations


# Hand-curated overrides for tickers whose Yahoo industry doesn't map
# cleanly to our AI value-chain layers, or where business model nuance
# matters more than the GICS bucket.
TICKER_OVERRIDES: dict = {
    # Hyperscalers / Big Tech (own the AI cloud infra)
    "MSFT": "hyperscalers", "GOOG": "hyperscalers", "GOOGL": "hyperscalers",
    "AMZN": "hyperscalers", "META": "hyperscalers", "AAPL": "hyperscalers",
    "ORCL": "hyperscalers", "IBM": "hyperscalers",

    # Networking / systems (yfinance often files these under
    # "Semiconductors" or "Communication Equipment" — they're really
    # the systems/interconnect layer in our taxonomy)
    "SMCI": "systems",  # Super Micro — AI servers
    "ANET": "systems",  # Arista — DC switching
    "CSCO": "systems",  "JNPR": "systems",  "NOK": "systems",
    "ERIC": "systems",  "HPE":  "systems",  "DELL": "systems",
    "CRDO": "systems",  # Credo — high-speed connectivity
    "ALAB": "systems",  # Astera Labs — semi connectivity
    "MRVL": "systems",  # Marvell — networking/storage semis
    "LITE": "systems",  # Lumentum — optical
    "COHR": "systems",  # Coherent — laser/optical
    "AAOI": "systems",  "FN":   "systems",  "ACMR": "systems",

    # Power, cooling & electrification
    "VRT":  "power_cooling",  "VST": "power_cooling",  "CEG": "power_cooling",
    "GEV":  "power_cooling",  "TLN": "power_cooling",  "POWL": "power_cooling",
    "MOD":  "power_cooling",  "UUUU": "power_cooling", "USAR": "power_cooling",
    "ETN":  "power_cooling",  "PWR":  "power_cooling", "NEE":  "power_cooling",
    "BWXT": "power_cooling",  "CWEN": "power_cooling",

    # AI software & applications
    "PLTR": "software", "SNOW": "software", "DDOG": "software",
    "NOW":  "software", "CRM":  "software", "MDB":  "software",
    "AI":   "software", "PATH": "software", "VEEV": "software",
    "ADBE": "software", "INTU": "software",

    # Compute / semis (only when industry alone wouldn't pick this up)
    "NVDA": "compute", "AVGO": "compute", "AMD":  "compute",
    "TSM":  "compute", "ASML": "compute", "MU":   "compute",
    "INTC": "compute", "QCOM": "compute", "ARM":  "compute",
    "MXL":  "compute", "ON":   "compute", "MCHP": "compute",
}


# Industry keyword → layer. Substring match against a *normalized*
# industry string (em-dashes → " - ", lowercased) so a single rule
# covers yfinance's variants. Order matters — first match wins, so put
# the most-specific phrases first.
INDUSTRY_RULES = [
    # Power & cooling
    ("utilities - renewable",                  "power_cooling"),
    ("utilities - independent power",          "power_cooling"),
    ("utilities - regulated electric",         "power_cooling"),
    ("utilities - regulated",                  "power_cooling"),
    ("utilities - diversified",                "power_cooling"),
    ("electrical equipment & parts",           "power_cooling"),
    ("electrical equipment and parts",         "power_cooling"),
    ("engineering & construction",             "power_cooling"),
    ("uranium",                                "power_cooling"),
    ("specialty industrial machinery",         "power_cooling"),

    # Software
    ("software - infrastructure",              "software"),
    ("software - application",                 "software"),
    ("internet content & information",         "software"),
    ("information technology services",        "software"),

    # Systems & networking
    ("computer hardware",                      "systems"),
    ("communication equipment",                "systems"),
    ("scientific & technical instruments",     "systems"),
    ("electronic gaming",                      "systems"),

    # Compute / semis (broadest catch for AI-adjacent semi names)
    ("semiconductor equipment & materials",    "compute"),
    ("semiconductor equipment and materials",  "compute"),
    ("semiconductors",                         "compute"),
    ("electronic components",                  "compute"),
]


def _normalize_industry(text: str) -> str:
    """Lowercase + collapse em/en dashes to ' - ' so a single rule matches
    every yfinance dash style (Yahoo varies between em-dash, en-dash, and
    plain ASCII hyphen depending on the ticker)."""
    if not text:
        return ""
    s = text.lower()
    for d in ("—", "–"):  # em-dash, en-dash
        s = s.replace(d, " - ")
    # Collapse runs of whitespace to a single space.
    s = " ".join(s.split())
    return s


def classify(
    ticker: str,
    info: dict,
    available_layers: list,
) -> tuple[str, str]:
    """Return (layer_key, reason). `available_layers` filters the
    classifier to layers that actually exist in the user's watchlist.yaml
    — we won't return a key that the writer can't insert into."""
    ticker = (ticker or "").upper()
    industry = (info.get("industry") or "")
    sector = (info.get("sector") or "")

    # 1. Hand-curated overrides
    if ticker in TICKER_OVERRIDES:
        layer = TICKER_OVERRIDES[ticker]
        if layer in available_layers:
            return layer, f"override (ticker={ticker})"

    # 2. Industry keyword match (against normalized industry string)
    industry_n = _normalize_industry(industry)
    for keyword, layer in INDUSTRY_RULES:
        if keyword in industry_n and layer in available_layers:
            return layer, f"industry: {industry}"

    # 3. Sector fallback
    sector_lc = sector.lower()
    if "utilities" in sector_lc and "power_cooling" in available_layers:
        return "power_cooling", f"sector: {sector}"
    if ("technology" in sector_lc or "communication" in sector_lc):
        if "compute" in available_layers:
            return "compute", f"sector: {sector} (default for tech)"

    # 4. Last resort — first available layer
    if available_layers:
        return available_layers[0], "no strong signal; default layer"
    return "compute", "no layers configured; falling back to compute"
