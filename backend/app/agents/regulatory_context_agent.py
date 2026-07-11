"""
Regulatory Context Agent.

Retrieves the regulatory context for the matched typology from the regulatory
knowledge base (`tools/regulatory_kb.py`, ~140 chunks) using the **hybrid
retriever** (BM25 + dense embeddings, RRF-fused, then reranked — see
`tools/retrieval.py`). This is the 2026 best-practice retrieval stack rather than
naive single-vector RAG.

Backends are pluggable and default to $0/offline:
  * embeddings: hashing (default) or Gemini neural (`EMBEDDING_BACKEND=gemini`)
  * retrieval: hybrid (default) / dense / bm25
  * reranker: lexical (default) / llm (Gemini) / none

The retriever is built once and cached.
"""
from __future__ import annotations

from typing import Any, Dict

from app.tools.regulatory_kb import build_chunks
from app.tools.retrieval import HybridRetriever
from app.tools.typologies import get_typology

_retriever: HybridRetriever = None  # type: ignore[assignment]


def _get_retriever() -> HybridRetriever:
    global _retriever
    if _retriever is None:
        _retriever = HybridRetriever(build_chunks())
    return _retriever


def get_regulatory_context(typology_match: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve regulatory context for the best-matched typology via hybrid RAG."""
    best = typology_match["best_match"]
    key = best["typology_key"]
    drivers = ", ".join(d["dimension"] for d in best.get("drivers", []))
    query = (f"{best['typology_label']} {best.get('definition', '')} "
             f"red flags indicators enhanced due diligence {drivers}")

    retriever = _get_retriever()
    retrieved = retriever.retrieve(query, k=5)

    canonical = get_typology(key)
    primary = {
        "typology_key": key,
        "label": canonical.label,
        "definition": canonical.definition,
        "red_flags": canonical.red_flags,
        "regulatory_note": (
            "Under a risk-based AML framework (FATF Recommendation 10) this pattern warrants "
            "Enhanced Due Diligence and, if suspicion is confirmed by a human analyst, a "
            "Suspicious Activity/Transaction Report (SAR/STR). This tool drafts that assessment; "
            "it does not file it."
        ),
    }
    return {
        "primary": primary,
        "retrieved": retrieved,
        "rag_backend": retriever.describe()["backend"],
        "rag_meta": retriever.describe(),
    }
