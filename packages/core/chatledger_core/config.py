"""Application settings — the ONLY module that reads the process environment.

Composition roots (API, worker, CLI, Alembic env) call :func:`get_settings` and
pass plain values into adapters; nothing below ``domain``/``usecase``/``infra``
imports this module (enforced by import-linter).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore", case_sensitive=False)

    database_url: str = "postgresql+psycopg://chatledger:chatledger@db:5432/chatledger"
    test_database_url: str = (
        "postgresql+psycopg://chatledger:chatledger@localhost:5432/chatledger_test"
    )
    blob_root: str = "/data/blobs"
    git_sha: str | None = None
    git_sha_file: str = "/app/GIT_SHA"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    job_lease_seconds: float = Field(default=60, gt=0)
    job_lease_renew_seconds: float = Field(default=20, gt=0)
    job_sweep_interval_seconds: float = Field(default=15, gt=0)
    job_poll_interval_seconds: float = Field(default=1.0, gt=0)
    job_max_attempts: int = Field(default=3, ge=1)
    job_retry_backoff_seconds: float = Field(default=5, ge=0)
    heartbeat_interval_seconds: float = Field(default=10, gt=0)
    worker_active_window_seconds: float = Field(default=30, gt=0)

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
