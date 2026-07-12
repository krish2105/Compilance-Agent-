# ComplianceAgent — Architecture

A multi-tenant, multi-agent AML/KYC investigation platform. Everything runs at **$0**
on free tiers; every design choice is swap-in-ready for production scale.

## System overview

```mermaid
flowchart TB
  subgraph Client["Frontend · React + TS + Tailwind (Vercel, PWA)"]
    UI["Case queue · Dashboard · Import wizard · Team · Billing<br/>⌘K palette · i18n/RTL · mobile bottom-nav"]
  end

  subgraph API["Backend · FastAPI (Render)"]
    MW["AuthN/RBAC + rate-limit + security-headers middleware"]
    R1["/api/auth · /api/cases · /api/ingest · /api/dashboard · /api/admin"]
  end

  subgraph Agents["Multi-agent pipeline · LangGraph state machine"]
    E["Evidence"] --> S["Sanctions screening"] --> G["GNN detector"]
    G --> T["Typology match"] --> RC["Regulatory-Context (RAG)"]
    RC --> N["Narrative"] --> V["Verifier"] --> F["Finalize + ensemble risk"]
  end

  subgraph Data["Data & ML"]
    DUCK[("DuckDB<br/>transactions / KYC / cases")]
    OPS[("SQLAlchemy store<br/>tenants · users · reviews · audit · uploads<br/>Postgres-durable / SQLite")]
    KB[("Regulatory KB<br/>hybrid BM25+ngram RAG")]
    GNN[("From-scratch NumPy GNN<br/>GraphSAGE, calibrated")]
    SANC[("Live OFAC + UN watchlist<br/>8k entities, blocking index")]
    CACHE[("Cache · Redis / in-memory")]
  end

  subgraph Prov["LLM (provider-agnostic)"]
    GEM["Gemini"] -.-> GRQ["Groq"] -.-> OFF["Deterministic offline"]
  end

  UI -->|"JWT / X-API-Key"| MW --> R1 --> Agents
  E --> DUCK
  E --> OPS
  S --> SANC
  G --> GNN
  RC --> KB
  N --> Prov
  R1 --> OPS
  R1 --> CACHE
  F -->|"draft only"| HUMAN["👤 Human approval gate<br/>(enforced in code)"] --> SAR["SAR/STR + goAML XML"]

  subgraph Obs["Cross-cutting"]
    MET["Prometheus /metrics + Grafana"]
    EVAL["Eval gates · red-team · fairness · LLM-judge"]
    TEST["80 unit · 12 Playwright E2E · Locust load"]
  end
```

## The 8-step agent pipeline
Deterministic `LangGraph` state machine (not a free-form loop), with a bounded retry
edge from Verifier → Narrative:

1. **Evidence** — pulls the case's transactions, KYC, network graph (no LLM; hard ground truth).
2. **Sanctions screening** — fuzzy match (Jaro-Winkler + blocking) vs the **real OFAC/UN** lists; a hit forces escalation.
3. **GNN detector** — from-scratch NumPy GraphSAGE scores each account; calibrated (Platt, Brier/ECE).
4. **Typology match** — 28 laundering patterns, rule-based + explainable.
5. **Regulatory-Context (RAG)** — hybrid BM25 + n-gram-dense retrieval, RRF-fused, reranked.
6. **Narrative** — LLM drafts the report, citing exact transactions/amounts.
7. **Verifier** — re-checks every figure and citation against the evidence; rejects + retries fabrications.
8. **Finalize** — ensemble risk (typology + GNN + screening) → the human approval gate.

## Multi-tenancy & SaaS layer
Every tenant is an isolated workspace: JWT carries the tenant; reviews, dispositions,
uploaded cases and audit are all tenant-scoped. Team management, plans/usage limits,
billing, org settings and audit export sit on top. See [ADRs](adr/).

## Deployment
- **Frontend** → Vercel (static + PWA). **Backend** → Render (Docker).
- **Durable mode** → set `DATABASE_URL` (Neon Postgres) + `REDIS_URL` (Upstash).
- **CI** → GitHub Actions: lint · tests+coverage · eval gate · responsible-AI · Playwright E2E.
- **Scheduled** → weekly cron refreshes the sanctions snapshot.

## Horizontal scaling & multi-region (L5-ready)
The app is designed to scale out; the *code* is free, running multiple instances/regions
is a paid config change.

- **Stateless backend.** All shared state lives in external stores: **Postgres** (tenants,
  users, reviews, audit, uploads) and **Redis** (cache, investigation results, **rate-limit
  and login-throttle counters** — atomic `INCR`). No request-affinity or sticky sessions
  needed, so any request can hit any instance.
- **Readiness probe.** `GET /api/ready` returns `horizontally_scalable: true` once Redis +
  Postgres are attached — a load balancer / orchestrator (Render, Fly, K8s) can gate traffic on it.
- **Graceful shutdown** drains in-flight requests on SIGTERM.
- **Frontend is already global** — Vercel serves it from a multi-region edge CDN (free).
- **To scale out (paid):** raise `numInstances` in [`render.yaml`](../render.yaml) (or `fly scale count`),
  and for multi-region run the backend per region + a Postgres read-replica. No code change.
