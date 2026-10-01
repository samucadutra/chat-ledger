import pytest

from chatledger_core.config import Settings, get_settings


def test_defaults_match_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "DATABASE_URL",
        "BLOB_ROOT",
        "JOB_LEASE_SECONDS",
        "JOB_LEASE_RENEW_SECONDS",
        "JOB_SWEEP_INTERVAL_SECONDS",
        "JOB_POLL_INTERVAL_SECONDS",
        "JOB_MAX_ATTEMPTS",
        "JOB_RETRY_BACKOFF_SECONDS",
        "HEARTBEAT_INTERVAL_SECONDS",
        "WORKER_ACTIVE_WINDOW_SECONDS",
        "CORS_ORIGINS",
        "LOG_LEVEL",
        "GIT_SHA",
    ):
        monkeypatch.delenv(key, raising=False)
    s = Settings()
    assert s.database_url == "postgresql+psycopg://chatledger:chatledger@db:5432/chatledger"
    assert s.blob_root == "/data/blobs"
    assert s.job_lease_seconds == 60
    assert s.job_lease_renew_seconds == 20
    assert s.job_sweep_interval_seconds == 15
    assert s.job_poll_interval_seconds == 1.0
    assert s.job_max_attempts == 3
    assert s.job_retry_backoff_seconds == 5
    assert s.heartbeat_interval_seconds == 10
    assert s.worker_active_window_seconds == 30
    assert s.cors_origin_list == ["http://localhost:3000"]
    assert s.log_level == "INFO"
    assert s.git_sha is None


def test_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_LEASE_SECONDS", "5")
    monkeypatch.setenv("CORS_ORIGINS", "http://a.test, http://b.test")
    monkeypatch.setenv("GIT_SHA", "abc")
    s = Settings()
    assert s.job_lease_seconds == 5
    assert s.cors_origin_list == ["http://a.test", "http://b.test"]
    assert s.git_sha == "abc"


def test_test_env_file_is_loaded() -> None:
    s = Settings()
    assert s.job_lease_seconds == 5
    assert s.job_retry_backoff_seconds == 0
    assert s.job_sweep_interval_seconds == 2


def test_invalid_value_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JOB_MAX_ATTEMPTS", "0")
    with pytest.raises(ValueError, match="job_max_attempts"):
        Settings()


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()
