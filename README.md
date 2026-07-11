<div align="center">

# 🛡️ ComplianceAgent

**A multi-agent AML/KYC case-investigation copilot** that pre-screens flagged transactions,
drafts case narratives and Enhanced Due Diligence (EDD) reports with **full evidence citations**,
**verifies every claim against source data**, and routes every case through a **mandatory human
approval gate** — it never auto-clears or auto-reports.

`LangGraph` · `FastAPI` · `React + TypeScript` · `DuckDB` · `ChromaDB` · `Gemini / Groq / offline` · **$0/month**

</div>

> ⚠️ **Disclaimer.** This is a **portfolio / demo** system built on **synthetic data**. It is **not**
> certified compliance software, it does **not** file reports, and **every output is a draft that
> requires human sign-off**. Nothing in this system auto-clears or auto-reports a case.

---

## Why this project

AML alert triage is a real bottleneck in banks: analysts drown in flagged transactions and spend
hours assembling evidence and writing case narratives / EDD reports by hand. This project is **not
another fraud-detection classifier** — it is the **investigation and documentation layer above one**:

- **Orchestrated specialist agents** that assemble evidence, match typologies, pull regulatory
  context, and draft the case.
- **A Verifier** that checks *every* factual claim, figure, and citation against the actual queried
  evidence — not the LLM's own say-so.
- **A mandatory, backend-enforced human approval gate** before any case is finalized.
- **A full, persistent audit log** of every agent decision and every human action.

It is designed to demonstrate **production-grade agentic AI engineering in a regulated domain**
(explainability, auditability, human-in-the-loop governance) for AI/Compliance/Agentic-AI roles in
the UAE banking & fintech market.

---

## Architecture

![Architecture](docs/architecture_diagram.svg)

```mermaid
flowchart TD
    A[Flagged case: transaction + linked KYC profile] --> B[FastAPI backend · auth · rate limit · SSE]
    B --> O{{LangGraph Orchestrator}}
    O --> E[Evidence Agent · DuckDB: network, KYC, history]
    E --> T[Typology-Match Agent · cosine vs 28 typologies]
    T --> R[Regulatory-Context Agent · ChromaDB RAG]
    R --> N[Narrative Agent · deterministic draft + LLM polish]
    N --> V[Verifier · re-checks every claim vs evidence]
    V -- unsupported content --> N
    V -- ok --> H[Human Approval Gate · Approve / Edit / Reject]
    H --> L[(SQLite audit log: every step + human action)]
```

Every agent step is **logged to the audit trail** and **emitted as a live SSE event** so the frontend
renders the reasoning as it happens.

---

## The agents

| Agent | Role | How it works |
|---|---|---|
| **Evidence** | Assemble the case | Queries DuckDB for the case's transaction network, subject + counterparty KYC, and prior history; computes a deterministic behavioural fact/signal vector. **No LLM** — evidence must be hard ground truth. |
| **Typology-Match** | Classify the pattern | Cosine similarity between the case signature and each of the **28 SAML-D typologies**, returning a ranked best match, confidence, and the dimensions that drove it. Deterministic and explainable — the LLM never "guesses" the label. |
| **Regulatory-Context** | Ground it in policy | RAG lookup over the typology knowledge base in **ChromaDB** (local, offline hashing embeddings — no model downloads). |
| **Narrative** | Draft the case | Builds a deterministic, evidence-cited EDD draft + machine-checkable claims, then asks the LLM to *polish the prose only*. The offline provider (and any failure) returns the deterministic draft verbatim. |
| **Verifier** | Guard correctness | Recomputes every structured claim, checks every `TXN…` citation exists, and checks every currency figure matches a real evidence amount. Flags unsupported content and **triggers a deterministic retry**. |
| **Orchestrator** | Coordinate | A **LangGraph** state machine with conditional edges and the retry path. |

---

## Free-tier LLM strategy (why not Claude)

The Anthropic API has no standing free tier, so the LLM sits behind a **single provider-agnostic
interface** (`app/llm/llm_client.py`) selected by one env var:

- **`gemini`** — Google AI Studio (Gemini 2.5 Flash), the intended **primary** (free tier, no card).
- **`groq`** — Llama 3.3 70B, the **failover** lane (free tier, no card).
- **`offline`** — a **deterministic, no-network** provider so the *entire system runs end-to-end at
  $0 with no API keys at all* (used by default and in CI).

Every LLM call supplies a deterministic, evidence-grounded `fallback_text`. If the provider is
`offline`, or if every online provider fails (rate limit / auth / network), the client returns that
draft — so the copilot **always** produces sensible, evidence-grounded output. Swapping providers is
a one-line config change; no agent code imports a provider SDK directly.

