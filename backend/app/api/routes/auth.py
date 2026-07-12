"""Auth + user-management routes (JWT login, current user, admin user CRUD)."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_db
from app.models import DEMO_TENANT_SLUG, ROLES, Tenant, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str
    org: str = DEMO_TENANT_SLUG  # tenant slug; defaults to the demo org


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    role: str = "analyst"
    full_name: str = ""
    email: str = ""


class RegisterOrgRequest(BaseModel):
    org_name: str = Field(min_length=2, max_length=64)
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    email: str = ""
    full_name: str = ""


class UpdateUserRequest(BaseModel):
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None  # admin resets a member's password


def _tenant_for(principal: auth.Principal, db: Session) -> Tenant:
    return db.execute(select(Tenant).where(Tenant.slug == principal.tenant)).scalar_one()


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> dict:
    # Brute-force protection: lock the (org, username) pair after repeated failures.
    throttle_key = f"{req.org}:{req.username}"
    locked = auth.login_lock_seconds(throttle_key)
    if locked:
        raise HTTPException(
            status_code=429,
            headers={"Retry-After": str(locked)},
            detail=f"Too many failed attempts. Try again in ~{locked // 60 + 1} min.",
        )
    tenant = db.execute(select(Tenant).where(Tenant.slug == req.org)).scalar_one_or_none()
    user = None
    if tenant is not None:
        user = db.execute(
            select(User).where(User.username == req.username, User.tenant_id == tenant.id)
        ).scalar_one_or_none()
    if not user or not user.active or not auth.verify_password(req.password, user.hashed_password):
        auth.record_login_failure(throttle_key)
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    auth.clear_login_failures(throttle_key)
    return {"token": auth.create_token(user, tenant.slug),
            "user": user.to_public(), "tenant": tenant.to_public()}


@router.post("/register-org")
def register_org(req: RegisterOrgRequest, db: Session = Depends(get_db)) -> dict:
    """Public self-serve onboarding — create a new organization + its first admin."""
    weak = auth.password_strength_error(req.password)
    if weak:
        raise HTTPException(status_code=422, detail=weak)
    try:
        tenant, user = auth.register_organization(
            db, req.org_name, req.username, req.password, req.email, req.full_name)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"token": auth.create_token(user, tenant.slug),
            "user": user.to_public(), "tenant": tenant.to_public()}


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)


@router.post("/change-password")
def change_password(req: ChangePasswordRequest,
                    principal: auth.Principal = Depends(auth.get_current_principal),
                    db: Session = Depends(get_db)) -> dict:
    """Self-service password change. Rotates token_version → all existing sessions are
    revoked; returns a fresh token so the caller stays logged in."""
    if principal.via != "jwt":
        raise HTTPException(status_code=403, detail="Demo/API-key sessions can't change a password.")
    tenant = _tenant_for(principal, db)
    user = db.execute(
        select(User).where(User.username == principal.username, User.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if not user or not auth.verify_password(req.old_password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Current password is incorrect.")
    weak = auth.password_strength_error(req.new_password)
    if weak:
        raise HTTPException(status_code=422, detail=weak)
    user.hashed_password = auth.hash_password(req.new_password)
    user.token_version = (user.token_version or 0) + 1  # revoke old sessions
    db.commit()
    return {"ok": True, "token": auth.create_token(user, tenant.slug)}


@router.get("/me")
def me(principal: auth.Principal = Depends(auth.get_current_principal)) -> dict:
    return {"username": principal.username, "role": principal.role,
            "via": principal.via, "tenant": principal.tenant}


@router.get("/users")
def list_users(principal: auth.Principal = Depends(auth.require_role("admin")),
               db: Session = Depends(get_db)) -> List[dict]:
    # Only users within the caller's own tenant.
    tenant = _tenant_for(principal, db)
    rows = db.execute(select(User).where(User.tenant_id == tenant.id)).scalars().all()
    return [u.to_public() for u in rows]


@router.post("/register")
def register(req: RegisterRequest,
             principal: auth.Principal = Depends(auth.require_role("admin")),
             db: Session = Depends(get_db)) -> dict:
    """Admin adds a teammate — scoped to the admin's own organization."""
    if req.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    weak = auth.password_strength_error(req.password)
    if weak:
        raise HTTPException(status_code=422, detail=weak)
    tenant = _tenant_for(principal, db)
    if db.execute(select(User).where(User.username == req.username,
                                     User.tenant_id == tenant.id)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists in this organization.")
    user = User(tenant_id=tenant.id, username=req.username, email=req.email,
                full_name=req.full_name, hashed_password=auth.hash_password(req.password),
                role=req.role)
    db.add(user)
    db.commit()
    return {"ok": True, "user": user.to_public()}


@router.patch("/users/{username}")
def update_user(username: str, req: UpdateUserRequest,
                principal: auth.Principal = Depends(auth.require_role("admin")),
                db: Session = Depends(get_db)) -> dict:
    """Change a teammate's role or active status — within the admin's own org.

    Guards against self-lockout: an admin cannot demote or deactivate themselves.
    """
    tenant = _tenant_for(principal, db)
    user = db.execute(
        select(User).where(User.username == username, User.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found in this organization.")
    is_self = user.username == principal.username
    if req.role is not None:
        if req.role not in ROLES:
            raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
        if is_self and req.role != "admin":
            raise HTTPException(status_code=409, detail="You cannot remove your own admin role.")
        user.role = req.role
    if req.active is not None:
        if is_self and req.active is False:
            raise HTTPException(status_code=409, detail="You cannot deactivate your own account.")
        user.active = req.active
    if req.password is not None:
        weak = auth.password_strength_error(req.password)
        if weak:
            raise HTTPException(status_code=422, detail=weak)
        user.hashed_password = auth.hash_password(req.password)
        user.token_version = (user.token_version or 0) + 1  # revoke the member's sessions
    db.commit()
    return {"ok": True, "user": user.to_public()}
