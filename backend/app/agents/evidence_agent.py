"""
Evidence Agent.

The first specialist in the pipeline. Given a case id it pulls, from DuckDB:
  * the case record + the focal (alerting) transaction,
  * the full network of related transactions,
  * the subject customer's KYC profile,
  * KYC profiles for the counterparties,
  * prior transaction history for the subject (outside this case),
and computes a deterministic set of behavioural facts/signals (see tools/signals).

It returns a structured, JSON-serialisable evidence bundle. It performs NO LLM
calls — evidence must be hard, quotable ground truth, so the Verifier can later
check every narrative claim against it.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.tools import db
from app.tools.signals import compute_facts


class EvidenceError(Exception):
    """Raised when a case cannot be assembled (missing case, empty network)."""


def gather_evidence(case_id: str) -> Dict[str, Any]:
    """Assemble the full evidence bundle for a case.

    Raises EvidenceError on missing case id, absent transaction network, or
    unresolvable KYC linkage.
    """
    case = db.get_case(case_id)
    if case is None:
        raise EvidenceError(f"Case '{case_id}' does not exist.")

    transactions = db.get_case_transactions(case_id)
    if not transactions:
        raise EvidenceError(f"Case '{case_id}' has no linked transactions.")

    subject = case["subject_account"]
    subject_kyc = db.get_kyc(subject)
    if subject_kyc is None:
        # Incomplete KYC linkage is itself a finding, not a crash.
        subject_kyc = {
            "account_number": subject,
            "full_name": "UNKNOWN — KYC profile not on file",
            "risk_rating": "Unknown",
            "pep_flag": False,
            "kyc_gap": True,
        }

    counterparties = db.get_counterparties(case_id)
    counterparty_kyc: Dict[str, Dict[str, Any]] = {}
    for acc in counterparties:
        if acc == subject:
            continue
        prof = db.get_kyc(acc)
        if prof:
            counterparty_kyc[acc] = prof

    history = db.get_account_history(subject, exclude_case_id=case_id, limit=20)

    facts = compute_facts(transactions, subject_kyc, counterparty_kyc)

    return {
        "case_id": case_id,
        "case": case,
        "subject_account": subject,
        "focal_transaction_id": case.get("focal_transaction_id"),
        "focal_transaction": _find_tx(transactions, case.get("focal_transaction_id")),
        "subject_kyc": subject_kyc,
        "counterparty_kyc": counterparty_kyc,
        "transactions": transactions,
        "prior_history": history,
        "facts": facts,
        "evidence_summary": _summarise(case_id, transactions, subject_kyc, facts),
    }


def _find_tx(transactions: List[Dict[str, Any]], txid: str) -> Dict[str, Any]:
    for t in transactions:
        if t["transaction_id"] == txid:
            return t
    return transactions[0] if transactions else {}


def _summarise(case_id, transactions, subject_kyc, facts) -> str:
    """A short human/agent-readable summary line (also emitted to the SSE trace)."""
    return (
        f"Assembled {facts['transaction_count']} related transactions "
        f"(total {facts['total_amount']:,.0f} across {', '.join(facts['currencies'])}) "
        f"for subject {subject_kyc.get('full_name', '?')} "
        f"[risk: {subject_kyc.get('risk_rating', '?')}, "
        f"PEP: {'Yes' if subject_kyc.get('pep_flag') else 'No'}]. "
        f"Counterparties: {facts['distinct_senders']} senders / "
        f"{facts['distinct_receivers']} receivers."
    )
