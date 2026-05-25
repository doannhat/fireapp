"""Investor strategy file — load, parse, save.

A user's investing philosophy lives in `STRATEGY.md` at the project
root. The file is Markdown with a YAML frontmatter block:

    ---
    horizon_years: [2, 5]
    target_return_multiple: 10
    position_style: concentrated
    themes:
      - AI super-cycle
    hard_rules:
      - No short-term trading
    ---

    # Free-form prose below
    ...

`claude_cli.py` reads this file once at startup and prepends the whole
document (frontmatter + body) to every Claude call as system context.
The Strategy tab in the UI renders the frontmatter as a form and the
body as a textarea, writing back through `save_strategy()` so changes
survive restarts.

Resolution order for `load_strategy()`:
  1. `$FIRE_STRATEGY_PATH` if set
  2. `<project root>/STRATEGY.md`  (committed; ships with defaults)
  3. empty Strategy (shouldn't happen post-checkout)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .config import ROOT


DEFAULT_PATH = ROOT / "STRATEGY.md"

# Frontmatter keys the Strategy tab renders as dedicated form fields.
# Any other key the user adds shows up in the Advanced YAML editor and
# round-trips on save.
KNOWN_KEYS: tuple[str, ...] = (
    "horizon_years",
    "target_return_multiple",
    "position_style",
    "themes",
    "hard_rules",
)

POSITION_STYLES: tuple[str, ...] = (
    "concentrated", "balanced", "diversified",
)


@dataclass
class Strategy:
    frontmatter: dict = field(default_factory=dict)
    body: str = ""
    source_path: Path | None = None

    def as_prompt(self) -> str:
        """The verbatim document the LLM sees as system context.

        Reassembled from frontmatter + body so callers don't have to
        re-read the file. If frontmatter is empty, the leading `---`
        block is omitted."""
        if not self.frontmatter and not self.body:
            return ""
        if not self.frontmatter:
            return self.body
        fm_text = yaml.safe_dump(
            self.frontmatter, sort_keys=False, allow_unicode=True
        ).rstrip()
        return f"---\n{fm_text}\n---\n\n{self.body}".rstrip() + "\n"


def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Split a Markdown document into (frontmatter dict, body str).

    Returns ({}, text) if no frontmatter block is present or the YAML
    fails to parse. The body has the trailing `---\n` stripped but
    preserves all other whitespace verbatim."""
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return {}, text
    # Find the closing `---` on its own line.
    rest = text[4:] if text.startswith("---\n") else text[5:]
    end = rest.find("\n---\n")
    if end < 0:
        # Tolerate end-of-file frontmatter with no trailing body.
        end = rest.find("\n---")
        if end < 0 or rest[end + 4:].strip():
            return {}, text
        fm_raw = rest[:end]
        body = ""
    else:
        fm_raw = rest[:end]
        body = rest[end + 5:]
        # Leading newline after the closing fence is convention; strip
        # at most one.
        if body.startswith("\n"):
            body = body[1:]
    try:
        fm = yaml.safe_load(fm_raw) or {}
    except yaml.YAMLError:
        return {}, text
    if not isinstance(fm, dict):
        return {}, text
    return fm, body


def _resolve_path() -> Path | None:
    """Resolution order described in the module docstring."""
    env = os.getenv("FIRE_STRATEGY_PATH")
    if env:
        return Path(env).expanduser()
    if DEFAULT_PATH.exists():
        return DEFAULT_PATH
    return None


def load_strategy() -> Strategy:
    """Load the user's strategy. Always returns a Strategy; empty if no
    file exists or it's unreadable."""
    path = _resolve_path()
    if path is None or not path.exists():
        return Strategy()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return Strategy(source_path=path)
    fm, body = _split_frontmatter(text)
    return Strategy(frontmatter=fm, body=body, source_path=path)


def save_strategy(frontmatter: dict, body: str) -> Path:
    """Write the strategy back to disk, preserving frontmatter ordering
    via ruamel.yaml. Returns the path that was written.

    The destination is whichever path `_resolve_path()` returned, or
    the default `STRATEGY.md` at the project root if no file exists yet."""
    from ruamel.yaml import YAML
    from io import StringIO

    path = _resolve_path() or DEFAULT_PATH

    y = YAML()
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    buf = StringIO()
    y.dump(frontmatter or {}, buf)
    fm_text = buf.getvalue().rstrip()

    # Body should end with exactly one trailing newline.
    body_text = (body or "").rstrip() + "\n"

    if fm_text:
        out = f"---\n{fm_text}\n---\n\n{body_text}"
    else:
        out = body_text

    path.write_text(out, encoding="utf-8")
    return path
