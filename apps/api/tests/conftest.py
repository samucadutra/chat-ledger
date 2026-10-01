from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from chatledger_api.main import create_app
from chatledger_core.config import Settings

GIT_SHA = "0123456789abcdef0123456789abcdef01234567"


@pytest.fixture
def blob_root(tmp_path: Path) -> Path:
    root = tmp_path / "blobs"
    root.mkdir()
    return root


@pytest.fixture
def make_settings(blob_root: Path) -> Callable[..., Settings]:
    def factory(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "database_url": os.environ["TEST_DATABASE_URL"],
            "blob_root": str(blob_root),
            "git_sha": GIT_SHA,
            "log_level": "WARNING",
        }
        values.update(overrides)
        return Settings(**values)  # type: ignore[arg-type]

    return factory


@pytest.fixture
def app(engine: Engine, make_settings: Callable[..., Settings]) -> FastAPI:
    return create_app(make_settings(), engine=engine)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app, raise_server_exceptions=False)
