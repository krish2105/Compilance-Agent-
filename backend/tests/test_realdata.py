"""
Wave 5 — real-data tests: live sanctions snapshot loads & matches; ingest dedupe.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools import sanctions  # noqa: E402


def test_live_watchlist_loads_and_matches_real_names():
    stats = sanctions.watchlist_stats()
    # The committed OFAC/UN snapshot should be present and sizeable.
    assert stats["live_loaded"] is True
    assert stats["live_entries"] > 1000
    # A real OFAC entity matches (exact + fuzzy with a typo).
    assert sanctions.match_name("Banco Nacional de Cuba")
    assert sanctions.match_name("Anglo Caribean Co")  # missing 'b' → still fuzzy-matches
    # Demo entries still hit (so the bundled demo cases keep working).
    assert sanctions.match_name("Global Shell Holdings")


def test_screening_is_fast_enough():
    import time

    t = time.time()
    for q in ["John Smith", "Acme Trading LLC", "Ibrahim Al Suwaydi"]:
        sanctions.match_name(q)
    assert (time.time() - t) < 2.0  # blocking index keeps 8k-name screening quick


def test_ingest_dedupes_and_drops_self_loops():
    from app.db import init_models
    from app.tools import tenant_data

    init_models()
    rows = [
        {"transaction_id": "T1", "sender_account": "A", "receiver_account": "B", "amount": 5000},
        {"transaction_id": "T1", "sender_account": "A", "receiver_account": "C", "amount": 4000},  # dup id
        {"transaction_id": "T2", "sender_account": "A", "receiver_account": "A", "amount": 1000},   # self-loop
        {"transaction_id": "T3", "sender_account": "A", "receiver_account": "D", "amount": 3000},
    ]
    case = tenant_data.ingest_case("realdata-test-tenant", rows)
    assert case["rows_received"] == 4
    assert case["transaction_count"] == 2   # T1 (first) + T3
    assert case["duplicates_dropped"] == 2  # dup id + self-loop
