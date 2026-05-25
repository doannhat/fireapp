"""Pluggable sentiment sources.

Each module exposes ``fetch_recent(ticker, since)`` returning a list of
post dicts::

    {
      "ticker": "NVDA",
      "source": "reddit",
      "external_id": "abc123",
      "created_at": "2026-05-20T14:30:00",   # ISO 8601 UTC
      "author": "u/someone" or "publisher",
      "weight": 1.0,
      "url": "https://...",
      "text": "title + body",
    }

Sources never raise — a transient network error returns ``[]`` so one
flaky API never aborts a full collection run.
"""
