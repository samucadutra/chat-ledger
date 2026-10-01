"""API composition root: the only place concrete adapters are instantiated."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from chatledger_api.http.errors import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    install_error_handlers,
)
from chatledger_api.http.routes import health, v1
from chatledger_core import __version__
from chatledger_core.config import Settings, get_settings
from chatledger_core.infra.db.engine import make_engine
from chatledger_core.infra.git_sha import resolve_git_sha
from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat
from chatledger_core.infra.logging import configure_logging


def create_app(settings: Settings | None = None, *, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, service="api")
    engine = engine or make_engine(settings.database_url)

    app = FastAPI(
        title="ChatLedger API",
        version=__version__,
        description="Slack export to RSMF evidence pipeline.",
    )
    app.state.engine = engine
    app.state.settings = settings
    app.state.health_deps = health.HealthDeps(
        engine=engine,
        heartbeat=PgHeartbeat(engine),
        blob_root=settings.blob_root,
        git_sha=resolve_git_sha(settings.git_sha, settings.git_sha_file),
        version=__version__,
        worker_active_window_seconds=settings.worker_active_window_seconds,
    )

    install_error_handlers(app)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=[REQUEST_ID_HEADER],
    )

    app.include_router(health.router)
    app.include_router(v1.router)
    return app


def __getattr__(name: str) -> FastAPI:
    # Lazily build the ASGI app so importing this module has no side effects
    # (uvicorn resolves ``chatledger_api.main:app`` through this hook).
    if name == "app":
        application = create_app()
        globals()["app"] = application
        return application
    raise AttributeError(name)
