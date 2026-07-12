# Case study — Building ComplianceAgent

*A multi-tenant, multi-agent AML/KYC investigation SaaS — built and deployed end-to-end at $0/month.*

## The problem
Banks generate thousands of anti-money-laundering "alerts." For each, an analyst manually
assembles the customer's history, works out the laundering pattern, and writes a long
regulatory report (a SAR/STR) — hours per case, most of them false positives. The bottleneck
isn't detecting the alert; it's the **investigation and paperwork**.

## What I built
An AI copilot that does the heavy lifting and routes every case through a **mandatory human
approval gate** — it never auto-clears or auto-files. A team of specialist agents:

> **evidence → sanctions screening → graph-neural-network risk → typology match → RAG regulatory context → narrative → verifier → human sign-off**

…plus the surrounding product: analyst chat, printable STR + **goAML** XML export, a portfolio
dashboard, and — as it grew into a SaaS — **multi-tenancy, team management, plans/billing,
bring-your-own-data ingestion, and real OFAC/UN sanctions screening.**

## Three engineering decisions I'm proud of
1. **A team of small agents, not one big prompt.** Most agents are deterministic; the LLM only
   writes prose. In a regulated domain, *reproducible* beats *clever*.
2. **A Verifier that checks against source data, not itself.** It re-reads the evidence and
   re-computes every figure/citation in the report; a fabricated `TXN…` or amount is caught and
   forced into a clean redraft. A genuine anti-hallucination control, unit-tested.
3. **Everything runs at $0.** A from-scratch NumPy GNN (no 2 GB PyTorch), a dependency-free
   n-gram embedder, DuckDB/SQLite, and a Gemini→Groq→offline LLM chain. It goes "generative" the
   moment a free key is added.

## Hardest problems solved
- **GNN mis-scored tiny case subgraphs → fixed** by scoring transductively against the full graph.
- **Deploy "exit 1"** traced to a build-time file write to a path absent in the Docker image.
- **Real sanctions at scale** — 20k OFAC/UN names were too slow to fuzzy-match, so I added a
  2-char **blocking index** (~40 ms/name).
- **Stale-session UX** — a JWT that no longer resolves now self-heals to the login screen.
- **Recurring free-tier deploy lag** — made the frontend resilient (client-side fallbacks) so the
  UI never dead-ends while the backend catches up.

## Proof it works
- **80 unit tests · 76% coverage · 12 Playwright E2E (desktop + mobile) · Locust load: ~40 req/s, 0% errors.**
- **Eval gates in CI:** groundedness, hallucination rate, retrieval quality, **6/6 → 11/11 red-team**, fairness (80% rule).
- **Model metrics:** GNN F1 0.86 / PR-AUC 0.94; retrieval +22% Recall@3 after the embedder upgrade.

## What it became
From a portfolio demo to an **early-stage multi-tenant SaaS**: isolated orgs, durable-ready data,
security hardening (session revocation, brute-force lock, password policy, security headers),
real sanctions data, a mobile-first PWA with i18n/RTL and a ⌘K palette, and a full test/quality
harness — all deployed, all at $0.

**Live:** https://frontend-three-pi-15.vercel.app · **Repo:** https://github.com/krish2105/Compilance-Agent-
