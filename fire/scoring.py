"""Tone scoring — turns a post or headline into a number in [-1, +1].

The interface is one function, ``score(text)``. The backend is chosen
by ``settings.yaml``::

    sentiment:
      scorer: vader      # vader (default) or finbert

VADER (Valence Aware Dictionary for sEntiment Reasoning) is rule-based,
zero-deps after a tiny pip install, deterministic, and tuned for
social-media text. It is the right default for a Phase-2 first cut.

FinBERT is a transformer pre-trained on financial text. It understands
phrases like "missed guidance" and "raised outlook" that VADER does not.
The cost is a ~500MB model download on first run and heavier deps
(``transformers``, ``torch``). The import is deferred so users who stay
on VADER do not pay that cost.
"""
from __future__ import annotations

from functools import lru_cache

from .config import setting


# --------------------------------------------------------------------------
# VADER — pure-Python, ships in a small pip package
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _vader():
    from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
    return SentimentIntensityAnalyzer()


def _score_vader(text: str) -> float:
    if not text:
        return 0.0
    return float(_vader().polarity_scores(text)["compound"])


# --------------------------------------------------------------------------
# FinBERT — optional, lazy-loaded
# --------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _finbert():
    from transformers import (AutoModelForSequenceClassification,
                              AutoTokenizer, pipeline)
    name = "ProsusAI/finbert"
    tok = AutoTokenizer.from_pretrained(name)
    mdl = AutoModelForSequenceClassification.from_pretrained(name)
    return pipeline("text-classification", model=mdl, tokenizer=tok,
                    return_all_scores=True, truncation=True)


def _score_finbert(text: str) -> float:
    if not text:
        return 0.0
    result = _finbert()(text[:512])[0]
    by_label = {r["label"].lower(): r["score"] for r in result}
    # Map FinBERT's three-class output to a signed scalar in [-1, +1].
    return float(by_label.get("positive", 0.0) - by_label.get("negative", 0.0))


# --------------------------------------------------------------------------
# Public API
# --------------------------------------------------------------------------
def current_scorer() -> str:
    return str(setting("sentiment.scorer", "vader")).lower()


def score(text: str) -> float:
    """Return a compound tone in [-1, +1]. Never raises — bad input
    returns 0.0 so a noisy source cannot abort a collection run."""
    backend = current_scorer()
    try:
        if backend == "finbert":
            return _score_finbert(text)
        return _score_vader(text)
    except Exception:
        return 0.0


def score_many(texts: list) -> list:
    """Convenience for batch scoring; preserves order."""
    return [score(t) for t in texts]
