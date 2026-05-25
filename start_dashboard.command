#!/bin/bash
# ──────────────────────────────────────────────────────────────────
# FIRE — AI Stock Dashboard launcher
# Double-click this file to start the dashboard. It opens in your
# browser and is reachable from other devices on the same Wi-Fi at
#
#     http://fire.local
#
# How it works:
#   1. Publishes `fire.local` via Bonjour (mDNS) so other devices on
#      the same Wi-Fi can resolve the hostname.
#   2. Adds a temporary `pf` rule that redirects incoming port 80 to
#      streamlit's port 8501 (needs sudo once — the rule is removed
#      when you close this window).
#   3. Launches streamlit.
#
# Close this window (or press Ctrl+C) to stop the dashboard and
# unwind the network bits.
# ──────────────────────────────────────────────────────────────────

cd "$(dirname "$0")" || exit 1

DASHBOARD_PORT=8501
HOSTNAME_PUBLIC="fire"
PF_ANCHOR_NAME="fire.dashboard"

echo "──────────────────────────────────────────"
echo "   FIRE — AI Stock Dashboard"
echo "──────────────────────────────────────────"

# First run: build the virtual environment and install dependencies.
if [ ! -d ".venv" ]; then
  echo ""
  echo "First run — setting things up (a minute or two)…"
  python3 -m venv .venv || {
    echo "ERROR: could not create the environment. Is Python 3 installed?"
    echo "Install it from https://www.python.org/downloads/ and try again."
    read -r -p "Press Return to close."
    exit 1
  }
  ./.venv/bin/pip install --quiet --upgrade pip
  ./.venv/bin/pip install --quiet -r requirements.txt || {
    echo "ERROR: could not install dependencies."
    read -r -p "Press Return to close."
    exit 1
  }
  echo "Setup complete."
fi

# First run: pull an initial round of data so the dashboard isn't empty.
if [ ! -f "data/fire.db" ]; then
  echo ""
  echo "Fetching the first round of market data (~30 seconds)…"
  ./.venv/bin/python -m fire.collector
fi

# ─── Detect network ───────────────────────────────────────────────
get_ip() {
  ipconfig getifaddr en0 2>/dev/null || \
  ipconfig getifaddr en1 2>/dev/null
}
IP="$(get_ip)"
ACTIVE_IFACE="$(route get default 2>/dev/null | awk '/interface:/{print $2}')"

# ─── Cleanup on exit ──────────────────────────────────────────────
DNS_PID=""
PF_LOADED=""

cleanup() {
  echo ""
  echo "Cleaning up…"
  if [ -n "$DNS_PID" ] && kill -0 "$DNS_PID" 2>/dev/null; then
    kill "$DNS_PID" 2>/dev/null || true
    echo "  · stopped mDNS publisher"
  fi
  if [ "$PF_LOADED" = "1" ]; then
    sudo pfctl -a "$PF_ANCHOR_NAME" -F all 2>/dev/null || true
    echo "  · flushed pf anchor ($PF_ANCHOR_NAME)"
  fi
  echo "Done."
}
trap cleanup EXIT INT TERM

# ─── Stop any stale streamlit on the same port ────────────────────
EXISTING_PID="$(lsof -t -iTCP:$DASHBOARD_PORT -sTCP:LISTEN 2>/dev/null | head -1)"
if [ -n "$EXISTING_PID" ]; then
  echo ""
  echo "Port $DASHBOARD_PORT is already in use by PID $EXISTING_PID."
  read -r -p "Stop it and start fresh? [Y/n] " yn
  if [[ ! "$yn" =~ ^[Nn] ]]; then
    kill "$EXISTING_PID" 2>/dev/null || true
    sleep 2
  fi
fi

# ─── Publish fire.local via Bonjour ───────────────────────────────
if [ -n "$IP" ]; then
  /usr/bin/dns-sd -P "$HOSTNAME_PUBLIC" _http._tcp local \
    "$DASHBOARD_PORT" "$HOSTNAME_PUBLIC.local" "$IP" path=/ \
    > /dev/null 2>&1 &
  DNS_PID=$!
  echo ""
  echo "▶ mDNS: $HOSTNAME_PUBLIC.local → $IP   (pid $DNS_PID)"
else
  echo ""
  echo "⚠ Could not detect a Wi-Fi IP — skipping mDNS publish."
  echo "  The dashboard will still work locally at http://localhost:$DASHBOARD_PORT"
fi

# ─── Port-80 redirect via pf ──────────────────────────────────────
if [ -n "$ACTIVE_IFACE" ]; then
  echo ""
  echo "▶ Setting up port-80 → $DASHBOARD_PORT redirect on $ACTIVE_IFACE"
  echo "  (needs sudo once; the rule is removed when you Ctrl+C)"

  # One-time: append rdr-anchor reference to /etc/pf.conf so our anchor is loaded.
  if ! grep -q "rdr-anchor \"$PF_ANCHOR_NAME\"" /etc/pf.conf 2>/dev/null; then
    echo "rdr-anchor \"$PF_ANCHOR_NAME\"" | sudo tee -a /etc/pf.conf >/dev/null
    echo "  · added rdr-anchor reference to /etc/pf.conf (one-time)"
  fi

  # Load the redirect rule into the anchor.
  echo "rdr pass on $ACTIVE_IFACE inet proto tcp from any to any port 80 -> 127.0.0.1 port $DASHBOARD_PORT" \
    | sudo pfctl -a "$PF_ANCHOR_NAME" -f - 2>/dev/null

  # Re-evaluate pf.conf so the anchor reference takes effect, then ensure pf is on.
  sudo pfctl -f /etc/pf.conf 2>/dev/null
  sudo pfctl -E 2>/dev/null
  PF_LOADED=1
  echo "  · pf rule active: $ACTIVE_IFACE :80 → 127.0.0.1:$DASHBOARD_PORT"
else
  echo ""
  echo "⚠ No default interface detected — skipping port-80 redirect."
  echo "  You'll need :8501 in the URL."
fi

# ─── Print the access URLs ────────────────────────────────────────
echo ""
echo "──────────────────────────────────────────"
echo "  Open from another device on the same Wi-Fi:"
if [ "$PF_LOADED" = "1" ]; then
  echo "    ► http://$HOSTNAME_PUBLIC.local"
fi
echo "    ► http://$HOSTNAME_PUBLIC.local:$DASHBOARD_PORT"
[ -n "$IP" ] && echo "    ► http://$IP:$DASHBOARD_PORT"
echo ""
echo "  Locally on this Mac:"
echo "    ► http://localhost:$DASHBOARD_PORT"
echo ""
echo "  Close this window (or Ctrl+C) to stop the dashboard"
echo "  and remove the pf redirect."
echo "──────────────────────────────────────────"
echo ""

./.venv/bin/streamlit run app.py
