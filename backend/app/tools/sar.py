"""
SAR/STR generation + goAML XML export + filing SLA.

A real Suspicious Activity/Transaction Report is a hybrid: **coded typology fields**
(e.g. FinCEN SAR Item 35 activity categories) PLUS a free-text narrative. This
module turns a completed investigation into:
  * a structured SAR record (coded suspicious-activity category + subject + amounts
    + indicators + narrative),
  * a **goAML XML** document — goAML is the UNODC reporting platform used by the UAE
    FIU (and ~60 jurisdictions) for STR/SAR filing; the XML here is structurally
    faithful to the goAML STR schema (report → reporting entity → transaction →
    parties → indicators), and
  * a **filing SLA** (deadline + status) from the human determination date.

Everything is a DRAFT for the MLRO's filing decision — this tool prepares the STR;
it does not file it.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from xml.dom import minidom

# Typology → coded suspicious-activity category (FinCEN SAR Item 35-style).
_ACTIVITY_CATEGORY = {
    "Structuring_Smurfing": "35(a) Structuring",
    "Cash_Intensive_Structuring": "35(a) Structuring — cash-intensive",
    "Fan_Out": "35(g) Money laundering — layering (fan-out)",
    "Fan_In": "35(g) Money laundering — layering (fan-in)",
    "Cycle": "35(g) Money laundering — round-tripping",
    "Scatter_Gather": "35(g) Money laundering — scatter-gather",
    "Gather_Scatter": "35(g) Money laundering — gather-scatter",
    "Bipartite": "35(g) Money laundering — layering",
    "Stacking": "35(g) Money laundering — chained layering",
    "Layered_Cross_Border": "35(g) Money laundering — layered cross-border",
    "Rapid_Movement": "35(g) Money laundering — pass-through",
    "Single_Large_Cross_Border": "35(s) Unusual large / cross-border transaction",
    "Trade_Based_Over_Invoicing": "33(k) Trade-based money laundering",
    "Shell_Company_Layering": "35(g) Money laundering — shell entity",
    "Sanctioned_Jurisdiction": "Sanctions nexus / prohibited transaction",
    "PEP_High_Risk": "PEP / suspected proceeds of corruption",
    "Deposit_Withdrawal": "35(g) Money laundering — deposit/withdrawal cycling",
}

REPORTING_ENTITY = {
    "name": "ComplianceAgent Demo Bank",
    "rentity_id": "AE-RE-000123",
    "reporting_person": "MLRO (pending assignment)",
}
# Policy: STR filed without undue delay; internal target 3 business days.
_SLA_DAYS = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def build_sar_record(result: Dict[str, Any], case: Dict[str, Any],
                     narrative_override: Optional[str] = None) -> Dict[str, Any]:
    ev = result["evidence"]
    kyc = ev["subject_kyc"]
    facts = ev["facts"]
    tm = result["typology_match"]["best_match"]
    key = tm["typology_key"]
    currency = facts.get("currencies", ["AED"])[0]

    indicators = list(tm.get("red_flags", []))
    scr = result.get("screening", {})
    if scr.get("sanctioned_jurisdictions"):
        indicators.append("Sanctioned/high-risk jurisdiction nexus")
    if scr.get("pep_flagged"):
        indicators.append("Politically Exposed Person involvement")

    return {
        "report_type": "STR",
        "case_id": case["case_id"],
        "generated_at": _now().isoformat(),
        "status": "DRAFT — pending MLRO filing decision (not filed)",
        "reporting_entity": REPORTING_ENTITY,
        "subject": {
            "name": kyc.get("full_name"),
            "account": kyc.get("account_number"),
            "date_of_birth": kyc.get("date_of_birth"),
            "nationality": kyc.get("nationality"),
            "risk_rating": kyc.get("risk_rating"),
            "pep": bool(kyc.get("pep_flag")),
        },
        "suspicious_activity": {
            "category_code": _ACTIVITY_CATEGORY.get(key, "35(z) Other"),
            "typology": tm["typology_label"],
            "total_amount": facts.get("total_amount"),
            "currency": currency,
            "transaction_count": facts.get("transaction_count"),
            "jurisdictions": facts.get("involved_locations", []),
            "overall_risk": result.get("risk", {}).get("overall_risk"),
            "risk_band": result.get("risk", {}).get("risk_band"),
        },
        "indicators": indicators,
        "narrative": narrative_override or result.get("narrative", ""),
        "transactions": [
            {
                "id": t["transaction_id"], "date": t["date"], "amount": t["amount"],
                "currency": t["payment_currency"], "from": t["sender_account"],
                "to": t["receiver_account"], "type": t["payment_type"],
                "from_country": t["sender_bank_location"], "to_country": t["receiver_bank_location"],
            }
            for t in ev["transactions"]
        ],
    }


def filing_sla(review: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute the STR filing SLA from the human determination (approval) date."""
    if not review or review.get("decision") not in ("APPROVED", "ESCALATED"):
        return {
            "policy": f"STR filed without undue delay (target: {_SLA_DAYS} business days).",
            "status": "PENDING_DETERMINATION",
            "determination_date": None, "deadline": None, "days_remaining": None,
        }
    det = datetime.fromisoformat(review["ts"].replace("Z", "+00:00")) \
        if isinstance(review.get("ts"), str) else _now()
    deadline = det + timedelta(days=_SLA_DAYS)
    remaining = (deadline - _now()).total_seconds() / 86400
    status = ("OVERDUE" if remaining < 0 else "DUE_SOON" if remaining < 1 else "ON_TIME")
    return {
        "policy": f"STR filed without undue delay (target: {_SLA_DAYS} business days).",
        "status": status,
        "determination_date": det.isoformat(),
        "deadline": deadline.isoformat(),
        "days_remaining": round(remaining, 2),
    }


