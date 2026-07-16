"""Golden retrieval-quality guard (Phase 5 eval). Lexical path — CI-safe/offline."""
from __future__ import annotations

from app.tools import regulatory_kb, retrieval
from eval import retrieval_eval


def test_lexical_retrieval_meets_quality_bar():
    r = retrieval.HybridRetriever(regulatory_kb.build_chunks())
    m = retrieval_eval.evaluate("lexical", r)
    # The RAG must surface the right regulation for the golden queries.
    assert m["recall"] >= 0.85, f"Recall@5 too low: {m}"
    assert m["mrr"] >= 0.6, f"MRR too low: {m}"
    assert m["ndcg"] >= 0.6
