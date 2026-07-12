"""
Tests for the analytics dashboard aggregation and the printable case report.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import orchestrator  # noqa: E402
from app.config import settings  # noqa: E402
from app.data_pipeline import build_database  # noqa: E402
from app.tools import analytics, audit, db, report  # noqa: E402


def _setup():
    if not os.path.exists(settings.duckdb_path):
        build_database()
    audit.init_db()


def test_dashboard_aggregates():
    _setup()
    analytics.invalidate()
    d = analytics.compute_dashboard()
    assert d["total_cases"] == 34
    assert sum(d["by_priority"].values()) == 34
    assert d["risk_bands"]
    assert 0.0 <= d["sar_rate"] <= 1.0
    assert d["top_typologies"]


def test_report_html_is_self_contained():
    _setup()
    r = orchestrator.run_case("CASE-0001")
    html = report.build_html_report(r, db.get_case("CASE-0001"), None)
    assert html.startswith("<!doctype html>")
    assert "window.print" in html          # auto-print
    assert "DRAFT" in html
    assert "Case Narrative" in html
    assert r["evidence"]["transactions"][0]["transaction_id"] in html
