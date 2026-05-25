"""Parallel deep-dive: thesis + every section paragraph in one job.

`build_deep_dive(...)` fans out ~10 Claude CLI subprocesses through a
`ThreadPoolExecutor`, registering each subprocess with the shared
`JobHandle` so a single Stop button can terminate them all. Cache-first
— sections already in `claude_cache` are returned instantly without a
new subprocess.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from ..claude_cli import Claude
from .sections import build_section_summary
from .thesis import build_thesis, gather_extras


# Sections we want a paragraph for. Order is the rendering order.
SECTION_KEYS = ("overview", "valuation", "growth", "quality",
                "health", "ai", "income", "sentiment", "fine")


def _ok(result) -> bool:
    return bool(result and getattr(result, "ok", False)
                and not getattr(result, "error", None))


def build_deep_dive(
    ticker: str,
    snap: dict,
    sections: dict,
    sentiment: dict,
    *,
    force: bool = False,
    handle=None,
    max_workers: int = 10,
) -> dict:
    """Fire thesis + every section paragraph in parallel. Returns:

        {
          "thesis":           {...},  # full thesis dict (or None on error)
          "thesis_meta":      {sources, cost, freshness},
          "sections":         {section_key: paragraph_str},
          "section_meta":     {section_key: {cost, cached, latency_ms}},
          "errors":           {key: error_message},
          "total_cost_usd":   float,
        }
    """
    claude = Claude()
    out: dict = {
        "thesis": None,
        "thesis_meta": {},
        "sections": {},
        "section_meta": {},
        "errors": {},
        "total_cost_usd": 0.0,
    }

    if handle:
        handle.set_progress("gathering extras…")

    # Compute extras (insider, 13F, P/B history, recent filings, analyst
    # consensus, etc.) ONCE here, then pass to both the thesis builder
    # and every section builder. Avoids each of the 10 Claude calls
    # round-tripping the DB / yfinance for the same data.
    try:
        extras = gather_extras(ticker)
    except Exception:
        extras = {}

    if handle:
        handle.set_progress("starting…")

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}

        # Thesis (extended schema — includes moat / positioning / pricing / multiplier)
        futures["__thesis__"] = pool.submit(
            build_thesis, ticker, snap, sections, sentiment,
            force=force, claude=claude, handle=handle, extras=extras,
        )

        # One call per section. Pass the shared extras so each section
        # paragraph can weave in its Phase 2.6 slice.
        for key in SECTION_KEYS:
            kpis = sections.get(key) if key != "sentiment" else []
            sent = sentiment if key == "sentiment" else None
            futures[key] = pool.submit(
                build_section_summary, ticker, key, kpis or [], snap, sent,
                extras=extras, force=force, claude=claude, handle=handle,
            )

        n_total = len(futures)
        n_done = 0
        for future in as_completed(futures.values()):
            n_done += 1
            if handle:
                if handle.is_cancelled():
                    # Pool shutdown happens on `with` exit; subprocesses
                    # already terminated by jobs.cancel().
                    break
                handle.set_progress(f"{n_done}/{n_total} ready")

        # Collect results (futures are now all done or cancelled).
        for key, fut in futures.items():
            try:
                data, result = fut.result(timeout=1)
            except Exception as exc:
                out["errors"][key] = str(exc)[:240]
                continue

            if not _ok(result):
                out["errors"][key] = (result.error or "unknown error")[:240]
                continue

            if result.cost_usd:
                out["total_cost_usd"] += float(result.cost_usd)

            if key == "__thesis__":
                out["thesis"] = data
                out["thesis_meta"] = {
                    "cost": (
                        f"${result.cost_usd:.2f}"
                        if result.cost_usd is not None else
                        ("cached" if result.cached else "—")
                    ),
                    "cached": result.cached,
                    "latency_ms": result.latency_ms,
                }
            else:
                # Section paragraph payload is `{"paragraph": "..."}`
                paragraph = ""
                if isinstance(data, dict):
                    paragraph = (data.get("paragraph") or "").strip()
                if paragraph:
                    out["sections"][key] = paragraph
                out["section_meta"][key] = {
                    "cost": result.cost_usd,
                    "cached": result.cached,
                    "latency_ms": result.latency_ms,
                }

    return out
