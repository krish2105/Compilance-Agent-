"""
Phase 5 — RAG reranker + relevance floor.

The lexical-path tests are deterministic/offline (CI-safe); the neural reranker test
is an HF integration test that skips without a token.
"""
from __future__ import annotations

from app.tools import abstention, entailment, regulatory_kb, retrieval

_R = retrieval.HybridRetriever(regulatory_kb.build_chunks())


def test_retrieve_exposes_relevance_and_floor():
    hits = _R.retrieve("structuring cash below reporting threshold", k=3)
    assert hits and all("relevance" in h and "below_floor" in h for h in hits)
    assert hits[0]["relevance"] >= hits[-1]["relevance"]  # sorted by relevance


def test_relevance_floor_flags_irrelevant_query():
    hits = _R.retrieve("the weather is nice today at the beach", k=1)
    assert hits[0]["below_floor"] is True, "an off-topic query should fall below the floor"


def test_relevant_query_is_above_floor():
    hits = _R.retrieve("enhanced due diligence politically exposed person", k=1)
    assert hits[0]["below_floor"] is False


def test_abstains_on_weak_regulatory_grounding():
    a = abstention.assess(
        verification={"passed": True},
        typology_match={"confidence": 0.8},
        risk={"sanctions_override": False},
        regulatory={"retrieval_low_confidence": True},
    )
    assert a["abstained"] is True
    assert any("Regulatory grounding is weak" in r for r in a["reasons"])


def test_neural_reranker_when_enabled():
    if not entailment.is_enabled():  # same HF token gates both
        import pytest
        pytest.skip("HuggingFace token not configured — neural reranker disabled")
    hits = _R.retrieve("wire transfer travel rule originator information",
                       k=3, reranker="neural")
    assert hits[0]["chunk_id"] == "fatf::rec16", "neural reranker should surface FATF Rec 16"
    assert hits[0]["relevance"] > 0.3
