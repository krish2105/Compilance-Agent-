"""
Narrative Agent.

Combines evidence + typology match + regulatory context into a draft case
narrative and Enhanced Due Diligence (EDD) report that explicitly cites specific
evidence (transaction IDs, amounts, dates, counterparties, KYC attributes).

Two-layer design for robustness and $0 operation:
  1. A DETERMINISTIC draft is built from the hard facts, with inline citations
     and a machine-checkable list of `claims` (each claim points at a fact the
     Verifier can independently recompute). This draft is always correct and is
     what the offline provider returns verbatim.
  2. The LLM (Gemini → Groq) is asked to POLISH the prose using ONLY the supplied
     facts. Whatever it returns is still run through the Verifier, so it can never
     smuggle an unsupported number past the guardrail.

Every generated document is explicitly a DRAFT pending human review — never a
cleared or filed case.
"""
from __future__ import annotations

from typing import Any, Dict, List

from app.llm.llm_client import LLMClient, llm_client

DRAFT_BANNER = (
    "> **DRAFT — PENDING HUMAN REVIEW.** This assessment was prepared by an AI "
    "copilot from synthetic data. It is **not** a cleared case and has **not** been "
    "reported to any authority. A qualified analyst must review, edit or reject it."
)

SYSTEM_PROMPT = (
    "You are an AML/KYC investigation copilot assisting a human compliance analyst. "
    "You write precise, factual case narratives. CRITICAL RULES: (1) Use ONLY the "
    "facts provided — never invent transaction IDs, amounts, dates, names or "
    "counterparties. (2) Cite specific evidence inline using the exact transaction "
    "IDs and amounts given. (3) Always frame the output as a DRAFT pending human "
    "review; never state a case is cleared, confirmed, or reported. (4) Keep the "
    "professional structure of the draft you are given."
)


def _fmt_money(amount: float, currency: str = "AED") -> str:
    return f"{currency} {amount:,.2f}"


