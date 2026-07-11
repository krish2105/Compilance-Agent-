# Architecture Decision Records — ComplianceAgent

Short, honest records of the non-obvious engineering choices and their trade-offs.
(This file exists because "a DECISIONS.md documenting architectural choices" is a
specific hiring signal — reviewers want to see *why*, not just *what*.)

---

### ADR-001 · Deterministic specialist agents over LLM-autonomous agents
**Decision:** The orchestration is an explicit **LangGraph state machine**, and the
Evidence, Typology-Match, and Verifier agents are **compute/rule-based, not LLM-driven**.
Only the Narrative agent calls an LLM.
**Why:** In a regulated AML/KYC workflow, reproducibility and auditability beat
flashy autonomy. The same case must always yield the same typology, the same
citations, and the same verification result — which a regulator can inspect. An
LLM deciding "which tool next" is a black box with run-to-run variance.
**Trade-off:** Less "agentic magic"; not the right call for open-ended research
tasks. Documented explicitly so it reads as a choice, not a limitation.

### ADR-002 · Provider-agnostic LLM client with a deterministic offline default
**Decision:** All LLM calls go through one `LLMClient.generate()`; provider is an
env var (`gemini` → `groq` → `offline`). The offline provider returns a
deterministic, evidence-grounded draft.
**Why:** No standing free tier for Claude; the project must run at **$0** with no
keys (for the demo and CI). The offline provider guarantees output even when every
online provider rate-limits or fails.
**Trade-off:** Offline narratives are templated (less fluent) until a key is added.

### ADR-003 · The Verifier checks claims against source data, not itself
**Decision:** The Verifier re-queries the evidence and re-derives every structured
claim, validates every `TXN…` citation exists, and checks every currency figure
matches a real amount. It never asks the LLM to "double-check."
**Why:** Self-verification by the same model is theatre. Grounding the check in the
queried DataFrame is what makes the guardrail real (see the adversarial test and
the `verifier_catch_rate` eval metric).

### ADR-004 · Backend-enforced human approval gate
**Decision:** A case only reaches a finalized state through a persisted human
decision (`POST /api/cases/{id}/review`). No code path auto-approves.
**Why:** Clearing/reporting a case has legal consequences (SAR/STR). Full autonomy
is a compliance and ethical non-starter. The copilot compresses the analyst's work;
it does not replace their judgement.

### ADR-005 · Pluggable vector store — in-memory default, ChromaDB optional
**Decision:** RAG retrieval defaults to a zero-dependency in-memory cosine store;
ChromaDB is an optional backend (`VECTOR_BACKEND=chroma`), imported lazily.
**Why:** ChromaDB pulls `onnxruntime`/`hnswlib` — heavy to build and to load. On a
512 MB free tier it caused OOM/boot failures. The in-memory store is identical in
behaviour (same embedder) and fits the constraint. (This was a real deploy bug fix.)
**Trade-off:** In-memory doesn't persist or scale to millions of chunks — fine for a
28-chunk KB; swap to ChromaDB/pgvector for a large corpus.

### ADR-006 · Hashing embedder over a neural embedding model
**Decision:** Both vector backends use a deterministic **hashing bag-of-words**
embedder (no model download).
**Why:** Keeps retrieval offline, deterministic, and $0. Good enough for a small,
well-separated knowledge base.
**Trade-off:** No true semantic generalisation. **Upgrade path:** drop in
`sentence-transformers` (`bge-small`) or Gemini/Voyage embeddings + hybrid search
(BM25+dense) + a cross-encoder reranker — the retrieval interface is isolated for
exactly this swap.

### ADR-007 · Eval-driven development: deterministic gates + optional LLM-judge
**Decision:** `eval/run_eval.py` computes RAGAS/DeepEval-style metrics
(faithfulness, context precision/recall, hallucination, answer relevancy) **against
the queried evidence**, enforced as CI gates. A separate `eval/deepeval_suite.py`
runs the framework-backed **LLM-as-judge** metrics when a key is present.
**Why:** Eval design is the single strongest signal a candidate has actually built
with LLMs, and the deterministic metrics can gate CI at $0 (an LLM judge cannot).
**Trade-off:** Deterministic metrics can't judge subjective prose quality — hence
the optional LLM-judge suite for that dimension.

### ADR-008 · Observability always-on locally, Langfuse optional
**Decision:** Every investigation records step-level latency, tokens, and cost
locally (surfaced in the UI + audit log). If Langfuse keys are set, the same spans
stream to a hosted trace view. Tracing never raises.
**Why:** Step-level tracing + cost/latency is a mainstream 2026 expectation, but a
demo shouldn't *require* a third-party account.

### ADR-009 · Model router (cheap tier for light tasks)
**Decision:** `generate(task=…)` routes lightweight tasks to a cheaper model
(`gemini-2.5-flash-lite` / `llama-3.1-8b`) and narrative to the primary model.
**Why:** Cost awareness separates production experience from lab experience; a model
router is the standard lever.

### ADR-010 · Schema-faithful synthetic data
**Decision:** Generate a reproducible synthetic dataset embedding all 28 SAML-D
typologies + KYC, rather than shipping real data.
**Why:** Real AML/KYC data can never be lawfully published; SAML-D itself is
synthetic. **Upgrade path:** ingest the real IBM AMLworld/Elliptic benchmarks.

### ADR-011 · Render + Vercel free tiers
**Decision:** Backend on Render (Docker), frontend on Vercel.
**Why:** $0 hosting with a real live demo (live demos measurably increase callbacks).
**Trade-off:** Render free tier sleeps → ~30–60s cold start on the first request.
Documented rather than hidden.