---

## Dataset

- **Primary reference:** **SAML-D** (Synthetic Anti-Money-Laundering Transaction Data) — ~9.5M
  synthetic transactions across **28 typologies** (11 normal + 17 suspicious, including graph
  structures: fan-in, fan-out, cycles, scatter-gather, gather-scatter). SAML-D is *fully synthetic*,
  released precisely because real AML data can never be lawfully published.
- **Supplementary:** synthetic **KYC** profiles (risk rating, PEP, jurisdiction, occupation, expected
  volume, source of funds) joined at the account level.

**What this repo generates.** The full 9.5M rows are far too large for an interactive MVP, and Kaggle
downloads require auth. So `app/data_pipeline.py` deterministically generates a **schema-faithful
sample** (~2.8k transactions, 280 customers, **34 investigation cases**) that embeds the **same graph
typology structures across all 28 typologies**, joined with KYC. This is a deliberate, industry-standard
choice — see [`backend/data/data_dictionary.md`](backend/data/data_dictionary.md) for the schema,
subsetting method, the 28 typology definitions, and explicit limitations. If you drop the real Kaggle
SAML-D CSV into `backend/data/raw/`, the pipeline detects it (see `_load_real_saml_d`) for ingestion.

---

## Run locally

**Prerequisites:** Python 3.9+ and Node 18+.

### 1. Backend (FastAPI)
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                 # defaults run at $0 with the offline provider
python -m app.data_pipeline          # builds DuckDB + ChromaDB + reference docs
uvicorn app.main:app --reload --port 8099
```
Health check: <http://127.0.0.1:8099/api/health> · API docs: <http://127.0.0.1:8099/docs>

To use a real LLM, set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=…` (or `groq` / `GROQ_API_KEY`) in
`backend/.env`.

