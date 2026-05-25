"""Lightweight threaded-job registry for long-running calls.

The Claude thesis subprocess takes ~60s. We don't want Streamlit's
synchronous script to freeze during that wait — the user should be able
to switch tabs, refresh other data, and stop the call.

This module is intentionally tiny:

  - `submit(job_id, runner)` starts a daemon thread; if a job with the
    same id is already running, returns the existing one.
  - `get(job_id)` returns the current `Job` dataclass (status / elapsed /
    result / error).
  - `cancel(job_id)` flips the status and `terminate()`s the registered
    subprocess if any.

The registry is process-global (a module-level dict guarded by a lock).
It does not persist across process restarts — the worst case is the
user clicks Generate again on next launch, which is fine because the
Claude SQLite cache covers most repeat calls.
"""
from __future__ import annotations

import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


_JOBS: "dict[str, Job]" = {}
_LOCK = threading.Lock()

# Finished jobs are forgotten after this many seconds. Keeps long-lived
# Streamlit processes from leaking Job dataclasses indefinitely.
_FINISHED_TTL_SECONDS = 60 * 60  # 1 hour


@dataclass
class Job:
    id: str
    status: str = "running"               # running | done | cancelled | error
    started_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    # A single job may own many subprocesses when its runner fans Claude
    # calls out in parallel (e.g. the deep-dive). Cancel terminates all.
    procs: list = field(default_factory=list)
    progress: str = ""                    # short human-readable status text
    result: Any = None
    error: Optional[str] = None

    @property
    def elapsed(self) -> float:
        end = self.finished_at or time.time()
        return end - self.started_at


class JobHandle:
    """Given to the worker so it can register its subprocesses, post
    progress messages, and check whether the job has been cancelled."""

    def __init__(self, job_id: str):
        self.job_id = job_id

    def set_proc(self, proc: subprocess.Popen) -> None:
        """Register a new running subprocess for this job. Cancellation
        will `terminate()` every proc registered here."""
        with _LOCK:
            job = _JOBS.get(self.job_id)
            if job:
                job.procs.append(proc)

    def set_progress(self, message: str) -> None:
        """Post a short status update visible from `jobs.get(id).progress`."""
        with _LOCK:
            job = _JOBS.get(self.job_id)
            if job:
                job.progress = message

    def is_cancelled(self) -> bool:
        with _LOCK:
            job = _JOBS.get(self.job_id)
            return bool(job and job.status == "cancelled")


def _gc_finished(now: float) -> None:
    """Drop finished jobs older than _FINISHED_TTL_SECONDS. Caller must
    hold _LOCK."""
    stale = [
        jid for jid, j in _JOBS.items()
        if j.status != "running"
        and j.finished_at is not None
        and (now - j.finished_at) > _FINISHED_TTL_SECONDS
    ]
    for jid in stale:
        _JOBS.pop(jid, None)


def submit(job_id: str,
           runner: Callable[[JobHandle], Any]) -> Job:
    """Start a daemon thread that runs `runner(handle)`. If a job with
    this id is already running, returns the existing one untouched."""
    now = time.time()
    with _LOCK:
        _gc_finished(now)
        existing = _JOBS.get(job_id)
        if existing and existing.status == "running":
            return existing
        job = Job(id=job_id)
        _JOBS[job_id] = job

    handle = JobHandle(job_id)

    def thread_target():
        try:
            result = runner(handle)
        except Exception as exc:
            with _LOCK:
                cur = _JOBS.get(job_id)
                if cur and cur.status == "running":
                    cur.status = "error"
                    cur.error = str(exc)[:400]
                    cur.finished_at = time.time()
            return
        with _LOCK:
            cur = _JOBS.get(job_id)
            if cur and cur.status == "running":
                cur.status = "done"
                cur.result = result
                cur.finished_at = time.time()

    threading.Thread(
        target=thread_target,
        daemon=True,
        name=f"fire-job-{job_id}",
    ).start()
    return job


def get(job_id: str) -> Optional[Job]:
    with _LOCK:
        return _JOBS.get(job_id)


def list_running(prefix: str = "") -> list:
    """All currently-running jobs whose id starts with `prefix` (use "" for
    all). Returned as a snapshot — safe to iterate without the lock."""
    with _LOCK:
        return [j for j in _JOBS.values()
                if j.status == "running" and j.id.startswith(prefix)]


def cancel(job_id: str) -> bool:
    """Flip the status to cancelled and terminate every proc the job
    owns. Returns True if a running job was actually cancelled."""
    with _LOCK:
        job = _JOBS.get(job_id)
        if not job or job.status != "running":
            return False
        job.status = "cancelled"
        job.finished_at = time.time()
        procs = list(job.procs)
    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            pass
    # Best-effort wait so the child processes are reaped before we return.
    for proc in procs:
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                proc.kill()
            except Exception:
                pass
        except Exception:
            pass
    return True


def clear(job_id: str) -> None:
    """Forget the job. Call after the UI has consumed its result so we
    don't leak the entry forever."""
    with _LOCK:
        _JOBS.pop(job_id, None)
