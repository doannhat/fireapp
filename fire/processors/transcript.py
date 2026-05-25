"""Claude extraction over an earnings call transcript — stub.

Future: ingest the most recent quarterly transcript and ask Claude for
bull/bear, dodged questions, and quotable lines.
"""
from __future__ import annotations

from ..claude_cli import Claude


def summarize_transcript(ticker: str, text: str = "",
                         claude: Claude | None = None) -> dict | None:
    if not text:
        return None
    c = claude or Claude()
    prompt = (
        f"Summarize this earnings call transcript for {ticker.upper()} as JSON:\n"
        f"  bull: list of 3 strings (each a single sentence)\n"
        f"  bear: list of 3 strings\n"
        f"  dodged: list of {{question, why_dodged}}\n"
        f"  quotes: list of {{speaker, text}}"
    )
    return c.call("transcript", ticker, prompt, content=text).data
