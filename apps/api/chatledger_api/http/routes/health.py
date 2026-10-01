"""``GET /health`` — DB, migrations, blob store, git SHA and active workers."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from chatledger_core.infra.db.engine import current_revision, ping
from chatledger_core.infra.db.migrations import head_revision
from chatledger_core.infra.heartbeat.pg_heartbeat import PgHeartbeat


@dataclass(frozen=True)
class HealthDeps:
    engine: Engine
    heartbeat: PgHeartbeat
    blob_root: str
    git_sha: str
    version: str
    worker_active_window_seconds: float


class HealthChecks(BaseModel):
    database: Literal["ok", "unavailable"]
    migrations: Literal["ok", "pending", "unknown"]
    blob_store: Literal["ok", "unavailable"]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    checks: HealthChecks
    migration_revision: str | None
    git_sha: str
    active_workers: int
    version: str


router = APIRouter(tags=["system"])


def blob_store_writable(root: str) -> bool:
    path = Path(root)
    if not path.is_dir():
        return False
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".health-", delete=True) as fh:
            fh.write(b"ok")
        return True
    except OSError:
        return False


def evaluate_health(deps: HealthDeps) -> tuple[int, HealthResponse]:
    database: Literal["ok", "unavailable"] = "unavailable"
    migrations: Literal["ok", "pending", "unknown"] = "unknown"
    revision: str | None = None
    active = 0
    if ping(deps.engine):
        database = "ok"
        try:
            revision = current_revision(deps.engine)
            migrations = "ok" if revision == head_revision() else "pending"
            if migrations == "ok":
                active = deps.heartbeat.count_active(deps.worker_active_window_seconds)
        except SQLAlchemyError:
            migrations = "unknown"
    blob_store: Literal["ok", "unavailable"] = (
        "ok" if blob_store_writable(deps.blob_root) else "unavailable"
    )
    healthy_core = database == "ok" and migrations == "ok"
    body = HealthResponse(
        status="ok" if healthy_core and blob_store == "ok" else "degraded",
        checks=HealthChecks(database=database, migrations=migrations, blob_store=blob_store),
        migration_revision=revision,
        git_sha=deps.git_sha,
        active_workers=active,
        version=deps.version,
    )
    return (200 if healthy_core else 503), body


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "Database or migrations not ready"}},
    summary="Service health",
)
def health(request: Request) -> JSONResponse:
    deps: HealthDeps = request.app.state.health_deps
    status, body = evaluate_health(deps)
    return JSONResponse(body.model_dump(), status_code=status)
