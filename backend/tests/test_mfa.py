"""2FA (TOTP) enrolment + login enforcement, and per-tenant observability."""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import auth  # noqa: E402


def _code(secret: str) -> str:
    return auth._hotp(secret, int(time.time()) // 30)


def test_totp_generate_and_verify():
    secret = auth.generate_totp_secret()
    assert len(secret) >= 16
    assert auth.verify_totp(secret, _code(secret)) is True
    assert auth.verify_totp(secret, "000000") is False


def test_mfa_login_flow_and_observability():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        tok = c.post("/api/auth/register-org",
                     json={"org_name": "MFA Test Co", "username": "mfauser",
                           "password": "Str0ngPass1"}).json()["token"]
        H = {"Authorization": f"Bearer {tok}"}

        # Enrol.
        secret = c.post("/api/auth/mfa/setup", headers=H).json()["secret"]
        assert c.post("/api/auth/mfa/enable", headers=H, json={"code": _code(secret)}).json()["mfa_enabled"] is True
        # A wrong code can't enable.
        # (already enabled; test disable path with wrong code)
        assert c.post("/api/auth/mfa/disable", headers=H, json={"code": "000000"}).status_code == 422

        # Login now requires the second factor.
        assert c.post("/api/auth/login",
                      json={"username": "mfauser", "password": "Str0ngPass1", "org": "mfa-test-co"}
                      ).status_code == 401
        ok = c.post("/api/auth/login",
                    json={"username": "mfauser", "password": "Str0ngPass1", "org": "mfa-test-co",
                          "mfa_code": _code(secret)})
        assert ok.status_code == 200 and ok.json()["user"]["mfa_enabled"] is True

        # Per-tenant observability reflects it.
        o = c.get("/api/admin/observability", headers=H).json()
        assert o["members"] == 1
        assert o["mfa_adoption"]["enabled"] == 1 and o["mfa_adoption"]["pct"] == 100
        assert "by_decision" in o["reviews"]
