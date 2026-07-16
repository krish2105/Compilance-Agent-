"""
Hallucination-guardrail tests (Phase 1).

Proves the Verifier catches fabricated content and is robust to the messy tokens a
real LLM can emit. The NLI/entailment assertion runs only when a HuggingFace token
is configured (so CI without a token still passes on the deterministic guarantees).
"""
from __future__ import annotations

from app.agents import verifier
from app.tools import entailment


def _evidence():
    return {
        "facts": {
            "transaction_count": 2,
            "total_amount": 150000.0,
            "max_amount": 100000.0,
            "expected_monthly_volume": 50000.0,
            "reporting_threshold": 10000.0,
            "sub_threshold_count": 0,
            "max_fan_out": 1,
            "max_fan_in": 1,
            "cross_border_tx": 1,
            "cash_tx": 0,
            "layering_depth": 1,
            "min_pass_through_minutes": None,
            "sanctioned_jurisdiction": False,
            "pep_involved": False,
            "currencies": ["AED"],
            "involved_locations": ["UAE", "Iran"],
        },
        "transactions": [
            {"transaction_id": "TXN0000001", "amount": 100000.0},
            {"transaction_id": "TXN0000002", "amount": 50000.0},
        ],
        "case": {"alert_summary": "Two cross-border transfers.", "case_id": "CASE-TEST"},
        "subject_kyc": {"full_name": "Test Subject", "risk_rating": "High",
                        "occupation": "Trader", "residence_country": "UAE",
                        "source_of_funds": "Business"},
    }


def _claims():
    return [
        {"id": "C1", "statement": "The case comprises 2 related transactions.",
         "fact_path": "transaction_count", "expected": 2},
        {"id": "C2", "statement": "The aggregate value of the network is 150,000.00.",
         "fact_path": "total_amount", "expected": 150000.0},
    ]


def _narrative(text: str, provider="groq", fallback=False, draft=None):
    return {"narrative": text,
            "deterministic_draft": text if draft is None else draft,
            "claims": _claims(), "llm_provider": provider, "llm_fallback_used": fallback}


def test_num_is_robust_to_garbage_tokens():
    assert verifier._num(",") is None
    assert verifier._num("") is None
    assert verifier._num("123,456.78") == 123456.78
    assert verifier._num(None) is None


def test_clean_narrative_passes():
    text = "The network moved AED 150,000.00 across TXN0000001 and TXN0000002."
    v = verifier.verify_narrative(_evidence(), _narrative(text), {"confidence": 0.8})
    assert v["passed"] is True
    assert v["should_retry"] is False


def test_catches_fabricated_citation():
    text = "Funds also flowed through TXN9999999, an offshore account."
    v = verifier.verify_narrative(_evidence(), _narrative(text), {"confidence": 0.8})
    assert "TXN9999999" in v["fabricated_citations"]
    assert any(i["type"] == "fabricated_citation" for i in v["issues"])
    assert v["should_retry"] is True


def test_catches_unsupported_figure():
    text = "The subject wired AED 999,999.99 to a shell company."
    v = verifier.verify_narrative(_evidence(), _narrative(text), {"confidence": 0.8})
    assert v["unsupported_figures"]
    assert v["should_retry"] is True


def test_does_not_crash_on_stray_currency_token():
    # A lone comma after a currency (real LLMs emit this) must not raise.
    text = "The transfer of AED , was flagged. Total AED 150,000.00 confirmed."
    v = verifier.verify_narrative(_evidence(), _narrative(text), {"confidence": 0.8})
    assert isinstance(v["passed"], bool)


def test_nli_flags_unsupported_statement():
    """When NLI is enabled, an evidence-contradicting statement is caught."""
    if not entailment.is_enabled():
        import pytest
        pytest.skip("HuggingFace token not configured — NLI check disabled")
    ev = _evidence()
    # Clean evidence-only draft; the "LLM" then appends a fabricated sentence that
    # the (no-PEP, no-sanctions) evidence flatly does not support.
    clean_draft = "The case comprises 2 related transactions totalling AED 150,000.00."
    fabricated = ("The customer is a sanctioned Politically Exposed Person who transferred "
                  "funds to a shell company in Panama over 40 separate transactions.")
    text = clean_draft + " " + fabricated
    v = verifier.verify_narrative(ev, _narrative(text, draft=clean_draft), {"confidence": 0.8})
    assert v["entailment"]["available"] is True
    assert v["unsupported_statements"], "NLI should flag the fabricated statement"
    assert v["should_retry"] is True
