"""
Subscription plans + usage limits (billing foundation).

Plans gate per-tenant capacity (team size, uploaded cases). Limits are enforced at
the point of creation (add-member, ingest). `None` means unlimited. Upgrading is a
stub here — wiring a real Stripe checkout only needs a payment webhook that sets
`Tenant.plan`; the enforcement below is already production-shaped.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Tenant, TenantCase, User

PLANS: Dict[str, Dict[str, Any]] = {
    "free": {"label": "Free", "price_usd": 0, "max_members": 3, "max_uploaded_cases": 5},
    "pro": {"label": "Pro", "price_usd": 99, "max_members": 25, "max_uploaded_cases": 200},
    "enterprise": {"label": "Enterprise", "price_usd": 499,
                   "max_members": None, "max_uploaded_cases": None},
}


class LimitError(Exception):
    """Raised when an action would exceed the tenant's plan limits."""


def plan_of(tenant_slug: str) -> str:
    db = SessionLocal()
    try:
        t = db.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalars().first()
        return (t.plan if t else "free")
    finally:
        db.close()


def _limits(plan: str) -> Dict[str, Any]:
    return PLANS.get(plan, PLANS["free"])


def usage(tenant_slug: str) -> Dict[str, Any]:
    """Current usage + plan limits for a tenant."""
    db = SessionLocal()
    try:
        t = db.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalars().first()
        plan = t.plan if t else "free"
        members = 0
        if t:
            members = db.execute(
                select(func.count(User.id)).where(User.tenant_id == t.id)
            ).scalar_one()
        uploaded = db.execute(
            select(func.count(TenantCase.id)).where(TenantCase.tenant == tenant_slug)
        ).scalar_one()
        lim = _limits(plan)
        return {
            "plan": plan,
            "limits": lim,
            "usage": {"members": members, "uploaded_cases": uploaded},
            "plans": PLANS,
        }
    finally:
        db.close()


def check_can_add_member(tenant_slug: str) -> None:
    u = usage(tenant_slug)
    cap = u["limits"]["max_members"]
    if cap is not None and u["usage"]["members"] >= cap:
        raise LimitError(
            f"Your {u['limits']['label']} plan allows {cap} members. Upgrade to add more.")


def check_can_upload(tenant_slug: str) -> None:
    u = usage(tenant_slug)
    cap = u["limits"]["max_uploaded_cases"]
    if cap is not None and u["usage"]["uploaded_cases"] >= cap:
        raise LimitError(
            f"Your {u['limits']['label']} plan allows {cap} uploaded cases. Upgrade for more.")


def set_plan(tenant_slug: str, plan: str) -> Optional[str]:
    """Change a tenant's plan (billing stub). Returns the new plan or None if invalid."""
    if plan not in PLANS:
        return None
    db = SessionLocal()
    try:
        t = db.execute(select(Tenant).where(Tenant.slug == tenant_slug)).scalars().first()
        if not t:
            return None
        t.plan = plan
        db.commit()
        return plan
    finally:
        db.close()
