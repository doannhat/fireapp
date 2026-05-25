"""Strategy loader / saver round-trip tests."""
from __future__ import annotations

from fire.strategy import (
    Strategy, _split_frontmatter, load_strategy, save_strategy,
)


SAMPLE = """\
---
horizon_years: [2, 3]
target_return_multiple: 10
position_style: concentrated
themes:
  - AI super-cycle
hard_rules:
  - No day-trading
custom_key: hello
---

# My philosophy

Some prose.

## Subsection

More prose.
"""


def test_split_frontmatter_parses_known_block():
    fm, body = _split_frontmatter(SAMPLE)
    assert fm["horizon_years"] == [2, 3]
    assert fm["target_return_multiple"] == 10
    assert fm["position_style"] == "concentrated"
    assert fm["themes"] == ["AI super-cycle"]
    assert fm["hard_rules"] == ["No day-trading"]
    assert fm["custom_key"] == "hello"
    assert body.startswith("# My philosophy")
    assert "More prose." in body


def test_split_frontmatter_no_block():
    text = "# Just a heading\n\nNo frontmatter here.\n"
    fm, body = _split_frontmatter(text)
    assert fm == {}
    assert body == text


def test_split_frontmatter_malformed_yaml():
    text = "---\nnot: valid: yaml: at all\n---\nbody\n"
    fm, body = _split_frontmatter(text)
    assert fm == {}
    assert body == text


def test_load_strategy_uses_env_path(isolated_strategy, monkeypatch):
    isolated_strategy.write_text(SAMPLE)
    s = load_strategy()
    assert s.source_path == isolated_strategy
    assert s.frontmatter["target_return_multiple"] == 10
    assert "philosophy" in s.body


def test_load_strategy_missing_returns_empty(isolated_strategy):
    # File doesn't exist; env var points at a non-existent path.
    s = load_strategy()
    assert s.frontmatter == {}
    assert s.body == ""


def test_as_prompt_round_trips(isolated_strategy):
    isolated_strategy.write_text(SAMPLE)
    s = load_strategy()
    prompt = s.as_prompt()
    # The prompt must contain both the frontmatter values and the body.
    assert "horizon_years" in prompt
    assert "AI super-cycle" in prompt
    assert "# My philosophy" in prompt


def test_save_strategy_writes_to_resolved_path(isolated_strategy):
    fm = {
        "horizon_years": [3, 5],
        "target_return_multiple": 8,
        "position_style": "balanced",
        "themes": ["Energy transition"],
        "hard_rules": ["No leverage"],
    }
    path = save_strategy(fm, "# New philosophy\n\nWords.\n")
    assert path == isolated_strategy
    contents = isolated_strategy.read_text()
    assert contents.startswith("---\n")
    assert "horizon_years" in contents
    assert "New philosophy" in contents

    # And it round-trips through load_strategy.
    s = load_strategy()
    assert s.frontmatter["horizon_years"] == [3, 5]
    assert s.frontmatter["position_style"] == "balanced"
    assert s.body.startswith("# New philosophy")


def test_save_strategy_preserves_extra_keys(isolated_strategy):
    fm = {
        "horizon_years": [1, 2],
        "themes": ["x"],
        "custom_key": {"nested": "value"},
    }
    save_strategy(fm, "body\n")
    s = load_strategy()
    assert s.frontmatter["custom_key"] == {"nested": "value"}


def test_empty_strategy_as_prompt_is_empty():
    assert Strategy().as_prompt() == ""
