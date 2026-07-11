"""Health & readiness endpoints (public — no auth required)."""
from __future__ import annotations

import os

from fastapi import APIRouter

from app.config import settings
from app.llm.llm_client import llm_client
from app.tools import tracing

router = APIRouter(prefix="/api/health", tags=["health"])


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
        "disclaimer": (
            "Portfolio/demo system on synthetic data. Not certified compliance "
            "software. Every output is a draft requiring human sign-off."
        ),
    }
