"""Transparent, rules-based valuation scoring.

This is deliberately simple and explainable. It is NOT a buy/sell signal.
It flags where a stock sits versus its own growth rate and trading range,
as a starting point for deeper research — the kind of context a long-term
investor uses to decide *when to dig in*, not *when to trade*.

Score convention: negative = cheaper-looking, positive = richer-looking.
"""
from __future__ import annotations

from .config import setting


def range_position(price, low, high):
    """Where price sits in the 52-week range: 0.0 = at the low, 1.0 = at the high."""
    if price is None or low is None or high is None:
        return None
    if high <= low:
        return None
    return max(0.0, min(1.0, (price - low) / (high - low)))


def percentile(values, current):
    """Percentile rank (0-100) of `current` within `values`. None if too little data."""
    clean = [v for v in values if v is not None]
    if len(clean) < 5 or current is None:
        return None
    below = sum(1 for v in clean if v <= current)
    return round(100.0 * below / len(clean), 1)


def score_valuation(snap: dict, ps_history: list = None) -> dict:
    """Score one snapshot. Returns {label, score, notes}.

    `ps_history` is the list of past price-to-sales readings for this ticker;
    once enough snapshots accumulate, the score also reflects how the stock
    is valued versus its *own* history.
    """
    peg_cheap = setting("valuation.peg_cheap", 1.0)
    peg_rich = setting("valuation.peg_rich", 2.5)
    range_low = setting("valuation.range_low", 0.25)
    range_high = setting("valuation.range_high", 0.80)

    score = 0.0
    notes = []

    # 1. PEG — price/earnings relative to growth.
    peg = snap.get("peg")
    if peg is not None and peg > 0:
        if peg <= peg_cheap:
            score -= 1.0
            notes.append(f"PEG {peg:.2f} — at/below {peg_cheap}, cheap versus growth")
        elif peg >= peg_rich:
            score += 1.0
            notes.append(f"PEG {peg:.2f} — at/above {peg_rich}, rich versus growth")
        else:
            notes.append(f"PEG {peg:.2f} — roughly in line with growth")

    # 2. Forward vs trailing P/E — are earnings expected to grow into the price?
    tpe, fpe = snap.get("trailing_pe"), snap.get("forward_pe")
    if tpe is not None and fpe is not None and tpe > 0 and fpe > 0:
        if fpe < tpe * 0.85:
            score -= 0.5
            notes.append(f"Forward P/E {fpe:.1f} well below trailing {tpe:.1f} "
                         f"— earnings expected to grow")
        elif fpe > tpe:
            score += 0.5
            notes.append(f"Forward P/E {fpe:.1f} above trailing {tpe:.1f} "
                         f"— earnings expected to fall")

    # 3. Position in the 52-week range.
    pos = range_position(snap.get("price"), snap.get("week52_low"),
                         snap.get("week52_high"))
    if pos is not None:
        if pos <= range_low:
            score -= 1.0
            notes.append(f"At {pos * 100:.0f}% of the 52-week range — near its lows")
        elif pos >= range_high:
            score += 1.0
            notes.append(f"At {pos * 100:.0f}% of the 52-week range — near its highs")
        else:
            notes.append(f"At {pos * 100:.0f}% of the 52-week range")

    # 4. Price-to-sales versus the stock's own collected history.
    if ps_history:
        pct = percentile(ps_history, snap.get("price_to_sales"))
        if pct is not None:
            if pct >= 80:
                score += 0.5
                notes.append(f"P/S in the {pct:.0f}th percentile of its own "
                             f"history — historically expensive")
            elif pct <= 20:
                score -= 0.5
                notes.append(f"P/S in the {pct:.0f}th percentile of its own "
                             f"history — historically cheap")
            else:
                notes.append(f"P/S in the {pct:.0f}th percentile of its own history")

    # Translate the score into a label.
    if not notes:
        return {"label": "n/a", "score": 0.0,
                "notes": ["Not enough data to score — see the raw metrics."]}

    if score <= -1.5:
        label = "Attractive"
    elif score <= -0.5:
        label = "Below average"
    elif score < 0.5:
        label = "Fair"
    elif score < 1.5:
        label = "Elevated"
    else:
        label = "Rich"

    return {"label": label, "score": round(score, 2), "notes": notes}
