# ADR 004 — Case-id-routed multi-tenancy

**Status:** Accepted · **Date:** 2026

## Context
To become a SaaS, each organization needs an isolated workspace — but re-plumbing
`tenant` through the entire agent pipeline would be invasive and risky.

## Decision
Tenant-scope the **operational data** (users, reviews, dispositions, audit, uploads) in
the SQLAlchemy store. Give uploaded cases **globally-unique, tenant-slug-prefixed ids** so
the existing `case_id`-routed pipeline serves them with **zero agent changes**. A shared
`demo` tenant keeps the public demo working.

## Consequences
- ✅ Real isolation (proven in tests) with minimal blast radius.
- ✅ Each org can bring its own data; demo book stays shared.
- ➖ The reference transaction dataset is common; per-tenant ingestion covers real data.
