"""
Case endpoints: listing, detail, non-streaming investigation, the audit trail,
and the mandatory human approval gate (approve / edit / reject).

The approval gate is BACKEND-ENFORCED: a case cannot reach a finalized state
except through a persisted human decision recorded here. There is no code path
that auto-approves, auto-clears, or auto-files a case.
"""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import auth
from app.agents import chat_agent, orchestrator
from app.api import store
from app.tools import audit, db, guardrails, jobs, memory, sar

router = APIRouter(prefix="/api/cases", tags=["cases"])


class ReviewRequest(BaseModel):
    decision: str = Field(..., description="APPROVED | REJECTED | EDITED | ESCALATED")
    reviewer: str = Field(..., min_length=1, description="Analyst identifier")
    notes: Optional[str] = Field(default=None)
    edited_narrative: Optional[str] = Field(
        default=None, description="Required when decision == EDITED"
    )


_VALID_DECISIONS = {"APPROVED", "REJECTED", "EDITED", "ESCALATED"}


@router.get("")
def list_cases() -> List[dict]:
    """All investigation cases with their current review status."""
    cases = db.list_cases()
    for c in cases:
        review = audit.get_latest_review(c["case_id"])
        c["review_status"] = review["status"] if review else "PENDING_REVIEW"
        c["reviewed_by"] = review["reviewer"] if review else None
    return cases


@router.get("/{case_id}")
def get_case_detail(case_id: str) -> dict:
    """Full case detail. Runs (or reuses a cached) investigation and attaches the
    current human-review state. Does NOT finalize anything."""
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    result = store.get_result(case_id)
    if result is None:
        result = orchestrator.run_case(case_id)
        store.put_result(case_id, result)

    review = audit.get_latest_review(case_id)
    return {
        "case": case,
        "result": result,
        "review": review,
        "review_history": audit.get_review_history(case_id),
    }


@router.post("/{case_id}/investigate")
def investigate(case_id: str) -> dict:
    """Run the multi-agent pipeline for a case (non-streaming) and cache it."""
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    result = orchestrator.run_case(case_id)
    store.put_result(case_id, result)
    return result


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    history: list = Field(default_factory=list)


@router.post("/{case_id}/chat")
def chat(case_id: str, req: ChatRequest,
         _: auth.Principal = Depends(auth.get_current_principal)) -> dict:
    """Conversational Q&A over a case (planner + tool use + case memory)."""
    result, _case = _result_and_case(case_id)
    return chat_agent.answer(result, case_id, req.question, req.history)


@router.get("/{case_id}/similar")
def similar(case_id: str) -> dict:
    """Case memory: the most similar prior cases + their dispositions."""
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    return {"case_id": case_id, "similar_cases": memory.similar_cases(case_id, k=5)}


def _run_and_cache(case_id: str) -> dict:
    result = orchestrator.run_case(case_id)
    store.put_result(case_id, result)
    return result


@router.post("/{case_id}/investigate/async")
def investigate_async(case_id: str) -> dict:
    """Submit the investigation as a background job (non-blocking) → returns a job id
    to poll at GET /api/jobs/{job_id}."""
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    job_id = jobs.jobs.submit("investigate", _run_and_cache, case_id)
    return {"job_id": job_id, "status_url": f"/api/jobs/{job_id}"}


@router.get("/{case_id}/audit")
def get_audit(case_id: str) -> dict:
    """The persisted audit trail: every agent step + every human action."""
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    return {
        "case_id": case_id,
        "events": audit.get_audit_trail(case_id),
        "reviews": audit.get_review_history(case_id),
    }


def _result_and_case(case_id: str):
    case = db.get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")
    result = store.get_result(case_id)
    if result is None:
        result = orchestrator.run_case(case_id)
        store.put_result(case_id, result)
    return result, case


@router.get("/{case_id}/sar")
def get_sar(case_id: str) -> dict:
    """Structured STR/SAR record (coded activity + subject + indicators + narrative)
    plus the filing SLA. Draft for the MLRO — not filed."""
    result, case = _result_and_case(case_id)
    review = audit.get_latest_review(case_id)
    edited = review.get("edited_narrative") if review else None
    return sar.build_all(result, case, review, narrative_override=edited)


@router.get("/{case_id}/sar.xml")
def get_sar_xml(case_id: str):
    """Download the STR as goAML-schema XML (the UAE FIU / UNODC filing format)."""
    result, case = _result_and_case(case_id)
    review = audit.get_latest_review(case_id)
    edited = review.get("edited_narrative") if review else None
    record = sar.build_sar_record(result, case, narrative_override=edited)
    xml = sar.goaml_xml(record)
    audit.log_event(case_id, "system", "SAR_XML_EXPORTED", actor_type="system",
                    summary="goAML STR XML exported (draft).")
    return Response(
        content=xml, media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="STR_{case_id}_goAML.xml"'},
    )


@router.post("/{case_id}/review")
def submit_review(case_id: str, req: ReviewRequest,
                  principal: auth.Principal = Depends(auth.get_current_principal)) -> dict:
    """The enforced human approval gate. RBAC: any authenticated analyst may EDIT a
    draft, but only an MLRO/admin may APPROVE / REJECT / ESCALATE (finalize)."""
    if db.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found.")

    decision = req.decision.upper()
    if decision not in _VALID_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"decision must be one of {sorted(_VALID_DECISIONS)}",
        )
    # Finalizing decisions are restricted to MLRO/admin.
    if decision in ("APPROVED", "REJECTED", "ESCALATED") and principal.role == "analyst":
        raise HTTPException(
            status_code=403,
            detail="Analysts may edit the draft; approving/rejecting/escalating "
                   "requires the MLRO role.",
        )
    if decision == "EDITED" and not (req.edited_narrative and req.edited_narrative.strip()):
        raise HTTPException(
            status_code=422,
            detail="edited_narrative is required when decision == EDITED.",
        )
    # Guardrails on human-supplied free text (OWASP LLM01/LLM05).
    if not guardrails.validate_reviewer(req.reviewer):
        raise HTTPException(status_code=422, detail="Invalid reviewer name.")
    for field, value in (("notes", req.notes), ("edited_narrative", req.edited_narrative)):
        if value and guardrails.detect_prompt_injection(value):
            raise HTTPException(
                status_code=422,
                detail=f"Potential prompt-injection detected in '{field}'; rejected.",
            )

    # Record the AUTHENTICATED reviewer (not a client-supplied name) for integrity.
    reviewer = f"{principal.username} ({principal.role})"
    review = audit.record_review(
        case_id, decision, reviewer,
        notes=req.notes, edited_narrative=req.edited_narrative,
    )
    memory.invalidate()  # refresh precedent dispositions in case memory
    return {"ok": True, "review": review}
