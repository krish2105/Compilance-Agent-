"""
Load test for the ComplianceAgent read API (proves it holds under concurrent load).

Focuses on the hot read paths analysts hit constantly — health, the case queue, case
detail (cached investigation), the audit trail and the portfolio dashboard. It does
NOT hammer the LLM investigation path (that's rate-limited and cost-bound by design).

Run against a locally-running backend:

    # terminal 1
    cd backend && .venv/bin/python -m uvicorn app.main:app --port 8099
    # terminal 2
    cd backend && .venv/bin/locust -f loadtest/locustfile.py --headless \
        -u 30 -r 10 -t 30s --host http://127.0.0.1:8099
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

API_KEY = "dev-local-key"
_HEADERS = {"X-API-Key": API_KEY}


class AnalystUser(HttpUser):
    """Simulates an analyst browsing the queue and opening cases."""

    wait_time = between(0.2, 1.0)

    def on_start(self):
        # Grab the case ids once so detail requests hit real cases.
        r = self.client.get("/api/cases", headers=_HEADERS, name="/api/cases")
        try:
            self.case_ids = [c["case_id"] for c in r.json()][:20] or ["CASE-0001"]
        except Exception:  # noqa: BLE001
            self.case_ids = ["CASE-0001"]

    @task(5)
    def list_cases(self):
        self.client.get("/api/cases", headers=_HEADERS, name="/api/cases")

    @task(4)
    def case_detail(self):
        cid = random.choice(self.case_ids)
        self.client.get(f"/api/cases/{cid}", headers=_HEADERS, name="/api/cases/[id]")

    @task(3)
    def dashboard(self):
        self.client.get("/api/dashboard", headers=_HEADERS, name="/api/dashboard")

    @task(2)
    def audit(self):
        cid = random.choice(self.case_ids)
        self.client.get(f"/api/cases/{cid}/audit", headers=_HEADERS, name="/api/cases/[id]/audit")

    @task(1)
    def health(self):
        self.client.get("/api/health", name="/api/health")
