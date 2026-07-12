"""
Structured, persistent audit log (SQLite).

Every agent decision, every piece of evidence used, and every human action is
written here with a timestamp. In a regulated AML/KYC context the audit trail is
the single most important production feature: it makes the copilot's reasoning
and the human's sign-off fully reconstructable after the fact.

Two tables:
  * `audit_events` — append-only event stream (agent steps + human actions).
  * `case_reviews`  — the current review state / human decision per case
                      (approve / edit / reject), also append-only via versioning.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.config import settings

_lock = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(settings.audit_db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    return con


def init_db() -> None:
    """Create tables if they don't exist. Safe to call at every startup."""
    with _lock, _connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id     TEXT NOT NULL,
                ts          TEXT NOT NULL,
                actor       TEXT NOT NULL,      -- agent name or 'human:<reviewer>'
                actor_type  TEXT NOT NULL,      -- 'agent' | 'human' | 'system'
                action      TEXT NOT NULL,
                summary     TEXT,
                detail_json TEXT,               -- JSON payload (evidence, results)
                llm_provider TEXT               -- provider used, if any
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS case_reviews (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id       TEXT NOT NULL,
                tenant        TEXT NOT NULL DEFAULT 'demo',  -- data-isolation boundary
                ts            TEXT NOT NULL,
                decision      TEXT NOT NULL,     -- 'APPROVED' | 'REJECTED' | 'EDITED' | 'ESCALATED'
                reviewer      TEXT NOT NULL,
                notes         TEXT,
                edited_narrative TEXT,           -- present when decision == 'EDITED'
                status        TEXT NOT NULL       -- resulting case status
            )
            """
        )
        # Migration: add `tenant` to case_reviews created before multi-tenancy.
        cols = {r["name"] for r in con.execute("PRAGMA table_info(case_reviews)").fetchall()}
        if "tenant" not in cols:
            con.execute("ALTER TABLE case_reviews ADD COLUMN tenant TEXT NOT NULL DEFAULT 'demo'")
        con.execute("CREATE INDEX IF NOT EXISTS idx_audit_case ON audit_events(case_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_review_case ON case_reviews(case_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_review_tenant ON case_reviews(tenant, case_id)")


def log_event(
    case_id: str,
    actor: str,
    action: str,
    *,
    actor_type: str = "agent",
    summary: Optional[str] = None,
    detail: Optional[Dict[str, Any]] = None,
    llm_provider: Optional[str] = None,
) -> Dict[str, Any]:
    """Append one audit event and return it (with its assigned id/ts)."""
    ts = _now()
    with _lock, _connect() as con:
        cur = con.execute(
            """
            INSERT INTO audit_events
                (case_id, ts, actor, actor_type, action, summary, detail_json, llm_provider)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [case_id, ts, actor, actor_type, action, summary,
             json.dumps(detail or {}, default=str), llm_provider],
        )
        event_id = cur.lastrowid
    return {
        "id": event_id, "case_id": case_id, "ts": ts, "actor": actor,
        "actor_type": actor_type, "action": action, "summary": summary,
        "detail": detail or {}, "llm_provider": llm_provider,
    }


def get_audit_trail(case_id: str) -> List[Dict[str, Any]]:
    with _lock, _connect() as con:
        rows = con.execute(
            "SELECT * FROM audit_events WHERE case_id = ? ORDER BY id", [case_id]
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["detail"] = json.loads(d.pop("detail_json") or "{}")
        except json.JSONDecodeError:
            d["detail"] = {}
        out.append(d)
    return out


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
    with _lock, _connect() as con:
        con.execute(
            """
            INSERT INTO case_reviews
                (case_id, tenant, ts, decision, reviewer, notes, edited_narrative, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [case_id, tenant, ts, decision.upper(), reviewer, notes, edited_narrative, status],
        )
    # Mirror the human action into the main audit stream.
    log_event(
        case_id, f"human:{reviewer}", f"REVIEW_{decision.upper()}",
        actor_type="human",
        summary=notes or f"Analyst {decision.lower()} the draft case.",
        detail={"decision": decision.upper(), "status": status, "tenant": tenant,
                "has_edit": edited_narrative is not None},
    )
    return {"case_id": case_id, "ts": ts, "decision": decision.upper(),
            "reviewer": reviewer, "status": status, "notes": notes}


def get_latest_review(case_id: str, tenant: str = "demo") -> Optional[Dict[str, Any]]:
    with _lock, _connect() as con:
        row = con.execute(
            "SELECT * FROM case_reviews WHERE case_id = ? AND tenant = ? ORDER BY id DESC LIMIT 1",
            [case_id, tenant],
        ).fetchone()
    return dict(row) if row else None


def get_review_history(case_id: str, tenant: str = "demo") -> List[Dict[str, Any]]:
    with _lock, _connect() as con:
        rows = con.execute(
            "SELECT * FROM case_reviews WHERE case_id = ? AND tenant = ? ORDER BY id",
            [case_id, tenant],
        ).fetchall()
    return [dict(r) for r in rows]
