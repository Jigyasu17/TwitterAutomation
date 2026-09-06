"""
Regression tests for the restored ADMIN_SECRET protection on manual
mutating endpoints (docs/security_todo.md). Verifies both directions:
- production (ENV != "development") without/with the wrong token -> 401
- production with the correct token -> passes through to the real handler
- development (the default in tests) -> unaffected, no token needed

Uses the auth dependency functions directly rather than spinning up the
full FastAPI app with a monkeypatched ENV, since app.config.settings is
already instantiated at import time (changing it after the fact via
monkeypatch.setattr is the reliable way to flip ENV/ADMIN_SECRET for a
single test without affecting the rest of the suite).
"""
import pytest
from fastapi import HTTPException
from app.api.auth import verify_admin_auth, verify_cron_auth
from app.config import settings


def test_admin_auth_skipped_in_development():
    assert settings.ENV == "development"
    verify_admin_auth(authorization=None)  # must not raise


def test_admin_auth_rejects_missing_token_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_SECRET", "correct-secret")
    with pytest.raises(HTTPException) as exc_info:
        verify_admin_auth(authorization=None)
    assert exc_info.value.status_code == 401


def test_admin_auth_rejects_wrong_token_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_SECRET", "correct-secret")
    with pytest.raises(HTTPException) as exc_info:
        verify_admin_auth(authorization="Bearer wrong-secret")
    assert exc_info.value.status_code == 401


def test_admin_auth_accepts_correct_token_in_production(monkeypatch):
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_SECRET", "correct-secret")
    verify_admin_auth(authorization="Bearer correct-secret")  # must not raise


def test_admin_auth_fails_closed_when_secret_unset_in_production(monkeypatch):
    """A missing ADMIN_SECRET must be a hard 401, never an open door."""
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "ADMIN_SECRET", "")
    with pytest.raises(HTTPException):
        verify_admin_auth(authorization="Bearer anything")


def test_cron_auth_still_independently_protected(monkeypatch):
    """Regression guard: restoring verify_admin_auth must not have disturbed verify_cron_auth."""
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "CRON_SECRET", "cron-secret")
    with pytest.raises(HTTPException):
        verify_cron_auth(authorization="Bearer wrong")
    verify_cron_auth(authorization="Bearer cron-secret")  # must not raise
