"""Display branding helpers for portal templates."""

from __future__ import annotations

from app.core.config import get_settings


def app_display_name() -> str:
    settings = get_settings()
    name = (settings.app_name or "AI Platform").replace(" API", "").strip()
    return name or "AI Platform"


def public_base_url() -> str:
    settings = get_settings()
    return (settings.public_url or "http://localhost:8088").rstrip("/")
