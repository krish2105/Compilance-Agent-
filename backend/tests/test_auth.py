"""
Auth + RBAC tests (JWT, password hashing, role gating).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402
from fastapi import HTTPException  # noqa: E402

from app import auth  # noqa: E402
from app.db import SessionLocal, init_models  # noqa: E402
from app.models import User  # noqa: E402


def _setup():
    init_models()
    auth.seed_default_users()


def test_password_hash_roundtrip():
    h = auth.hash_password("secret123")
    assert auth.verify_password("secret123", h)
    assert not auth.verify_password("wrong", h)


def test_token_roundtrip_and_role():
    _setup()
    db = SessionLocal()
    user = db.query(User).filter(User.username == "mlro").first()
    token = auth.create_token(user)
    payload = auth._decode_token(token)
    assert payload["sub"] == "mlro"
    assert payload["role"] == "mlro"
    db.close()


def test_require_role_hierarchy():
    analyst = auth.Principal("a", "analyst", "jwt")
    mlro = auth.Principal("m", "mlro", "jwt")
    dep = auth.require_role("mlro")
    # analyst is below mlro -> forbidden
    with pytest.raises(HTTPException) as exc:
        dep(principal=analyst)
    assert exc.value.status_code == 403
    # mlro passes
    assert dep(principal=mlro) is mlro


def test_default_users_seeded():
    _setup()
    db = SessionLocal()
    roles = {u.username: u.role for u in db.query(User).all()}
    db.close()
    assert roles.get("admin") == "admin"
    assert roles.get("mlro") == "mlro"
    assert roles.get("analyst") == "analyst"
