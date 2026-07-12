# ADR 006 — Stronger n-gram embedder as the $0 default

**Status:** Accepted · **Date:** 2026

## Context
Plain single-token hashing embeddings miss paraphrase/morphology. sentence-transformers
would help but pulls torch (~2 GB) — untenable on the free tier.

## Decision
Default to a **dependency-free n-gram embedder**: word unigrams + bigrams + char 3/4-grams,
TF-weighted, signed-hashed to 512-d. Gemini neural embeddings remain a one-flag upgrade.

## Consequences
- ✅ **+22% Recall@3 / +23% MRR** on paraphrased queries vs hashing (measured); still $0, offline, deterministic.
- ➖ Not as strong as a true neural encoder; the interface makes the swap trivial.
