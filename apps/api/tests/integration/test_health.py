from __future__ import annotations

import os
import stat
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from chatledger_api.main import create_app
from chatledger_core.config import Settings
from chatledger_core.infra.db import migrations
from chatledger_core.infra.db.engine import make_engine

GIT_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def no_heartbeats(clean_jobs: Engine) -> Engine:
    return clean_jobs


def test_health_ok(client: TestClient, no_heartbeats: Engine) -> None:
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "status": "ok",
        "checks": {"database": "ok", "migrations": "ok", "blob_store": "ok"},
        "migration_revision": "0002_intake",
        "git_sha": GIT_SHA,
        "active_workers": 0,
        "version": "0.1.0",
    }
    assert res.headers["X-Request-ID"]


def test_health_db_unavailable(make_settings: Callable[..., Settings]) -> None:
    dead = make_engine("postgresql+psycopg://x:y@127.0.0.1:1/none", connect_timeout=1)
    client = TestClient(create_app(make_settings(), engine=dead))
    res = client.get("/health")
    dead.dispose()
    assert res.status_code == 503
    body = res.json()
    assert body["status"] == "degraded"
    assert body["checks"] == {
        "database": "unavailable",
        "migrations": "unknown",
        "blob_store": "ok",
    }
    assert body["migration_revision"] is None
    assert body["active_workers"] == 0
    assert body["git_sha"] == GIT_SHA


def test_health_migrations_pending(client: TestClient, test_database_url: str) -> None:
    migrations.downgrade(test_database_url, "base")
    try:
        res = client.get("/health")
    finally:
        migrations.upgrade(test_database_url, "head")
    assert res.status_code == 503
    assert res.json()["checks"]["migrations"] == "pending"
    assert res.json()["migration_revision"] is None


def test_health_active_workers_counts_recent_only(
    client: TestClient, no_heartbeats: Engine
) -> None:
    with no_heartbeats.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO worker_heartbeat (worker_id, hostname, pid, git_sha, last_seen_at) "
                "VALUES ('recent', 'h', 1, 'unknown', now() - interval '5 seconds'), "
                "('stale', 'h', 2, 'unknown', now() - interval '45 seconds')"
            )
        )
    assert client.get("/health").json()["active_workers"] == 1


@pytest.mark.skipif(os.geteuid() == 0, reason="root ignores directory permissions")
def test_health_blob_store_unwritable(client: TestClient, blob_root: Path) -> None:
    blob_root.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        res = client.get("/health")
    finally:
        blob_root.chmod(stat.S_IRWXU)
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "degraded"
    assert body["checks"]["blob_store"] == "unavailable"


def test_health_blob_store_missing(
    engine: Engine, make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    app = create_app(make_settings(blob_root=str(tmp_path / "missing")), engine=engine)
    body = TestClient(app).get("/health").json()
    assert body["checks"]["blob_store"] == "unavailable"


def test_unknown_git_sha_when_unset(
    engine: Engine, make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    app = create_app(
        make_settings(git_sha=None, git_sha_file=str(tmp_path / "none")), engine=engine
    )
    assert TestClient(app).get("/health").json()["git_sha"] == "unknown"


def test_openapi_schema_exposes_health(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/health" in schema["paths"]
    assert "HealthResponse" in schema["components"]["schemas"]
