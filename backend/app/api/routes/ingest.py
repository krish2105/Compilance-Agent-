"""
Per-tenant transaction ingestion — "bring your own data".

An org admin uploads a batch of transactions (CSV or JSON); we derive a case,
persist it durably, and it immediately flows through the full multi-agent
investigation pipeline like any other case — scoped to that tenant.
"""
from __future__ import annotations

import csv
import io
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app import auth
from app.tools import guardrails, tenant_data

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

_TEMPLATE = (
    "transaction_id,timestamp,sender_account,receiver_account,amount,"
    "payment_currency,payment_type,sender_bank_location,receiver_bank_location\n"
    "TX0001,2026-03-01T09:15:00,ACC-1001,ACC-2002,48500,AED,Wire,UAE,UAE\n"
    "TX0002,2026-03-01T09:40:00,ACC-1001,ACC-3003,49200,AED,Wire,UAE,Iran\n"
    "TX0003,2026-03-02T11:05:00,ACC-1001,ACC-4004,47800,AED,Cash Deposit,UAE,UAE\n"
)


class IngestJson(BaseModel):
    rows: List[dict] = Field(..., description="Transaction rows (lenient column names).")
    summary: Optional[str] = Field(default=None, max_length=280)


@router.get("/template", response_class=PlainTextResponse)
def template() -> str:
    """A starter CSV showing the accepted columns."""
    return _TEMPLATE


def _finalize(tenant: str, rows: List[dict], summary: Optional[str]) -> dict:
    if summary and guardrails.detect_prompt_injection(summary):
        raise HTTPException(status_code=422, detail="Potential injection in summary; rejected.")
    try:
        case = tenant_data.ingest_case(tenant, rows, summary=summary)
    except tenant_data.IngestError as e:
        raise HTTPException(status_code=422, detail=str(e))
    # Refresh this tenant's dashboard so the new case is reflected.
    from app.tools import analytics
    analytics.invalidate(tenant)
    return {"ok": True, "case": case}


@router.post("/transactions")
def ingest_json(req: IngestJson,
                principal: auth.Principal = Depends(auth.require_role("analyst"))) -> dict:
    """Ingest transactions as JSON rows (any authenticated org member)."""
    return _finalize(principal.tenant, req.rows, req.summary)


@router.post("/csv")
async def ingest_csv(file: UploadFile,
                     principal: auth.Principal = Depends(auth.require_role("analyst"))) -> dict:
    """Ingest a CSV file upload."""
    raw = (await file.read()).decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(raw))
    rows = [dict(r) for r in reader]
    if not rows:
        raise HTTPException(status_code=422, detail="CSV had no data rows.")
    return _finalize(principal.tenant, rows, None)
