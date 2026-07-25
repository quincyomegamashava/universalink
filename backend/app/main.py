from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

from app import __version__
from app.api.routers import (
    admin,
    admin_ui,
    agents,
    auth,
    chats,
    ollama_bridge,
    openai_compat,
    portal,
    portal_settings,
    rag,
    users,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.session import AsyncSessionLocal, Base, engine
from app.middleware.logging import RequestLoggingMiddleware
from app.services.bootstrap import bootstrap_admin
from app.services.ollama import ollama_client
from app.services.rate_limit import rate_limiter
import app.models  # noqa: F401 — register models


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.validate_production_secrets()
    setup_logging(settings.app_debug)
    # Local/dev: create_all for convenience. Production: alembic via entrypoint only.
    if not settings.is_production:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    await rate_limiter.connect()
    async with AsyncSessionLocal() as session:
        await bootstrap_admin(session)
    yield
    await rate_limiter.close()
    await ollama_client.aclose()
    await engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    docs = "/api/docs" if settings.app_debug else None
    redoc = "/api/redoc" if settings.app_debug else None
    openapi = "/api/openapi.json" if settings.app_debug else None
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        lifespan=lifespan,
        docs_url=docs,
        redoc_url=redoc,
        openapi_url=openapi,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(auth.router)
    app.include_router(portal.router)
    app.include_router(portal_settings.router)
    app.include_router(users.router)
    app.include_router(chats.router)
    app.include_router(admin.router)
    app.include_router(admin_ui.router)
    app.include_router(openai_compat.router)
    app.include_router(ollama_bridge.router)
    app.include_router(rag.router)
    app.include_router(agents.router)

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/admin/static", StaticFiles(directory=str(static_dir)), name="admin-static")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/metrics")
    async def metrics() -> Response:
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
