"""
Backend middleware: API-key auth + simple in-memory rate limiting.

Auth: every route except a small allow-list (health, docs, openapi, CORS
preflight) requires a matching `X-API-Key` header. This is a lightweight,
portfolio-appropriate shared-secret gate — not a full IAM system.

Rate limiting: a per-key sliding window on the case-processing routes to protect
the free-tier LLM quota and the demo backend from runaway loops.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import settings

# Paths that never require auth.
_PUBLIC_PREFIXES = ("/api/health", "/api/auth/login", "/docs", "/openapi.json",
                    "/redoc", "/favicon")

# Paths that are rate limited (the expensive case-processing endpoints).
_LIMITED_SUBSTRINGS = ("/investigate", "/stream")

_windows: Dict[str, Deque[float]] = defaultdict(deque)


def _client_id(request: Request) -> str:
    key = request.headers.get("x-api-key", "")
    ip = request.client.host if request.client else "unknown"
    return f"{key or 'anon'}:{ip}"


class AuthAndRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Always allow CORS preflight, the root info page, and public paths.
        if request.method == "OPTIONS" or path == "/" or path.startswith(_PUBLIC_PREFIXES):
            return await call_next(request)

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
        if any(s in path for s in _LIMITED_SUBSTRINGS):
            now = time.time()
            window = _windows[_client_id(request)]
            cutoff = now - settings.rate_limit_window_seconds
            while window and window[0] < cutoff:
                window.popleft()
            if len(window) >= settings.rate_limit_requests:
                retry_after = int(window[0] + settings.rate_limit_window_seconds - now) + 1
                return JSONResponse(
                    status_code=429,
                    headers={"Retry-After": str(retry_after)},
                    content={"error": "rate_limited",
                             "message": f"Rate limit exceeded "
                                        f"({settings.rate_limit_requests} requests / "
                                        f"{settings.rate_limit_window_seconds}s). "
                                        f"Retry in ~{retry_after}s."},
                )
            window.append(now)

        return await call_next(request)
