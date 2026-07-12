"""
Screening Agent — sanctions / PEP / high-risk-jurisdiction screening.

Screens the case subject and all counterparties (by name) and every involved
jurisdiction against the watchlists (`tools/sanctions.py`). Produces structured
hits and a screening risk contribution that feeds the ensemble.

This is a first-class AML control that most "AML AI" demos omit entirely — a
sanctions nexus requires freezing/escalation independent of any laundering
typology, so it runs as its own specialist agent.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.tools import sanctions


def screen_case(evidence: Dict[str, Any]) -> Dict[str, Any]:
    subject_kyc = evidence.get("subject_kyc", {})
    counterparty_kyc = evidence.get("counterparty_kyc", {})
    facts = evidence.get("facts", {})

    # --- Name screening (subject + counterparties) ---
    name_hits: List[Dict[str, Any]] = []
    pep_hits: List[Dict[str, Any]] = []

    def _screen(name: str, account: str, is_subject: bool):
        for hit in sanctions.match_name(name):
            hit["screened_account"] = account
            hit["is_subject"] = is_subject
            (pep_hits if hit["type"] == "pep" else name_hits).append(hit)

    _screen(subject_kyc.get("full_name", ""), subject_kyc.get("account_number", ""), True)
    for acc, k in counterparty_kyc.items():
        _screen(k.get("full_name", ""), acc, False)

    # --- KYC PEP flags (independent of the watchlist name match) ---
    pep_flagged = []
    if subject_kyc.get("pep_flag"):
        pep_flagged.append({"account": subject_kyc.get("account_number"),
                            "name": subject_kyc.get("full_name"), "is_subject": True,
                            "source": "KYC PEP flag"})
    for acc, k in counterparty_kyc.items():
        if k.get("pep_flag"):
            pep_flagged.append({"account": acc, "name": k.get("full_name"),
                                "is_subject": False, "source": "KYC PEP flag"})

    # --- Jurisdiction screening ---
    jurisdiction_hits = []
    for loc in facts.get("involved_locations", []):
        res = sanctions.screen_jurisdiction(loc)
        if res:
            jurisdiction_hits.append(res)
    sanctioned_juris = [j for j in jurisdiction_hits if j["status"] == "sanctioned"]

    # --- Screening risk contribution ---
    if name_hits or sanctioned_juris:
        risk = 1.0
        level = "Sanctions match — freeze & escalate"
    elif pep_hits or pep_flagged or jurisdiction_hits:
        risk = 0.6
        level = "PEP / high-risk jurisdiction — EDD required"
    else:
        risk = 0.0
        level = "No screening hits — cleared"

    cleared = risk == 0.0
    total_hits = len(name_hits) + len(pep_hits) + len(pep_flagged) + len(jurisdiction_hits)
    summary = (f"Screening: {len(name_hits)} sanctions name hit(s), "
               f"{len(pep_hits) + len(pep_flagged)} PEP hit(s), "
               f"{len(jurisdiction_hits)} jurisdiction hit(s) "
               f"({len(sanctioned_juris)} sanctioned).")

    return {
        "cleared": cleared,
        "screening_risk": risk,
        "risk_level": level,
        "name_hits": name_hits,
        "pep_hits": pep_hits,
        "pep_flagged": pep_flagged,
        "jurisdiction_hits": jurisdiction_hits,
        "sanctioned_jurisdictions": sanctioned_juris,
        "total_hits": total_hits,
        "watchlist": sanctions.watchlist_stats(),
        "summary": summary,
    }
