"""Inject the Google Fonts used by the v2 design."""
from __future__ import annotations

import streamlit as st


FONTS_HTML = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
"""


def inject_fonts() -> None:
    st.markdown(FONTS_HTML, unsafe_allow_html=True)
