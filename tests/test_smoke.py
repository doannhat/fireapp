"""Smoke tests — does the app render at all?

These don't validate semantics, just that each tab executes without an
unhandled exception. Run from the project root:

    python -m pytest tests/

Or one-off:

    .venv/bin/python tests/test_smoke.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_app_renders():
    """Streamlit's AppTest runs the whole `app.py` headlessly."""
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "app.py")).run(timeout=120)
    assert not at.exception, f"app.py raised: {at.exception}"


def test_research_no_exception():
    """Loading the Research view for NVDA shouldn't crash."""
    from fire import db
    from fire.metrics import build_research_data

    db.init_db()
    data = build_research_data("NVDA")
    assert data["ticker"] == "NVDA"
    assert "snapshot" in data
    assert "sections" in data
    # All nine section keys should at least be present (may be empty lists).
    for key in ("overview", "valuation", "growth", "quality",
                "health", "ai", "income", "fine"):
        assert key in data["sections"], f"missing section {key}"


def test_list_round_trip():
    """set_list / get_list / list_counts / remove_ticker_meta."""
    from fire import db

    db.init_db()
    with db.connect() as c:
        db.set_list(c, "TESTTKR", "watchlist")
        assert db.get_list(c, "TESTTKR") == "watchlist"
        db.set_list(c, "TESTTKR", "shortlist")
        assert db.get_list(c, "TESTTKR") == "shortlist"
        counts = db.list_counts(c)
        assert counts["shortlist"] >= 1
        db.remove_ticker_meta(c, "TESTTKR")
        assert "TESTTKR" not in db.get_lists(c)


def test_claude_cache_round_trip():
    """save_claude_cache / get_claude_cache / recent_claude_activity."""
    from fire import db

    db.init_db()
    with db.connect() as c:
        db.save_claude_cache(
            c, cache_key="test::ABCDEF",
            ticker="ABCDEF", kind="thesis",
            prompt_hash="ph", content_hash="ch", strategy_hash="sh",
            response_json='{"verdict": "test"}',
            cost_usd=0.01, latency_ms=100,
        )
        row = db.get_claude_cache(c, "test::ABCDEF")
        assert row is not None
        assert row["ticker"] == "ABCDEF"
        # Clean up so the cache stays small.
        c.execute("DELETE FROM claude_cache WHERE cache_key = ?",
                  ("test::ABCDEF",))


if __name__ == "__main__":
    test_research_no_exception()
    print("research data ok")
    test_list_round_trip()
    print("list round-trip ok")
    test_claude_cache_round_trip()
    print("claude cache round-trip ok")
    test_app_renders()
    print("app.py renders ok")
    print("\nAll smoke tests passed.")
