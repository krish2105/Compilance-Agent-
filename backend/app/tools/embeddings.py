"""
Pluggable text embeddings for RAG.

Three backends, selected by `EMBEDDING_BACKEND`:
  * **ngram** (default) — a stronger dependency-free embedder: word unigrams +
    bigrams + character 3/4-grams, TF-weighted (1+log) and signed-hashed into 512d.
    Captures sub-word and phrase overlap (e.g. "structuring" ≈ "structured"), so it
    retrieves measurably better than plain single-token hashing — still $0, offline,
    deterministic, no torch/sentence-transformers.
  * **hashing** — the original bag-of-words hashing embedder (kept for comparison).
  * **gemini** — real neural embeddings via Google's `text-embedding-004` API,
    used when a Gemini key is configured. Falls back to ngram on any error.

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
_NGRAM_DIM = 512


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _l2(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _sig_hash(feature: str) -> tuple:
    """Return (index, sign) for a feature via a stable hash (signed hashing trick)."""
    h = int(hashlib.md5(feature.encode()).hexdigest(), 16)
    return h, 1.0 if (h >> 8) % 2 == 0 else -1.0


def _hash_embed(text: str) -> List[float]:
    vec = [0.0] * _HASH_DIM
    for tok in _tokenize(text):
        h, sign = _sig_hash(tok)
        vec[h % _HASH_DIM] += sign
    return _l2(vec)


def _ngram_features(text: str):
    """Yield (feature, weight) pairs: word unigrams + bigrams + char 3/4-grams."""
    toks = _tokenize(text)
    for t in toks:                                   # word unigrams
        yield ("w:" + t, 1.0)
    for a, b in zip(toks, toks[1:]):                 # word bigrams (phrases)
        yield (f"b:{a}_{b}", 0.7)
    for t in toks:                                   # char 3/4-grams (sub-word)
        padded = f"#{t}#"
        for n in (3, 4):
            for i in range(len(padded) - n + 1):
                yield ("c:" + padded[i:i + n], 0.5)


def _ngram_embed(text: str) -> List[float]:
    counts: dict = {}
    weights: dict = {}
    for feat, w in _ngram_features(text):
        counts[feat] = counts.get(feat, 0) + 1
        weights[feat] = w
    vec = [0.0] * _NGRAM_DIM
    for feat, c in counts.items():
        idx, sign = _sig_hash(feat)
        tf = 1.0 + math.log(c)                       # sublinear TF
        vec[idx % _NGRAM_DIM] += sign * tf * weights[feat]
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
        self.backend = (settings.embedding_backend or "ngram").lower()
        self._active = self.backend
        if self.backend == "gemini" and not settings.gemini_api_key:
            self._active = "ngram"

    @property
    def active_backend(self) -> str:
        return self._active

    def embed(self, texts: List[str]) -> List[List[float]]:
        if self._active == "gemini":
            try:
                return _gemini_embed(texts)
            except Exception:  # noqa: BLE001 - never break retrieval on embed failure
                self._active = "ngram"
        if self._active == "hashing":
            return [_hash_embed(t) for t in texts]
        return [_ngram_embed(t) for t in texts]  # default: ngram

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


def cosine(a: List[float], b: List[float]) -> float:
    # Both L2-normalised → cosine == dot product.
    return sum(x * y for x, y in zip(a, b))
