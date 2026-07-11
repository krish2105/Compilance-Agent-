"""
Streaming investigation endpoint (Server-Sent Events).

Runs the LangGraph orchestrator for a case and streams one SSE event per agent
step so the frontend can render the reasoning trace live, followed by a terminal
`result` event carrying the full draft (narrative, citations, typology match,
verification status). The multi-agent pipeline is synchronous, so it runs in a
worker thread and events are bridged to the async response via a queue — keeping
the event loop responsive.
"""
from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Dict

from fastapi import APIRouter, HTTPException
from sse_starlette.sse import EventSourceResponse

from app.agents import orchestrator
from app.api import store
from app.tools import db

router = APIRouter(prefix="/api/cases", tags=["stream"])

_SENTINEL = object()


def _run_pipeline_to_queue(case_id: str, queue: "asyncio.Queue", loop: asyncio.AbstractEventLoop) -> None:
    """Worker thread: drive the sync generator, push events onto the async queue."""
    def push(item):
        loop.call_soon_threadsafe(queue.put_nowait, item)

    try:
        gen = orchestrator.run_case_events(case_id)
        final_state: Dict[str, Any] = {}
        while True:
            try:
                event = next(gen)
            except StopIteration as stop:
                final_state = stop.value or {}
                break
            push({"event": "agent_step", "data": event})

        result = orchestrator.assemble_result(case_id, final_state)
        store.put_result(case_id, result)
        push({"event": "result", "data": result})
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the client
        push({"event": "error",
              "data": {"message": "Investigation failed.", "detail": str(exc)}})
    finally:
        push(_SENTINEL)


@router.get("/{case_id}/stream")
async def stream_investigation(case_id: str):
    """Stream the investigation for `case_id` as SSE."""
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    threading.Thread(
        target=_run_pipeline_to_queue, args=(case_id, queue, loop), daemon=True
    ).start()

    async def event_generator():
        # Opening event so the client can render the pipeline shell immediately.
        yield {"event": "start",
               "data": json.dumps({"case_id": case_id, "status": "running"})}
        while True:
            item = await queue.get()
            if item is _SENTINEL:
                break
            yield {"event": item["event"], "data": json.dumps(item["data"], default=str)}
        yield {"event": "end", "data": json.dumps({"case_id": case_id})}

    return EventSourceResponse(event_generator())
