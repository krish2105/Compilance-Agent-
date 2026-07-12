# ADR 001 — Deterministic multi-agent state machine

**Status:** Accepted · **Date:** 2026

## Context
Compliance work is regulated and auditable: the same input must yield the same,
explainable result. A single free-form "do the investigation" LLM prompt is neither
reproducible nor inspectable.

## Decision
Model the investigation as a **LangGraph state machine** of specialist agents
(evidence → screening → GNN → typology → RAG → narrative → verifier → finalize) with a
**bounded** retry edge (Verifier → Narrative). Most agents are **deterministic** (no LLM);
the LLM is used only where prose is genuinely needed.

## Consequences
- ✅ Reproducible, unit-testable per agent, every step audit-logged and streamed.
- ✅ Failure isolation + a real anti-hallucination control (the Verifier).
- ➖ More upfront structure than a single prompt; fewer "emergent" behaviours (intended).