def build_claims(evidence: Dict[str, Any], typology_match: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Machine-checkable claims. Each references a fact the Verifier recomputes."""
    facts = evidence["facts"]
    claims: List[Dict[str, Any]] = [
        {
            "id": "C1",
            "statement": f"The case comprises {facts['transaction_count']} related transactions.",
            "fact_path": "transaction_count",
            "expected": facts["transaction_count"],
        },
        {
            "id": "C2",
            "statement": f"The aggregate value of the network is {facts['total_amount']:,.2f}.",
            "fact_path": "total_amount",
            "expected": facts["total_amount"],
        },
        {
            "id": "C3",
            "statement": f"The largest single transaction is {facts['max_amount']:,.2f}.",
            "fact_path": "max_amount",
            "expected": facts["max_amount"],
        },
    ]
    if facts["sub_threshold_count"] >= 2:
        claims.append({
            "id": "C4",
            "statement": (
                f"{facts['sub_threshold_count']} transactions fall just below the "
                f"{facts['reporting_threshold']:,.0f} reporting threshold."
            ),
            "fact_path": "sub_threshold_count",
            "expected": facts["sub_threshold_count"],
        })
    if facts["max_fan_out"] >= 3:
        claims.append({
            "id": "C5",
            "statement": f"A single account distributes to up to {facts['max_fan_out']} "
                         f"counterparties (fan-out).",
            "fact_path": "max_fan_out",
            "expected": facts["max_fan_out"],
        })
    if facts["max_fan_in"] >= 3:
        claims.append({
            "id": "C6",
            "statement": f"A single account receives from up to {facts['max_fan_in']} "
                         f"counterparties (fan-in).",
            "fact_path": "max_fan_in",
            "expected": facts["max_fan_in"],
        })
    if facts["cross_border_tx"] > 0:
        claims.append({
            "id": "C7",
            "statement": f"{facts['cross_border_tx']} transactions are cross-border.",
            "fact_path": "cross_border_tx",
            "expected": facts["cross_border_tx"],
        })
    if facts["sanctioned_jurisdiction"]:
        claims.append({
            "id": "C8",
            "statement": "At least one transaction involves a sanctioned/high-risk jurisdiction.",
            "fact_path": "sanctioned_jurisdiction",
            "expected": True,
        })
    if facts["pep_involved"]:
        claims.append({
            "id": "C9",
            "statement": "A Politically Exposed Person (PEP) is involved in the case.",
            "fact_path": "pep_involved",
            "expected": True,
        })
    if facts["min_pass_through_minutes"] is not None and facts["min_pass_through_minutes"] < 60:
        claims.append({
            "id": "C10",
            "statement": (
                f"Funds passed through an account in {facts['min_pass_through_minutes']:.0f} "
                f"minutes (rapid movement)."
            ),
            "fact_path": "min_pass_through_minutes",
            "expected": facts["min_pass_through_minutes"],
        })
    return claims


def _deterministic_draft(
    evidence: Dict[str, Any],
    typology_match: Dict[str, Any],
    regulatory: Dict[str, Any],
    claims: List[Dict[str, Any]],
) -> str:
    facts = evidence["facts"]
    kyc = evidence["subject_kyc"]
    case = evidence["case"]
    best = typology_match["best_match"]
    primary = regulatory["primary"]
    txs = evidence["transactions"]
    currency = facts["currencies"][0] if facts["currencies"] else "AED"

    # Cited transaction table (first 8 for readability, all are in evidence).
    tx_lines = []
    for t in txs[:8]:
        tx_lines.append(
            f"- `[{t['transaction_id']}]` {t['date']} {t['time']} — "
            f"{_fmt_money(t['amount'], t['payment_currency'])} via {t['payment_type']} "
            f"from `{t['sender_account']}` ({t['sender_bank_location']}) → "
            f"`{t['receiver_account']}` ({t['receiver_bank_location']})"
        )
    more = f"\n- …and {len(txs) - 8} further related transactions in the case network." if len(txs) > 8 else ""

    red_flags = "\n".join(f"  - {rf}" for rf in best["red_flags"])
    claim_lines = "\n".join(f"- **[{c['id']}]** {c['statement']}" for c in claims)

    return f"""{DRAFT_BANNER}

# Case Narrative & EDD Draft — {case['case_id']}

**Subject account:** `{evidence['subject_account']}` — {kyc.get('full_name', 'Unknown')}
**Priority:** {case.get('priority', 'N/A')}  |  **Focal transaction:** `{evidence['focal_transaction_id']}`
**Assessed typology (draft):** {best['typology_label']} — confidence {typology_match['confidence']:.0%}

## 1. Alert Summary
{case.get('alert_summary', 'N/A')}

## 2. Customer Profile (KYC)
- **Name:** {kyc.get('full_name', 'Unknown')}
- **Risk rating:** {kyc.get('risk_rating', 'Unknown')}  |  **PEP:** {'Yes' if kyc.get('pep_flag') else 'No'}
- **Occupation:** {kyc.get('occupation', 'Unknown')}
- **Residence / nationality:** {kyc.get('residence_country', 'Unknown')}
- **Declared source of funds:** {kyc.get('source_of_funds', 'Unknown')}
- **Expected monthly volume:** {_fmt_money(float(kyc.get('expected_monthly_volume_aed', 0) or 0))}
- **KYC last reviewed:** {kyc.get('kyc_last_review_date', 'Unknown')}

## 3. Transaction Analysis
The case network contains **{facts['transaction_count']} transactions** with an aggregate
value of **{_fmt_money(facts['total_amount'], currency)}** (largest single transaction
**{_fmt_money(facts['max_amount'], currency)}**), spanning jurisdictions:
{', '.join(facts['involved_locations'])}.

Key structural observations: max fan-out **{facts['max_fan_out']}**, max fan-in
**{facts['max_fan_in']}**, layering depth **{facts['layering_depth']}**,
cross-border transactions **{facts['cross_border_tx']}**, cash transactions
**{facts['cash_tx']}**, sub-threshold deposits **{facts['sub_threshold_count']}**,
minimum pass-through time **{facts['min_pass_through_minutes'] if facts['min_pass_through_minutes'] is not None else 'n/a'} min**.

Representative cited transactions:
{chr(10).join(tx_lines)}{more}

## 4. Typology Assessment
The behavioural signature best matches **{best['typology_label']}**
(similarity {best['similarity']:.2f}, confidence {typology_match['confidence']:.0%}).
{best['definition']}

**Indicators observed / to verify:**
{red_flags}

## 5. Regulatory Context
{primary['definition']}

{primary['regulatory_note']}

## 6. Recommended Next Steps (DRAFT — for analyst decision)
1. Human analyst to review the cited evidence and the typology assessment above.
2. Consider Enhanced Due Diligence: corroborate source of funds and business rationale.
3. If suspicion is confirmed *by the analyst*, escalate to the MLRO for a potential
   SAR/STR filing decision. **This tool does not file reports or clear cases.**

## 7. Verifiable Claims
Each claim below is independently recomputed by the Verifier against the queried evidence:
{claim_lines}

---
*Prepared by ComplianceAgent (AI copilot). Draft only — requires human sign-off.*
"""


def draft_narrative(
    evidence: Dict[str, Any],
    typology_match: Dict[str, Any],
    regulatory: Dict[str, Any],
    *,
    force_offline: bool = False,
) -> Dict[str, Any]:
    """Produce the draft narrative + structured claims + provenance.

    `force_offline=True` bypasses the online LLM and returns the deterministic,
    evidence-only draft — used by the orchestrator's retry path when the Verifier
    catches an LLM hallucination.
    """
    claims = build_claims(evidence, typology_match)
    deterministic = _deterministic_draft(evidence, typology_match, regulatory, claims)

    client = LLMClient(provider="offline") if force_offline else llm_client

    # Ask the LLM to polish. It receives ONLY the deterministic draft as the source
    # of truth and is instructed not to introduce new facts. The offline provider
    # (and any failure) returns the deterministic draft verbatim.
    prompt = (
        "Polish the following AML case narrative for a compliance analyst. Improve "
        "flow and readability but DO NOT add, remove, or alter any transaction ID, "
        "amount, date, name, or figure, and keep every section and the DRAFT framing. "
        "Return only the narrative in Markdown.\n\n"
        f"---\n{deterministic}\n---"
    )
    response = client.generate(
        prompt, fallback_text=deterministic, system=SYSTEM_PROMPT,
        temperature=0.2, max_tokens=1800,
    )

    return {
        "narrative": response.text,
        "deterministic_draft": deterministic,
        "claims": claims,
        "citations": [t["transaction_id"] for t in evidence["transactions"]],
        "llm_provider": response.provider_used,
        "llm_model": response.model,
        "llm_fallback_used": response.fallback_used,
        "llm_note": response.note,
    }
