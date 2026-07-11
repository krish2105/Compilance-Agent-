"""
Read-only data access over the processed DuckDB database.

All evidence the agents reason about flows through this module — this is the
single source of ground truth the Verifier checks generated claims against.
Connections are opened read-only per call (DuckDB allows many concurrent
readers), keeping the agents side-effect free.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import duckdb

from app.config import settings


def _con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(settings.duckdb_path, read_only=True)


def _rows_to_dicts(cur) -> List[Dict[str, Any]]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def list_cases() -> List[Dict[str, Any]]:
    """Return all investigation cases with a lightweight transaction count."""
    with _con() as con:
        cur = con.execute(
            """
            SELECT c.case_id, c.created_at, c.subject_account, c.focal_transaction_id,
                   c.alert_summary, c.priority, c.status,
                   (SELECT COUNT(*) FROM transactions t WHERE t.case_id = c.case_id)
                       AS transaction_count
            FROM cases c
            ORDER BY
                CASE c.priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1
                                WHEN 'Medium' THEN 2 ELSE 3 END,
                c.case_id
            """
        )
        return _rows_to_dicts(cur)


def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    with _con() as con:
        cur = con.execute("SELECT * FROM cases WHERE case_id = ?", [case_id])
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None


def get_case_transactions(case_id: str) -> List[Dict[str, Any]]:
    """All transactions belonging to a case's network, chronologically."""
    with _con() as con:
        cur = con.execute(
            "SELECT * FROM transactions WHERE case_id = ? ORDER BY timestamp",
            [case_id],
        )
        return _rows_to_dicts(cur)


def get_kyc(account: str) -> Optional[Dict[str, Any]]:
    with _con() as con:
        cur = con.execute(
            "SELECT * FROM kyc_profiles WHERE account_number = ?", [account]
        )
        rows = _rows_to_dicts(cur)
        return rows[0] if rows else None


def get_account_history(
    account: str, exclude_case_id: Optional[str] = None, limit: int = 25
) -> List[Dict[str, Any]]:
    """Prior transaction history for an account, excluding the case's own network."""
    with _con() as con:
        cur = con.execute(
            """
            SELECT * FROM transactions
            WHERE (sender_account = ? OR receiver_account = ?)
              AND (case_id IS NULL OR case_id <> ?)
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            [account, account, exclude_case_id or "__none__", limit],
        )
        return _rows_to_dicts(cur)


def get_counterparties(case_id: str) -> List[str]:
    """Distinct counterparties involved in a case's transaction network."""
    txs = get_case_transactions(case_id)
    accounts = set()
    for t in txs:
        accounts.add(t["sender_account"])
        accounts.add(t["receiver_account"])
    return sorted(accounts)
