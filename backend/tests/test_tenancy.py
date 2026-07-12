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
from app.db import SessionLocal, init_models  # noqa: E402
from app.tools import analytics, audit  # noqa: E402


def _setup():
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


def test_review_isolation_between_tenants():
    _setup()
    case_id = "CASE-0001"
    audit.record_review(case_id, "APPROVED", "alice (mlro)", tenant="tenant-a")
    # Tenant A sees its decision; tenant B and the demo tenant do not.
    assert audit.get_latest_review(case_id, "tenant-a")["decision"] == "APPROVED"
    assert audit.get_latest_review(case_id, "tenant-b") is None
    assert audit.get_latest_review(case_id, "demo") is None


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
