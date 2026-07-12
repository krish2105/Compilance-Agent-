"""Auth + user-management routes (JWT login, current user, admin user CRUD)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import auth
from app.db import get_db
from app.models import ROLES, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    role: str = "analyst"
    full_name: str = ""
    email: str = ""


@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)) -> dict:
    user = db.execute(select(User).where(User.username == req.username)).scalar_one_or_none()
    if not user or not user.active or not auth.verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"token": auth.create_token(user), "user": user.to_public()}


@router.get("/me")
def me(principal: auth.Principal = Depends(auth.get_current_principal)) -> dict:
    return {"username": principal.username, "role": principal.role, "via": principal.via}


@router.get("/users")
def list_users(_: auth.Principal = Depends(auth.require_role("admin")),
               db: Session = Depends(get_db)) -> List[dict]:
    return [u.to_public() for u in db.execute(select(User)).scalars().all()]


@router.post("/register")
def register(req: RegisterRequest,
             _: auth.Principal = Depends(auth.require_role("admin")),
             db: Session = Depends(get_db)) -> dict:
    if req.role not in ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of {ROLES}")
    if db.execute(select(User).where(User.username == req.username)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already exists.")
    user = User(username=req.username, email=req.email, full_name=req.full_name,
                hashed_password=auth.hash_password(req.password), role=req.role)
    db.add(user)
    db.commit()
    return {"ok": True, "user": user.to_public()}
