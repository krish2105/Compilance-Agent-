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
    mfa_code: Optional[str] = None  # required when the user has 2FA enabled


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
    # Second factor, if the user enabled 2FA.
    if user.mfa_enabled:
        if not req.mfa_code:
            raise HTTPException(status_code=401, detail="MFA code required.")
        if not auth.verify_totp(user.totp_secret, req.mfa_code):
            auth.record_login_failure(throttle_key)
            raise HTTPException(status_code=401, detail="Invalid MFA code.")
    auth.clear_login_failures(throttle_key)
    return {"token": auth.create_token(user, tenant.slug),
            "user": user.to_public(), "tenant": tenant.to_public()}


class MfaCodeRequest(BaseModel):
    code: str


def _current_user(principal: auth.Principal, db: Session) -> User:
    tenant = _tenant_for(principal, db)
    user = db.execute(
        select(User).where(User.username == principal.username, User.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return user, tenant


@router.post("/mfa/setup")
def mfa_setup(principal: auth.Principal = Depends(auth.get_current_principal),
              db: Session = Depends(get_db)) -> dict:
    """Begin 2FA enrolment: generate a secret + otpauth URI to add to an authenticator app."""
    if principal.via != "jwt":
        raise HTTPException(status_code=403, detail="Demo/API-key sessions can't enable 2FA.")
    user, tenant = _current_user(principal, db)
    secret = auth.generate_totp_secret()
    user.totp_secret = secret  # stored but not active until a code is verified
    db.commit()
    return {"secret": secret,
            "otpauth_uri": auth.totp_provisioning_uri(secret, user.username, tenant.slug)}


@router.post("/mfa/enable")
def mfa_enable(req: MfaCodeRequest,
               principal: auth.Principal = Depends(auth.get_current_principal),
               db: Session = Depends(get_db)) -> dict:
    """Confirm 2FA: verify a code against the pending secret, then enable."""
    user, _ = _current_user(principal, db)
    if not user.totp_secret or not auth.verify_totp(user.totp_secret, req.code):
        raise HTTPException(status_code=422, detail="Invalid code — check your authenticator app.")
    user.mfa_enabled = True
    db.commit()
    return {"ok": True, "mfa_enabled": True}


@router.post("/mfa/disable")
def mfa_disable(req: MfaCodeRequest,
                principal: auth.Principal = Depends(auth.get_current_principal),
                db: Session = Depends(get_db)) -> dict:
    """Turn 2FA off (requires a valid current code)."""
    user, _ = _current_user(principal, db)
    if user.mfa_enabled and not auth.verify_totp(user.totp_secret, req.code):
        raise HTTPException(status_code=422, detail="Invalid code.")
    user.mfa_enabled = False
    user.totp_secret = ""
    db.commit()
    return {"ok": True, "mfa_enabled": False}


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


class PlanRequest(BaseModel):
    plan: str


class OrgSettingsRequest(BaseModel):
    name: str = Field(min_length=2, max_length=128)


@router.get("/billing")
def billing(principal: auth.Principal = Depends(auth.get_current_principal)) -> dict:
    """Current plan, limits and usage for the caller's organization."""
    from app.tools import plans
    return plans.usage(principal.tenant)


@router.post("/billing/plan")
def change_plan(req: PlanRequest,
                principal: auth.Principal = Depends(auth.require_role("admin"))) -> dict:
    """Change the org plan (billing stub — a real Stripe webhook would set this)."""
    from app.tools import plans
    new = plans.set_plan(principal.tenant, req.plan)
    if new is None:
        raise HTTPException(status_code=422, detail=f"Unknown plan '{req.plan}'.")
    return {"ok": True, "plan": new, "billing": plans.usage(principal.tenant)}


@router.patch("/org")
def update_org(req: OrgSettingsRequest,
               principal: auth.Principal = Depends(auth.require_role("admin")),
               db: Session = Depends(get_db)) -> dict:
    """Rename the organization's display name (admin only)."""
    tenant = _tenant_for(principal, db)
    tenant.name = req.name.strip()
    db.commit()
    return {"ok": True, "tenant": tenant.to_public()}


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
    from app.tools import plans
    try:
        plans.check_can_add_member(principal.tenant)
    except plans.LimitError as e:
        raise HTTPException(status_code=402, detail=str(e))
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
