# FIRE — your personal AI stock research dashboard

A friendly dashboard for **long-term** stock research. You give it a
list of company stock symbols you're interested in, and it pulls
fresh prices, fundamentals, recent earnings, SEC filings, and online
sentiment for each one. Then your **own Claude AI** writes a
research thesis on each company, tailored to the investing philosophy
you describe.

Everything runs on your own laptop. No accounts to create, no cloud
services, no data shared with anyone.

> Informational only — not investment advice. The dashboard is a
> research tool. It does not place trades or move your money.

---

## Before you start, you'll need

1. **A laptop** running macOS, Windows, or Linux.
2. **A Claude subscription** — Pro, Max, or Team. The dashboard uses
   your subscription to write its thesis cards. Anthropic bills you
   for the AI usage; the dashboard itself never does.
3. **Python 3.10 or newer.** macOS usually has it already. On
   Windows, install from [python.org](https://www.python.org/downloads/)
   and tick **"Add Python to PATH"** during installation.
4. **The Claude CLI** — Anthropic's command-line tool that connects
   the dashboard to your Claude subscription. Follow the install
   instructions at
   [docs.claude.com/en/docs/claude-code](https://docs.claude.com/en/docs/claude-code),
   then open a terminal and run `claude login` once to sign in.

Plan on about 15 minutes for first-time setup.

> The dashboard still runs without the Claude CLI installed — you'll
> just see a simpler heuristic thesis instead of one written by
> Claude. You can add Claude later.

---

## Easy setup (macOS)

1. **Download FIRE.** On the project page at
   [github.com/doannhat/fireapp](https://github.com/doannhat/fireapp),
   click the green **Code** button and choose **Download ZIP**.
   Unzip the file somewhere convenient like your Desktop or
   Documents folder.
2. **Open the unzipped folder in Finder** and double-click
   `start_dashboard.command`.
3. **First-time prompts:**
   - macOS may say *"cannot be opened because it is from an
     unidentified developer"*. Right-click the file → **Open** →
     confirm **Open**. After this once, normal double-clicks work.
   - The launcher installs the dashboard's packages (a minute or
     two) and fetches the first round of market data (~30 seconds).
   - You'll see one password prompt — that lets the launcher set up
     a nice `http://fire.local` shortcut for your other devices on
     the same Wi-Fi. Press Return to skip if you'd rather not; the
     dashboard still works on this laptop without it.
4. **Your browser opens to the dashboard.** That's it.

To stop the dashboard, close the Terminal window or press **Ctrl+C**
in it. The launcher cleans up after itself.

---

## Setup (Windows / Linux)

There's no double-click launcher on these platforms yet, so you run
a handful of commands. Open **Terminal** (Linux) or **Command
Prompt / PowerShell** (Windows), then:

```bash
# 1. Download the code. (Or download the ZIP from GitHub and unzip.)
git clone https://github.com/doannhat/fireapp.git fire
cd fire

# 2. Create a private Python workspace just for this app.
python3 -m venv .venv

# 3. Activate the workspace.
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 4. Install the dashboard's packages (one-time).
pip install -r requirements.txt

# 5. Launch.
streamlit run app.py
```

Your browser opens to the dashboard at `http://localhost:8501`.

**Future launches** are short — open a terminal, navigate into the
folder, activate the workspace, then run Streamlit:

```bash
cd fire
source .venv/bin/activate          # Windows: .venv\Scripts\activate
streamlit run app.py
```

---

## Using the dashboard

The app has four tabs across the top:

- **RESEARCH** — pick a stock, see all the fundamentals on one page,
  and click *"Generate Claude thesis"* for an AI-written analysis
  tailored to your strategy.
- **COMPARE** — pin up to four tickers side-by-side to compare
  valuation, growth, profitability, and signals at a glance.
- **WATCHLIST** — a three-column ladder of stocks you own
  (**Holding**), are seriously considering (**Shortlist**), or are
  just tracking (**Watchlist**). Use the "+ ADD" form to add new
  tickers.
- **STRATEGY** — edit your investing philosophy. The dashboard
  feeds this to Claude as context for every thesis.

**Personal notes on any ticker.** In both the Research and Watchlist
tabs you'll find a 📝 *Notes* button next to each stock. Click it to
jot down your thesis, what to watch for, why you bought, what
changed — anything. Notes save only to your laptop.

### Your first session

1. Open the **STRATEGY** tab and write a few sentences about what
   you're looking for — your time horizon, target return, themes
   you care about, and any hard rules you never break ("no tobacco
   companies", "no leveraged ETFs", etc.). Save.
2. Open the **WATCHLIST** tab. Type a stock symbol (e.g. `AVGO`)
   into the ADD TICKER box and click **ADD**. The dashboard
   validates the symbol, fetches a snapshot, and slots it under
   the appropriate list.
3. Hop to **RESEARCH** → pick that ticker from the dropdown → click
   **◇ Generate Claude thesis**. The first run takes ~60 seconds.

---

## Using it from your phone or another laptop

The dashboard is reachable from any phone, tablet, or other laptop
on the same Wi-Fi network as the laptop running it.

**By IP address** (works everywhere, no setup):
When Streamlit starts it prints a *"Network URL"* like
`http://192.168.1.42:8501`. Type that into the other device's
browser.

**By a friendly name** (macOS host):
Open **System Settings → General → Sharing** on the host Mac and
set the local hostname to `fire`. Other devices on the same Wi-Fi
can now use `http://fire.local:8501`.

> 📱 **On a phone, always include `:8501` at the end.** Phone
> browsers default to port 80, so a bare `http://fire.local` won't
> connect to the dashboard. The `:8501` URL works on every device.

If you launched with `start_dashboard.command` on macOS *and*
entered your password when prompted, you can also use plain
`http://fire.local` without the port — the launcher set up a
temporary forwarding rule that gets removed when you close the
window.

---

## Editing your investing strategy

The dashboard tailors every Claude thesis to your investing
philosophy, stored in a file called `STRATEGY.md`. You edit it from
the **STRATEGY** tab — no need to touch the file by hand.

Set your time horizon, target return, the themes you care about, and
the hard rules you never break. Anything you write in the body is
read verbatim by Claude as system context for the thesis.

When you change your strategy, theses written under the old strategy
stay cached (scroll back to see them), but every new thesis uses the
new lens automatically.

---

## Keeping the data fresh

When the dashboard is running it pulls fresh prices on demand. To
refresh *everything* at once (prices, sentiment, filings for every
ticker on your watchlist), open a terminal in the project folder and
run:

```bash
python -m fire.collector              # ~30 seconds
```

Add `--pre-warm` to also generate Claude theses for everything on
your **Holding** list, so the Research tab loads instantly the next
time you open it:

```bash
python -m fire.collector --pre-warm   # ~2-3 minutes
```

Some people schedule this to run automatically each morning (via
**cron** on macOS / Linux, or **Task Scheduler** on Windows).

---

## Troubleshooting

**The browser doesn't open automatically.** Type
`http://localhost:8501` into your browser manually.

**"`claude: command not found`" when the dashboard tries to write a
thesis.** The Claude CLI isn't installed yet, or isn't on your
system PATH. See the prerequisite list at the top. The dashboard
will fall back to a simpler heuristic thesis until you install it.

**"Port 8501 is already in use".** Another copy of the dashboard
is already running. Either close that window, or restart your
laptop.

**My phone can't reach the dashboard.** Make sure your phone is on
the same Wi-Fi network as the laptop. Try the IP-based URL
(printed when Streamlit starts) before the `fire.local` shortcut,
and remember to include `:8501` at the end on phones.

**A stock shows no price.** The free Yahoo Finance data source
occasionally fails on a symbol. Try again later, or double-check
the ticker symbol is correct (e.g. some non-US stocks need a
suffix like `.L` for London or `.TO` for Toronto).

**Reset all collected data and start fresh.** Close the dashboard,
then delete the file `data/fire.db` from the project folder. The
next launch rebuilds it.

---

## Where your data lives

Everything stays on your laptop:

- `data/fire.db` — the database with prices, sentiment, your notes,
  and Claude's saved responses.
- `briefs/` — Markdown research briefs, if you generate any.
- `STRATEGY.md` and `watchlist.yaml` — your investing rules and the
  list of stocks you're tracking. Plain text, safe to edit by hand.
- `.env` (optional) — for advanced API extras like Reddit and X
  tokens. The dashboard runs fine without it.

Nothing is uploaded anywhere. Claude calls go through your local
Claude CLI directly to Anthropic and back.

---

## Notes & limits

- Yahoo Finance is unofficial. Occasionally a stock returns partial
  data — the dashboard skips failures rather than crashing.
- No made-up numbers. If a source has no data for a metric, the
  section is left blank rather than filled in with a guess.
- This tool does not place trades or move money.

---

## For developers

Run the test suite:

```bash
.venv/bin/python -m pytest tests/
```

Project layout:

```
fire/
  app.py                    Streamlit entry — four tabs
  STRATEGY.md               your investing philosophy
  watchlist.yaml            your tickers + lists
  settings.yaml             thresholds + cost caps
  requirements.txt
  .env.example              optional API-key template
  .streamlit/config.toml    theme + LAN binding
  fire/
    config.py               yaml + .env loaders
    strategy.py             STRATEGY.md loader/saver
    db.py                   SQLite + Claude cache + migrations
    market.py               yfinance snapshots
    edgar.py                SEC EDGAR filings + full-text search
    metrics.py              KPI assembly per section
    valuation.py            heuristic valuation scoring
    sentiment.py            Reddit / StockTwits / news ingest
    scoring.py              VADER tone scorer (FinBERT opt-in)
    claude_cli.py           local `claude` CLI wrapper
    collector.py            daily snapshot collector
    brief.py                Markdown research brief generator
    sources/                sentiment adapters
    processors/             Claude prompts per document type
    ui/
      research.py           Research tab
      compare.py            Compare tab
      watchlist.py          Watchlist tab
      strategy.py           Strategy tab
      notes.py              per-ticker notes popover
      theme.py              terminal stylesheet
  tests/
    test_smoke.py           AppTest + DB round-trips
    test_strategy.py        strategy loader/saver
  data/                     created on first run
  briefs/                   created on first run
```

---

## License

MIT — see `LICENSE`.
