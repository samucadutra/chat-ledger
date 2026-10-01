"""Programmatic Alembic helpers (head revision, upgrade/downgrade)."""

from __future__ import annotations

from importlib.resources import files

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("path_separator", "os")
    cfg.set_main_option("script_location", str(files("chatledger_core") / "migrations"))
    cfg.set_main_option(
        "version_locations", str(files("chatledger_core") / "migrations" / "versions")
    )
    if url:
        cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    cfg.attributes["configure_logger"] = False
    return cfg


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)
