"""Per-ticker notes popover.

A lightweight `st.popover` button that lets the user attach a single
free-form note to a ticker. Used from two surfaces:

  - Research tab: full label "📝 Notes" in the control strip.
  - Watchlist card: compact label "📝" in the action row.

Notes are stored in `watchlist_meta.note` (a column that's been in the
schema since v1 but went unused). Writing a note on a research-only
ticker auto-adds it to the default list — taking a note is intent to
track, so landing on the loosest list is the sensible default.
"""
from __future__ import annotations

from datetime import datetime

import streamlit as st

from .. import db


def _relative(updated_at: str | None) -> str:
    """Human-friendly 'last edited' suffix from an ISO timestamp."""
    if not updated_at:
        return ""
    try:
        ts = datetime.fromisoformat(updated_at)
    except ValueError:
        return ""
    delta = datetime.now() - ts
    secs = delta.total_seconds()
    if secs < 60:
        return "just now"
    if secs < 3600:
        return f"{int(secs // 60)}m ago"
    if secs < 86400:
        return f"{int(secs // 3600)}h ago"
    if secs < 86400 * 7:
        return f"{int(secs // 86400)}d ago"
    return ts.strftime("%b %d, %Y")


def render_notes_popover(ticker: str,
                         *,
                         key: str,
                         compact: bool = False) -> None:
    """Render the Notes popover button + body for one ticker.

    Args:
        ticker: symbol to attach the note to.
        key: namespace for widget keys (prevents collisions when the
             same ticker is rendered in two surfaces).
        compact: True for the watchlist card (icon-only); False for the
             research control strip (icon + label).
    """
    with db.connect() as conn:
        note = db.get_note(conn, ticker)
    has_note = bool((note["content"] or "").strip())

    if compact:
        label = "📝 •" if has_note else "📝"
    else:
        label = "📝 Notes •" if has_note else "📝 Notes"

    try:
        popover_ctx = st.popover(label, use_container_width=False)
    except TypeError:
        popover_ctx = st.popover(label)

    with popover_ctx:
        st.markdown(f"**Note on {ticker}**")

        draft = st.text_area(
            f"note_{ticker}",
            value=note["content"],
            height=180,
            key=f"{key}_textarea",
            label_visibility="collapsed",
            placeholder=(
                "Free-form notes — markdown supported. "
                "What's your thesis, what changed, what to watch for?"
            ),
        )

        if has_note:
            st.caption(f"Last edited {_relative(note['updated_at'])}")
        else:
            st.caption("No note yet")

        cols = st.columns([1, 1])
        with cols[0]:
            if st.button(
                "Save",
                key=f"{key}_save",
                type="primary",
                use_container_width=True,
            ):
                with db.connect() as conn:
                    db.set_note(conn, ticker, draft)
                st.toast("Note saved")
                st.rerun()
        with cols[1]:
            if st.button(
                "Clear",
                key=f"{key}_clear",
                use_container_width=True,
                disabled=not has_note,
            ):
                with db.connect() as conn:
                    db.set_note(conn, ticker, "")
                st.toast("Note cleared")
                st.rerun()
