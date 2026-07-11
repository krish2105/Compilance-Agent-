"""
Pluggable text embeddings for RAG.

Two backends, selected by `EMBEDDING_BACKEND`:
  * **hashing** (default) — deterministic, offline, zero-dependency hashing
    bag-of-words embedder. $0, no network, reproducible; keeps the free-tier image
    lean (no torch / sentence-transformers).
  * **gemini** — real neural embeddings via Google's `text-embedding-004` API,
    used when a Gemini key is configured. Falls back to hashing on any error.

Isolating embeddings behind this interface is what makes the "swap in a real
embedding model" upgrade a one-line config change (ADR-006). Vectors are always
L2-normalised so downstream cosine == dot product.
"""
from __future__ import annotations

import hashlib
import math
import re
from typing import List

from app.config import settings

_HASH_DIM = 256


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _l2(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _hash_embed(text: str) -> List[float]:
    vec = [0.0] * _HASH_DIM
    for tok in _tokenize(text):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % _HASH_DIM] += 1.0 if (h >> 8) % 2 == 0 else -1.0
    return _l2(vec)


def _gemini_embed(texts: List[str]) -> List[List[float]]:
    import google.generativeai as genai

    genai.configure(api_key=settings.gemini_api_key)
    out: List[List[float]] = []
    for t in texts:
        res = genai.embed_content(model="models/text-embedding-004", content=t or " ")
        out.append(_l2(list(res["embedding"])))
    return out


class Embedder:
    """Embeds text with the configured backend; safe fallback to hashing."""

    def __init__(self) -> None:
        self.backend = (settings.embedding_backend or "hashing").lower()
        self._active = self.backend
        if self.backend == "gemini" and not settings.gemini_api_key:
            self._active = "hashing"

    @property
    def active_backend(self) -> str:
        return self._active

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self._active == "gemini":
            try:
                return _gemini_embed(texts)
            except Exception:  # noqa: BLE001 - never break retrieval on embed failure
                self._active = "hashing"
        return [_hash_embed(t) for t in texts]

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


def cosine(a: List[float], b: List[float]) -> float:
    # Both L2-normalised → cosine == dot product.
    return sum(x * y for x, y in zip(a, b))
