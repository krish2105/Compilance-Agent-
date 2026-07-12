"""Ops routes: Prometheus /metrics + async job status."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

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


@router.get("/api/responsible-ai")
def responsible_ai() -> dict:
    """Golden-set groundedness + red-team pass rate + bias/fairness audit (cached)."""
    from app.tools import cache

    cached = cache.get("responsible_ai")
    if cached is not None:
        return cached
    from eval.responsible_ai import run

    summary = run()
    cache.set("responsible_ai", summary, ttl=3600)
    return summary
