"""
Hybrid retrieval for the Regulatory-Context RAG.

Implements the 2026 best-practice retrieval stack (each measurably beats naive
single-vector RAG — see the research notes in the README):

  1. **Hybrid search** — sparse **BM25** (lexical) + dense (embedding cosine),
     fused with **Reciprocal Rank Fusion (RRF)**.
  2. **Reranking** — a funnel: retrieve Top-N, then rerank to Top-k. Default is a
     deterministic lexical cross-encoder-style reranker (offline, $0); an optional
     LLM reranker (Gemini) is available via `RERANKER=llm`.

All pieces are pure-Python (rank-bm25) + the pluggable embedder, so the whole
stack stays lean and runs at $0 with the hashing embedder, and upgrades to real
neural retrieval the moment a Gemini key is set.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from rank_bm25 import BM25Okapi

from app.config import settings
from app.tools.embeddings import Embedder, cosine

_RRF_K = 60


def _tok(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


@dataclass
class Chunk:
    id: str
    typology_key: str
    text: str
    metadata: Dict[str, Any]


class HybridRetriever:
    def __init__(self, chunks: List[Chunk], embedder: Optional[Embedder] = None) -> None:
        self.chunks = chunks
        self.embedder = embedder or Embedder()
        self._tokenized = [_tok(c.text) for c in chunks]
        self._bm25 = BM25Okapi(self._tokenized)
        self._doc_vecs = self.embedder.embed([c.text for c in chunks])

    # ---- individual scorers -------------------------------------------------
    def _dense_ranked(self, query: str) -> List[int]:
        q = self.embedder.embed_one(query)
        sims = [(cosine(q, v), i) for i, v in enumerate(self._doc_vecs)]
        sims.sort(reverse=True)
        return [i for _, i in sims]

    def _bm25_ranked(self, query: str) -> List[int]:
        scores = self._bm25.get_scores(_tok(query))
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return order

    @staticmethod
    def _rrf(rank_lists: List[List[int]], top_n: int) -> List[int]:
        agg: Dict[int, float] = {}
        for ranks in rank_lists:
            for rank, idx in enumerate(ranks):
                agg[idx] = agg.get(idx, 0.0) + 1.0 / (_RRF_K + rank)
        fused = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)
        return [idx for idx, _ in fused[:top_n]]

    # ---- reranking ----------------------------------------------------------
    def _rerank_lexical(self, query: str, cand_idx: List[int]) -> List[int]:
        """Deterministic cross-encoder-style reranker: weighted token overlap +
        phrase containment between the query and each candidate."""
        q_tokens = set(_tok(query))
        scored = []
        for i in cand_idx:
            c_tokens = _tok(self.chunks[i].text)
            c_set = set(c_tokens)
            overlap = len(q_tokens & c_set)
            jaccard = overlap / (len(q_tokens | c_set) or 1)
            coverage = overlap / (len(q_tokens) or 1)  # how much of the query is covered
            score = 0.6 * coverage + 0.4 * jaccard
            scored.append((score, i))
        scored.sort(reverse=True)
        return [i for _, i in scored]

    def _rerank_llm(self, query: str, cand_idx: List[int]) -> List[int]:
        """Optional LLM reranker (Gemini). Falls back to lexical on any issue."""
        try:
            from app.llm.llm_client import LLMClient

            client = LLMClient()
            scored = []
            for i in cand_idx:
                prompt = (
                    "Rate how relevant the passage is to the query on a 0-10 scale. "
                    "Reply with ONLY the number.\n\n"
                    f"Query: {query}\n\nPassage: {self.chunks[i].text}"
                )
                resp = client.generate(prompt, fallback_text="5", task="classify",
                                       name="rerank", max_tokens=4)
                m = re.search(r"\d+(\.\d+)?", resp.text)
                scored.append((float(m.group()) if m else 5.0, i))
            scored.sort(reverse=True)
            return [i for _, i in scored]
        except Exception:  # noqa: BLE001
            return self._rerank_lexical(query, cand_idx)

    # ---- public API ---------------------------------------------------------
    def retrieve(self, query: str, k: int = 3, *, mode: Optional[str] = None,
                 reranker: Optional[str] = None, top_n: int = 10) -> List[Dict[str, Any]]:
        mode = (mode or settings.retrieval_mode or "hybrid").lower()
        reranker = (reranker or settings.reranker or "lexical").lower()

        if mode == "dense":
            candidates = self._dense_ranked(query)[:top_n]
        elif mode == "bm25":
            candidates = self._bm25_ranked(query)[:top_n]
        else:  # hybrid
            candidates = self._rrf(
                [self._dense_ranked(query), self._bm25_ranked(query)], top_n)

        if reranker == "llm":
            ranked = self._rerank_llm(query, candidates)
        elif reranker == "none":
            ranked = candidates
        else:
            ranked = self._rerank_lexical(query, candidates)

        out = []
        for rank, i in enumerate(ranked[:k]):
            c = self.chunks[i]
            out.append({
                "chunk_id": c.id,
                "typology_key": c.typology_key,
                "label": c.metadata.get("label"),
                "section": c.metadata.get("section"),
                "text": c.text,
                "rank": rank,
            })
        return out

    def describe(self) -> Dict[str, Any]:
        return {
            "backend": f"hybrid(bm25+dense)+rerank · {self.embedder.active_backend}-embeddings",
            "n_chunks": len(self.chunks),
            "retrieval_mode": settings.retrieval_mode,
            "reranker": settings.reranker,
        }
