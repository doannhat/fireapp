"""Claude-driven document processors.

Each module exposes a `build_*` or `summarize_*` function that takes a
ticker (and optionally raw content), calls the local `claude` CLI via
`fire.claude_cli.Claude`, and returns a structured dict.

`thesis.py` is the only one wired into the UI today — `tenk`,
`transcript`, and `social` are placeholders for the Phase 3 pre-warm.
"""
