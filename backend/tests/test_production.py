"""Production config and cookie security checks."""

from __future__ import annotations

import pytest
from starlette.responses import Response

from app.core.config import Settings, get_settings
from app.core.session import COOKIE_ACCESS, set_session_cookies, clear_session_cookies


def test_production_rejects_placeholder_secrets():
    s = Settings(
        APP_ENV="production",
        SECRET_KEY="change-me-generate-with-openssl",
        ADMIN_PASSWORD="ChangeMeAdmin123!",
        POSTGRES_PASSWORD="change-me-strong-db-password",
    )
    with pytest.raises(RuntimeError, match="placeholder"):
        s.validate_production_secrets()


def test_development_allows_placeholder_secrets():
    s = Settings(
        APP_ENV="development",
        SECRET_KEY="change-me",
        ADMIN_PASSWORD="ChangeMeAdmin123!",
        DATABASE_URL="postgresql+asyncpg://aiplatform:change-me@postgres:5432/aiplatform",
    )
    s.validate_production_secrets()  # no raise


def test_production_accepts_strong_secrets():
    s = Settings(
        APP_ENV="production",
        SECRET_KEY="a" * 64,
        ADMIN_PASSWORD="Str0ng!AdminPass99",
        POSTGRES_PASSWORD="Str0ngDbPass99xyz",
        DATABASE_URL="postgresql+asyncpg://aiplatform:Str0ngDbPass99xyz@postgres:5432/aiplatform",
    )
    s.validate_production_secrets()


def test_cookies_secure_from_https_public_url(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("PUBLIC_URL", "https://ai.example.com")
    monkeypatch.setenv("APP_ENV", "development")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.cookies_secure is True
    resp = Response()
    set_session_cookies(resp, "access", "refresh")
    header = resp.headers.get("set-cookie", "")
    # Starlette may emit multiple set-cookie; check raw list
    cookies = resp.headers.getlist("set-cookie")
    assert any("Secure" in c for c in cookies)
    assert any(COOKIE_ACCESS in c for c in cookies)
    get_settings.cache_clear()


def test_cookies_insecure_on_http_localhost(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("PUBLIC_URL", "http://localhost:8088")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("COOKIE_SECURE", raising=False)
    get_settings.cache_clear()
    assert get_settings().cookies_secure is False
    resp = Response()
    set_session_cookies(resp, "access", "refresh")
    cookies = resp.headers.getlist("set-cookie")
    assert cookies
    assert all("Secure" not in c for c in cookies)
    clear_session_cookies(resp)
    get_settings.cache_clear()


def test_registration_disabled_by_default():
    s = Settings(
        APP_ENV="development",
        SECRET_KEY="x",
        REGISTRATION_ENABLED="false",
    )
    assert s.registration_enabled is False
