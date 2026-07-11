"""
Tests for the IBM AMLworld real-format ingestion path.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data_ingest import (  # noqa: E402
    AMLWORLD_COLUMNS,
    generate_amlworld_sample,
    ingest_amlworld,
)


def test_sample_has_amlworld_schema(tmp_path):
    import pandas as pd

    p = generate_amlworld_sample(tmp_path / "amlworld_sample.csv")
    df = pd.read_csv(p)
    assert list(df.columns) == AMLWORLD_COLUMNS
    assert df["Is Laundering"].sum() > 0
    assert len(df) > 100


def test_ingest_maps_to_schema_and_derives_cases(tmp_path):
    p = generate_amlworld_sample(tmp_path / "amlworld_sample.csv")
    tx, kyc, cases, ctx = ingest_amlworld(p)

    assert tx and kyc and cases and ctx
    # Transactions map to our schema.
    required = {"transaction_id", "sender_account", "receiver_account", "amount",
                "payment_currency", "is_laundering", "laundering_type", "case_id"}
    assert required.issubset(tx[0].keys())
    # Derived cases are non-trivial laundering components.
    assert all(c["ground_truth_typology"] == "AMLworld_Imported" for c in cases)
    assert all(c["case_id"].startswith("AML-") for c in cases)
    # Every case-transaction link points at a real transaction id.
    tx_ids = {t["transaction_id"] for t in tx}
    assert all(link["transaction_id"] in tx_ids for link in ctx)
