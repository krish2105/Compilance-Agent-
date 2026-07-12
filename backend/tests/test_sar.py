"""
Tests for SAR/STR generation, goAML XML export, and filing SLA.
"""
from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import orchestrator  # noqa: E402
from app.config import settings  # noqa: E402
from app.data_pipeline import build_database  # noqa: E402
from app.tools import audit, db, sar  # noqa: E402


def _setup():
    if not os.path.exists(settings.duckdb_path):
        build_database()
    audit.init_db()


def test_sar_record_has_coded_activity_and_subject():
    _setup()
    r = orchestrator.run_case("CASE-0029")
    rec = sar.build_sar_record(r, db.get_case("CASE-0029"))
    assert rec["report_type"] == "STR"
    assert rec["suspicious_activity"]["category_code"]
    assert rec["subject"]["name"]
    assert rec["transactions"]
    assert "DRAFT" in rec["status"]


def test_goaml_xml_is_well_formed():
    _setup()
    r = orchestrator.run_case("CASE-0001")
    rec = sar.build_sar_record(r, db.get_case("CASE-0001"))
    xml = sar.goaml_xml(rec)
    root = ET.fromstring(xml)                      # raises if malformed
    assert root.tag == "report"
    assert root.find("report_code").text == "STR"
    assert root.find("rentity_id") is not None
    assert root.find("transaction") is not None


def test_filing_sla_states():
    assert sar.filing_sla(None)["status"] == "PENDING_DETERMINATION"
    approved = sar.filing_sla({"decision": "APPROVED", "ts": "2026-07-12T00:00:00+00:00"})
    assert approved["status"] in ("ON_TIME", "DUE_SOON", "OVERDUE")
    assert approved["deadline"] is not None
