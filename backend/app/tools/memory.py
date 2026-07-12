"""
Case memory — episodic recall of similar prior cases.

Agents benefit from precedent: "this case resembles CASE-0012, which was a confirmed
STR." This module builds an in-memory index of every case's behavioural signature
(the same 12-dim vector the Typology-Match agent uses) and, for a target case,
returns the most similar prior cases together with their disposition (from the audit
review history). Pure cosine similarity — deterministic and $0.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.tools import audit, db
from app.tools.signals import compute_facts
from app.tools.typologies import SIGNATURE_DIMS

_index: Optional[List[Dict[str, Any]]] = None


def _signature_for(case_id: str) -> Optional[Dict[str, float]]:
    txs = db.get_case_transactions(case_id)
    if not txs:
        return None
    case = db.get_case(case_id)
    subject_kyc = db.get_kyc(case["subject_account"]) if case else None
    facts = compute_facts(txs, subject_kyc, None)
    return facts["signature"]


def _build_index() -> List[Dict[str, Any]]:
    idx = []
    for c in db.list_cases():
        sig = _signature_for(c["case_id"])
        if sig is None:
            continue
        review = audit.get_latest_review(c["case_id"])
        idx.append({
            "case_id": c["case_id"],
            "signature": sig,
            "priority": c.get("priority"),
            "typology": db.get_case(c["case_id"]).get("ground_truth_label"),
            "disposition": review["status"] if review else "PENDING_REVIEW",
            "reviewed_by": review["reviewer"] if review else None,
        })
    return idx


def _get_index() -> List[Dict[str, Any]]:
    global _index
    if _index is None:
        _index = _build_index()
    return _index


def invalidate() -> None:
    """Drop the cache (call after a new review so dispositions refresh)."""
    global _index
    _index = None


def _cosine(a: Dict[str, float], b: Dict[str, float]) -> float:
    dot = sum(a[d] * b[d] for d in SIGNATURE_DIMS)
    na = math.sqrt(sum(a[d] ** 2 for d in SIGNATURE_DIMS))
    nb = math.sqrt(sum(b[d] ** 2 for d in SIGNATURE_DIMS))
    return dot / (na * nb) if na and nb else 0.0


def similar_cases(case_id: str, k: int = 3) -> List[Dict[str, Any]]:
    target = _signature_for(case_id)
    if target is None:
        return []
    scored = []
    for entry in _get_index():
        if entry["case_id"] == case_id:
            continue
        scored.append({
            "case_id": entry["case_id"],
            "similarity": round(_cosine(target, entry["signature"]), 3),
            "typology": entry["typology"],
            "disposition": entry["disposition"],
            "reviewed_by": entry["reviewed_by"],
            "priority": entry["priority"],
        })
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    return scored[:k]
