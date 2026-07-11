"""
Agent / orchestrator test suite.

Runs the fixed benchmark cases through the full LangGraph pipeline and asserts:
  * correct typology routing (top-1 for the benchmark typologies; top-3 always),
  * non-empty, accurate evidence citations,
  * the Verifier passes clean deterministic drafts, and
  * the Verifier correctly flags a deliberately UNSUPPORTED (hallucinated) claim
    instead of passing it through.

These run entirely offline ($0, no API keys) thanks to the deterministic LLM
provider, so they are safe for CI.
"""
from __future__ import annotations

import os
import sys

import pytest

# Ensure the backend package is importable when pytest is run from repo root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents import (  # noqa: E402
    evidence_agent,
    orchestrator,
    typology_match_agent,
    verifier,
)
from app.data_pipeline import build_database  # noqa: E402
from app.tools import audit, db  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _ensure_data():
    """Build the dataset + audit DB once for the whole test session if missing."""
    from app.config import settings

    if not os.path.exists(settings.duckdb_path):
        build_database()
    audit.init_db()


# Benchmark: (ground-truth typology label that must be the TOP-1 match).
BENCHMARK_TYPOLOGIES = {
    "Structuring / Smurfing",
    "Fan-Out Distribution",
    "Fan-In Consolidation",
    "Cyclic / Round-Trip Flow",
    "Rapid Movement of Funds (Pass-Through)",
    "Sanctioned / High-Risk Jurisdiction Transfer",
    "High-Risk PEP Transaction",
    "Single Large Cross-Border Transfer",
}


def _benchmark_case_ids():
    ids = []
    for c in db.list_cases():
        gt = db.get_case(c["case_id"])["ground_truth_label"]
        if gt in BENCHMARK_TYPOLOGIES:
            ids.append(c["case_id"])
    return ids


def test_dataset_covers_all_28_typologies():
    import duckdb

    from app.config import settings

    con = duckdb.connect(settings.duckdb_path, read_only=True)
    n = con.execute("SELECT COUNT(DISTINCT laundering_type) FROM transactions").fetchone()[0]
    con.close()
    assert n == 28, f"expected all 28 typologies present, got {n}"


def test_evidence_agent_returns_structured_evidence():
    ev = evidence_agent.gather_evidence("CASE-0001")
    assert ev["case_id"] == "CASE-0001"
    assert ev["facts"]["transaction_count"] > 0
    assert ev["subject_kyc"]["account_number"]
    assert len(ev["transactions"]) == ev["facts"]["transaction_count"]


def test_evidence_agent_raises_on_missing_case():
    with pytest.raises(evidence_agent.EvidenceError):
        evidence_agent.gather_evidence("CASE-DOES-NOT-EXIST")


@pytest.mark.parametrize("case_id", _benchmark_case_ids())
def test_benchmark_typology_routing_top1(case_id):
    """Benchmark typologies must be the TOP-1 match."""
    result = orchestrator.run_case(case_id)
    gt = db.get_case(case_id)["ground_truth_label"]
    best = result["typology_match"]["best_match"]["typology_label"]
    assert best == gt, f"{case_id}: matched '{best}', expected '{gt}'"


def test_all_cases_route_correct_typology_in_top3():
    """Across the full case set, the correct typology is always in the top 3."""
    misses = []
    for c in db.list_cases():
        result = orchestrator.run_case(c["case_id"])
        gt = db.get_case(c["case_id"])["ground_truth_label"]
        ranked = [r["typology_label"] for r in result["typology_match"]["ranked"]]
        if gt not in ranked:
            misses.append((c["case_id"], gt, ranked))
    assert not misses, f"cases where ground truth not in top-3: {misses}"


def test_citations_are_non_empty_and_real():
    result = orchestrator.run_case("CASE-0003")
    citations = result["citations"]
    assert citations, "expected non-empty citations"
    real_ids = {t["transaction_id"] for t in result["evidence"]["transactions"]}
    assert set(citations).issubset(real_ids), "all citations must be real transactions"


def test_verifier_passes_clean_deterministic_draft():
    from app.agents import narrative_agent, regulatory_context_agent

    ev = evidence_agent.gather_evidence("CASE-0001")
    tm = typology_match_agent.match_typology(ev)
    rg = regulatory_context_agent.get_regulatory_context(tm)
    nr = narrative_agent.draft_narrative(ev, tm, rg, force_offline=True)
    v = verifier.verify_narrative(ev, nr, tm)
    assert v["passed"], f"clean draft should verify; issues={v['issues']}"
    assert v["fabricated_citations"] == []
    assert v["unsupported_figures"] == []


def test_verifier_flags_unsupported_claim():
    """Adversarial: inject a fabricated citation + bogus figure; Verifier must flag."""
    from app.agents import narrative_agent, regulatory_context_agent

    ev = evidence_agent.gather_evidence("CASE-0001")
    tm = typology_match_agent.match_typology(ev)
    rg = regulatory_context_agent.get_regulatory_context(tm)
    nr = narrative_agent.draft_narrative(ev, tm, rg, force_offline=True)

    # Tamper with the narrative to introduce unsupported content.
    nr = dict(nr)
    nr["narrative"] = nr["narrative"] + (
        "\n\nAdditional (fabricated) finding: transaction `TXN9999999` moved "
        "AED 4,242,424.00 to an unknown party."
    )
    v = verifier.verify_narrative(ev, nr, tm)
    assert not v["passed"], "verifier must not pass an unsupported claim"
    assert "TXN9999999" in v["fabricated_citations"]
    assert any("4,242,424" in f for f in v["unsupported_figures"])
    assert v["should_retry"], "hallucination should trigger a retry"


def test_full_pipeline_emits_all_agent_steps():
    steps = [ev["agent"] for ev in orchestrator.run_case_events("CASE-0005")]
    for agent in ("EvidenceAgent", "TypologyMatchAgent", "RegulatoryContextAgent",
                  "NarrativeAgent", "Verifier", "Orchestrator"):
        assert agent in steps, f"missing step from {agent}"


def test_audit_log_persists_pipeline_and_review():
    orchestrator.run_case("CASE-0006")
    trail = audit.get_audit_trail("CASE-0006")
    assert any(e["action"] == "GATHER_EVIDENCE" for e in trail)
    assert any(e["action"] == "VERIFY_NARRATIVE" for e in trail)

    audit.record_review("CASE-0006", "APPROVED", "test_reviewer", notes="looks good")
    latest = audit.get_latest_review("CASE-0006")
    assert latest["decision"] == "APPROVED"
    assert latest["status"] == "APPROVED_FOR_FILING_REVIEW"
