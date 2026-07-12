"""
Tests for the sanctions / PEP screening agent + fuzzy-match engine.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import screening_agent  # noqa: E402
from app.tools import sanctions  # noqa: E402


def test_fuzzy_name_match_hits_watchlist():
    hits = sanctions.match_name("Ibrahim Al Suwaydi")  # misspelled on purpose
    assert hits, "fuzzy match should catch a near-spelling of a watchlist entry"
    assert hits[0]["matched_entry"] == "Ibrahim Al Suwaidi"
    assert hits[0]["score"] >= 0.86


def test_clean_name_does_not_match():
    assert sanctions.match_name("Jane Ordinary Smith") == []


def test_jurisdiction_screening():
    assert sanctions.screen_jurisdiction("Iran")["status"] == "sanctioned"
    assert sanctions.screen_jurisdiction("Panama")["status"] == "high_risk"
    assert sanctions.screen_jurisdiction("UAE") == {}


def test_screen_case_flags_sanctioned_jurisdiction():
    evidence = {
        "subject_kyc": {"full_name": "Jane Smith", "account_number": "AE1", "pep_flag": False},
        "counterparty_kyc": {},
        "facts": {"involved_locations": ["UAE", "Iran"]},
    }
    res = screening_agent.screen_case(evidence)
    assert not res["cleared"]
    assert res["screening_risk"] == 1.0
    assert res["sanctioned_jurisdictions"][0]["country"] == "Iran"


def test_screen_case_clears_clean_case():
    evidence = {
        "subject_kyc": {"full_name": "Jane Smith", "account_number": "AE1", "pep_flag": False},
        "counterparty_kyc": {"AE2": {"full_name": "John Doe", "pep_flag": False}},
        "facts": {"involved_locations": ["UAE"]},
    }
    res = screening_agent.screen_case(evidence)
    assert res["cleared"]
    assert res["screening_risk"] == 0.0


def test_screen_case_flags_pep():
    evidence = {
        "subject_kyc": {"full_name": "Some Official", "account_number": "AE1", "pep_flag": True},
        "counterparty_kyc": {},
        "facts": {"involved_locations": ["UAE"]},
    }
    res = screening_agent.screen_case(evidence)
    assert not res["cleared"]
    assert res["pep_flagged"]
