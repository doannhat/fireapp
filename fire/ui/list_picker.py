"""Pill-style interactive list picker + the shared `add_ticker` helper.

The picker now lives behind a `st.popover` so it works as a single
clickable button that opens a menu — visually consistent with the v2
mockup's pill dropdown.

When the user types a ticker into the Research combobox that isn't on
any list yet, the picker shows "+ ADD TO LIST" with options. Otherwise
it shows the current list name and the actions (move / remove).

`add_ticker(ticker, list_name)` is the shared write path used by:
  - the Add-ticker form on the Watchlist tab
  - the popover's "+ Add" actions on the Research tab
It validates the symbol via yfinance, classifies it into a layer, and
writes to both `watchlist.yaml` and `watchlist_meta`.
"""
from __future__ import annotations

import streamlit as st

from .. import db
from ..classifier import classify
from ..config import (LIST_LABEL, LISTS, add_ticker_to_yaml,
                      layer_keys, remove_ticker_from_yaml)
from ..market import fetch_snapshot


def add_ticker(ticker: str, list_name: str) -> tuple[bool, str]:
    """Validate via yfinance → classify into a layer → persist.

    Returns (ok, message). On success message is a human-readable
    summary like "AVGO → Holding under Compute & Semiconductors".
    On failure message describes what went wrong.
    """
    tk = (ticker or "").strip().upper()
    if not tk:
        return False, "Empty ticker."
    if list_name not in LISTS:
        return False, f"Unknown list: {list_name!r}"

    # Validate-first: pull a snapshot before persisting anywhere.
    try:
        snap = fetch_snapshot(tk)
    except Exception as exc:
        return False, f"{tk}: yfinance lookup failed — {exc}"

    if snap.get("price") is None:
        return False, (
            f"{tk}: yfinance returned no price. Check the symbol "
            f"(delisted, wrong exchange suffix?). Nothing was written."
        )

    # Classify into a layer in watchlist.yaml.
    layer_map = layer_keys()  # {layer_key: human_label}
    layer_key, reason = classify(tk, snap, list(layer_map.keys()))

    try:
        add_ticker_to_yaml(tk, layer_key)
    except Exception as exc:
        return False, f"Could not add to watchlist.yaml: {exc}"

    with db.connect() as conn:
        db.set_list(conn, tk, list_name)
        db.save_snapshot(conn, snap)

    name = snap.get("name") or tk
    return True, (
        f"{tk} ({name}) → {LIST_LABEL[list_name]} "
        f"under {layer_map.get(layer_key, layer_key)} · {reason}"
    )


def remove_ticker(ticker: str) -> tuple[bool, str]:
    """Remove a ticker from both watchlist.yaml and watchlist_meta."""
    tk = (ticker or "").strip().upper()
    if not tk:
        return False, "Empty ticker."
    with db.connect() as conn:
        db.remove_ticker_meta(conn, tk)
    try:
        remove_ticker_from_yaml(tk)
    except Exception:
        pass
    return True, f"{tk} removed from all lists"


# --------------------------------------------------------------------------
# Pill-style popover picker — used by the Research tab.
# --------------------------------------------------------------------------
_PILL_LABEL = {
    "holding":   "● HOLDING",
    "shortlist": "● SHORTLIST",
    "watchlist": "● WATCHLIST",
}


def render_list_picker(ticker: str,
                       key_prefix: str = "lp") -> None:
    """Pill button that opens a popover with list-management actions.

    Reads the ticker's state from `watchlist_meta` itself so callers
    don't need to pass it in (and so the picker can show the special
    'research-only' state when the ticker isn't on any list yet).
    """
    with db.connect() as conn:
        on_list = db.is_on_list(conn, ticker)
        current = db.get_list(conn, ticker) if on_list else None

    label = _PILL_LABEL[current] if (on_list and current in _PILL_LABEL) \
        else "+ ADD TO LIST"

    # The popover's button is what the user sees as the "pill".
    try:
        popover_ctx = st.popover(label, use_container_width=False)
    except TypeError:
        # Older Streamlit without `use_container_width` arg.
        popover_ctx = st.popover(label)

    with popover_ctx:
        st.markdown(f"**Manage {ticker}**")
        if on_list:
            st.caption(f"Currently on **{LIST_LABEL[current]}**.")
        else:
            st.caption(
                "**Research-only** — not on any list yet. "
                "Add to a list to track it."
            )

        cols = st.columns(len(LISTS))
        for col, lst in zip(cols, LISTS):
            with col:
                is_current = on_list and lst == current
                btn_label = f"● {LIST_LABEL[lst]}" if is_current else LIST_LABEL[lst]
                if st.button(
                        btn_label,
                        key=f"{key_prefix}_{ticker}_{lst}",
                        disabled=is_current,
                        type="primary" if is_current else "secondary",
                        use_container_width=True,
                ):
                    if not on_list:
                        ok, msg = add_ticker(ticker, lst)
                    else:
                        with db.connect() as c:
                            db.set_list(c, ticker, lst)
                        ok, msg = True, f"{ticker} → {LIST_LABEL[lst]}"
                    if ok:
                        st.toast(msg)
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(msg)

        if on_list:
            st.divider()
            if st.button(
                    "× Remove from all lists",
                    key=f"{key_prefix}_{ticker}_remove",
                    use_container_width=True,
            ):
                ok, msg = remove_ticker(ticker)
                st.toast(msg)
                st.cache_data.clear()
                # Reroute off the deleted ticker so the Research view
                # doesn't get stranded on data the user just disowned.
                # Falls back to leaving `active_ticker` alone if the
                # watchlist is now empty — the page will show the
                # research-only mode for the orphan.
                from ..config import all_tickers
                remaining = all_tickers()
                if remaining:
                    st.session_state["active_ticker"] = remaining[0]
                st.rerun()
