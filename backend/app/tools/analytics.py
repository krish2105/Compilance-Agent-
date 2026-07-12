"""
Portfolio analytics for the dashboard.

Aggregates across the case book: alert volume by priority, review dispositions +
SAR rate, and (via a fast, no-LLM assessment) the ensemble risk-band and typology
distribution + average cost/latency. Cached (TTL) so the dashboard is cheap to load.
"""
from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List

from app.tools import audit, cache, db

_CACHE_KEY = "dashboard"


def _quick_assess(case_id: str) -> Dict[str, Any]:
    """Risk band + typology WITHOUT the LLM narrative (fast, $0)."""
    from app.agents import (
        evidence_agent,
        gnn_agent,
        orchestrator,
        screening_agent,
        typology_match_agent,
    )

    ev = evidence_agent.gather_evidence(case_id)
    scr = screening_agent.screen_case(ev)
    gnn = gnn_agent.score_case(ev["transactions"], ev["subject_account"])
    tm = typology_match_agent.match_typology(ev)
    risk = orchestrator._ensemble_risk(tm, gnn, scr)
    return {
        "risk_band": risk["risk_band"],
        "overall_risk": risk["overall_risk"],
        "typology": tm["best_match"]["typology_label"],
        "screening_cleared": scr["cleared"],
        "residence": ev["subject_kyc"].get("residence_country"),
    }


def compute_dashboard() -> Dict[str, Any]:
    cached = cache.get(_CACHE_KEY)
    if cached is not None:
        return cached

    cases = db.list_cases()
    by_priority = Counter(c.get("priority", "Medium") for c in cases)

    dispositions = Counter()
    finalized = 0
    for c in cases:
        review = audit.get_latest_review(c["case_id"])
        status = review["status"] if review else "PENDING_REVIEW"
        dispositions[status] += 1
        if status.startswith(("APPROVED", "ESCALATED")):
            finalized += 1

    risk_bands = Counter()
    typologies = Counter()
    screening_hits = 0
    assessments: List[Dict[str, Any]] = []
    for c in cases:
        try:
            a = _quick_assess(c["case_id"])
        except Exception:  # noqa: BLE001
            continue
        risk_bands[a["risk_band"]] += 1
        typologies[a["typology"]] += 1
        if not a["screening_cleared"]:
            screening_hits += 1
        assessments.append(a)

    n = len(cases)
    result = {
        "total_cases": n,
        "by_priority": dict(by_priority),
        "dispositions": dict(dispositions),
        "sar_rate": round(finalized / n, 3) if n else 0.0,
        "risk_bands": dict(risk_bands),
        "top_typologies": Counter(typologies).most_common(8),
        "screening_hit_rate": round(screening_hits / max(len(assessments), 1), 3),
        "pending_review": dispositions.get("PENDING_REVIEW", 0),
        "critical_high": by_priority.get("Critical", 0) + by_priority.get("High", 0),
    }
    cache.set(_CACHE_KEY, result, ttl=300)
    return result


def invalidate() -> None:
    cache.set(_CACHE_KEY, None, ttl=1)
