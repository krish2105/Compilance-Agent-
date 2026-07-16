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

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from rank_bm25 import BM25Okapi

from app.config import settings
from app.tools.embeddings import Embedder, cosine

logger = logging.getLogger("complianceagent.retrieval")
_RRF_K = 60
_HF_ROUTER = "https://router.huggingface.co/hf-inference/models/{model}"
_rerank_cache: Dict[str, Optional[List[float]]] = {}


_STOPWORDS = frozenset((
    "the a an of to in on at for and or is are was were be been being it its this that "
    "these those with as by from into over under about above below between out up down "
    "not no so if then than too very can will just do does did has have had i you he she "
    "we they them his her their our your my me but which who whom what when where why how"
).split())


def _tok(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _content_tok(text: str) -> List[str]:
    """Tokens with stopwords + 1-char tokens removed — for relevance scoring so an
    off-topic query (all stopwords) scores ~0 and trips the relevance floor."""
    return [t for t in _tok(text) if t not in _STOPWORDS and len(t) > 1]


def _hf_rerank_scores(query: str, texts: List[str]) -> Optional[List[float]]:
    """Neural relevance of each passage to the query via HF sentence-similarity.

    One HF call scores all candidates. Returns None if unavailable (no token / rate
    limit / error) so the caller falls back to the lexical reranker.
    """
    if not (settings.huggingface_token and texts):
        return None
    ck = query + "||" + "::".join(t[:80] for t in texts)
    if ck in _rerank_cache:
        return _rerank_cache[ck]
    payload = json.dumps({"inputs": {"source_sentence": query, "sentences": texts}}).encode()
    req = urllib.request.Request(
        _HF_ROUTER.format(model=settings.hf_rerank_model), data=payload, method="POST",
        headers={"Authorization": f"Bearer {settings.huggingface_token}",
                 "Content-Type": "application/json", "X-Wait-For-Model": "true"})
    try:
        with urllib.request.urlopen(req, timeout=settings.entailment_timeout) as resp:
            scores = json.loads(resp.read().decode("utf-8"))
        if isinstance(scores, list) and len(scores) == len(texts):
            _rerank_cache[ck] = [float(s) for s in scores]
            return _rerank_cache[ck]
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError,
            ValueError) as exc:
        logger.warning("Neural reranker unavailable: %s", exc)
    return None


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

    # ---- reranking (each returns [(idx, relevance_score)], sorted desc) ------
    def _rerank_lexical(self, query: str, cand_idx: List[int]) -> List[Tuple[int, float]]:
        """Deterministic cross-encoder-style reranker: weighted token overlap +
        phrase containment between the query and each candidate."""
        q_tokens = set(_content_tok(query))
        scored = []
        for i in cand_idx:
            c_set = set(_content_tok(self.chunks[i].text))
            overlap = len(q_tokens & c_set)
            jaccard = overlap / (len(q_tokens | c_set) or 1)
            coverage = overlap / (len(q_tokens) or 1)  # how much of the query is covered
            scored.append((i, 0.6 * coverage + 0.4 * jaccard))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    def _rerank_neural(self, query: str, cand_idx: List[int]) -> List[Tuple[int, float]]:
        """Neural reranker via HF sentence-similarity. Falls back to lexical."""
        scores = _hf_rerank_scores(query, [self.chunks[i].text for i in cand_idx])
        if scores is None:
            return self._rerank_lexical(query, cand_idx)
        scored = list(zip(cand_idx, scores))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    def _rerank_llm(self, query: str, cand_idx: List[int]) -> List[Tuple[int, float]]:
        """Optional LLM reranker. Falls back to lexical on any issue."""
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
                scored.append((i, (float(m.group()) if m else 5.0) / 10.0))
            scored.sort(key=lambda t: t[1], reverse=True)
            return scored
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

        if reranker == "neural":
            ranked = self._rerank_neural(query, candidates)
        elif reranker == "llm":
            ranked = self._rerank_llm(query, candidates)
        elif reranker == "none":
            ranked = [(i, 0.0) for i in candidates]
        else:
            ranked = self._rerank_lexical(query, candidates)

        floor = settings.rag_relevance_floor
        out = []
        for rank, (i, score) in enumerate(ranked[:k]):
            c = self.chunks[i]
            out.append({
                "chunk_id": c.id,
                "typology_key": c.typology_key,
                "label": c.metadata.get("label"),
                "section": c.metadata.get("section"),
                "text": c.text,
                "rank": rank,
                "relevance": round(float(score), 4),
                "below_floor": bool(score < floor),
            })
        return out

    def describe(self) -> Dict[str, Any]:
        return {
            "backend": f"hybrid(bm25+dense)+rerank · {self.embedder.active_backend}-embeddings",
            "n_chunks": len(self.chunks),
            "retrieval_mode": settings.retrieval_mode,
            "reranker": settings.reranker,
        }
