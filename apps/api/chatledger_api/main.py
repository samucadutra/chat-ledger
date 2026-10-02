"""API composition root: the only place concrete adapters are instantiated."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine

from chatledger_api.http.errors import (
    REQUEST_ID_HEADER,
    RequestIdMiddleware,
    install_error_handlers,
)
from chatledger_api.http.routes import health, v1
from chatledger_api.http.routes.matters import IntakeServices
from chatledger_api.janitor import Janitor
from chatledger_core import __version__
from chatledger_core.config import Settings, get_settings
from chatledger_core.domain.intake.archive import ArchiveLimits
from chatledger_core.infra.blobstore.fs_blob_store import FsBlobStore
from chatledger_core.infra.db.engine import make_engine
from chatledger_core.infra.git_sha import resolve_git_sha
from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat
from chatledger_core.infra.intake.pg_unit_of_work import PgIntakeUnitOfWork
from chatledger_core.infra.intake.zip_archive_inspector import ZipArchiveInspector
from chatledger_core.infra.logging import configure_logging
from chatledger_core.usecase.intake.create_matter import CreateMatter
from chatledger_core.usecase.intake.get_matter import GetMatter
from chatledger_core.usecase.intake.list_collections import GetCollection, ListCollections
from chatledger_core.usecase.intake.list_matters import ListMatters
from chatledger_core.usecase.intake.register_collection import RegisterCollection


def build_intake_services(settings: Settings, engine: Engine) -> IntakeServices:
    blob_store = FsBlobStore(settings.blob_root)

    def uow_factory() -> PgIntakeUnitOfWork:
        return PgIntakeUnitOfWork(engine)

    return IntakeServices(
        create_matter=CreateMatter(uow_factory),
        list_matters=ListMatters(uow_factory),
        get_matter=GetMatter(uow_factory),
        list_collections=ListCollections(uow_factory),
        get_collection=GetCollection(uow_factory),
        register_collection=RegisterCollection(
            uow_factory,
            blob_store,
            ZipArchiveInspector(),
            ArchiveLimits(
                max_entries=settings.archive_max_entries,
                max_uncompressed_bytes=settings.archive_max_uncompressed_bytes,
                max_ratio=settings.archive_max_ratio,
                ratio_min_entry_bytes=settings.archive_ratio_min_entry_bytes,
            ),
            settings.max_collections_per_matter,
        ),
        blob_store=blob_store,
        max_upload_bytes=settings.max_upload_bytes,
        upload_chunk_bytes=settings.upload_chunk_bytes,
    )


def create_app(settings: Settings | None = None, *, engine: Engine | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, service="api")
    engine = engine or make_engine(settings.database_url)

    intake = build_intake_services(settings, engine)
    janitor = Janitor(
        Path(intake.blob_store.tmp_dir),
        settings.upload_janitor_interval_seconds,
        settings.upload_stale_seconds,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        janitor.start()
        try:
            yield
        finally:
            janitor.stop()

    app = FastAPI(
        lifespan=lifespan,
        title="ChatLedger API",
        version=__version__,
        description="Slack export to RSMF evidence pipeline.",
    )
    app.state.engine = engine
    app.state.settings = settings
    app.state.intake = intake
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
