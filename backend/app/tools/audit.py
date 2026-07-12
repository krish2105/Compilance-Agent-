"""
Structured, persistent audit log — durable operational store (SQLAlchemy).

Every agent decision, every piece of evidence used, and every human action is
written here with a timestamp. In a regulated AML/KYC context the audit trail is
the single most important production feature: it makes the copilot's reasoning
and the human's sign-off fully reconstructable after the fact.

Storage: the shared SQLAlchemy operational store — **Postgres** when `DATABASE_URL`
is set (so the trail + decisions survive restarts), with a **SQLite** fallback for
local/$0 runs. Two tables (see `app/models.py`):
  * `audit_events` — append-only event stream (agent steps + human actions).
  * `case_reviews`  — the current review state / human decision per case, per tenant.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select

from app.db import SessionLocal, init_models
from app.models import AuditEvent, CaseReview


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def init_db() -> None:
    """Ensure the operational tables exist. Safe to call at every startup."""
    init_models()


def _event_to_dict(e: AuditEvent) -> Dict[str, Any]:
    try:
        detail = json.loads(e.detail_json or "{}")
    except json.JSONDecodeError:
        detail = {}
    return {
        "id": e.id, "case_id": e.case_id, "tenant": e.tenant, "ts": e.ts,
        "actor": e.actor, "actor_type": e.actor_type, "action": e.action,
        "summary": e.summary, "detail": detail, "llm_provider": e.llm_provider,
    }


def _review_to_dict(r: CaseReview) -> Dict[str, Any]:
    return {
        "id": r.id, "case_id": r.case_id, "tenant": r.tenant, "ts": r.ts,
        "decision": r.decision, "reviewer": r.reviewer, "notes": r.notes,
        "edited_narrative": r.edited_narrative, "status": r.status,
    }


def log_event(
    case_id: str,
    actor: str,
    action: str,
    *,
    actor_type: str = "agent",
    tenant: str = "demo",
    summary: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    llm_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one audit event and return it (with its assigned id/ts)."""
    ts = _now()
    ev = AuditEvent(
        case_id=case_id, tenant=tenant, ts=ts, actor=actor, actor_type=actor_type,
        action=action, summary=summary, detail_json=json.dumps(detail or {}, default=str),
        llm_provider=llm_provider,
    )
    db = SessionLocal()
    try:
        db.add(ev)
        db.commit()
        event_id = ev.id
    finally:
        db.close()
    return {
        "id": event_id, "case_id": case_id, "tenant": tenant, "ts": ts, "actor": actor,
        "actor_type": actor_type, "action": action, "summary": summary,
        "detail": detail or {}, "llm_provider": llm_provider,
    }


def get_audit_trail(case_id: str) -> List[Dict[str, Any]]:
    """All events for a case (the shared reasoning trail), oldest first."""
    db = SessionLocal()
    try:
        rows = db.execute(
            select(AuditEvent).where(AuditEvent.case_id == case_id).order_by(AuditEvent.id)
        ).scalars().all()
        return [_event_to_dict(e) for e in rows]
    finally:
        db.close()


def record_review(
    case_id: str,
    decision: str,
    reviewer: str,
    *,
    tenant: str = "demo",
    notes: Optional[str] = None,
    edited_narrative: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist a human review decision (the enforced approval gate), scoped to a tenant."""
    status_map = {
        "APPROVED": "APPROVED_FOR_FILING_REVIEW",
        "REJECTED": "REJECTED_CLOSED",
        "EDITED": "EDITED_PENDING_APPROVAL",
        "ESCALATED": "ESCALATED_TO_MLRO",
    }
    status = status_map.get(decision.upper(), "PENDING_REVIEW")
    ts = _now()
    rv = CaseReview(
        case_id=case_id, tenant=tenant, ts=ts, decision=decision.upper(),
        reviewer=reviewer, notes=notes, edited_narrative=edited_narrative, status=status,
    )
    db = SessionLocal()
    try:
        db.add(rv)
        db.commit()
    finally:
        db.close()
    # Mirror the human action into the main audit stream.
    log_event(
        case_id, f"human:{reviewer}", f"REVIEW_{decision.upper()}",
        actor_type="human", tenant=tenant,
        summary=notes or f"Analyst {decision.lower()} the draft case.",
        detail={"decision": decision.upper(), "status": status, "tenant": tenant,
                "has_edit": edited_narrative is not None},
    )
    return {"case_id": case_id, "ts": ts, "decision": decision.upper(),
            "reviewer": reviewer, "status": status, "notes": notes}


def get_latest_review(case_id: str, tenant: str = "demo") -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        row = db.execute(
            select(CaseReview)
            .where(CaseReview.case_id == case_id, CaseReview.tenant == tenant)
            .order_by(CaseReview.id.desc())
            .limit(1)
        ).scalars().first()
        return _review_to_dict(row) if row else None
    finally:
        db.close()


def get_review_history(case_id: str, tenant: str = "demo") -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(CaseReview)
            .where(CaseReview.case_id == case_id, CaseReview.tenant == tenant)
            .order_by(CaseReview.id)
        ).scalars().all()
        return [_review_to_dict(r) for r in rows]
    finally:
        db.close()
