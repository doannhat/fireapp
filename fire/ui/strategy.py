"""Strategy tab — edit STRATEGY.md from the UI.

Renders the YAML frontmatter as a structured form (one widget per
known field) and the Markdown body as a textarea. Unknown frontmatter
keys are surfaced in an Advanced expander as a raw YAML editor so the
user can extend the schema without losing data on save.

Saving rewrites STRATEGY.md via `fire.strategy.save_strategy()`. Since
the strategy hash is part of every Claude cache key, the warning
above the save button reminds the user that changes will trigger
fresh Claude calls on next use.
"""
from __future__ import annotations

import yaml
import streamlit as st

from ..strategy import KNOWN_KEYS, POSITION_STYLES, load_strategy, save_strategy


def _list_to_text(items) -> str:
    if not items:
        return ""
    return "\n".join(str(x) for x in items)


def _text_to_list(text: str) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def _horizon_pair(value) -> tuple[int, int]:
    """Normalize horizon_years into a (min, max) int pair.

    Accepts [min, max], a single number (treated as both), or anything
    unparseable (falls back to (2, 5)).
    """
    if isinstance(value, list) and len(value) >= 2:
        try:
            return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            pass
    if isinstance(value, (int, float)):
        v = int(value)
        return v, v
    return 2, 5


def render_strategy() -> None:
    strategy = load_strategy()
    fm = dict(strategy.frontmatter)

    src = strategy.source_path
    src_text = f"Loaded from <code>{src}</code>" if src else (
        "No <code>STRATEGY.md</code> found — saving will create one at "
        "the project root."
    )

    st.html(
        f"""
        <div class="section-head">
          <span class="num">—</span>
          <h2>Strategy</h2>
          <span class="badge">YOUR INVESTING PHILOSOPHY · used as system context for every Claude call</span>
        </div>
        <div class="claude-line">
          <span class="glyph">◇</span>
          <span>{src_text} Edit the fields below or open the prose body
          to refine. Saving rewrites the file and invalidates Claude
          cache entries that used the old strategy.</span>
        </div>
        """
    )

    # Pre-extract known fields with sensible defaults.
    hz_min, hz_max = _horizon_pair(fm.get("horizon_years"))
    target_mult = fm.get("target_return_multiple")
    try:
        target_mult = float(target_mult) if target_mult is not None else 10.0
    except (TypeError, ValueError):
        target_mult = 10.0
    pos_style = fm.get("position_style") or "concentrated"
    if pos_style not in POSITION_STYLES:
        pos_style = "concentrated"
    themes_text = _list_to_text(fm.get("themes"))
    rules_text = _list_to_text(fm.get("hard_rules"))

    # Unknown frontmatter keys → dump as YAML for the Advanced editor.
    extras = {k: v for k, v in fm.items() if k not in KNOWN_KEYS}
    extras_yaml_default = (
        yaml.safe_dump(extras, sort_keys=False, allow_unicode=True).rstrip()
        if extras else ""
    )

    with st.form("strategy_form", clear_on_submit=False, border=False):
        st.markdown("##### Horizon and return target")
        c1, c2, c3 = st.columns([1, 1, 2])
        with c1:
            hz_min_in = st.number_input(
                "Min horizon (years)", min_value=0, max_value=50,
                value=int(hz_min), step=1,
            )
        with c2:
            hz_max_in = st.number_input(
                "Max horizon (years)", min_value=0, max_value=50,
                value=int(hz_max), step=1,
            )
        with c3:
            target_mult_in = st.number_input(
                "Target return multiple (e.g. 10 = 10×)",
                min_value=1.0, max_value=1000.0,
                value=float(target_mult), step=0.5,
            )

        st.markdown("##### Style")
        pos_style_in = st.selectbox(
            "Position style",
            POSITION_STYLES,
            index=POSITION_STYLES.index(pos_style),
        )

        st.markdown("##### Themes — one per line")
        themes_in = st.text_area(
            "Themes",
            value=themes_text, height=140,
            label_visibility="collapsed",
            placeholder="AI super-cycle infrastructure\nMemory and optical interconnect\n...",
        )

        st.markdown("##### Hard rules — one per line")
        rules_in = st.text_area(
            "Hard rules",
            value=rules_text, height=140,
            label_visibility="collapsed",
            placeholder="Long-term positions only\nDerivatives only for hedging or income\n...",
        )

        with st.expander("Advanced — raw YAML for extra frontmatter keys"):
            extras_in = st.text_area(
                "Extra frontmatter (raw YAML)",
                value=extras_yaml_default, height=120,
                label_visibility="collapsed",
                help="Anything outside the known fields. Edit at your own risk.",
            )

        st.markdown("##### Philosophy (prose)")
        body_in = st.text_area(
            "Body",
            value=strategy.body or "", height=400,
            label_visibility="collapsed",
            placeholder="Free-form Markdown. The LLM reads everything below the frontmatter.",
        )

        st.caption(
            "⚠ Saving changes the strategy hash and will invalidate "
            "cached Claude results that used the old one."
        )
        saved = st.form_submit_button(
            "💾 SAVE STRATEGY", type="primary", use_container_width=True,
        )

    if not saved:
        return

    # Validate and merge.
    if hz_min_in > hz_max_in:
        st.error("Min horizon must be ≤ max horizon.")
        return

    try:
        extras_parsed = yaml.safe_load(extras_in) if extras_in.strip() else {}
    except yaml.YAMLError as e:
        st.error(f"Advanced YAML is invalid: {e}")
        return
    if extras_parsed is None:
        extras_parsed = {}
    if not isinstance(extras_parsed, dict):
        st.error("Advanced YAML must be a mapping (key: value pairs).")
        return

    # Known fields take precedence over anything the user re-typed into
    # the Advanced editor (avoids two sources of truth for the same key).
    overlap = set(extras_parsed) & set(KNOWN_KEYS)
    if overlap:
        st.warning(
            f"Ignoring {sorted(overlap)} from Advanced — these are "
            "owned by the form fields above."
        )
        for k in overlap:
            extras_parsed.pop(k, None)

    new_fm: dict = {
        "horizon_years": [int(hz_min_in), int(hz_max_in)],
        "target_return_multiple": (
            int(target_mult_in)
            if float(target_mult_in).is_integer()
            else float(target_mult_in)
        ),
        "position_style": pos_style_in,
        "themes": _text_to_list(themes_in),
        "hard_rules": _text_to_list(rules_in),
    }
    # Append extras after the known keys so the file reads top-down.
    new_fm.update(extras_parsed)

    path = save_strategy(new_fm, body_in)
    st.toast(f"Saved {path.name}")
    st.rerun()
