"""Shared pytest fixtures.

Most fixtures here exist to keep tests off the developer's real config:
- `isolated_strategy` points FIRE_STRATEGY_PATH at a temp file so a
  test never reads the user's actual STRATEGY.md.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def isolated_strategy(tmp_path, monkeypatch):
    """Point FIRE_STRATEGY_PATH at a fresh empty file for this test."""
    path = tmp_path / "STRATEGY.md"
    monkeypatch.setenv("FIRE_STRATEGY_PATH", str(path))
    return path
