"""
In-memory cache of the most recent investigation result per case.

Investigations are deterministic and cheap to recompute, but caching the last
assembled result lets the approval-gate and case-detail endpoints reference the
exact narrative the analyst reviewed (including which LLM provider produced it)
without recomputation. This is process-local; the durable record of what happened
lives in the SQLite audit log.
"""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

_lock = threading.Lock()
_results: Dict[str, Dict[str, Any]] = {}


def put_result(case_id: str, result: Dict[str, Any]) -> None:
    with _lock:
        _results[case_id] = result


def get_result(case_id: str) -> Optional[Dict[str, Any]]:
    with _lock:
        return _results.get(case_id)
