"""SQLAlchemy models for the operational store (users + case assignments)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Role hierarchy (higher index = more privilege).
ROLES = ["analyst", "mlro", "admin"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
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
