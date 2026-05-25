"""Claude extraction over a 10-K — stub for Phase 3 pre-warm.

Real implementation pulls the latest 10-K from SEC EDGAR, slices it to
risk factors / customer concentration / segment revenue, and asks
Claude to extract structured fields. Wired into the collector
`--pre-warm` flag once the EDGAR fetcher is augmented.
"""
from __future__ import annotations

from ..claude_cli import Claude


def summarize_10k(ticker: str, text: str = "",
                  claude: Claude | None = None) -> dict | None:
    """Return {risks, segments, capex_guide, ai_mentions} — None if no text."""
    if not text:
        return None
    c = claude or Claude()
    prompt = (
        f"Summarize this 10-K excerpt for {ticker.upper()} as JSON with keys:\n"
        f"  risks: list of {{title, snippet, page}}\n"
        f"  segments: list of {{name, pct_revenue}}\n"
        f"  capex_guide: short string or null\n"
        f"  ai_mentions: integer count of substantive AI mentions\n"
        f"Include only what's actually in the text."
    )
    result = c.call("tenk", ticker, prompt, content=text)
    return result.data
