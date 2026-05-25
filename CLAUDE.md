# FIRE — AI Stock Research Dashboard

A local Streamlit dashboard for **long-term** investing in the AI value
chain. Runs entirely on the user's machine; talks to the local `claude`
CLI for AI-authored research, yfinance for market data, and SEC EDGAR
for filings. SQLite for persistence. No server, no auth, no cloud.

## Spirit of the tool (read first)

This is research, not trading. When proposing features or logic:

- **Long-term positions only.** No short-term trading or day-trading
  signals. The user's specific horizon and return targets live in
  `STRATEGY.md` (see below) and should be respected.
- **Derivatives are for hedging and income only**, never directional
  bets. Covered calls on holdings the user would be willing to sell;
  cash-secured puts on stocks they want to accumulate.
- **Valuation labels and Claude theses are research inputs, not
  buy/sell calls.** Keep all scoring transparent and explainable in
  the UI.
- **The tool never places trades or moves money.**

## Architecture

- `app.py` — Streamlit UI. Four tabs:
  - **RESEARCH** — per-ticker deep dive (sticky context bar, 9 KPI
    sections, Claude thesis card).
  - **COMPARE** — pin up to 4 tickers side-by-side.
  - **WATCHLIST** — three-column ladder (Holding / Shortlist /
    Watchlist), add tickers, EDGAR theme search.
  - **STRATEGY** — edit `STRATEGY.md` (frontmatter + body) from the UI.
- `fire/` — Python package:
  - `config.py` — loads `watchlist.yaml`, `settings.yaml`, `.env`;
    writes back to `watchlist.yaml` (comment-preserving via ruamel.yaml).
  - `strategy.py` — loads/saves `STRATEGY.md` (YAML frontmatter +
    Markdown body). Used as system context for every Claude call.
  - `db.py` — SQLite storage (snapshots, earnings, filings, sentiment,
    `watchlist_meta` lists, Claude response cache).
  - `market.py` — Yahoo Finance data via yfinance.
  - `edgar.py` — SEC EDGAR filings + full-text search.
  - `valuation.py` — transparent rules-based valuation scoring.
  - `scoring.py` — pluggable tone scorer (VADER default, FinBERT opt-in).
  - `sources/` — sentiment adapters: reddit, stocktwits, news, x (dormant).
  - `sentiment.py` — orchestrator: ingest, score, persist, rollups.
  - `claude_cli.py` — wrapper around the local `claude` CLI (cached + cost-capped).
  - `processors/` — per-document-type Claude prompts (thesis, 10-K, transcript, social).
  - `collector.py` — daily snapshot + sentiment collector (CLI + importable).
  - `brief.py` — Markdown research brief generator.
- `watchlist.yaml` / `settings.yaml` / `STRATEGY.md` — user-editable config.
- `.streamlit/config.toml` — theme + home-network binding.
- Data lives in `data/fire.db` (gitignored). History matters: shift
  and percentile signals sharpen as daily snapshots accumulate.

## Lists (the user's funnel)

Every ticker lives on exactly one list, stored in SQLite
(`watchlist_meta.list_name`):

  **`holding`** → **`shortlist`** → **`watchlist`**

Tickers move freely between lists via the per-card picker in the
Watchlist tab. Initial list assignment comes from the optional `lists:`
block at the bottom of `watchlist.yaml` the first time a ticker is
seen; after that the DB is the source of truth and the YAML is written
back only when a ticker is added or removed.

## Strategy file

`STRATEGY.md` at the project root holds the user's investing
philosophy as YAML frontmatter (horizon, return target, themes, hard
rules) plus a free-form Markdown body. `claude_cli.py` reads this
file via `fire.strategy.load_strategy()` and prepends the whole
document to every Claude prompt as system context.

The Strategy tab edits this file from the UI. The strategy hash is
part of every Claude cache key — editing the strategy invalidates the
cached responses that used the old version.

## Running it

- `streamlit run app.py` — dashboard (or double-click `start_dashboard.command` on macOS).
- `python -m fire.collector` — refresh prices, fundamentals, sentiment.
- `python -m fire.collector --pre-warm` — also pre-runs Claude theses on every `holding` ticker.
- `python -m fire.brief` — generate a Markdown research brief.

## Conventions

- **Data fetches must degrade gracefully.** A bad or delisted ticker
  returns empty data, never crashes a run. Wrap all network calls in
  try/except.
- **The core dashboard requires no API keys.** Optional Phase-2 keys
  (Reddit user-agent, X bearer token) go in `.env` (see `.env.example`).
- **Verify changes before declaring done:** `python -m py_compile` on
  touched files, and `pytest tests/` for the smoke suite (includes
  `streamlit.testing.v1.AppTest` against `app.py`).
- **For non-trivial work, discuss the design first, then build.**

## Roadmap

- **Phase 1 (done):** core dashboard — prices, fundamentals, earnings,
  filings, valuation scoring, collector, brief.
- **Phase 2 (done):** sentiment — Reddit + StockTwits + news (yfinance +
  Google News RSS), VADER scoring (FinBERT opt-in), shift detection
  against a 30-day baseline. X/Twitter wired as a pluggable module that
  stays OFF until `X_BEARER_TOKEN` is set.
- **Phase 2.5 (done):** Claude-authored thesis card per ticker, with
  the user's strategy as system context. Editable strategy via the UI.
- **Phase 3 (next):** options-income engine — covered-call /
  cash-secured-put scanner using local holdings and cost basis (kept
  local, never uploaded).
