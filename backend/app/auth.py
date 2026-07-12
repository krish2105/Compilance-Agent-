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
from app.models import DEMO_TENANT_SLUG, ROLES, Tenant, User

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
def create_token(user: User, tenant_slug: str) -> str:
    payload = {
        "sub": user.username, "role": user.role, "tid": tenant_slug,
        "tv": user.token_version,  # session-revocation counter
        "exp": datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


# --------------------------------------------------------------------- password policy
def password_strength_error(password: str) -> Optional[str]:
    """Return a human message if the password is too weak, else None."""
    if len(password) < 8:
        return "Password must be at least 8 characters."
    if password.lower() in {"password", "12345678", "changeme", "admin123", "qwerty123"}:
        return "Password is too common — choose something less guessable."
    classes = sum(bool(set(password) & s) for s in (
        set("abcdefghijklmnopqrstuvwxyz"),
        set("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        set("0123456789"),
    ))
    if classes < 2:
        return "Password must mix at least two of: lower-case, upper-case, digits."
    return None


def _decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except Exception:  # noqa: BLE001
        return None


# --------------------------------------------------------------------- current user
class Principal:
    """The authenticated caller (a real user, or the demo API-key admin)."""

    def __init__(self, username: str, role: str, via: str,
                 tenant: str = DEMO_TENANT_SLUG) -> None:
        self.username = username
        self.role = role
        self.via = via  # "jwt" | "api_key"
        self.tenant = tenant  # tenant slug — the data-isolation boundary


def get_current_principal(request: Request, db: Session = Depends(get_db)) -> Principal:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        payload = _decode_token(auth[7:].strip())
        tid = (payload or {}).get("tid", DEMO_TENANT_SLUG)
        if payload and payload.get("sub"):
            # Resolve the tenant, then the user within it (usernames are per-tenant).
            tenant = db.execute(select(Tenant).where(Tenant.slug == tid)).scalar_one_or_none()
            if tenant is not None:
                user = db.execute(
                    select(User).where(User.username == payload["sub"],
                                       User.tenant_id == tenant.id)
                ).scalar_one_or_none()
                # token_version must match — a password change / reset revokes old tokens.
                if (user and user.active
                        and payload.get("tv", 0) == user.token_version):
                    return Principal(user.username, user.role, "jwt", tenant.slug)
        raise HTTPException(status_code=401, detail="Invalid or expired token.")
    # Legacy/demo API key → synthetic admin on the demo tenant so the demo keeps working.
    if request.headers.get("x-api-key") == settings.backend_api_key:
        return Principal("demo-api-key", "admin", "api_key", DEMO_TENANT_SLUG)
    raise HTTPException(status_code=401, detail="Not authenticated.")


# --------------------------------------------------------------------- login throttle
# Backed by the shared cache (Redis when attached) so brute-force protection stays
# correct across horizontally-scaled instances; in-process otherwise.
_MAX_FAILS = 5
_LOCK_SECONDS = 900  # 15 min


def _fail_key(key: str) -> str:
    return f"loginfail:{key}"


def login_lock_seconds(key: str) -> int:
    """Seconds remaining before `key` (org:username) may retry, or 0 if not locked."""
    from app.tools import cache

    count = cache.get(_fail_key(key)) or 0
    if int(count) >= _MAX_FAILS:
        return cache.ttl(_fail_key(key)) or _LOCK_SECONDS
    return 0


def record_login_failure(key: str) -> None:
    from app.tools import cache

    cache.incr(_fail_key(key), _LOCK_SECONDS)


def clear_login_failures(key: str) -> None:
    from app.tools import cache

    cache.delete(_fail_key(key))


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


def get_or_create_tenant(db: Session, slug: str, name: str = "") -> Tenant:
    tenant = db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(slug=slug, name=name or slug.replace("-", " ").title())
        db.add(tenant)
        db.flush()  # assign id
    return tenant


def slugify(name: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")
    while "--" in base:
        base = base.replace("--", "-")
    return base[:40] or "org"


def register_organization(db: Session, org_name: str, username: str, password: str,
                          email: str = "", full_name: str = "") -> tuple[Tenant, User]:
    """Self-serve onboarding: create a new tenant and its first admin user.

    Raises ValueError if the organization slug is already taken.
    """
    slug = slugify(org_name)
    if db.execute(select(Tenant).where(Tenant.slug == slug)).scalar_one_or_none():
        raise ValueError(f"An organization named '{org_name}' already exists.")
    tenant = Tenant(slug=slug, name=org_name)
    db.add(tenant)
    db.flush()
    user = User(tenant_id=tenant.id, username=username, email=email,
                full_name=full_name, hashed_password=hash_password(password), role="admin")
    db.add(user)
    db.commit()
    return tenant, user


def seed_default_users() -> None:
    """Create the demo tenant + demo users on first run (idempotent)."""
    db = SessionLocal()
    try:
        tenant = get_or_create_tenant(db, DEMO_TENANT_SLUG, "Demo Organization")
        tenant.plan = "enterprise"  # the public demo is never limited
        for username, pw, role, full_name in _DEFAULT_USERS:
            exists = db.execute(
                select(User).where(User.username == username, User.tenant_id == tenant.id)
            ).scalar_one_or_none()
            if not exists:
                db.add(User(tenant_id=tenant.id, username=username,
                            email=f"{username}@demo.local", full_name=full_name,
                            hashed_password=hash_password(pw), role=role))
        db.commit()
    finally:
        db.close()
