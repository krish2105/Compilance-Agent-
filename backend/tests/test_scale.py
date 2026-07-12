"""
Horizontal-scalability readiness: shared counters (rate-limit / throttle) + readiness probe.
These are what make the backend safe to run as multiple instances behind a load balancer.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools import cache  # noqa: E402


def test_shared_counter_fixed_window():
    cache.delete("t:counter")
    assert cache.incr("t:counter", 60) == 1
    assert cache.incr("t:counter", 60) == 2
    assert cache.incr("t:counter", 60) == 3
    assert (cache.get("t:counter") or 0) == 3
    assert cache.ttl("t:counter") > 0
    cache.delete("t:counter")
    assert (cache.get("t:counter") or 0) == 0


def test_cache_reports_distribution_mode():
    info = cache.info()
    assert "cache_backend" in info
    assert "distributed" in info  # True only when Redis is attached


def test_readiness_probe():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.get("/api/ready")  # public, no auth
        assert r.status_code == 200
        body = r.json()
        assert body["ready"] is True
        assert "distributed" in body and "durable_db" in body
        assert "horizontally_scalable" in body
