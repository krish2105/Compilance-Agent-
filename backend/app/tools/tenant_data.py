"""
Per-tenant data ingestion (SaaS: "bring your own transactions").

An organization uploads its own transaction rows; we derive a case and persist it
in the durable operational store. Uploaded case ids are globally unique (tenant-slug
prefixed) so the existing `case_id`-routed agent pipeline — evidence, graph, GNN,
typology, screening, narrative, verification — serves them unchanged, with no tenant
plumbing through the agents.

Transactions from other tenants are never visible: `list_cases(tenant)` only returns
that tenant's uploads (merged with the shared demo book by the caller).
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import TenantCase, TenantTransaction

MAX_ROWS = 1000


class IngestError(ValueError):
    """Raised when an upload can't be parsed into a valid case."""


def _priority_for(max_amount: float) -> str:
    if max_amount >= 100_000:
        return "Critical"
    if max_amount >= 50_000:
        return "High"
    if max_amount >= 10_000:
        return "Medium"
    return "Low"


def _f(v: Any) -> Optional[float]:
    try:
        return float(str(v).replace(",", "").replace("AED", "").strip())
    except (TypeError, ValueError):
        return None


def _norm_row(raw: Dict[str, Any], idx: int, base: datetime) -> Dict[str, Any]:
    """Normalise one uploaded row into the internal transaction shape (lenient keys)."""
    def pick(*keys: str) -> Any:
        for k in keys:
            for rk in raw:
                if rk.strip().lower().replace(" ", "_") == k:
                    return raw[rk]
        return None

    sender = str(pick("sender_account", "sender", "from", "from_account") or "").strip()
    receiver = str(pick("receiver_account", "receiver", "to", "to_account") or "").strip()
    amount = _f(pick("amount", "value", "amount_aed"))
    if not sender or not receiver or amount is None:
        raise IngestError(
            f"Row {idx + 1}: 'sender_account', 'receiver_account' and a numeric 'amount' are required."
        )
    ts = pick("timestamp", "date", "datetime", "time")
    ts = str(ts).strip() if ts else (base + timedelta(minutes=idx)).strftime("%Y-%m-%dT%H:%M:%S")
    txid = str(pick("transaction_id", "txid", "id") or f"UTX{idx + 1:05d}").strip()
    return {
        "transaction_id": txid, "timestamp": ts, "sender_account": sender,
        "receiver_account": receiver, "amount": round(amount, 2),
        "payment_currency": str(pick("payment_currency", "currency") or "AED").strip()[:8],
        "payment_type": str(pick("payment_type", "type", "channel") or "Transfer").strip()[:32],
        "sender_bank_location": str(pick("sender_bank_location", "sender_country", "from_country") or "UAE").strip()[:48],
        "receiver_bank_location": str(pick("receiver_bank_location", "receiver_country", "to_country") or "UAE").strip()[:48],
    }


def ingest_case(tenant: str, rows: List[Dict[str, Any]], summary: Optional[str] = None) -> Dict[str, Any]:
    """Create one case from a batch of uploaded transaction rows. Returns the case dict."""
    if not rows:
        raise IngestError("No transaction rows provided.")
    if len(rows) > MAX_ROWS:
        raise IngestError(f"Too many rows ({len(rows)}); max {MAX_ROWS} per upload.")

    base = datetime.now(timezone.utc).replace(microsecond=0)
    norm = [_norm_row(r, i, base) for i, r in enumerate(rows)]

    # Subject = the account that sends most often (the one moving the money).
    subject = Counter(t["sender_account"] for t in norm).most_common(1)[0][0]
    focal = max(norm, key=lambda t: t["amount"])
    max_amt = focal["amount"]
    total = round(sum(t["amount"] for t in norm), 2)

    db = SessionLocal()
    try:
        n = db.execute(
            select(func.count(TenantCase.id)).where(TenantCase.tenant == tenant)
        ).scalar_one() or 0
        case_id = f"{tenant}-U{n + 1:03d}"
        created = base.strftime("%Y-%m-%dT%H:%M:%S")
        alert = summary or (
            f"Uploaded batch: {len(norm)} transactions, total {total:,.0f} "
            f"{norm[0]['payment_currency']}; largest {max_amt:,.0f} from {subject[-8:]}."
        )
        tc = TenantCase(
            case_id=case_id, tenant=tenant, created_at=created, subject_account=subject,
            focal_transaction_id=focal["transaction_id"], alert_summary=alert,
            priority=_priority_for(max_amt), status="OPEN",
        )
        db.add(tc)
        for t in norm:
            db.add(TenantTransaction(case_id=case_id, tenant=tenant, **t))
        db.commit()
        return tc.to_case_dict() | {"transaction_count": len(norm)}
    finally:
        db.close()


# -------- read side (called by app.tools.db fall-through) --------------------
def get_case(case_id: str) -> Optional[Dict[str, Any]]:
    db = SessionLocal()
    try:
        tc = db.execute(
            select(TenantCase).where(TenantCase.case_id == case_id)
        ).scalars().first()
        return tc.to_case_dict() if tc else None
    finally:
        db.close()


def get_case_transactions(case_id: str) -> List[Dict[str, Any]]:
    db = SessionLocal()
    try:
        rows = db.execute(
            select(TenantTransaction)
            .where(TenantTransaction.case_id == case_id)
            .order_by(TenantTransaction.timestamp)
        ).scalars().all()
        return [t.to_tx_dict() for t in rows]
    finally:
        db.close()


def list_cases(tenant: str) -> List[Dict[str, Any]]:
    """This tenant's uploaded cases (newest first), with transaction counts."""
    db = SessionLocal()
    try:
        cases = db.execute(
            select(TenantCase).where(TenantCase.tenant == tenant).order_by(TenantCase.id.desc())
        ).scalars().all()
        out = []
        for c in cases:
            cnt = db.execute(
                select(func.count(TenantTransaction.id)).where(TenantTransaction.case_id == c.case_id)
            ).scalar_one()
            out.append(c.to_case_dict() | {"transaction_count": cnt})
        return out
    finally:
        db.close()
