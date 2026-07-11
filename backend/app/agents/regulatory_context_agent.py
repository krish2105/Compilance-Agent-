"""
Regulatory Context Agent.

Given the matched typology, retrieves its plain-English regulatory definition and
red-flag indicators from a ChromaDB vector store built over
`data/typology_reference.md`.

To keep the whole system $0 and fully offline, ChromaDB is configured with a
LOCAL, deterministic embedding function (a hashing bag-of-words embedder) instead
of downloading an ONNX model. This is a genuine semantic-ish retrieval over the
knowledge base — the query ("typology label + drivers") is embedded and matched
against the indexed typology chunks — while requiring no network and no API keys.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, List

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

from app.config import settings
from app.tools.typologies import ALL_TYPOLOGIES, get_typology

_EMBED_DIM = 256
_COLLECTION = "typology_reference"


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class HashingEmbeddingFunction(EmbeddingFunction):
    """Deterministic, offline hashing embedder (no model download).

    Each token is hashed into one of `_EMBED_DIM` buckets with a signed weight;
    vectors are L2-normalised. Good enough for retrieving the right typology chunk
    from a small, well-separated knowledge base, at zero cost.
    """

    def __call__(self, input: Documents) -> Embeddings:  # noqa: A002 (chroma API name)
        out: Embeddings = []
        for doc in input:
            vec = [0.0] * _EMBED_DIM
            for tok in _tokenize(doc):
                h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
                idx = h % _EMBED_DIM
                sign = 1.0 if (h >> 8) % 2 == 0 else -1.0
                vec[idx] += sign
            norm = sum(v * v for v in vec) ** 0.5 or 1.0
            out.append([v / norm for v in vec])
        return out


_client = None
_collection = None


def _ensure_index():
    """Build (once) the Chroma collection from the typology knowledge base."""
    global _client, _collection
    if _collection is not None:
        return _collection

    _client = chromadb.PersistentClient(
        path=settings.chroma_path,
        settings=chromadb.Settings(anonymized_telemetry=False, allow_reset=True),
    )
    embedder = HashingEmbeddingFunction()
    _collection = _client.get_or_create_collection(
        name=_COLLECTION, embedding_function=embedder,
        metadata={"hnsw:space": "cosine"},
    )
    if _collection.count() < len(ALL_TYPOLOGIES):
        # (Re)index. One chunk per typology: definition + red flags.
        docs, ids, metas = [], [], []
        for t in ALL_TYPOLOGIES:
            docs.append(
                f"{t.label}. {t.definition} Red flags: {'; '.join(t.red_flags)}."
            )
            ids.append(t.key)
            metas.append({"typology_key": t.key, "label": t.label, "category": t.category})
        # Upsert keeps it idempotent across restarts.
        _collection.upsert(documents=docs, ids=ids, metadatas=metas)
    return _collection


def get_regulatory_context(typology_match: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve the regulatory context for the best-matched typology via RAG."""
    best = typology_match["best_match"]
    key = best["typology_key"]
    drivers = ", ".join(d["dimension"] for d in best.get("drivers", []))
    query = f"{best['typology_label']} {best.get('definition', '')} indicators {drivers}"

    collection = _ensure_index()
    result = collection.query(query_texts=[query], n_results=3)

    retrieved: List[Dict[str, Any]] = []
    ids = result.get("ids", [[]])[0]
    docs = result.get("documents", [[]])[0]
    dists = result.get("distances", [[]])[0]
    metas = result.get("metadatas", [[]])[0]
    for i, doc in enumerate(docs):
        retrieved.append({
            "typology_key": ids[i] if i < len(ids) else None,
            "label": metas[i].get("label") if i < len(metas) else None,
            "text": doc,
            "distance": round(float(dists[i]), 4) if i < len(dists) else None,
        })

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
        "rag_backend": "chromadb+local-hashing-embeddings",
    }
