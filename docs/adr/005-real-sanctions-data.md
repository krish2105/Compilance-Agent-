# ADR 005 — Ship a real OFAC/UN sanctions snapshot

**Status:** Accepted · **Date:** 2026

## Context
A demo watchlist undersells the product. The real public OFAC SDN + UN consolidated
lists are free and authoritative, but ~20k names make naive fuzzy matching slow.

## Decision
Pull + normalise OFAC + UN into a **committed 8k-entity snapshot**; load it alongside the
demo entries. Screen with a **2-char blocking index + length pre-filter** so fuzzy
matching stays ~40 ms/name. A weekly cron + admin endpoint keep it fresh.

## Consequences
- ✅ Screens against genuine sanctions data (exact + typo matches); still $0/offline.
- ✅ Blocking keeps it fast at scale; snapshot ships in the image (no boot-time network).
- ➖ Capped at 8k for repo/latency; a production build would index the full list.
