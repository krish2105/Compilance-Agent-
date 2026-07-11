"""
ComplianceAgent — FastAPI application entrypoint.

Wires together the middleware (auth + rate limit), CORS, the API routers, and
startup tasks (ensure the audit DB + processed dataset exist). Run with:

    uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.middleware import AuthAndRateLimitMiddleware
from app.api.routes import cases, chat, health
from app.config import settings
from app.tools import audit

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("complianceagent")

app = FastAPI(
    title="ComplianceAgent API",
    version="1.0.0",
    description=(
        "Multi-agent AML/KYC case-investigation copilot. Drafts case narratives and "
        "EDD reports with full evidence citations, verifies every claim against source "
        "data, and routes every case through a mandatory human approval gate. "
        "Portfolio/demo system on synthetic data — not certified compliance software."
    ),
)

# CORS for the Vite frontend. Auth is via the X-API-Key header (not cookies), so
# when CORS_ORIGINS is "*" we can safely allow any origin with credentials off —
# this lets the deployed backend accept the Vercel frontend without hardcoding its
# URL. Otherwise we use the explicit allow-list.
if settings.cors_origins.strip() == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
# Auth + rate limiting (runs before routing for every request).
app.add_middleware(AuthAndRateLimitMiddleware)

app.include_router(health.router)
app.include_router(cases.router)
app.include_router(chat.router)


@app.on_event("startup")
def _startup() -> None:
    audit.init_db()
    if not os.path.exists(settings.duckdb_path):
        logger.warning(
            "Processed dataset not found at %s. Run `python -m app.data_pipeline` "
            "from the backend/ directory to build it.", settings.duckdb_path
        )
    logger.info("ComplianceAgent API ready. LLM strategy: %s", settings.llm_provider)


@app.get("/", tags=["root"])
def root() -> dict:
    return {
        "name": "ComplianceAgent API",
        "docs": "/docs",
        "health": "/api/health",
        "note": "Send X-API-Key header on all /api/cases routes.",
    }
