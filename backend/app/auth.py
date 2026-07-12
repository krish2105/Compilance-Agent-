"""
Authentication & RBAC.

Two auth lanes:
  * **JWT bearer** — real users log in (username/password) and get a signed JWT
    carrying their role. Roles: analyst < mlro < admin.
  * **X-API-Key** — the legacy/demo shared key still works and maps to a synthetic
    admin user, so the bundled demo keeps functioning without a login.

Passwords are hashed with PBKDF2-HMAC-SHA256 (stdlib — no heavy deps). RBAC is
enforced per-route via the `require_role` dependency (e.g. only MLRO/admin may
approve or file a SAR; only admin manages users).
"""
from __future__ import annotations

import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, get_db
from app.models import ROLES, User

_PBKDF2_ROUNDS = 120_000


# --------------------------------------------------------------------- passwords
def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split(":")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ROUNDS)
        return dk.hex() == dk_hex
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------- tokens
def create_token(user: User) -> str:
    payload = {
        "sub": user.username, "role": user.role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def _decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------- current user
class Principal:
    """The authenticated caller (a real user, or the demo API-key admin)."""

    def __init__(self, username: str, role: str, via: str) -> None:
        self.username = username
        self.role = role
        self.via = via  # "jwt" | "api_key"


def get_current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        payload = _decode_token(auth[7:].strip())
        if payload and payload.get("sub"):
            user = db.execute(select(User).where(User.username == payload["sub"])).scalar_one_or_none()
            if user and user.active:
                return Principal(user.username, user.role, "jwt")
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    # Legacy/demo API key → synthetic admin so the demo keeps working.
    if request.headers.get("x-api-key") == settings.backend_api_key:
        return Principal("demo-api-key", "admin", "api_key")
    raise HTTPException(status_code=401, detail="Not authenticated.")


def require_role(*allowed: str):
    """Dependency: caller's role must rank >= the lowest allowed role."""
    min_rank = min(ROLES.index(r) for r in allowed)

    def _dep(principal: Principal = Depends(get_current_principal)) -> Principal:
        if ROLES.index(principal.role) < min_rank:
            raise HTTPException(
                status_code=403,
                detail=f"Requires role {'/'.join(allowed)} — you are '{principal.role}'.",
            )
        return principal

    return _dep


# --------------------------------------------------------------------- seeding
_DEFAULT_USERS = [
    ("admin", "admin123", "admin", "Platform Admin"),
    ("mlro", "mlro123", "mlro", "Money Laundering Reporting Officer"),
    ("analyst", "analyst123", "analyst", "AML Analyst"),
]


def seed_default_users() -> None:
    """Create the demo users on first run (idempotent)."""
    db = SessionLocal()
    try:
        for username, pw, role, full_name in _DEFAULT_USERS:
            exists = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
            if not exists:
                db.add(User(username=username, email=f"{username}@demo.local",
                            full_name=full_name, hashed_password=hash_password(pw), role=role))
        db.commit()
    finally:
        db.close()
