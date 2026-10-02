"""Application settings — the ONLY module that reads the process environment.

Composition roots (API, worker, CLI, Alembic env) call :func:`get_settings` and
pass plain values into adapters; nothing below ``domain``/``usecase``/``infra``
imports this module (enforced by import-linter).
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
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

    max_upload_bytes: int = Field(default=2_147_483_648, gt=0)
    upload_chunk_bytes: int = Field(default=8_388_608, gt=0)
    upload_stale_seconds: float = Field(default=600, gt=0)
    upload_janitor_interval_seconds: float = Field(default=60, gt=0)
    max_collections_per_matter: int = Field(default=20, ge=1)
    archive_max_entries: int = Field(default=200_000, ge=1)
    archive_max_uncompressed_bytes: int = Field(default=21_474_836_480, ge=1)
    archive_max_ratio: int = Field(default=100, ge=1)
    archive_ratio_min_entry_bytes: int = Field(default=1_048_576, ge=0)

    generator_bytes_per_message: int = Field(default=350, ge=1)
    generator_disk_headroom: float = Field(default=1.5, ge=1)
    generator_progress_every: int = Field(default=5000, ge=1)
    # Test-only knobs (spec A24): inert at their defaults, read only by composition roots.
    generator_free_space_override_bytes: int | None = Field(default=None, ge=0)
    generator_test_delay_ms_per_conversation: int = Field(default=0, ge=0)
    generator_test_fail_always: bool = False

    @field_validator("generator_free_space_override_bytes", mode="before")
    @classmethod
    def _blank_override_is_unset(cls, value: object) -> object:
        """Compose passes an unset variable through as an empty string."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("generator_test_delay_ms_per_conversation", mode="before")
    @classmethod
    def _blank_delay_is_zero(cls, value: object) -> object:
        return 0 if isinstance(value, str) and not value.strip() else value

    @field_validator("generator_test_fail_always", mode="before")
    @classmethod
    def _blank_fail_is_false(cls, value: object) -> object:
        return False if isinstance(value, str) and not value.strip() else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
