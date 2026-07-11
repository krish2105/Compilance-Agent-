"""
Verifier Agent — the correctness guardrail.

It cross-checks the drafted narrative against the ACTUAL queried evidence, not
against the LLM's own say-so. Three independent checks:

  1. Structured-claim check: each machine-checkable claim from the Narrative Agent
     is independently recomputed from the evidence facts and compared.
  2. Citation check: every `TXNxxxxxxx` id mentioned in the narrative text must
     exist in the case's real transaction set (no fabricated citations).
  3. Figure check: every currency-tagged monetary figure in the narrative must
     correspond to a real evidence amount (a transaction amount, the aggregate,
     the max, or the customer's expected volume) within tolerance — this catches
     an LLM inventing a plausible-but-wrong number.

If any check fails, the Verifier returns `passed = False` and `should_retry`, and
the orchestrator re-runs the narrative step in deterministic (evidence-only) mode.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_TXN_RE = re.compile(r"TXN\d{7}")
_MONEY_RE = re.compile(r"\b(AED|USD|EUR|GBP|INR)\s*([\d,]+(?:\.\d+)?)")
_FLOAT_TOL = 0.5      # absolute tolerance for money comparison
_REL_TOL = 0.01       # 1% relative tolerance


def _num(x) -> float:
    return float(str(x).replace(",", ""))


def _approx_in(value: float, allowed: List[float]) -> bool:
    for a in allowed:
        if abs(value - a) <= _FLOAT_TOL or (a != 0 and abs(value - a) / abs(a) <= _REL_TOL):
            return True
    return False


def verify_narrative(
    evidence: Dict[str, Any],
    narrative_result: Dict[str, Any],
    typology_match: Dict[str, Any],
) -> Dict[str, Any]:
    facts = evidence["facts"]
    text = narrative_result["narrative"]
    claims = narrative_result["claims"]

    issues: List[Dict[str, Any]] = []
    verified_claims: List[Dict[str, Any]] = []

    # -- 1. structured-claim recomputation ---------------------------------
    for c in claims:
        actual = facts.get(c["fact_path"])
        expected = c["expected"]
        ok = (
            (isinstance(expected, bool) and actual == expected)
            or (isinstance(expected, (int, float)) and not isinstance(expected, bool)
                and actual is not None and abs(_num(actual) - _num(expected)) <= _FLOAT_TOL)
            or (actual == expected)
        )
        verified_claims.append({
            "id": c["id"], "statement": c["statement"],
            "fact_path": c["fact_path"], "expected": expected,
            "actual": actual, "verified": bool(ok),
        })
        if not ok:
            issues.append({
                "type": "claim_mismatch", "claim_id": c["id"],
                "detail": f"Claim {c['id']} expected {expected} but evidence shows {actual}.",
            })

    # -- 2. citation check -------------------------------------------------
    real_txids = {t["transaction_id"] for t in evidence["transactions"]}
    cited = set(_TXN_RE.findall(text))
    fabricated = sorted(cited - real_txids)
    for txid in fabricated:
        issues.append({
            "type": "fabricated_citation", "reference": txid,
            "detail": f"Narrative cites {txid}, which is not in the case evidence.",
        })

    # -- 3. figure check ---------------------------------------------------
    # Allowed = every real transaction amount, the aggregate/max/expected/threshold,
    # AND any figure already present in the SOURCE evidence text (e.g. the analyst's
    # alert summary and KYC fields). The check exists to catch figures the NARRATIVE
    # invents beyond the queried evidence — figures that came from the evidence
    # itself are legitimate.
    allowed_amounts = [float(t["amount"]) for t in evidence["transactions"]]
    allowed_amounts += [
        float(facts.get("total_amount", 0)),
        float(facts.get("max_amount", 0)),
        float(facts.get("expected_monthly_volume", 0)),
        float(facts.get("reporting_threshold", 0)),
    ]
    _source_text = " ".join([
        str(evidence.get("case", {}).get("alert_summary", "")),
        str(evidence.get("subject_kyc", {}).get("source_of_funds", "")),
    ])
    for tok in re.findall(r"[\d,]+(?:\.\d+)?", _source_text):
        try:
            allowed_amounts.append(_num(tok))
        except ValueError:
            continue
    unsupported_figures: List[str] = []
    for _cur, raw in _MONEY_RE.findall(text):
        val = _num(raw)
        if val == 0:
            continue
        if not _approx_in(val, allowed_amounts):
            unsupported_figures.append(f"{_cur} {raw}")
    for fig in sorted(set(unsupported_figures)):
        issues.append({
            "type": "unsupported_figure", "reference": fig,
            "detail": f"Figure {fig} in the narrative does not match any evidence amount.",
        })

    # -- 4. typology sanity ------------------------------------------------
    conf = typology_match.get("confidence", 0)
    low_confidence = conf < 0.35

    passed = len(issues) == 0
    # Retry only for issues a deterministic re-draft can fix (LLM hallucinations).
    hallucination_issues = [i for i in issues if i["type"] in
                            ("fabricated_citation", "unsupported_figure")]
    should_retry = bool(hallucination_issues)

    summary = (
        f"Verified {sum(1 for c in verified_claims if c['verified'])}/{len(verified_claims)} "
        f"structured claims; {len(cited)} citations checked "
        f"({len(fabricated)} fabricated); "
        f"{len(set(unsupported_figures))} unsupported figures."
    )
    if low_confidence:
        summary += " NOTE: typology confidence is low — flag for careful human review."

    return {
        "passed": passed,
        "should_retry": should_retry,
        "issues": issues,
        "verified_claims": verified_claims,
        "citations_checked": len(cited),
        "fabricated_citations": fabricated,
        "unsupported_figures": sorted(set(unsupported_figures)),
        "low_confidence": low_confidence,
        "summary": summary,
    }
