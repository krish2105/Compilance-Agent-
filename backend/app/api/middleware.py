"""
Backend middleware: API-key auth + simple in-memory rate limiting.

Auth: every route except a small allow-list (health, docs, openapi, CORS
preflight) requires a matching `X-API-Key` header. This is a lightweight,
portfolio-appropriate shared-secret gate — not a full IAM system.

Rate limiting: a per-key sliding window on the case-processing routes to protect
the free-tier LLM quota and the demo backend from runaway loops.
"""
from __future__ import annotations

import re
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings
from app.tools import metrics

# Paths that never require auth (health/readiness probes, login, self-serve signup).
_PUBLIC_PREFIXES = ("/api/health", "/api/ready", "/api/auth/login", "/api/auth/register-org",
                    "/metrics", "/docs", "/openapi.json", "/redoc", "/favicon")

_ID_RE = re.compile(r"/(CASE-\d+|AML-\d+|job_\d+)")


def _norm_path(path: str) -> str:
    """Collapse resource ids so Prometheus label cardinality stays bounded."""
    return _ID_RE.sub("/{id}", path)

# Paths that are rate limited (the expensive case-processing endpoints).
_LIMITED_SUBSTRINGS = ("/investigate", "/stream")


def _client_id(request: Request) -> str:
    key = request.headers.get("x-api-key", "")
    ip = request.client.host if request.client else "unknown"
    return f"{key or 'anon'}:{ip}"


class AuthAndRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow CORS preflight, the root info page, and public paths.
        if request.method == "OPTIONS" or path == "/" or path.startswith(_PUBLIC_PREFIXES):
            return await self._timed(request, call_next)

        # --- Auth (coarse gate) ---
        # Accept EITHER a Bearer JWT (real user; validated per-route by the RBAC
        # dependency) OR the legacy X-API-Key. Fine-grained role checks happen in
        # the route dependencies (require_role).
        has_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
        has_key = request.headers.get("x-api-key", "") == settings.backend_api_key
        if not (has_bearer or has_key):
            return JSONResponse(
                status_code=401,
                content={"error": "unauthorized",
                         "message": "Missing credentials — log in or send X-API-Key."},
            )

        # --- Rate limit (only the expensive routes) ---
        # Shared fixed-window counter via the cache layer — correct across
        # horizontally-scaled instances when Redis is attached (in-process otherwise).
        if any(s in path for s in _LIMITED_SUBSTRINGS):
            from app.tools import cache

            win = settings.rate_limit_window_seconds
            rl_key = f"rl:{_client_id(request)}:{int(time.time()) // win}"
            count = cache.incr(rl_key, win)
            if count > settings.rate_limit_requests:
                retry_after = cache.ttl(rl_key) or win
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={"error": "rate_limited",
                             "message": f"Rate limit exceeded "
                                        f"({settings.rate_limit_requests} requests / "
                                        f"{win}s). Retry in ~{retry_after}s."},
                )

        return await self._timed(request, call_next)

    async def _timed(self, request: Request, call_next):
        """Run the request, add security headers, and record HTTP metrics."""
        t0 = time.perf_counter()
        norm = _norm_path(request.url.path)
        try:
            response = await call_next(request)
            status = response.status_code
        except Exception:
            metrics.HTTP_REQUESTS.labels(request.method, norm, "500").inc()
            raise
        finally:
            metrics.HTTP_LATENCY.labels(norm).observe(time.perf_counter() - t0)
        metrics.HTTP_REQUESTS.labels(request.method, norm, str(status)).inc()
        for k, v in _SECURITY_HEADERS.items():
            response.headers.setdefault(k, v)
        return response


# Applied to every response — baseline hardening (JSON API, so CSP is strict).
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}
