"""
Prometheus metrics + OpenTelemetry-style semantic attributes.

Exposes real Prometheus metrics at `/metrics` (scrapeable by Prometheus / Grafana
Cloud free tier). Instrumented across the stack: HTTP requests, investigations,
LLM usage (tokens/cost, `gen_ai.*` OTel conventions), cache, and jobs — the five
production monitoring layers (infra, cost, quality, throughput, ops).
"""
from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# ---- HTTP / infra ----
HTTP_REQUESTS = Counter("ca_http_requests_total", "HTTP requests",
                        ["method", "path", "status"])
HTTP_LATENCY = Histogram("ca_http_request_seconds", "HTTP request latency", ["path"])

# ---- Investigations / throughput ----
INVESTIGATIONS = Counter("ca_investigations_total", "Investigations run", ["status"])
INVESTIGATION_LATENCY = Histogram("ca_investigation_seconds", "Investigation latency")
RISK_BAND = Counter("ca_risk_band_total", "Investigations by ensemble risk band", ["band"])

# ---- LLM / cost (OTel gen_ai.* semantics) ----
LLM_CALLS = Counter("ca_gen_ai_calls_total", "LLM calls", ["provider", "task"])
LLM_TOKENS = Counter("ca_gen_ai_tokens_total", "LLM tokens", ["provider", "direction"])
LLM_COST = Counter("ca_gen_ai_cost_usd_total", "LLM cost (USD)", ["provider"])

# ---- Cache / jobs ----
CACHE_OPS = Counter("ca_cache_ops_total", "Cache operations", ["op"])  # hit|miss|set
JOBS = Counter("ca_jobs_total", "Async jobs", ["status"])
ACTIVE_JOBS = Gauge("ca_active_jobs", "Currently running async jobs")


def record_investigation(metrics_summary: dict, risk_band: str | None) -> None:
    INVESTIGATIONS.labels(status="ok").inc()
    lat = metrics_summary.get("total_latency_ms")
    if lat is not None:
        INVESTIGATION_LATENCY.observe(lat / 1000.0)
    if risk_band:
        RISK_BAND.labels(band=risk_band).inc()
    for g in metrics_summary.get("generations", []):
        prov = g.get("provider", "?")
        LLM_CALLS.labels(provider=prov, task=g.get("task") or "?").inc()
        LLM_TOKENS.labels(provider=prov, direction="input").inc(g.get("input_tokens", 0))
        LLM_TOKENS.labels(provider=prov, direction="output").inc(g.get("output_tokens", 0))
        LLM_COST.labels(provider=prov).inc(g.get("cost_usd", 0.0))


def render_latest() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
