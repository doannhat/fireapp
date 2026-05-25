"""FIRE v2 dark theme — extracted verbatim from mockups/research_redesign_v2.html.

`inject_theme()` writes the stylesheet plus a Streamlit override block that
hides the default chrome (header, footer, page padding) so the v2 layout
can take the full viewport.
"""
from __future__ import annotations

import streamlit as st


# Full v2 stylesheet — kept as one string so updates from the mockup are a
# straight copy-paste. The trailing Streamlit overrides are FIRE-specific.
THEME_CSS = r"""
:root {
  --bg-0:        #0b0c0f;
  --bg-1:        #11131a;
  --bg-2:        #161821;
  --bg-3:        #1c1f28;
  --bg-hi:       #21242e;
  --line:        #232631;
  --line-soft:   #1a1c24;
  --line-strong: #2e323d;

  --text-0:      #ece8d8;
  --text-1:      #aaa697;
  --text-2:      #74716a;
  --text-3:      #4d4b46;

  --amber:       #d4a04a;
  --amber-hi:    #f0c270;
  --amber-low:   #8a6c2c;
  --amber-bg:    rgba(212,160,74,0.07);
  --amber-line:  rgba(212,160,74,0.25);

  --cool:        #79a7ad;
  --cool-bg:     rgba(121,167,173,0.10);
  --cool-line:   rgba(121,167,173,0.32);

  --warm:        #b27d56;
  --warm-bg:     rgba(178,125,86,0.08);
  --warm-line:   rgba(178,125,86,0.28);

  --pos:         #87a87f;
  --neg:         #b27a6a;
  --pos-bg:      rgba(135,168,127,0.10);
  --neg-bg:      rgba(178,122,106,0.10);

  --stage-hold:  #d4a04a;
  --stage-watch: #79a7ad;
  --stage-pass:  #74716a;
}

* { box-sizing: border-box; }

html, body, [class*="stApp"] {
  background: var(--bg-0) !important;
  color: var(--text-0);
  font-family: "Hanken Grotesk", system-ui, sans-serif;
  font-size: 13px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
  font-feature-settings: "ss01";
}

[data-testid="stAppViewContainer"] {
  background-image:
    radial-gradient(1100px 600px at 80% -10%, rgba(212,160,74,0.05), transparent 60%),
    radial-gradient(800px 500px at 10% -10%, rgba(121,167,173,0.03), transparent 70%),
    radial-gradient(circle at 1px 1px, rgba(255,255,255,0.018) 1px, transparent 0);
  background-size: auto, auto, 22px 22px;
  background-attachment: fixed;
}

/* hide default streamlit chrome we don't want */
header[data-testid="stHeader"] { background: transparent; }
footer { visibility: hidden; }
#MainMenu { visibility: hidden; }
[data-testid="stToolbar"] { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }

/* let our custom layout span the full viewport */
.block-container {
  max-width: 1480px !important;
  padding-top: 1rem !important;
  padding-bottom: 3rem !important;
  padding-left: 24px !important;
  padding-right: 24px !important;
}

/* native Streamlit tabs styled to look like topnav */
[data-baseweb="tab-list"] {
  border-bottom: 1px solid var(--line) !important;
  background: rgba(11,12,15,0.92) !important;
  gap: 0 !important;
}
[data-baseweb="tab"] {
  padding: 10px 16px !important;
  color: var(--text-2) !important;
  font-size: 11px !important;
  font-weight: 500 !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
  background: transparent !important;
}
[data-baseweb="tab"]:hover { color: var(--text-0) !important; }
[data-baseweb="tab"][aria-selected="true"] {
  color: var(--amber-hi) !important;
  border-bottom: 2px solid var(--amber) !important;
}
[data-baseweb="tab-highlight"] { background: var(--amber) !important; }

/* native Streamlit widgets adapted to the dark canvas */
[data-testid="stTextInput"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] > div {
  background: var(--bg-1) !important;
  border: 1px solid var(--line) !important;
  color: var(--text-0) !important;
  font-family: "JetBrains Mono", monospace !important;
}
[data-testid="stTextInput"] input:focus {
  border-color: var(--amber) !important;
}

/* The selectbox dropdown popup — keep it scrollable so a long
   watchlist doesn't take over the viewport. BaseWeb renders the
   listbox in a portal at the document body, so the selectors target
   the rendered nodes directly. */
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="menu"] [role="listbox"],
ul[role="listbox"] {
  max-height: 320px !important;
  overflow-y: auto !important;
  scrollbar-width: thin;
  scrollbar-color: var(--line-strong) var(--bg-1);
}
[data-baseweb="popover"] [role="listbox"]::-webkit-scrollbar,
[data-baseweb="menu"] [role="listbox"]::-webkit-scrollbar,
ul[role="listbox"]::-webkit-scrollbar {
  width: 6px;
}
[data-baseweb="popover"] [role="listbox"]::-webkit-scrollbar-thumb,
[data-baseweb="menu"] [role="listbox"]::-webkit-scrollbar-thumb,
ul[role="listbox"]::-webkit-scrollbar-thumb {
  background: var(--line-strong);
  border-radius: 1px;
}

button[kind="secondary"], button[kind="primary"] {
  background: var(--bg-2) !important;
  border: 1px solid var(--line) !important;
  color: var(--text-1) !important;
  font-family: "JetBrains Mono", monospace !important;
  font-size: 10px !important;
  letter-spacing: 1.4px !important;
  text-transform: uppercase !important;
  border-radius: 2px !important;
}
button[kind="secondary"]:hover, button[kind="primary"]:hover {
  color: var(--amber-hi) !important;
  border-color: var(--amber-line) !important;
}
button[kind="primary"] {
  background: var(--amber-bg) !important;
  color: var(--amber-hi) !important;
  border-color: var(--amber-line) !important;
}

/* Popover-internal buttons: tighter so 3 list pills (Holding /
   Shortlist / Watchlist) sit on one line each inside the list-picker
   popover. The default 1.4px letter-spacing pushes "WATCHLIST" past
   the column edge and forces a second line. */
[data-baseweb="popover"] button[kind="secondary"],
[data-baseweb="popover"] button[kind="primary"] {
  font-size: 9px !important;
  letter-spacing: 0.6px !important;
  padding: 4px 6px !important;
  white-space: nowrap !important;
}
[data-baseweb="popover"] [data-testid="stVerticalBlockBorderWrapper"],
[data-baseweb="popover"] > div {
  min-width: 320px;
}

/* ----------  T O P   B A R  ---------- */
.topbar {
  display: flex;
  align-items: center;
  padding: 0 24px;
  height: 44px;
  border-bottom: 1px solid var(--line);
  background: rgba(11,12,15,0.92);
  margin: -1rem -24px 0;
}
.brand {
  font-weight: 700;
  font-size: 15px;
  letter-spacing: -0.2px;
  color: var(--text-0);
}
.brand .slash { color: var(--amber); margin: 0 8px; }
.brand .sub {
  font-weight: 400;
  color: var(--text-2);
  margin-left: 6px;
  font-size: 12px;
}
.topbar .spacer { flex: 1; }
.topbar .meta {
  display: flex;
  gap: 18px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: var(--text-2);
}
.topbar .meta .live { color: var(--text-1); }
.topbar .meta .live::before {
  content: "●";
  color: var(--amber);
  margin-right: 6px;
  font-size: 8px;
  vertical-align: 2px;
  animation: livePulse 2.4s ease-in-out infinite;
}
@keyframes livePulse { 0%, 70%, 100% { opacity: 1; } 35% { opacity: 0.25; } }

/* ----------  T I C K E R   B A R  ---------- */
.ticker-bar {
  background: var(--bg-1);
  border: 1px solid var(--line);
  margin-bottom: 10px;
}

/* List picker — sits in normal flow right below the hero. The
   button itself is styled to look like the hero pill (amber border,
   small caps, JetBrains Mono) so it still reads as part of the hero
   region without overlapping any of its content. */
.st-key-hero_picker {
  margin-bottom: 18px;
  width: fit-content;
  max-width: 240px;
}
.st-key-hero_picker [data-testid="stPopover"] > div > button,
.st-key-hero_picker button[kind="secondary"]:first-of-type {
  background: var(--amber-bg) !important;
  border: 1px solid var(--amber-line) !important;
  color: var(--amber-hi) !important;
  font-family: "JetBrains Mono", monospace !important;
  font-size: 10px !important;
  font-weight: 600 !important;
  letter-spacing: 1.5px !important;
  text-transform: uppercase !important;
  border-radius: 2px !important;
  padding: 4px 11px !important;
  min-height: 0 !important;
  height: auto !important;
  line-height: 1.4 !important;
}
.st-key-hero_picker [data-testid="stPopover"] > div > button:hover {
  border-color: var(--amber) !important;
  color: var(--amber-hi) !important;
}
.ticker-row {
  padding: 20px 24px 16px;
  display: grid;
  grid-template-columns: 340px 1fr auto;
  gap: 32px;
  align-items: center;
}
.ticker-id {
  display: flex;
  align-items: baseline;
  gap: 14px;
  flex-wrap: wrap;
}
.ticker-symbol {
  font-family: "JetBrains Mono", monospace;
  font-weight: 700;
  font-size: 34px;
  letter-spacing: -1px;
  color: var(--text-0);
  line-height: 1;
}
.ticker-symbol .exch {
  font-size: 11px;
  color: var(--text-3);
  font-weight: 400;
  margin-right: 6px;
  letter-spacing: 1px;
}
.ticker-name {
  color: var(--text-1);
  font-size: 13px;
  line-height: 1.3;
}
.ticker-name .sector {
  color: var(--text-3);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1.4px;
  margin-top: 2px;
  font-weight: 500;
}
.stat-strip {
  display: grid;
  grid-template-columns: repeat(6, minmax(0, 1fr));
  gap: 24px;
  align-items: end;
}
.stat-cell .lbl {
  font-size: 9.5px;
  text-transform: uppercase;
  color: var(--text-3);
  letter-spacing: 1.6px;
  font-weight: 600;
  margin-bottom: 5px;
}
.stat-cell .val {
  font-family: "JetBrains Mono", monospace;
  font-size: 18px;
  font-weight: 500;
  color: var(--text-0);
  font-feature-settings: "tnum";
  line-height: 1.05;
}
.stat-cell .val .ccy { color: var(--text-2); font-weight: 400; margin-right: 1px; }
.stat-cell .sub {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: var(--text-2);
  margin-top: 2px;
}
.price-cell .val {
  font-size: 26px;
  font-weight: 600;
  color: var(--text-0);
}
.delta {
  display: inline-block;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 2px;
  margin-left: 8px;
  font-weight: 500;
  vertical-align: 4px;
}
.delta.up { background: var(--pos-bg); color: var(--pos); }
.delta.dn { background: var(--neg-bg); color: var(--neg); }

.refresh-block {
  text-align: right;
  font-family: "JetBrains Mono", monospace;
}
.refresh-block .at {
  font-size: 10px;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 1.5px;
}
.refresh-block .ago {
  font-size: 12px;
  color: var(--text-1);
  margin-top: 2px;
}

/* section tab nav */
.section-nav {
  display: flex;
  gap: 0;
  border-top: 1px solid var(--line-soft);
  overflow-x: auto;
  scrollbar-width: none;
}
.section-nav::-webkit-scrollbar { display: none; }
.section-nav a {
  flex: 0 0 auto;
  padding: 10px 18px 11px;
  color: var(--text-2);
  text-decoration: none;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 1.6px;
  font-weight: 600;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}
.section-nav a .num {
  font-family: "JetBrains Mono", monospace;
  color: var(--text-3);
  margin-right: 8px;
  font-weight: 400;
}
.section-nav a:hover { color: var(--text-0); }
.section-nav a:hover .num { color: var(--amber); }
.section-nav a.active {
  color: var(--amber-hi);
  border-bottom-color: var(--amber);
}
.section-nav a.active .num { color: var(--amber); }

/* ----------  T H E S I S   C A R D  ---------- */
.tldr {
  margin: 24px 0;
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-left: 2px solid var(--amber);
}
.tldr-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 18px;
  border-bottom: 1px solid var(--line-soft);
  background: var(--bg-2);
}
.tldr-head .label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 2px;
  font-weight: 600;
  color: var(--amber);
  font-family: "JetBrains Mono", monospace;
}
.tldr-head .label .glyph { font-size: 14px; }
.tldr-head .meta {
  font-family: "JetBrains Mono", monospace;
  font-size: 10.5px;
  color: var(--text-2);
  letter-spacing: 0.5px;
}
.tldr-head .meta .dot { color: var(--text-3); margin: 0 8px; }
.thesis-body { padding: 22px 22px 20px; }

.verdict-section { margin-bottom: 20px; padding-bottom: 18px; border-bottom: 1px solid var(--line-soft); }
.block-label {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 2px;
  color: var(--amber);
  font-weight: 600;
  margin: 0 0 10px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.block-label .right {
  color: var(--text-3);
  font-weight: 400;
  letter-spacing: 0.5px;
  font-size: 10px;
}
.verdict-text {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-1);
  font-weight: 400;
  letter-spacing: -0.05px;
  max-width: 880px;
  margin: 0 0 10px;
}
.verdict-text:last-child { margin-bottom: 0; }
.verdict-text:first-of-type {
  font-size: 15px;
  color: var(--text-0);
  font-weight: 500;
}
.verdict-text strong { color: var(--text-0); font-weight: 600; }
.verdict-text em,
.sizing-row .v em {
  color: var(--amber-hi);
  font-style: normal;
  background: var(--amber-bg);
  padding: 1px 5px;
  border-radius: 1px;
  -webkit-box-decoration-break: clone;
  box-decoration-break: clone;
}

.thesis-row-1 {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
  padding-bottom: 18px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--line-soft);
}
.strategy-check, .position-sizing { margin-top: 4px; }
.strategy-item {
  display: grid;
  grid-template-columns: 22px 1fr auto;
  gap: 8px;
  padding: 7px 0;
  align-items: center;
  border-top: 1px dotted var(--line-soft);
  font-size: 12.5px;
}
.strategy-item:first-child { border-top: none; padding-top: 2px; }
.strategy-item .check {
  font-family: "JetBrains Mono", monospace;
  font-size: 13px;
  font-weight: 700;
  text-align: center;
}
.strategy-item.pass .check { color: var(--cool); }
.strategy-item.fail .check { color: var(--warm); }
.strategy-item.partial .check { color: var(--amber); }
.strategy-item .label { color: var(--text-1); min-width: 0; }
.strategy-item .verdict {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 1.4px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 1px;
}
.strategy-item.pass .verdict { color: var(--cool); background: var(--cool-bg); }
.strategy-item.fail .verdict { color: var(--warm); background: var(--warm-bg); }
.strategy-item.partial .verdict { color: var(--amber); background: var(--amber-bg); }

.sizing-row {
  display: grid;
  grid-template-columns: 86px 1fr;
  gap: 12px;
  padding: 7px 0;
  border-top: 1px dotted var(--line-soft);
  align-items: baseline;
  font-size: 12.5px;
}
.sizing-row:first-child { border-top: none; padding-top: 2px; }
.sizing-row .k {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 1.4px;
  font-weight: 600;
}
.sizing-row .v {
  color: var(--text-1);
  font-weight: 500;
  line-height: 1.5;
}

.bull-bear {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 28px;
  padding-bottom: 18px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--line-soft);
}
.case-col h4 {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 2px;
  margin: 0 0 10px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}
.case-col h4::before { content: ""; width: 18px; height: 1px; }
.case-col.bull h4 { color: var(--cool); }
.case-col.bull h4::before { background: var(--cool); }
.case-col.bear h4 { color: var(--warm); }
.case-col.bear h4::before { background: var(--warm); }
.case-list { list-style: none; padding: 0; margin: 0; }
.case-list li {
  position: relative;
  padding: 9px 0 9px 20px;
  font-size: 12.5px;
  color: var(--text-1);
  border-top: 1px dotted var(--line-soft);
  line-height: 1.5;
}
.case-list li:first-child { border-top: none; padding-top: 4px; }
.case-list li::before {
  content: "▸";
  position: absolute;
  left: 0;
  top: 9px;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
}
.case-list li:first-child::before { top: 4px; }
.case-col.bull .case-list li::before { color: var(--cool); }
.case-col.bear .case-list li::before { color: var(--warm); }
.case-list li strong { color: var(--text-0); font-weight: 600; }

/* ---- Deep-dive blocks inside the thesis card ---- */
.thesis-deepdive {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
  padding-bottom: 18px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--line-soft);
}
.thesis-block {
  background: var(--bg-2);
  border: 1px solid var(--line);
  padding: 14px 16px;
  min-width: 0;
}
.thesis-block.moat        { border-left: 2px solid var(--amber); }
.thesis-block.positioning { border-left: 2px solid var(--cool); }
.thesis-block.pricing     { border-left: 2px solid var(--amber-low); }
.thesis-block.multiplier  { border-left: 2px solid var(--warm); }
.thesis-block .block-paragraph {
  font-size: 12.5px;
  color: var(--text-1);
  line-height: 1.55;
  margin-top: 4px;
}
.thesis-block .block-paragraph strong { color: var(--text-0); font-weight: 600; }
.thesis-block .block-bullets {
  list-style: none;
  padding: 0;
  margin: 8px 0 0;
}
.thesis-block .block-bullets li {
  position: relative;
  padding: 5px 0 5px 16px;
  font-size: 12px;
  color: var(--text-1);
  line-height: 1.45;
  border-top: 1px dotted var(--line-soft);
}
.thesis-block .block-bullets li:first-child { border-top: none; }
.thesis-block .block-bullets li::before {
  content: "▸";
  position: absolute;
  left: 0;
  color: var(--amber);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  top: 6px;
}
.thesis-block .verdict-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 1px;
  letter-spacing: 1px;
}
.thesis-block .verdict-pill.cool  { color: var(--cool);  background: var(--cool-bg); }
.thesis-block .verdict-pill.warm  { color: var(--warm);  background: var(--warm-bg); }
.thesis-block .verdict-pill.amber { color: var(--amber); background: var(--amber-bg); }
.thesis-block .layer-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 1.2px;
  color: var(--cool);
  background: var(--cool-bg);
  padding: 2px 7px;
  border-radius: 1px;
}
@media (max-width: 900px) {
  .thesis-deepdive { grid-template-columns: 1fr; }
}

/* ---- v2: HEADLINE ribbon (conviction tier + variant view) ---- */
.headline-ribbon {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 16px;
  align-items: center;
  margin: 0 0 18px;
  padding: 12px 14px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  border-left: 2px solid var(--amber);
}
.conviction-pill {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 2px;
  padding: 6px 12px;
  border-radius: 1px;
  text-align: center;
  min-width: 60px;
}
.conviction-pill.core  { color: var(--amber-hi); background: var(--amber-bg); border: 1px solid var(--amber-line); }
.conviction-pill.add   { color: var(--cool);     background: var(--cool-bg);  border: 1px solid var(--cool-line); }
.conviction-pill.watch { color: var(--text-1);   background: var(--bg-3);     border: 1px solid var(--line); }
.conviction-pill.pass  { color: var(--warm);     background: var(--warm-bg);  border: 1px solid var(--warm-line); }
.headline-body { min-width: 0; }
.headline-line {
  font-size: 14px;
  color: var(--text-0);
  font-weight: 500;
  line-height: 1.45;
  margin-bottom: 4px;
}
.headline-line strong { color: var(--text-0); font-weight: 600; }
.variant-view {
  display: flex;
  gap: 10px;
  font-size: 12px;
  color: var(--text-1);
  line-height: 1.4;
}
.variant-label {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  letter-spacing: 1.4px;
  color: var(--cool);
  background: var(--cool-bg);
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 1px;
  flex-shrink: 0;
  height: fit-content;
  margin-top: 1px;
}
.variant-text strong { color: var(--text-0); font-weight: 600; }
.variant-text em {
  color: var(--amber-hi);
  font-style: normal;
  background: var(--amber-bg);
  padding: 1px 4px;
  border-radius: 1px;
}

/* ---- v2: Strategy-check evidence line ---- */
.strategy-item .label .strategy-evidence {
  display: block;
  font-family: "JetBrains Mono", monospace;
  font-size: 10.5px;
  color: var(--text-2);
  font-weight: 400;
  margin-top: 2px;
  letter-spacing: 0.2px;
  line-height: 1.35;
}
.strategy-evidence em { color: var(--amber-hi); font-style: normal; background: var(--amber-bg); padding: 0 4px; }

/* ---- v2: Extras row (catalysts / premortem / optionality) ---- */
.thesis-extras {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  gap: 14px;
  padding-bottom: 18px;
  margin-bottom: 18px;
  border-bottom: 1px solid var(--line-soft);
}
@media (max-width: 1100px) {
  .thesis-extras { grid-template-columns: 1fr; }
}
.thesis-extras .thesis-block { padding: 14px 16px; }
.thesis-block.catalysts-block  { border-left: 2px solid var(--cool); }
.thesis-block.premortem-block  { border-left: 2px solid var(--warm); }
.thesis-block.optionality-block { border-left: 2px solid var(--amber); }

.catalyst-grid { margin-top: 2px; }
.catalyst-row {
  display: grid;
  grid-template-columns: 95px 1fr 1fr 70px;
  gap: 10px;
  padding: 8px 0;
  border-top: 1px dotted var(--line-soft);
  align-items: baseline;
  font-size: 12px;
  line-height: 1.4;
}
.catalyst-row:first-child { border-top: none; padding-top: 2px; }
.catalyst-row .when {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
}
.catalyst-row .event { color: var(--text-1); }
.catalyst-row .event strong { color: var(--text-0); font-weight: 600; }
.catalyst-row .edge { color: var(--text-2); font-size: 11.5px; }
.catalyst-row .edge em {
  color: var(--amber-hi);
  font-style: normal;
  background: var(--amber-bg);
  padding: 1px 4px;
  border-radius: 1px;
}
.catalyst-row .conf {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 1.2px;
  padding: 2px 6px;
  border-radius: 1px;
  text-align: center;
  white-space: nowrap;
}
.catalyst-row .conf.cool  { color: var(--cool);  background: var(--cool-bg); }
.catalyst-row .conf.amber { color: var(--amber); background: var(--amber-bg); }
.catalyst-row .conf.warm  { color: var(--warm);  background: var(--warm-bg); }

/* ---- v2: Pre-mortem block ---- */
.kill-switch {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-top: 4px;
  padding: 8px 10px;
  background: var(--warm-bg);
  border: 1px solid var(--warm-line);
}
.ks-label {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 1.4px;
  color: var(--warm);
  flex-shrink: 0;
  margin-top: 1px;
}
.ks-text {
  font-size: 12px;
  color: var(--text-0);
  line-height: 1.45;
}
.ks-text strong { color: var(--text-0); font-weight: 600; }
.ks-text em { color: var(--warm); font-style: normal; }
.ignored-label {
  margin-top: 12px;
  margin-bottom: 4px;
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  letter-spacing: 1.2px;
  color: var(--text-3);
  text-transform: uppercase;
  font-weight: 600;
}

/* ---- v2: Scenario row vs-PT badge + asymmetry summary ---- */
.scenario-row .vs-pt {
  display: block;
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.5px;
  margin-top: 1px;
  font-weight: 400;
}
.asymmetry-row {
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dotted var(--line-soft);
  font-family: "JetBrains Mono", monospace;
  font-size: 10.5px;
  letter-spacing: 1px;
}
.asymmetry-row span:first-child {
  color: var(--text-3);
  text-transform: uppercase;
  font-weight: 600;
}
.asymmetry-row span:last-child {
  color: var(--amber-hi);
  font-weight: 600;
}

/* ---- v2: Ownership card QoQ Δ badge ---- */
.flow-row .qoq {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  font-weight: 400;
  margin-left: 6px;
}
.flow-row .qoq.pos { color: var(--cool); }
.flow-row .qoq.neg { color: var(--warm); }
.flow-row .qoq.flat { color: var(--text-3); }

/* ---- Per-section Claude paragraph (between header and KPI grid) ---- */
.section-paragraph {
  background: var(--bg-1);
  border: 1px solid var(--line-soft);
  border-left: 2px solid var(--amber);
  padding: 12px 16px;
  margin: 4px 0 14px;
  font-size: 12.5px;
  color: var(--text-1);
  line-height: 1.55;
}
.section-paragraph strong { color: var(--text-0); font-weight: 600; }
.section-paragraph .glyph { color: var(--amber); margin-right: 8px; }

.thesis-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.thesis-mini {
  background: var(--bg-2);
  border: 1px solid var(--line);
  padding: 14px 16px;
  min-width: 0;
}
.thesis-mini h5 {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  text-transform: uppercase;
  color: var(--text-2);
  letter-spacing: 1.6px;
  font-weight: 700;
  margin: 0 0 12px;
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 10px;
}
.thesis-mini h5 > span:first-child { flex: 1 1 auto; min-width: 0; }
.thesis-mini h5 .tag {
  font-weight: 500;
  letter-spacing: 0.6px;
  font-size: 9.5px;
  padding: 1px 6px;
  border-radius: 1px;
  white-space: nowrap;
  flex-shrink: 0;
}
.thesis-mini h5 .tag.cool { color: var(--cool); background: var(--cool-bg); }
.thesis-mini h5 .tag.warm { color: var(--warm); background: var(--warm-bg); }
.thesis-mini h5 .tag.amber { color: var(--amber); background: var(--amber-bg); }

.flow-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 6px 0;
  font-size: 12px;
  color: var(--text-1);
  gap: 12px;
}
.flow-row + .flow-row { border-top: 1px dotted var(--line-soft); }
.flow-row .who {
  color: var(--text-2);
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  font-weight: 600;
  min-width: 0;
}
.flow-row .val {
  font-family: "JetBrains Mono", monospace;
  color: var(--text-0);
  font-weight: 500;
  font-size: 12px;
}
.flow-row .val.pos { color: var(--cool); }
.flow-row .val.neg { color: var(--warm); }
.flow-row .val.flat { color: var(--text-2); }

.thesis-takeaway {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px solid var(--line-soft);
  font-size: 11.5px;
  color: var(--text-1);
  line-height: 1.5;
}
.thesis-takeaway strong { color: var(--amber-hi); font-weight: 600; }

.scenario-row {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr) 44px 58px;
  gap: 8px;
  padding: 6px 0;
  font-family: "JetBrains Mono", monospace;
  font-size: 11.5px;
  align-items: baseline;
}
.scenario-row + .scenario-row { border-top: 1px dotted var(--line-soft); }
.scenario-row .name {
  font-size: 9.5px;
  text-transform: uppercase;
  letter-spacing: 1.4px;
  font-weight: 700;
}
.scenario-row.bull .name { color: var(--cool); }
.scenario-row.base .name { color: var(--text-1); }
.scenario-row.bear .name { color: var(--warm); }
.scenario-row .desc {
  font-family: "Hanken Grotesk", sans-serif;
  font-size: 11px;
  color: var(--text-2);
  line-height: 1.35;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.scenario-row .multi {
  color: var(--text-0);
  font-weight: 600;
  text-align: right;
}
.scenario-row .px { color: var(--text-1); text-align: right; }
.scenario-row.bull .multi { color: var(--cool); }
.scenario-row.bear .multi { color: var(--warm); }

/* ----------  S E C T I O N S  ---------- */
.section {
  margin-bottom: 36px;
  /* sticky topbar height + a small breathing buffer so the anchor scroll
     doesn't tuck the heading under the bar */
  scroll-margin-top: 64px;
}
html { scroll-behavior: smooth; }
.section-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding-bottom: 8px;
  margin-bottom: 12px;
  border-bottom: 1px solid var(--line);
}
.section-head .num {
  font-family: "JetBrains Mono", monospace;
  color: var(--amber);
  font-size: 12px;
  letter-spacing: 1.5px;
}
.section-head h2 {
  font-size: 16px;
  font-weight: 600;
  letter-spacing: 1.5px;
  text-transform: uppercase;
  margin: 0;
  color: var(--text-0);
}
.section-head .badge {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--text-3);
  margin-left: auto;
  letter-spacing: 0.8px;
}
.claude-line {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 16px;
  padding: 0 2px;
  color: var(--text-1);
  font-size: 12.5px;
  line-height: 1.5;
}
.claude-line .glyph {
  color: var(--amber);
  font-size: 11px;
  margin-top: 2px;
  flex-shrink: 0;
}
.claude-line strong { color: var(--text-0); font-weight: 600; }

/* ----------  K P I   G R I D  ---------- */
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.kpi-grid.cols-6 { grid-template-columns: repeat(6, minmax(0, 1fr)); }
.kpi-grid.cols-5 { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.kpi-grid.cols-3 { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.kpi-grid.cols-2 { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.kpi {
  background: var(--bg-1);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  position: relative;
  min-height: 132px;
}
.kpi:hover { background: var(--bg-2); }
.kpi-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.kpi-label {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--text-2);
  letter-spacing: 1.5px;
  font-weight: 600;
}
.kpi-tag {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  padding: 1px 5px;
  border-radius: 1px;
  letter-spacing: 0.5px;
  font-weight: 500;
}
.kpi-tag.cool { background: var(--cool-bg); color: var(--cool); }
.kpi-tag.warm { background: var(--warm-bg); color: var(--warm); }
.kpi-tag.amber { background: var(--amber-bg); color: var(--amber); }
.kpi-tag.neutral { background: var(--bg-3); color: var(--text-2); }

.kpi-value {
  font-family: "JetBrains Mono", monospace;
  font-weight: 500;
  font-size: 28px;
  color: var(--text-0);
  line-height: 1;
  letter-spacing: -0.5px;
  font-feature-settings: "tnum";
}
.kpi-value .unit {
  font-size: 16px;
  color: var(--text-2);
  margin-left: 2px;
  font-weight: 400;
}
.kpi-value .ccy { color: var(--text-2); font-weight: 400; }
.kpi-caption {
  font-size: 11.5px;
  color: var(--text-1);
  line-height: 1.4;
  margin-top: auto;
  padding-top: 4px;
}
.kpi-caption strong { color: var(--text-0); font-weight: 600; }

/* ----- KPI info popover -------------------------------------------- */
/* Group tag + info button on the right of the header. Keeps the tag
   layout intact when the info button is present. */
.kpi-head-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
/* The <details>/<summary> native disclosure widget powers the popover.
   We hide the default arrow and style summary as a discreet info chip. */
.kpi-info {
  position: relative;
  line-height: 1;
}
.kpi-info > summary {
  list-style: none;
  cursor: pointer;
  user-select: none;
  font-size: 11px;
  color: var(--text-3);
  width: 16px;
  height: 16px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  transition: color 120ms, background 120ms;
}
.kpi-info > summary::-webkit-details-marker { display: none; }
.kpi-info > summary::marker { content: ""; }
.kpi-info > summary:hover {
  color: var(--text-1);
  background: var(--bg-3);
}
.kpi-info[open] > summary {
  color: var(--amber);
  background: var(--amber-bg, var(--bg-3));
}
/* Popover body — absolutely positioned so it overlays neighbouring
   tiles. Right-anchored so it doesn't push beyond the viewport on the
   rightmost column. z-index keeps it above the next tile's hover state. */
.kpi-info-popover {
  position: absolute;
  top: calc(100% + 8px);
  right: -4px;
  z-index: 200;
  width: 280px;
  background: var(--bg-0, #0d0d0d);
  border: 1px solid var(--line);
  padding: 12px 14px;
  font-family: "Inter", -apple-system, system-ui, sans-serif;
  font-size: 11.5px;
  color: var(--text-1);
  line-height: 1.45;
  box-shadow: 0 10px 32px rgba(0, 0, 0, 0.5);
  border-radius: 3px;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
}
/* Small ▴ pointer at the top-right indicating the popover came from
   the info button. */
.kpi-info-popover::before {
  content: "";
  position: absolute;
  top: -5px;
  right: 8px;
  width: 8px;
  height: 8px;
  background: var(--bg-0, #0d0d0d);
  border-top: 1px solid var(--line);
  border-left: 1px solid var(--line);
  transform: rotate(45deg);
}
.kpi-info-section + .kpi-info-section { margin-top: 10px; }
.kpi-info-key {
  display: block;
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  letter-spacing: 1.2px;
  color: var(--text-3);
  margin-bottom: 4px;
  font-weight: 600;
}
.kpi-info-popover p {
  margin: 0;
  color: var(--text-1);
}
/* On the rightmost column the right-anchored popover can still poke
   past the page. The .kpi-grid keeps overflow visible via default, but
   we add a media-query fallback below for narrow viewports. */
@media (max-width: 720px) {
  .kpi-info-popover { width: 240px; right: -2px; }
}

.pctile {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
.pct-track {
  position: relative;
  flex: 1;
  height: 4px;
  background: var(--bg-3);
}
.pct-track::before {
  content: "";
  position: absolute;
  left: 50%;
  top: -3px;
  bottom: -3px;
  width: 1px;
  background: var(--text-3);
}
.pct-mark {
  position: absolute;
  top: -2px;
  width: 2px;
  height: 8px;
  background: var(--amber);
  transform: translateX(-1px);
}
.pct-caption {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  color: var(--text-2);
  letter-spacing: 0.3px;
  flex-shrink: 0;
}

.spark-wrap {
  margin-top: 4px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.spark {
  width: 90px;
  height: 22px;
  overflow: visible;
}
.spark polyline {
  fill: none;
  stroke: var(--amber);
  stroke-width: 1.4;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.spark .spark-dot { fill: var(--amber-hi); }
.spark-cap {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--text-2);
  letter-spacing: 0.3px;
}

/* ----------  S E N T I M E N T  ---------- */
.sent-grid {
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: 16px;
}
.sent-meter-card {
  background: var(--bg-1);
  border: 1px solid var(--line);
  padding: 18px 20px;
}
.sent-meter-card .h {
  font-size: 10px;
  text-transform: uppercase;
  color: var(--text-2);
  letter-spacing: 1.6px;
  font-weight: 600;
  margin-bottom: 14px;
  display: flex;
  justify-content: space-between;
}
.sent-meter-card .h .delta-small { color: var(--pos); }
.sent-meter-card .big {
  font-family: "JetBrains Mono", monospace;
  font-size: 56px;
  color: var(--text-0);
  line-height: 1;
  margin-bottom: 4px;
  font-weight: 500;
  letter-spacing: -2px;
}
.sent-meter-card .big .pos { color: var(--amber-hi); }
.sent-meter-card .baseline {
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  color: var(--text-1);
  margin-bottom: 14px;
}
.sent-meter-card .baseline .ref { color: var(--text-3); }
.sent-track {
  position: relative;
  height: 24px;
  margin: 6px 0 8px;
}
.sent-track .bar {
  position: absolute;
  left: 0; right: 0;
  top: 50%;
  height: 3px;
  transform: translateY(-50%);
  background: linear-gradient(to right, var(--warm) 0%, var(--text-3) 50%, var(--cool) 100%);
  opacity: 0.4;
}
.sent-track .marker {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 12px; height: 12px;
  border-radius: 50%;
  background: var(--amber);
  box-shadow: 0 0 0 3px var(--bg-1);
}
.sent-track .baseline-tick {
  position: absolute;
  top: 50%;
  transform: translate(-50%, -50%);
  width: 1px; height: 12px;
  background: var(--text-3);
}
.sent-track .ticks {
  position: absolute;
  width: 100%;
  bottom: -16px;
  display: flex;
  justify-content: space-between;
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  color: var(--text-3);
  letter-spacing: 0.5px;
}
.sent-trust {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--text-3);
  letter-spacing: 0.3px;
  margin: -4px 0 12px;
}
.sent-trust.untrusted {
  color: var(--warm);
  font-weight: 600;
}
.sent-meter-card[data-untrusted="1"] {
  opacity: 0.55;
}
.sent-meter-card[data-untrusted="1"] .big {
  color: var(--text-2);
}
.sent-meter-card[data-untrusted="1"] .big .pos {
  color: var(--text-1);
}

.sent-counts {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-top: 28px;
  padding-top: 16px;
  border-top: 1px solid var(--line-soft);
}
.sent-counts .c .l {
  font-size: 9.5px;
  text-transform: uppercase;
  color: var(--text-3);
  letter-spacing: 1.4px;
  font-weight: 600;
}
.sent-counts .c .n {
  font-family: "JetBrains Mono", monospace;
  font-size: 16px;
  color: var(--text-0);
  margin-top: 2px;
}

.sent-themes {
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-left: 2px solid var(--amber);
  padding: 16px 18px;
}
.sent-themes .h {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  text-transform: uppercase;
  color: var(--amber);
  letter-spacing: 2px;
  font-weight: 600;
  margin-bottom: 12px;
  display: flex;
  justify-content: space-between;
}
.sent-themes .h .meta { color: var(--text-2); font-weight: 400; letter-spacing: 0.5px; }
.sent-themes ul { margin: 0; padding: 0; list-style: none; }
.sent-themes li {
  display: grid;
  grid-template-columns: 80px 1fr auto;
  gap: 14px;
  align-items: baseline;
  padding: 8px 0;
  border-top: 1px dotted var(--line-soft);
  font-size: 12.5px;
  color: var(--text-1);
}
.sent-themes li:first-child { border-top: none; padding-top: 4px; }
.sent-themes li .tag {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  font-weight: 600;
}
.sent-themes li .tag.bull { color: var(--cool); }
.sent-themes li .tag.bear { color: var(--warm); }
.sent-themes li .tag.watch { color: var(--amber); }
.sent-themes li .text { color: var(--text-0); }
.sent-themes li .vol {
  font-family: "JetBrains Mono", monospace;
  font-size: 10.5px;
  color: var(--text-2);
}

.quote-grid {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 1px;
  background: var(--line);
  border: 1px solid var(--line);
}
.qcard {
  background: var(--bg-1);
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: 130px;
}
.qcard .src {
  display: flex;
  justify-content: space-between;
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 1.2px;
}
.qcard .src .score { font-weight: 600; }
.qcard .src .score.pos { color: var(--cool); }
.qcard .src .score.neg { color: var(--warm); }
.qcard .q {
  font-size: 12px;
  color: var(--text-0);
  line-height: 1.45;
  margin-top: 2px;
}
.qcard .q::before {
  content: "\201C";
  color: var(--amber);
  margin-right: 2px;
}
.qcard .meta {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  color: var(--text-3);
  margin-top: auto;
  letter-spacing: 0.5px;
}

/* ----------  A C T I V I T Y   B A N D  ---------- */
.activity-band {
  margin-top: 32px;
  padding: 14px 16px;
  background: var(--bg-1);
  border: 1px solid var(--line);
  display: grid;
  grid-template-columns: 200px 1fr;
  gap: 24px;
  align-items: center;
}
.activity-band .lbl {
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--amber);
  text-transform: uppercase;
  letter-spacing: 2px;
  font-weight: 600;
}
.activity-band .lbl .glyph { margin-right: 6px; }
.activity-band ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: 22px;
  flex-wrap: wrap;
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  color: var(--text-1);
}
.activity-band li { display: flex; gap: 8px; }
.activity-band li .t { color: var(--text-3); }
.activity-band li.live .t::after {
  content: " ●";
  color: var(--amber);
  animation: livePulse 1.5s ease-in-out infinite;
}

.footer-note {
  margin: 40px auto 60px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  color: var(--text-3);
  font-size: 11px;
  font-family: "JetBrains Mono", monospace;
  text-align: center;
  letter-spacing: 0.5px;
}
.footer-note strong { color: var(--amber); font-weight: 500; }

/* ----------  C O M P A R E  ---------- */
.pin-row {
  display: grid;
  background: var(--bg-1);
  border: 1px solid var(--line);
  margin-top: 16px;
}
.pin-cell {
  padding: 14px 16px;
  border-right: 1px solid var(--line);
}
.pin-cell:last-child { border-right: none; }
.pin-cell.row-lbl {
  background: var(--bg-2);
  display: flex;
  flex-direction: column;
  justify-content: center;
  color: var(--text-2);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1.6px;
  font-weight: 600;
}
.pin-cell.row-lbl .count {
  font-family: "JetBrains Mono", monospace;
  color: var(--text-3);
  font-weight: 400;
  margin-top: 4px;
}
.pin-cell .pin-id {
  font-family: "JetBrains Mono", monospace;
  font-weight: 700;
  font-size: 18px;
  color: var(--text-0);
  letter-spacing: -0.3px;
}
.pin-cell .pin-name {
  color: var(--text-3);
  font-size: 10.5px;
  margin-top: 2px;
  text-transform: uppercase;
  letter-spacing: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pin-cell .pin-price {
  font-family: "JetBrains Mono", monospace;
  font-size: 16px;
  color: var(--text-0);
  margin-top: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.pin-cell .pin-price .delta-mini {
  font-size: 10.5px;
  padding: 1px 4px;
  border-radius: 1px;
  font-weight: 500;
}
.pin-cell .pin-price .delta-mini.up { color: var(--pos); background: var(--pos-bg); }
.pin-cell .pin-price .delta-mini.dn { color: var(--neg); background: var(--neg-bg); }
.pin-cell .pin-meta {
  display: flex;
  gap: 12px;
  margin-top: 6px;
  font-family: "JetBrains Mono", monospace;
  font-size: 10px;
  color: var(--text-2);
}

/* .pin-row uses inline grid-template-columns set by the renderer so it
   matches the .ct table width below it. */

.ct {
  display: grid;
  border: 1px solid var(--line);
  border-top: none;
  margin-bottom: 32px;
}
.ct-group-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  padding: 14px 16px 8px;
  background: var(--bg-2);
  border-top: 1px solid var(--line);
}
.ct-group-head .num {
  font-family: "JetBrains Mono", monospace;
  color: var(--amber);
  font-size: 11px;
  letter-spacing: 1.5px;
}
.ct-group-head h3 {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 1.6px;
  text-transform: uppercase;
  margin: 0;
  color: var(--text-0);
}
.ct .lbl {
  padding: 12px 16px;
  background: var(--bg-2);
  color: var(--text-1);
  font-size: 11.5px;
  border-top: 1px solid var(--line-soft);
  border-right: 1px solid var(--line);
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.ct .lbl .lbl-hint {
  color: var(--text-3);
  font-size: 10px;
  margin-top: 2px;
  font-family: "JetBrains Mono", monospace;
  letter-spacing: 0.3px;
}
.ct .cell {
  padding: 12px 16px;
  border-top: 1px solid var(--line-soft);
  border-right: 1px solid var(--line);
  font-family: "JetBrains Mono", monospace;
  font-size: 14px;
  color: var(--text-0);
  display: flex;
  align-items: center;
  position: relative;
  font-feature-settings: "tnum";
}
.ct .cell:last-child { border-right: none; }
.ct .cell.best {
  background: var(--cool-bg);
  color: var(--cool);
  border-left: 2px solid var(--cool);
  padding-left: 14px;
}
.ct .cell.worst {
  background: var(--warm-bg);
  color: var(--warm);
}
.ct .cell .badge {
  position: absolute;
  top: 4px; right: 6px;
  font-size: 9px;
  color: var(--cool);
  letter-spacing: 0.5px;
  font-weight: 600;
  text-transform: uppercase;
}

/* ----------  W A T C H L I S T  ---------- */
.wl-col-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  border: 1px solid var(--line);
  background: var(--bg-2);
  margin-bottom: 12px;
}
.wl-col-head .wl-col-name {
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  letter-spacing: 2px;
  font-weight: 700;
}
.wl-col-head .wl-col-count {
  font-family: "JetBrains Mono", monospace;
  font-size: 12px;
  color: var(--text-2);
}
.wl-col-head.wl-amber { border-left: 2px solid var(--amber); }
.wl-col-head.wl-amber .wl-col-name { color: var(--amber); }
.wl-col-head.wl-warm  { border-left: 2px solid var(--warm); }
.wl-col-head.wl-warm  .wl-col-name { color: var(--warm); }
.wl-col-head.wl-cool  { border-left: 2px solid var(--cool); }
.wl-col-head.wl-cool  .wl-col-name { color: var(--cool); }

.wl-empty {
  text-align: center;
  padding: 24px 12px;
  color: var(--text-3);
  font-family: "JetBrains Mono", monospace;
  font-size: 11px;
  letter-spacing: 1px;
  border: 1px dashed var(--line);
  margin-bottom: 12px;
}

.watch-card {
  background: var(--bg-1);
  border: 1px solid var(--line);
  border-left: 2px solid var(--text-3);
  padding: 12px 14px 10px;
  margin-bottom: 6px;
}
.watch-card.is-holding   { border-left-color: var(--amber); }
.watch-card.is-shortlist { border-left-color: var(--warm); }
.watch-card.is-watchlist { border-left-color: var(--cool); }
.watch-card .wc-top {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}
.watch-card .wc-id {
  font-family: "JetBrains Mono", monospace;
  font-weight: 700;
  font-size: 18px;
  color: var(--text-0);
  letter-spacing: -0.3px;
}
.watch-card .wc-list {
  font-family: "JetBrains Mono", monospace;
  font-size: 9.5px;
  color: var(--text-3);
  letter-spacing: 1.4px;
}
.watch-card .wc-name {
  color: var(--text-2);
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-top: 3px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.watch-card .wc-price {
  font-family: "JetBrains Mono", monospace;
  font-size: 15px;
  color: var(--text-0);
  margin-top: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.watch-card .wc-price .delta-mini {
  font-size: 10.5px;
  padding: 1px 4px;
  border-radius: 1px;
  font-weight: 500;
}
.watch-card .wc-price .delta-mini.up { color: var(--pos); background: var(--pos-bg); }
.watch-card .wc-price .delta-mini.dn { color: var(--neg); background: var(--neg-bg); }
.watch-card .wc-meta {
  font-family: "JetBrains Mono", monospace;
  font-size: 10.5px;
  color: var(--text-3);
  margin-top: 4px;
  letter-spacing: 0.4px;
}

@media (max-width: 1280px) {
  .kpi-grid.cols-6 { grid-template-columns: repeat(4, 1fr); }
  .kpi-grid.cols-5 { grid-template-columns: repeat(4, 1fr); }
  .quote-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 1200px) {
  .thesis-cards { grid-template-columns: 1fr 1fr; }
}
@media (max-width: 960px) {
  .kpi-grid, .kpi-grid.cols-4 { grid-template-columns: repeat(2, 1fr); }
  .ticker-row { grid-template-columns: 1fr; }
  .stat-strip { grid-template-columns: repeat(3, 1fr); }
  .sent-grid { grid-template-columns: 1fr; }
  .thesis-cards { grid-template-columns: 1fr; }
  .thesis-row-1, .bull-bear { grid-template-columns: 1fr; }
}
"""


SVG_DEFS = """
<svg width="0" height="0" style="position:absolute">
  <defs>
    <linearGradient id="grad-amber" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#d4a04a" stop-opacity="0.7"/>
      <stop offset="100%" stop-color="#d4a04a" stop-opacity="0"/>
    </linearGradient>
  </defs>
</svg>
"""


def inject_theme() -> None:
    """Write the v2 stylesheet + reusable SVG defs into the page."""
    st.markdown(f"<style>{THEME_CSS}</style>", unsafe_allow_html=True)
    st.markdown(SVG_DEFS, unsafe_allow_html=True)
