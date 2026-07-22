"""Shared Jinja2 templates with globals (css cache-bust, etc.)."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import __version__

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["css_version"] = __version__
