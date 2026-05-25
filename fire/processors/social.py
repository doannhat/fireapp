"""Claude clustering of social posts → themes.

Replaces (or augments) VADER tone scoring with topic clustering for the
Sentiment section's theme list. Stub for the collector pre-warm hook.
"""
from __future__ import annotations

from ..claude_cli import Claude


def cluster_social(ticker: str, posts: list,
                   claude: Claude | None = None) -> list | None:
    """Return list of {kind: bull|bear|watch, text, vol} themes."""
    if not posts:
        return None
    c = claude or Claude()
    # Compact representation — top N posts only
    sample = []
    for p in posts[:80]:
        text = (p.get("text") or "")[:300]
        score = p.get("tone") or p.get("score")
        src = p.get("source", "?")
        sample.append(f"[{src} score={score}] {text}")
    blob = "\n".join(sample)
    prompt = (
        f"Cluster these {len(sample)} social posts about {ticker.upper()} "
        f"into 5 themes. Return JSON: list of objects "
        f"{{kind: 'bull'|'bear'|'watch', text: 'theme summary "
        f"(may use **bold**)', vol: 'n posts · +/-0.XX'}}. "
        f"Use ONLY what's in the posts."
    )
    return c.call("social", ticker, prompt, content=blob).data
