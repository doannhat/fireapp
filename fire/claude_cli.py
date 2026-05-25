"""Wrapper around the local `claude` CLI.

Used by the processors to summarize filings, cluster social posts, and
build the investment thesis card. Every call is keyed by (kind, ticker,
prompt-hash, content-hash, strategy-hash) and cached in SQLite so
re-runs are cheap.

Design choices
--------------
- We pass the user's strategy memory as the system prompt to every call,
  so summaries are tailored to the 2-3yr / 5-10× / hidden-gem worldview.
- We shell out via `subprocess.run` rather than the Python SDK because
  this dashboard is local-only and assumes the user already has the
  `claude` CLI installed (it's the same tool they're using to author
  this codebase). Switching to the SDK is a Phase 3.5 follow-up.
- Cost tracking is rough — the CLI doesn't return token counts in the
  default print mode, so we just record whether a call hit and how long
  it took. Switching to `--output-format json` gives us proper costs.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import time
from dataclasses import dataclass

from . import db
from .config import ROOT, setting
from .strategy import load_strategy


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()[:16]


@dataclass
class ClaudeResult:
    ok: bool
    text: str
    data: dict | None
    cost_usd: float | None
    latency_ms: int
    error: str | None
    cached: bool


class Claude:
    """Thin wrapper around `claude -p ...` for structured summarization."""

    def __init__(self,
                 model: str = "claude-sonnet-4-5",
                 cli_path: str | None = None,
                 cost_cap_usd: float | None = None):
        self.model = model
        self.cli = cli_path or shutil.which("claude") or "claude"
        self.strategy = load_strategy().as_prompt()
        self.strategy_hash = _hash(self.strategy)
        self.cost_cap_usd = (
            cost_cap_usd
            if cost_cap_usd is not None
            else setting("claude.cost_cap_usd", 5.00)
        )
        self.run_cost_usd: float = 0.0

    # ---------- core call ----------
    def call(self, kind: str, ticker: str, prompt: str,
             content: str = "", *,
             structured: bool = True,
             force: bool = False,
             timeout: int = 180,
             handle=None) -> ClaudeResult:
        """One Claude call. Returns the cached result if available unless
        `force=True`.

        `handle` is an optional `fire.jobs.JobHandle` — if given, the
        subprocess is registered with the handle so the UI's Stop
        button can `terminate()` it mid-call. The result then comes
        back as `error="cancelled"`.
        """
        prompt_hash = _hash(prompt)
        content_hash = _hash(content)
        cache_key = "::".join([
            kind, ticker.upper(), self.model,
            prompt_hash, content_hash, self.strategy_hash,
        ])

        if not force:
            with db.connect() as conn:
                row = db.get_claude_cache(conn, cache_key)
            if row:
                try:
                    data = json.loads(row["response_json"]) if structured else None
                except (TypeError, ValueError):
                    data = None
                return ClaudeResult(
                    ok=True,
                    text=row["response_json"],
                    data=data,
                    cost_usd=row.get("cost_usd"),
                    latency_ms=row.get("latency_ms") or 0,
                    error=None,
                    cached=True,
                )

        if (self.cost_cap_usd is not None
                and self.run_cost_usd >= self.cost_cap_usd):
            return ClaudeResult(
                ok=False, text="", data=None, cost_usd=None,
                latency_ms=0,
                error=f"Cost cap ${self.cost_cap_usd} reached this run.",
                cached=False,
            )

        # Compose the prompt: strategy first, then the user request, then
        # the content. We rely on Claude to pick out structure.
        composed_parts = []
        if self.strategy:
            composed_parts.append(
                f"<investor-strategy>\n{self.strategy}\n</investor-strategy>"
            )
        composed_parts.append(prompt)
        if content:
            composed_parts.append(f"<content>\n{content}\n</content>")
        if structured:
            composed_parts.append(
                "Return ONLY valid JSON. No prose before or after the JSON. "
                "No markdown code fence. No commentary."
            )
        composed = "\n\n".join(composed_parts)

        cmd = [self.cli, "-p", composed,
               "--model", self.model,
               "--output-format", "json"]
        t0 = time.time()
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(ROOT),
            )
        except FileNotFoundError:
            return ClaudeResult(
                ok=False, text="", data=None, cost_usd=None, latency_ms=0,
                error=f"`claude` CLI not found at {self.cli}",
                cached=False,
            )

        if handle is not None:
            handle.set_proc(proc)

        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
            return ClaudeResult(
                ok=False, text="", data=None, cost_usd=None,
                latency_ms=int((time.time() - t0) * 1000),
                error=f"claude CLI timed out after {timeout}s",
                cached=False,
            )

        latency_ms = int((time.time() - t0) * 1000)

        if handle is not None and handle.is_cancelled():
            return ClaudeResult(
                ok=False, text="", data=None, cost_usd=None,
                latency_ms=latency_ms,
                error="cancelled by user",
                cached=False,
            )

        if proc.returncode != 0:
            return ClaudeResult(
                ok=False, text=stdout or "", data=None,
                cost_usd=None, latency_ms=latency_ms,
                error=(stderr or "")[:400],
                cached=False,
            )

        # claude CLI in json output mode returns a wrapper with .result + cost
        result_text = (stdout or "").strip()
        cost = None
        result_payload = result_text
        try:
            outer = json.loads(result_text)
            if isinstance(outer, dict):
                result_payload = outer.get("result", result_text)
                cost = outer.get("total_cost_usd") or outer.get("cost_usd")
        except (TypeError, ValueError):
            pass

        if cost is not None:
            self.run_cost_usd += float(cost)

        # If structured, parse the inner JSON
        data = None
        if structured and isinstance(result_payload, str):
            try:
                data = json.loads(_strip_json_fence(result_payload))
            except (TypeError, ValueError):
                data = None
        elif structured and isinstance(result_payload, (dict, list)):
            data = result_payload

        store_text = (
            json.dumps(data) if (data is not None) else
            (result_payload if isinstance(result_payload, str) else
             json.dumps(result_payload))
        )

        with db.connect() as conn:
            db.save_claude_cache(
                conn, cache_key,
                ticker=ticker.upper(), kind=kind,
                prompt_hash=prompt_hash,
                content_hash=content_hash,
                strategy_hash=self.strategy_hash,
                response_json=store_text,
                cost_usd=cost, latency_ms=latency_ms,
            )

        return ClaudeResult(
            ok=True, text=store_text, data=data,
            cost_usd=cost, latency_ms=latency_ms,
            error=None, cached=False,
        )


def _strip_json_fence(text: str) -> str:
    """Best-effort: strip ```json fences if Claude added them anyway."""
    text = text.strip()
    if text.startswith("```"):
        # Drop the opening fence line
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    return text.strip()
