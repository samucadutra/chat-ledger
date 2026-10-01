"""SQLAlchemy Core table definitions (the schema created by migration 0001)."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    Identity,
    Index,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

metadata = MetaData()

job = Table(
    "job",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")),
    Column("kind", String(64), nullable=False),
    Column("payload", JSONB, nullable=False, server_default=text("'{}'")),
    Column("state", String(16), nullable=False, server_default=text("'queued'")),
    Column("priority", SmallInteger, nullable=False, server_default=text("100")),
    Column("group_key", String(128)),
    Column("attempts", Integer, nullable=False, server_default=text("0")),
    Column("max_attempts", Integer, nullable=False, server_default=text("3")),
    Column("lease_owner", String(128)),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("run_after", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("last_error", Text),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    CheckConstraint("state IN ('queued','leased','done','failed')", name="ck_job_state"),
    CheckConstraint("attempts >= 0 AND max_attempts >= 1", name="ck_job_attempts"),
    CheckConstraint(
        "state <> 'leased' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)",
        name="ck_job_lease",
    ),
    Index("ix_job_claimable", "priority", "created_at", postgresql_where=text("state = 'queued'")),
    Index("ix_job_leased_expiry", "lease_expires_at", postgresql_where=text("state = 'leased'")),
    Index(
        "ix_job_group_state",
        "group_key",
        "state",
        postgresql_where=text("group_key IS NOT NULL"),
    ),
)

audit_event = Table(
    "audit_event",
    metadata,
    Column("id", BigInteger, Identity(always=True), primary_key=True),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("action", String(64), nullable=False),
    Column("entity_type", String(64), nullable=False),
    Column("entity_id", String(128), nullable=False),
    Column("details", JSONB, nullable=False, server_default=text("'{}'")),
    CheckConstraint(r"action ~ '^[a-z_]+(\.[a-z_]+)+$'", name="ck_audit_action_format"),
    Index("ix_audit_entity", "entity_type", "entity_id", "id"),
    Index("ix_audit_occurred_at", "occurred_at"),
)

worker_heartbeat = Table(
    "worker_heartbeat",
    metadata,
    Column("worker_id", String(128), primary_key=True),
    Column("hostname", String(255), nullable=False),
    Column("pid", Integer, nullable=False),
    Column("git_sha", String(40), nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("last_seen_at", DateTime(timezone=True), nullable=False, server_default=text("now()")),
    Column("current_job_id", UUID(as_uuid=True)),
    Index("ix_worker_heartbeat_last_seen", "last_seen_at"),
)
