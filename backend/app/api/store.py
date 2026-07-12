"""
Investigation result cache.

Delegates to the pluggable cache layer (`tools.cache`) — an in-process TTL cache by
default, or Redis when `REDIS_URL` is set — so results are cached with a TTL, cache
hits/misses are exported to Prometheus, and the cache can be shared across instances.
Investigations are deterministic and cheap to recompute; the durable record of what
happened lives in the SQLite audit log.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.tools import cache


def _key(case_id: str) -> str:
    return f"result:{case_id}"


def put_result(case_id: str, result: Dict[str, Any]) -> None:
    cache.set(_key(case_id), result)


def get_result(case_id: str) -> Optional[Dict[str, Any]]:
    return cache.get(_key(case_id))
