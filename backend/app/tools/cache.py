"""
Caching abstraction.

In-process TTL cache by default (zero-dependency, $0); switches to **Redis** when
`REDIS_URL` is set (e.g. a free Upstash instance) for a shared cache across
instances. Cache hits/misses are exported to Prometheus.
"""
from __future__ import annotations

import json
import threading
import time
from typing import Any, Optional

from app.config import settings
from app.tools import metrics


class _MemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            item = self._store.get(key)
            if not item:
                return None
            expiry, value = item
            if expiry < time.time():
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, ttl: int) -> None:
        with self._lock:
            self._store[key] = (time.time() + ttl, value)

    def incr(self, key: str, ttl: int) -> int:
        """Atomic increment within a window; sets the TTL on first touch."""
        with self._lock:
            item = self._store.get(key)
            now = time.time()
            if not item or item[0] < now:
                self._store[key] = (now + ttl, 1)
                return 1
            expiry, value = item
            self._store[key] = (expiry, value + 1)
            return value + 1

    def ttl(self, key: str) -> int:
        with self._lock:
            item = self._store.get(key)
            return max(0, int(item[0] - time.time())) if item else 0

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class _RedisCache:
    def __init__(self, url: str) -> None:
        import redis  # lazy — only when REDIS_URL is set

        self._r = redis.from_url(url, decode_responses=True)

    def get(self, key: str) -> Optional[Any]:
        raw = self._r.get(key)
        return json.loads(raw) if raw else None

    def set(self, key: str, value: Any, ttl: int) -> None:
        self._r.set(key, json.dumps(value, default=str), ex=ttl)

    def incr(self, key: str, ttl: int) -> int:
        # Atomic across all instances — this is what makes rate-limit/throttle
        # correct when the backend is horizontally scaled.
        n = self._r.incr(key)
        if n == 1:
            self._r.expire(key, ttl)
        return int(n)

    def ttl(self, key: str) -> int:
        return max(0, int(self._r.ttl(key) or 0))

    def delete(self, key: str) -> None:
        self._r.delete(key)

    def clear(self) -> None:
        self._r.flushdb()


def _make_backend():
    if settings.redis_url:
        try:
            return _RedisCache(settings.redis_url), "redis"
        except Exception:  # noqa: BLE001 - fall back to memory on any redis issue
            pass
    return _MemoryCache(), "memory"


_backend, BACKEND_NAME = _make_backend()


def get(key: str) -> Optional[Any]:
    val = _backend.get(key)
    metrics.CACHE_OPS.labels(op="hit" if val is not None else "miss").inc()
    return val


def set(key: str, value: Any, ttl: Optional[int] = None) -> None:  # noqa: A001
    metrics.CACHE_OPS.labels(op="set").inc()
    _backend.set(key, value, settings.cache_ttl_seconds if ttl is None else ttl)


def incr(key: str, ttl: int) -> int:
    """Shared fixed-window counter (atomic on Redis) — for rate limiting / throttling
    that stays correct across horizontally-scaled instances."""
    return _backend.incr(key, ttl)


def ttl(key: str) -> int:
    return _backend.ttl(key)


def delete(key: str) -> None:
    _backend.delete(key)


def clear() -> None:
    _backend.clear()


def info() -> dict:
    # `distributed` = state is shared across instances → safe to horizontally scale.
    return {"cache_backend": BACKEND_NAME, "distributed": BACKEND_NAME == "redis"}