### 2. Frontend (React + Vite)
```bash
cd frontend
npm install
cp .env.example .env                 # VITE_API_URL=http://127.0.0.1:8099, VITE_API_KEY=dev-local-key
npm run dev
```
Open the printed URL (e.g. <http://localhost:5173>). Select a case → **Run investigation** → watch the
agents stream → review the draft → **Approve / Edit / Reject** at the human gate.

### 3. Docker (backend)
```bash
docker compose up --build            # backend on http://localhost:8099 (dataset built into the image)
```

### Run the tests
```bash
cd backend && pytest -q              # 25 tests, fully offline
```

---

## Evaluation

A fixed benchmark of cases spanning diverse typologies lives in
[`evaluation/eval_cases.md`](evaluation/eval_cases.md). The suite
([`backend/tests/test_agents.py`](backend/tests/test_agents.py)) runs them through the orchestrator and
asserts typology routing, non-empty & real citations, and correct Verifier behaviour.

**Typology-matching results on the 34-case set (deterministic, reproducible):**

| Metric | Result |
|---|---|
| Benchmark typologies (top-1) | **16 / 16** correct |
| Full set — top-1 accuracy | **~68%** (23 / 34) |
| Full set — **top-3 accuracy** | **100%** (34 / 34) — the correct typology is *always* surfaced |
| Verifier adversarial check | Catches fabricated citations + unsupported figures, triggers retry |

The remaining top-1 misses are all between **genuinely sibling typologies** (scatter-gather vs
gather-scatter, structuring vs cash-intensive structuring, bipartite vs PEP) — an honest, defensible
outcome for 17 fine-grained overlapping AML structures, and the correct label is always in the top-3.

---

## Guardrails (all genuinely functional, not cosmetic)

- **Verifier checks against real data.** It re-queries the evidence and recomputes/matches every claim,
  figure, and citation — see `test_verifier_flags_unsupported_claim`.
- **Human approval gate is backend-enforced.** A case only reaches a finalized state via a persisted
  human decision (`POST /api/cases/{id}/review`). No code path auto-approves.
- **Persistent audit log.** Every agent decision and human action is written to SQLite with timestamps
  (`app/tools/audit.py`), viewable in the UI.
- **Draft-only framing everywhere.** The UI banner, generated narratives, and API all state the output
  is a draft pending human review; the system never implies a case is cleared or reported.

---

## Production hardening

- API-key auth middleware on all `/api/cases` routes.
- Per-client sliding-window **rate limiting** on the case-processing endpoints.
- **Graceful LLM failover** (Gemini → Groq → deterministic offline) with clean, non-stack-trace error
  messages surfaced to the frontend.
- CI (GitHub Actions): ruff lint + pytest on the backend, ESLint + type-check + build on the frontend.
- No secrets committed; everything sensitive is via `.env` (`.env.example` documents every variable).

---

## Deployment

- **Backend → Render** (free web service). The `Dockerfile` builds the dataset into the image and serves
  on `$PORT`. Note: the free tier **sleeps on inactivity**, so the first request after idle has a
  cold-start delay (typically 30–60s) — expected for a portfolio demo.
- **Frontend → Vercel** (Hobby). Set `VITE_API_URL` to the live backend URL and `VITE_API_KEY` to match
  the backend's `BACKEND_API_KEY`.
- **Live demo link:** _add after deploying_ · **Walkthrough:** see
  [`docs/demo_video_link.md`](docs/demo_video_link.md).

---

## Repo layout

```
backend/    FastAPI · LangGraph agents · DuckDB · ChromaDB · SQLite audit · tests
frontend/   React + TS + Vite + Tailwind · SSE hook · premium light/dark UI
docs/       architecture diagram · demo walkthrough
evaluation/ benchmark case set
```

---

## Limitations & known failure modes (be honest)

- **Synthetic data.** Typologies are simplified, stylised representations; thresholds and jurisdiction
  lists are illustrative, not a regulatory reference.
- **Deterministic typology matcher** favours transparency over raw accuracy; sibling typologies are
  sometimes swapped at top-1 (always caught in top-3).
- **Offline LLM prose** is templated (excellent for auditability and $0 running, less "fluent" than a
  live model). Set a Gemini/Groq key for richer narratives.
- **Single-tenant, lightweight auth** (shared API key) — not an enterprise IAM.

---

## Future improvements

- Real vector-DB-backed, multi-jurisdiction regulatory knowledge base (with citations to actual
  regulations).
- Graph-native typology detection (GNN) feeding the matcher.
- Arabic-language case narratives for the UAE market.
- Analyst feedback loop that fine-tunes typology thresholds.
- SSO + role-based access (analyst / MLRO) and true SAR/STR workflow integration.

---

## Viva / interview Q&A

<details>
<summary><b>Why multiple agents instead of one big prompt?</b></summary>

Separation of concerns makes each step **auditable and independently testable**. Evidence gathering,
typology matching, and verification are deterministic and don't need an LLM at all; only the narrative
prose does. A single mega-prompt would blur these boundaries, be far harder to verify, and couple
correctness to model behaviour — unacceptable in a regulated workflow.
</details>

<details>
<summary><b>How does the Verifier actually work — isn't it just the LLM checking itself?</b></summary>

No. The Verifier re-queries the **actual evidence** and (1) recomputes every structured claim from the
facts, (2) confirms every `TXN…` citation exists in the case's real transaction set, and (3) confirms
every currency figure matches a real evidence amount within tolerance. It has data access; it does not
ask the LLM to "double-check." If it finds an invented figure or citation, it fails and the orchestrator
re-drafts deterministically. See `test_verifier_flags_unsupported_claim`.
</details>

<details>
<summary><b>Why a human-in-the-loop gate — why not full autonomy?</b></summary>

In AML/KYC, clearing or reporting a case has legal consequences (SAR/STR filings, customer impact,
regulatory liability). Full autonomy is both a compliance and an ethical non-starter. The copilot's job
is to **compress the analyst's work**, not replace their judgement. The gate is backend-enforced: no
case is finalized without a persisted human decision, and everything is captured in the audit log.
</details>

<details>
<summary><b>Why is the typology matcher deterministic rather than an LLM classifier?</b></summary>

Reproducibility and explainability. The same case always yields the same ranked match with the same
driving dimensions — which a regulator or an auditor can inspect. An LLM classifier would be a black box
with run-to-run variance. The LLM is reserved for the one thing it's best at: readable prose.
</details>

<details>
<summary><b>How would you scale this to the real 9.5M-row SAML-D?</b></summary>

DuckDB already handles far more than the sample; the agents query per-case, so scale is bounded by the
case network, not the table. For production I'd add proper alert generation upstream, partition the data,
move the audit log to Postgres, add a real vector DB, and put the LLM behind a queue with per-tenant
rate limits and the same failover chain.
</details>

<details>
<summary><b>How do you keep it $0?</b></summary>

DuckDB, ChromaDB (with local hashing embeddings — no model downloads), and SQLite are all embedded and
free. The LLM defaults to a deterministic offline provider, with Gemini/Groq free tiers available via a
one-line config change. Hosting uses Render + Vercel free tiers.
</details>

---

<div align="center">
<sub>Built as a portfolio project. Synthetic data · draft-only outputs · human sign-off required.</sub>
</div>
