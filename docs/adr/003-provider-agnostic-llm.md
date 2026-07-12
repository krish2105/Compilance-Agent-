# ADR 003 — Provider-agnostic LLM with offline fallback

**Status:** Accepted · **Date:** 2026

## Context
Anthropic/OpenAI have no free tier; the project must run at $0 and never hard-fail on
a provider outage or missing key.

## Decision
One LLM interface, three providers: **Gemini → Groq → deterministic offline**. A model
router picks cheap/primary tiers; every generation records tokens/cost/latency.

## Consequences
- ✅ $0 by default; "generative" the moment a free key is added; graceful failover.
- ✅ CI and tests run fully offline and deterministically.
- ➖ Offline prose is templated (excellent for auditability, less fluent).
