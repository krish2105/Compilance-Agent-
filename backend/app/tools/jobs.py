"""
Async job manager — non-blocking investigations.

A live-Gemini investigation can take ~15s; blocking the request thread doesn't
scale. This runs investigations as background jobs (thread pool) so the API returns
a `job_id` immediately and the client polls for the result. In-process for the free
tier; the same interface swaps to Celery/RQ + Redis for horizontal scale.

Job ids are deterministic-free (a monotonically increasing counter, no Date.now /
uuid randomness required at import) and jobs are kept for a short TTL.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional

from app.tools import metrics

_MAX_WORKERS = 4
_JOB_TTL = 600  # keep finished jobs for 10 min


class _JobStore:
    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=_MAX_WORKERS)
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._counter = 0

    def _new_id(self) -> str:
        with self._lock:
            self._counter += 1
            return f"job_{self._counter:06d}"

    def submit(self, kind: str, fn: Callable[..., Any], *args: Any) -> str:
        job_id = self._new_id()
        with self._lock:
            self._jobs[job_id] = {"id": job_id, "kind": kind, "status": "queued",
                                  "submitted_at": time.time(), "result": None, "error": None}
        metrics.JOBS.labels(status="queued").inc()

        def _run():
            metrics.ACTIVE_JOBS.inc()
            self._set(job_id, status="running")
            try:
                result = fn(*args)
                self._set(job_id, status="done", result=result, finished_at=time.time())
                metrics.JOBS.labels(status="done").inc()
            except Exception as exc:  # noqa: BLE001
                self._set(job_id, status="error", error=str(exc), finished_at=time.time())
                metrics.JOBS.labels(status="error").inc()
            finally:
                metrics.ACTIVE_JOBS.dec()

        self._executor.submit(_run)
        return job_id

    def _set(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            if job_id in self._jobs:
                self._jobs[job_id].update(fields)

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        self._reap()
        with self._lock:
            return self._jobs.get(job_id)

    def _reap(self) -> None:
        now = time.time()
        with self._lock:
            stale = [jid for jid, j in self._jobs.items()
                     if j.get("finished_at") and now - j["finished_at"] > _JOB_TTL]
            for jid in stale:
                self._jobs.pop(jid, None)


jobs = _JobStore()
