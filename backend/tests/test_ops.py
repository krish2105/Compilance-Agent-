"""
Tests for the ops layer: async jobs, cache, Prometheus metrics.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools import cache, jobs, metrics  # noqa: E402


def test_cache_set_get_and_expiry():
    cache.set("k1", {"a": 1}, ttl=60)
    assert cache.get("k1") == {"a": 1}
    cache.set("k2", "v", ttl=0)  # already expired
    time.sleep(0.01)
    assert cache.get("k2") is None


def test_job_runs_and_completes():
    job_id = jobs.jobs.submit("test", lambda x: x * 2, 21)
    for _ in range(50):
        job = jobs.jobs.get(job_id)
        if job and job["status"] == "done":
            break
        time.sleep(0.02)
    job = jobs.jobs.get(job_id)
    assert job["status"] == "done"
    assert job["result"] == 42


def test_job_captures_error():
    def _boom():
        raise ValueError("kaboom")

    job_id = jobs.jobs.submit("test", _boom)
    for _ in range(50):
        job = jobs.jobs.get(job_id)
        if job and job["status"] == "error":
            break
        time.sleep(0.02)
    assert jobs.jobs.get(job_id)["status"] == "error"
    assert "kaboom" in jobs.jobs.get(job_id)["error"]


def test_metrics_render_prometheus():
    metrics.INVESTIGATIONS.labels(status="ok").inc()
    payload, content_type = metrics.render_latest()
    text = payload.decode()
    assert "ca_investigations_total" in text
    assert "text/plain" in content_type
