"""
Observability & cost/latency instrumentation.

Two layers, both always available:

  * **Local RunMetrics** (always on, zero-dependency): per-investigation step-level
    timing, token usage, and $ cost — surfaced in the API/UI and used by the eval
    pipeline. This is the "62% do step-level tracing" baseline, at $0.
  * **Langfuse tracing** (optional): if `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`
    are set, every agent node and LLM call is also emitted as a Langfuse
    trace/span/generation for a full hosted trace view. Entirely no-op (and never
    raises) when unconfigured or on any SDK error.

A `ContextVar` carries the current run so agents and the LLM client can attach
spans/generations without threading an object through every call.
"""
from __future__ import annotations

import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings

# ---- Cost model (illustrative USD per 1,000,000 tokens; 2025/2026 list prices) ----
# Documented as approximate in the README's "Cost model" section.
_PRICES = {
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-1.5-flash": (0.075, 0.30),
    "llama-3.3-70b": (0.59, 0.79),
    "llama-3.1-8b": (0.05, 0.08),
    "deterministic-template-v1": (0.0, 0.0),
}


def estimate_tokens(text: str) -> int:
    """~4 chars/token heuristic when a provider doesn't return usage."""
    return max(1, len(text or "") // 4)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    m = (model or "").lower()
    price = None
    for key, p in _PRICES.items():
        if key in m:
            price = p
            break
    if price is None:
        price = (0.0, 0.0)
    return round(input_tokens / 1_000_000 * price[0] + output_tokens / 1_000_000 * price[1], 6)


@dataclass
class RunMetrics:
    case_id: str
    spans: List[Dict[str, Any]] = field(default_factory=list)
    generations: List[Dict[str, Any]] = field(default_factory=list)
    _t0: float = field(default_factory=time.perf_counter)

    def add_span(self, name: str, latency_ms: float, **extra: Any) -> None:
        self.spans.append({"name": name, "latency_ms": round(latency_ms, 1), **extra})

    def add_generation(self, **gen: Any) -> None:
        self.generations.append(gen)

    def summary(self) -> Dict[str, Any]:
        total_in = sum(g.get("input_tokens", 0) for g in self.generations)
        total_out = sum(g.get("output_tokens", 0) for g in self.generations)
        total_cost = round(sum(g.get("cost_usd", 0.0) for g in self.generations), 6)
        return {
            "total_latency_ms": round((time.perf_counter() - self._t0) * 1000, 1),
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_tokens": total_in + total_out,
            "total_cost_usd": total_cost,
            "llm_calls": len(self.generations),
            "providers": sorted({g.get("provider", "?") for g in self.generations}),
            "spans": self.spans,
            "generations": self.generations,
        }


@dataclass
class RunContext:
    metrics: RunMetrics
    trace: Any = None  # Langfuse trace handle or None


_current: ContextVar[Optional[RunContext]] = ContextVar("current_run", default=None)


def _langfuse_client():
    if not (settings.langfuse_public_key and settings.langfuse_secret_key):
        return None
    try:
        from langfuse import Langfuse

        return Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
        )
    except Exception:  # noqa: BLE001 - tracing must never break the pipeline
        return None


def start_run(case_id: str) -> RunContext:
    metrics = RunMetrics(case_id=case_id)
    trace = None
    client = _langfuse_client()
    if client is not None:
        try:
            trace = client.trace(name="investigation", metadata={"case_id": case_id})
        except Exception:  # noqa: BLE001
            trace = None
    ctx = RunContext(metrics=metrics, trace=trace)
    _current.set(ctx)
    return ctx


def current() -> Optional[RunContext]:
    return _current.get()


@contextmanager
def span(name: str, **metadata: Any):
    """Time a named step; record it locally and (optionally) to Langfuse."""
    ctx = _current.get()
    lf_span = None
    if ctx and ctx.trace is not None:
        try:
            lf_span = ctx.trace.span(name=name, metadata=metadata)
        except Exception:  # noqa: BLE001
            lf_span = None
    t0 = time.perf_counter()
    try:
        yield
    finally:
        ms = (time.perf_counter() - t0) * 1000
        if ctx:
            ctx.metrics.add_span(name, ms, **metadata)
        if lf_span is not None:
            try:
                lf_span.end()
            except Exception:  # noqa: BLE001
                pass


def record_generation(
    *,
    name: str,
    provider: str,
    model: str,
    input_text: str,
    output_text: str,
    latency_ms: float,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    task: Optional[str] = None,
) -> Dict[str, Any]:
    """Record one LLM call's usage + cost, locally and (optionally) to Langfuse."""
    in_tok = input_tokens if input_tokens is not None else estimate_tokens(input_text)
    out_tok = output_tokens if output_tokens is not None else estimate_tokens(output_text)
    cost = cost_usd(model, in_tok, out_tok)
    gen = {
        "name": name, "provider": provider, "model": model, "task": task,
        "input_tokens": in_tok, "output_tokens": out_tok,
        "cost_usd": cost, "latency_ms": round(latency_ms, 1),
    }
    ctx = _current.get()
    if ctx:
        ctx.metrics.add_generation(**gen)
        if ctx.trace is not None:
            try:
                g = ctx.trace.generation(
                    name=name, model=model,
                    usage={"input": in_tok, "output": out_tok},
                    metadata={"provider": provider, "task": task, "cost_usd": cost},
                )
                g.end(output=output_text[:2000])
            except Exception:  # noqa: BLE001
                pass
    return gen


def finish_run() -> Dict[str, Any]:
    ctx = _current.get()
    if ctx is None:
        return {}
    summary = ctx.metrics.summary()
    client = _langfuse_client()
    if client is not None:
        try:
            client.flush()
        except Exception:  # noqa: BLE001
            pass
    _current.set(None)
    return summary


def observability_status() -> Dict[str, Any]:
    return {
        "langfuse_enabled": bool(settings.langfuse_public_key and settings.langfuse_secret_key),
        "langfuse_host": settings.langfuse_host if settings.langfuse_public_key else None,
        "local_metrics": True,
    }
