"""Ops routes: Prometheus /metrics + async job status."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app import auth
from app.tools import jobs, metrics

router = APIRouter(tags=["ops"])


@router.get("/metrics")
def prometheus_metrics():
    """Prometheus exposition endpoint (scrape target for Prometheus/Grafana). Public."""
    payload, content_type = metrics.render_latest()
    return Response(content=payload, media_type=content_type)


@router.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    """Poll an async investigation job."""
    job = jobs.jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found or expired.")
    return job


@router.get("/api/model")
def model_info() -> dict:
    """GNN model registry (versioned model card + metrics) + live drift check."""
    from app.agents import gnn_agent

    return gnn_agent.model_info()


@router.get("/api/dashboard")
def dashboard(principal: auth.Principal = Depends(auth.get_current_principal)) -> dict:
    """Portfolio analytics (alert volume, dispositions, SAR rate, risk-band + typology
    distribution) scoped to the caller's tenant. Cached per tenant."""
    from app.tools import analytics

    return analytics.compute_dashboard(principal.tenant)


@router.get("/api/admin/sanctions")
def sanctions_status(_: auth.Principal = Depends(auth.require_role("admin"))) -> dict:
    """Sanctions watchlist status: live OFAC/UN counts, source, freshness."""
    from app.tools import sanctions
    return sanctions.watchlist_stats()


@router.post("/api/admin/sanctions/refresh")
def sanctions_refresh(_: auth.Principal = Depends(auth.require_role("admin"))) -> dict:
    """Pull the live public OFAC + UN lists and reload the watchlist (may take ~30s).

    Note: on an ephemeral free-tier container this updates the in-memory snapshot
    until the next restart; the committed snapshot (kept fresh by the scheduled cron)
    is the durable baseline.
    """
    from app.tools import sanctions
    from app.tools.sanctions_refresh import refresh_all

    try:
        result = refresh_all()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Feed refresh failed: {e}")
    sanctions.reload_watchlist()
    return {"ok": True, **result, "status": sanctions.watchlist_stats()}


@router.get("/api/responsible-ai")
def responsible_ai() -> dict:
    """Golden-set groundedness + red-team pass rate + bias/fairness audit.

    The full suite runs ~40 multi-agent investigations, so it is precomputed at image
    build time (see Dockerfile) and served from that artifact — instant, no per-request
    LLM calls. Falls back to a live run only if the artifact is missing.
    """
    from app.config import settings
    from app.tools import cache

    cached = cache.get("responsible_ai")
    if cached is not None:
        return cached

    from eval.responsible_ai import load_cached, run

    summary = load_cached()
    if summary is None:
        summary = run()  # fallback: compute live (slow — only if the artifact is absent)
    # Reflect the live provider (the artifact is built in offline mode).
    summary = {**summary, "llm_judge_available": settings.llm_provider != "offline"}
    cache.set("responsible_ai", summary, ttl=3600)
    return summary
