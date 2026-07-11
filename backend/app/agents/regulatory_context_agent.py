"""
Regulatory Context Agent.

Given the matched typology, retrieves its plain-English regulatory definition and
red-flag indicators from a vector store built over the 28-typology knowledge base
(the same content as `data/typology_reference.md`).

Pluggable vector backend (selected by `VECTOR_BACKEND`, default `memory`):

  * **memory** (default) — a zero-dependency, in-process vector store using a
    deterministic offline hashing embedder + cosine similarity. No native deps,
    tiny memory footprint — ideal for $0 free-tier hosting (512 MB) and CI.
  * **chroma** — ChromaDB with the same local hashing embedding function (no model
    downloads). Enable with `pip install -r requirements-full.txt` and
    `VECTOR_BACKEND=chroma`. `chromadb` is imported lazily only when selected, so
    it never inflates boot memory on the default path.

Both backends implement genuine semantic-ish retrieval: the query
("typology label + drivers") is embedded and matched against the indexed typology
chunks. Keeping one hashing embedder means the two backends behave identically.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from app.config import settings
from app.tools.typologies import ALL_TYPOLOGIES, get_typology

_EMBED_DIM = 256


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _embed(text: str) -> List[float]:
    """Deterministic, offline hashing embedding (no model download).

    Each token is hashed into one of `_EMBED_DIM` buckets with a signed weight;
    the vector is L2-normalised. Good enough to retrieve the right typology chunk
    from a small, well-separated knowledge base, at zero cost.
    """
    vec = [0.0] * _EMBED_DIM
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % _EMBED_DIM
        sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
        vec[idx] += sign
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _doc_for(typ) -> str:
    return f"{typ.label}. {typ.definition} Red flags: {'; '.join(typ.red_flags)}."


# --------------------------------------------------------------------------- #
#  In-memory vector store (default)
# --------------------------------------------------------------------------- #
class _InMemoryVectorStore:
    """Tiny cosine-similarity store over the 28 typology chunks."""

    def __init__(self) -> None:
        self._ids: List[str] = []
        self._labels: List[str] = []
        self._docs: List[str] = []
        self._vecs: List[List[float]] = []
        for t in ALL_TYPOLOGIES:
            doc = _doc_for(t)
            self._ids.append(t.key)
            self._labels.append(t.label)
            self._docs.append(doc)
            self._vecs.append(_embed(doc))

    def query(self, text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        q = _embed(text)
        scored: List[Tuple[float, int]] = []
        for i, v in enumerate(self._vecs):
            sim = sum(a * b for a, b in zip(q, v))  # both L2-normalised → cosine
            scored.append((sim, i))
        scored.sort(reverse=True)
        out = []
        for sim, i in scored[:n_results]:
            out.append({
                "typology_key": self._ids[i],
                "label": self._labels[i],
                "text": self._docs[i],
                "distance": round(1.0 - sim, 4),  # cosine distance, matches chroma
            })
        return out


# --------------------------------------------------------------------------- #
#  ChromaDB vector store (optional; imported lazily)
# --------------------------------------------------------------------------- #
class _ChromaVectorStore:
    def __init__(self) -> None:
        import chromadb  # lazy — only when VECTOR_BACKEND=chroma
        from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

        class _HashingEmbeddingFunction(EmbeddingFunction):
            def __call__(self, input: Documents) -> Embeddings:  # noqa: A002 (chroma API)
                return [_embed(d) for d in input]

        client = chromadb.PersistentClient(
            path=settings.chroma_path,
            settings=chromadb.Settings(anonymized_telemetry=False, allow_reset=True),
        )
        self._col = client.get_or_create_collection(
            name="typology_reference",
            embedding_function=_HashingEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )
        if self._col.count() < len(ALL_TYPOLOGIES):
            self._col.upsert(
                documents=[_doc_for(t) for t in ALL_TYPOLOGIES],
                ids=[t.key for t in ALL_TYPOLOGIES],
                metadatas=[{"label": t.label, "category": t.category} for t in ALL_TYPOLOGIES],
            )

    def query(self, text: str, n_results: int = 3) -> List[Dict[str, Any]]:
        res = self._col.query(query_texts=[text], n_results=n_results)
        ids = res.get("ids", [[]])[0]
        docs = res.get("documents", [[]])[0]
        dists = res.get("distances", [[]])[0]
        metas = res.get("metadatas", [[]])[0]
        out = []
        for i, doc in enumerate(docs):
            out.append({
                "typology_key": ids[i] if i < len(ids) else None,
                "label": metas[i].get("label") if i < len(metas) else None,
                "text": doc,
                "distance": round(float(dists[i]), 4) if i < len(dists) else None,
            })
        return out


_store = None
_store_backend = None


def _get_store():
    """Build (once) the selected vector store, with a safe fallback to memory."""
    global _store, _store_backend
    if _store is not None:
        return _store, _store_backend

    backend = (settings.vector_backend or "memory").lower()
    if backend == "chroma":
        try:
            _store = _ChromaVectorStore()
            _store_backend = "chromadb+local-hashing-embeddings"
            return _store, _store_backend
        except Exception:  # noqa: BLE001 - chromadb missing / failed → fall back
            backend = "memory"
    _store = _InMemoryVectorStore()
    _store_backend = "in-memory-hashing-embeddings"
    return _store, _store_backend


def get_regulatory_context(typology_match: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve the regulatory context for the best-matched typology via RAG."""
    best = typology_match["best_match"]
    key = best["typology_key"]
    drivers = ", ".join(d["dimension"] for d in best.get("drivers", []))
    query = f"{best['typology_label']} {best.get('definition', '')} indicators {drivers}"

    store, backend = _get_store()
    retrieved = store.query(query, n_results=3)

    # Guarantee the exact matched typology's canonical text is present and primary,
    # even if vector ranking put a near neighbour first.
    canonical = get_typology(key)
    primary = {
        "typology_key": key,
        "label": canonical.label,
        "definition": canonical.definition,
        "red_flags": canonical.red_flags,
        "regulatory_note": (
            "Under a risk-based AML framework this pattern warrants Enhanced Due "
            "Diligence and, if suspicion is confirmed by a human analyst, a Suspicious "
            "Activity/Transaction Report (SAR/STR). This tool drafts that assessment; "
            "it does not file it."
        ),
    }
    return {
        "primary": primary,
        "retrieved": retrieved,
        "rag_backend": backend,
    }
