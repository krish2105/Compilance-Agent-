"""Health & readiness endpoints (public — no auth required)."""
from __future__ import annotations

import os

from fastapi import APIRouter

from app.config import settings
from app.llm.llm_client import llm_client
from app.tools import tracing

router = APIRouter(prefix="/api/health", tags=["health"])


def _ops_info() -> dict:
    from app.db import backend_info
    from app.tools import cache

    return {**cache.info(), **backend_info()}


@router.get("")
def health() -> dict:
    """Liveness + a summary of the configured LLM strategy and data readiness."""
    db_ready = os.path.exists(settings.duckdb_path)
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "data_ready": db_ready,
        "llm": llm_client.health(),
        "observability": tracing.observability_status(),
        "auth": {"rbac": True, "roles": ["analyst", "mlro", "admin"]},
        "ops": {**_ops_info(), "metrics_endpoint": "/metrics"},
        "disclaimer": (
            "Portfolio/demo system on synthetic data. Not certified compliance "
            "software. Every output is a draft requiring human sign-off."
        ),
    }


@router.get("/llm")
def llm_diagnostic() -> dict:
    """Live LLM check: runs a tiny generation and reports which provider answered
    (and, on fallback, the exact error). Handy for diagnosing why Gemini isn't
    being used. Public — returns no secrets."""
    resp = llm_client.generate(
        "Reply with the single word: OK.",
        fallback_text="OK (offline)", task="classify", max_tokens=8, name="diagnostic",
    )
    return {
        "provider_used": resp.provider_used,
        "model": resp.model,
        "fallback_used": resp.fallback_used,
        "note": resp.note,
        "text_preview": resp.text[:120],
    }