def goaml_xml(sar: Dict[str, Any]) -> str:
    """Build a goAML-STR-schema-faithful XML document from the SAR record."""
    report = ET.Element("report")
    ET.SubElement(report, "rentity_id").text = REPORTING_ENTITY["rentity_id"]
    ET.SubElement(report, "submission_code").text = "E"          # electronic
    ET.SubElement(report, "report_code").text = sar["report_type"]  # STR
    ET.SubElement(report, "entity_reference").text = sar["case_id"]
    ET.SubElement(report, "submission_date").text = sar["generated_at"]
    ET.SubElement(report, "currency_code_local").text = sar["suspicious_activity"]["currency"]

    rperson = ET.SubElement(report, "reporting_person")
    ET.SubElement(rperson, "first_name").text = "MLRO"
    ET.SubElement(rperson, "last_name").text = "Reviewer"

    ET.SubElement(report, "reason").text = (
        f"{sar['suspicious_activity']['category_code']} — "
        f"{sar['suspicious_activity']['typology']}. "
        f"Risk band: {sar['suspicious_activity'].get('risk_band')}."
    )
    ET.SubElement(report, "action").text = sar["status"]

    for t in sar["transactions"]:
        tx = ET.SubElement(report, "transaction")
        ET.SubElement(tx, "transactionnumber").text = t["id"]
        ET.SubElement(tx, "date_transaction").text = t["date"]
        ET.SubElement(tx, "value_local").text = str(t["amount"])
        ET.SubElement(tx, "transaction_currency").text = t["currency"]
        t_from = ET.SubElement(tx, "t_from")
        ET.SubElement(t_from, "from_account").text = t["from"]
        ET.SubElement(t_from, "from_country").text = t["from_country"]
        t_to = ET.SubElement(tx, "t_to")
        ET.SubElement(t_to, "to_account").text = t["to"]
        ET.SubElement(t_to, "to_country").text = t["to_country"]

    indicators = ET.SubElement(report, "report_indicators")
    for ind in sar["indicators"]:
        ET.SubElement(indicators, "indicator").text = ind

    raw = ET.tostring(report, encoding="unicode")
    return minidom.parseString(raw).toprettyxml(indent="  ")


def build_all(result: Dict[str, Any], case: Dict[str, Any],
              review: Optional[Dict[str, Any]] = None,
              narrative_override: Optional[str] = None) -> Dict[str, Any]:
    sar = build_sar_record(result, case, narrative_override)
    return {"sar": sar, "sla": filing_sla(review), "goaml_available": True}
