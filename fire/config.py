"""Configuration loading for the FIRE dashboard.

Reads watchlist.yaml, settings.yaml and the optional .env file that sit
in the project root (one level above this package).
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

# Load .env if present (harmless no-op if it is missing).
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "fire.db"
BRIEFS_DIR = ROOT / "briefs"

WATCHLIST_PATH = ROOT / "watchlist.yaml"
SETTINGS_PATH = ROOT / "settings.yaml"

# The three lists in the v2 schema. A ticker lives on exactly one.
LISTS = ("holding", "shortlist", "watchlist")
DEFAULT_LIST = "watchlist"

LIST_LABEL = {
    "holding":   "Holding",
    "shortlist": "Shortlist",
    "watchlist": "Watchlist",
}

# One-shot migration from the old stage taxonomy to the new list taxonomy.
# Rows with stage == 'passed' are deleted (not migrated) by db._migrate_lists.
STAGE_TO_LIST = {
    "investment":    "holding",
    "deep_research": "shortlist",
    "preliminary":   "shortlist",
    "draft":         "watchlist",
    # 'passed' has no entry — those rows are dropped.
}


def _load_yaml(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    with open(path, "r") as fh:
        return yaml.safe_load(fh) or default


def _reload():
    """Re-read both yaml files. Used after the sidebar edits the watchlist."""
    global WATCHLIST, SETTINGS
    WATCHLIST = _load_yaml(WATCHLIST_PATH, {"layers": {}})
    SETTINGS = _load_yaml(SETTINGS_PATH, {})


WATCHLIST = _load_yaml(WATCHLIST_PATH, {"layers": {}})
SETTINGS = _load_yaml(SETTINGS_PATH, {})


def all_tickers() -> list:
    """Every ticker across every layer, de-duplicated and sorted."""
    tickers: list = []
    for layer in WATCHLIST.get("layers", {}).values():
        tickers.extend(layer.get("tickers", []))
    return sorted({str(t).upper() for t in tickers})


def ticker_layers() -> dict:
    """Map of ticker -> human-readable layer label."""
    mapping: dict = {}
    for key, layer in WATCHLIST.get("layers", {}).items():
        label = layer.get("label", key)
        for t in layer.get("tickers", []):
            mapping[str(t).upper()] = label
    return mapping


def layer_keys() -> dict:
    """Map of layer key (yaml id) -> human-readable label."""
    return {key: layer.get("label", key)
            for key, layer in WATCHLIST.get("layers", {}).items()}


def initial_lists() -> dict:
    """First-time list hints from watchlist.yaml. Upper-cased keys.

    Reads the new `lists:` block first; falls back to the legacy `stages:`
    block (translated via STAGE_TO_LIST) so existing yaml still seeds
    correctly on upgrade.
    """
    out = {}
    raw = WATCHLIST.get("lists", {}) or {}
    for t, lst in raw.items():
        lst = str(lst).lower()
        if lst in LISTS:
            out[str(t).upper()] = lst
    legacy = WATCHLIST.get("stages", {}) or {}
    for t, stage in legacy.items():
        key = str(t).upper()
        if key in out:
            continue  # explicit lists: entry wins
        translated = STAGE_TO_LIST.get(str(stage).lower())
        if translated:
            out[key] = translated
    return out


def setting(path: str, default=None):
    """Dotted-path lookup into settings.yaml, e.g. setting('valuation.peg_cheap')."""
    node = SETTINGS
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def env(key: str, default=None):
    """Read an environment variable; treat empty strings as unset."""
    val = os.getenv(key, default)
    if isinstance(val, str) and not val.strip():
        return default
    return val


# --------------------------------------------------------------------------
# Watchlist editing — preserves comments and layout via ruamel.yaml.
# --------------------------------------------------------------------------
def _yaml_rt():
    """Lazy import: ruamel.yaml is only needed for writes."""
    from ruamel.yaml import YAML
    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def add_ticker_to_yaml(ticker: str, layer_key: str) -> bool:
    """Append a ticker to the named layer in watchlist.yaml. Returns True
    if the file changed. No-op if the ticker is already there."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    y = _yaml_rt()
    with open(WATCHLIST_PATH, "r") as fh:
        data = y.load(fh)
    layers = data.get("layers", {})
    if layer_key not in layers:
        raise ValueError(f"Unknown layer: {layer_key}")
    tickers = layers[layer_key].get("tickers", [])
    existing = {str(t).upper() for t in tickers}
    if ticker in existing:
        return False
    tickers.append(ticker)
    layers[layer_key]["tickers"] = tickers
    with open(WATCHLIST_PATH, "w") as fh:
        y.dump(data, fh)
    _reload()
    return True


def clear_watchlist_yaml() -> int:
    """Remove every ticker from every layer in watchlist.yaml. Layer
    structure is preserved (you may want to re-add tickers under the
    same layers). Returns the number of tickers removed."""
    y = _yaml_rt()
    with open(WATCHLIST_PATH, "r") as fh:
        data = y.load(fh)
    removed = 0
    for layer in data.get("layers", {}).values():
        removed += len(layer.get("tickers", []) or [])
        layer["tickers"] = []
    # Also wipe the seed hints — they refer to tickers we just dropped.
    if "lists" in data:
        data["lists"] = {}
    if "stages" in data:
        data["stages"] = {}
    with open(WATCHLIST_PATH, "w") as fh:
        y.dump(data, fh)
    _reload()
    return removed


def remove_ticker_from_yaml(ticker: str) -> bool:
    """Remove a ticker from whichever layer it lives in. Returns True if
    the file changed."""
    ticker = ticker.strip().upper()
    if not ticker:
        return False
    y = _yaml_rt()
    with open(WATCHLIST_PATH, "r") as fh:
        data = y.load(fh)
    changed = False
    for layer_key, layer in data.get("layers", {}).items():
        tickers = layer.get("tickers", [])
        keep = [t for t in tickers if str(t).upper() != ticker]
        if len(keep) != len(tickers):
            layer["tickers"] = keep
            changed = True
    if changed:
        with open(WATCHLIST_PATH, "w") as fh:
            y.dump(data, fh)
        _reload()
    return changed
