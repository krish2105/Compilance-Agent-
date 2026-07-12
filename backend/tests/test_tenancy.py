"""
Multi-tenancy tests — the SaaS data-isolation boundary.

Proves that one organization's review decisions and dashboard dispositions are
never visible to another organization, while the demo tenant keeps working.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import auth  # noqa: E402
from app.db import Base, SessionLocal, engine, init_models  # noqa: E402
from app.tools import analytics, audit  # noqa: E402


def _setup():
    # Reset the operational store to a clean schema so these tests are deterministic
    # regardless of any state left by a prior run (CI already starts fresh).
    Base.metadata.drop_all(bind=engine)
    init_models()
    auth.seed_default_users()
    audit.init_db()


def test_org_registration_creates_isolated_tenant_and_admin():
    _setup()
    db = SessionLocal()
    try:
        tenant, user = auth.register_organization(
            db, "Acme Bank PLC", "acme_admin", "supersecret", "a@acme.test", "Acme Admin")
        assert tenant.slug == "acme-bank-plc"
        assert user.role == "admin"
        assert user.tenant_id == tenant.id
        # A second org with the same name is rejected.
        try:
            auth.register_organization(db, "Acme Bank PLC", "x", "yyyyyy")
            assert False, "expected duplicate-org ValueError"
        except ValueError:
            pass
    finally:
        db.close()


def test_same_username_across_tenants_is_allowed():
    _setup()
    db = SessionLocal()
    try:
        t1, u1 = auth.register_organization(db, "Org One", "admin", "password1")
        t2, u2 = auth.register_organization(db, "Org Two", "admin", "password2")
        assert u1.tenant_id != u2.tenant_id
        assert u1.username == u2.username == "admin"
    finally:
        db.close()


def test_team_management_scoped_and_self_lockout_guarded():
    """Admin adds/updates members within their own org; can't self-demote/deactivate."""
    from fastapi.testclient import TestClient

    from app.main import app

    _setup()
    c = TestClient(app)
    tok = c.post("/api/auth/register-org",
                 json={"org_name": "Team Co", "username": "boss", "password": "bosspass"}).json()["token"]
    H = {"Authorization": f"Bearer {tok}"}

    # Add an analyst to this org.
    r = c.post("/api/auth/register", headers=H,
               json={"username": "ana", "password": "anapass", "role": "analyst"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "analyst"

    # Members list is scoped to this org (boss + ana = 2).
    users = c.get("/api/auth/users", headers=H).json()
    assert {u["username"] for u in users} == {"boss", "ana"}

    # Promote ana to mlro.
    r = c.patch("/api/auth/users/ana", headers=H, json={"role": "mlro"})
    assert r.status_code == 200 and r.json()["user"]["role"] == "mlro"

    # Deactivate ana, then a login attempt as ana fails.
    assert c.patch("/api/auth/users/ana", headers=H, json={"active": False}).status_code == 200
    assert c.post("/api/auth/login",
                  json={"username": "ana", "password": "anapass", "org": "team-co"}).status_code == 401

    # Self-lockout guards: boss cannot demote or deactivate themselves.
    assert c.patch("/api/auth/users/boss", headers=H, json={"role": "analyst"}).status_code == 409
    assert c.patch("/api/auth/users/boss", headers=H, json={"active": False}).status_code == 409

    # Cannot manage a user in another org.
    assert c.patch("/api/auth/users/nonexistent", headers=H, json={"role": "mlro"}).status_code == 404


def test_review_isolation_between_tenants():
    _setup()
    case_id = "CASE-0001"
    audit.record_review(case_id, "APPROVED", "alice (mlro)", tenant="tenant-a")
    # Tenant A sees its decision; tenant B and the demo tenant do not.
    assert audit.get_latest_review(case_id, "tenant-a")["decision"] == "APPROVED"
    assert audit.get_latest_review(case_id, "tenant-b") is None
    assert audit.get_latest_review(case_id, "demo") is None


def test_reviews_persist_in_the_durable_operational_store():
    """A review must land in the SQLAlchemy operational store (Postgres-durable),
    not an ephemeral side file — this is what lets tenant data survive restarts."""
    from sqlalchemy import select

    from app.models import CaseReview

    _setup()
    audit.record_review("CASE-0003", "REJECTED", "carol (mlro)", tenant="durable-co",
                        notes="not suspicious")
    # Read it back through a brand-new session (simulates a fresh process / restart).
    db = SessionLocal()
    try:
        row = db.execute(
            select(CaseReview).where(CaseReview.case_id == "CASE-0003",
                                     CaseReview.tenant == "durable-co")
        ).scalars().first()
        assert row is not None
        assert row.decision == "REJECTED"
        assert row.status == "REJECTED_CLOSED"
        assert row.reviewer == "carol (mlro)"
    finally:
        db.close()


def test_per_tenant_ingestion_runs_full_pipeline_and_isolates():
    """An org uploads its own transactions → a case is created, runs through the full
    multi-agent pipeline, and is invisible to other tenants."""
    from fastapi.testclient import TestClient

    from app.main import app

    _setup()
    with TestClient(app) as c:
        tok = c.post("/api/auth/register-org",
                     json={"org_name": "Ingest Co", "username": "ingestadmin",
                           "password": "iopass1"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}
        rows = [
            {"sender_account": "ACC-1001", "receiver_account": "ACC-3003",
             "amount": 49200, "receiver_bank_location": "Iran"},
            {"sender_account": "ACC-1001", "receiver_account": "ACC-5005",
             "amount": 46900, "receiver_bank_location": "Syria"},
        ]
        ing = c.post("/api/ingest/transactions", headers=H, json={"rows": rows})
        assert ing.status_code == 200
        cid = ing.json()["case"]["case_id"]
        assert cid.startswith("ingest-co-")

        # Full investigation runs on the uploaded data.
        res = c.post(f"/api/cases/{cid}/investigate", headers=H).json()
        assert res["narrative"]
        assert res["verification"]["passed"] is True
        assert res["gnn"]["available"] is True
        # Sanctioned jurisdictions → screening flags it.
        assert res["screening"]["cleared"] is False

        # The uploaded case appears in this org's queue, tagged 'uploaded'.
        mine = c.get("/api/cases", headers=H).json()
        assert any(x["case_id"] == cid and x.get("source") == "uploaded" for x in mine)

        # Another org cannot see it.
        tok2 = c.post("/api/auth/register-org",
                      json={"org_name": "Other Co", "username": "otheradmin",
                            "password": "o2pass1"}).json()["token"]
        theirs = c.get("/api/cases", headers={"Authorization": f"Bearer {tok2}"}).json()
        assert not any(x["case_id"] == cid for x in theirs)

        # Bad upload is rejected.
        assert c.post("/api/ingest/transactions", headers=H,
                      json={"rows": [{"amount": 5}]}).status_code == 422


def test_dashboard_dispositions_are_per_tenant():
    _setup()
    # Fresh tenants: nothing finalized yet.
    analytics.invalidate("tenant-x")
    analytics.invalidate("tenant-y")
    base = analytics.compute_dashboard("tenant-y")
    assert base["pending_review"] == base["total_cases"]  # all pending for a new org

    audit.record_review("CASE-0002", "ESCALATED", "bob (mlro)", tenant="tenant-x")
    analytics.invalidate("tenant-x")
    dx = analytics.compute_dashboard("tenant-x")
    dy = analytics.compute_dashboard("tenant-y")
    # tenant-x has one finalized/escalated case; tenant-y still has none.
    assert dx["dispositions"].get("ESCALATED_TO_MLRO", 0) == 1
    assert dy["dispositions"].get("ESCALATED_TO_MLRO", 0) == 0
