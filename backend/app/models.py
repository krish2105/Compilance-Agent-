"""SQLAlchemy models for the operational store (users + case assignments)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Role hierarchy (higher index = more privilege).
ROLES = ["analyst", "mlro", "admin"]

# The bundled demo organization — every seeded demo user and the demo API key
# belong to it, so the public demo keeps working exactly as before.
DEMO_TENANT_SLUG = "demo"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tenant(Base):
    """An organization (customer). The unit of data isolation for SaaS multi-tenancy —
    users, reviews and dispositions are all scoped to a tenant."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_public(self) -> dict:
        return {"slug": self.slug, "name": self.name}


class User(Base):
    __tablename__ = "users"
    # Usernames are unique *within* a tenant, not globally — two orgs can each have
    # an "admin".
    __table_args__ = (UniqueConstraint("tenant_id", "username", name="uq_tenant_username"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), index=True, default=1)
    username: Mapped[str] = mapped_column(String(64), index=True)
    email: Mapped[str] = mapped_column(String(128), default="")
    full_name: Mapped[str] = mapped_column(String(128), default="")
    hashed_password: Mapped[str] = mapped_column(String(256))
    role: Mapped[str] = mapped_column(String(16), default="analyst")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    def to_public(self) -> dict:
        return {"username": self.username, "email": self.email,
                "full_name": self.full_name, "role": self.role, "active": self.active}


class CaseAssignment(Base):
    __tablename__ = "case_assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    assigned_to: Mapped[str] = mapped_column(String(64))
    assigned_by: Mapped[str] = mapped_column(String(64))
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditEvent(Base):
    """Append-only audit stream (agent steps + human actions). Lives in the durable
    operational store so the trail survives restarts on Postgres. `ts` is an ISO
    string for exact API compatibility with existing consumers."""

    __tablename__ = "audit_events"
    __table_args__ = (Index("ix_audit_case", "case_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(48))
    tenant: Mapped[str] = mapped_column(String(48), default=DEMO_TENANT_SLUG)
    ts: Mapped[str] = mapped_column(String(32))
    actor: Mapped[str] = mapped_column(String(128))
    actor_type: Mapped[str] = mapped_column(String(16))
    action: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text, default="", nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, default="{}")
    llm_provider: Mapped[str] = mapped_column(String(32), default="", nullable=True)


class CaseReview(Base):
    """The human review decision per case, per tenant (the enforced approval gate).
    Durable + tenant-scoped."""

    __tablename__ = "case_reviews"
    __table_args__ = (Index("ix_review_tenant_case", "tenant", "case_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    case_id: Mapped[str] = mapped_column(String(48))
    tenant: Mapped[str] = mapped_column(String(48), default=DEMO_TENANT_SLUG)
    ts: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(16))
    reviewer: Mapped[str] = mapped_column(String(128))
    notes: Mapped[str] = mapped_column(Text, default="", nullable=True)
    edited_narrative: Mapped[str] = mapped_column(Text, default="", nullable=True)
    status: Mapped[str] = mapped_column(String(48))
