"""Foundation: job queue, append-only audit log, worker heartbeat.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-10-01
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE job (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind VARCHAR(64) NOT NULL,
            payload JSONB NOT NULL DEFAULT '{}',
            state VARCHAR(16) NOT NULL DEFAULT 'queued'
                CONSTRAINT ck_job_state CHECK (state IN ('queued','leased','done','failed')),
            priority SMALLINT NOT NULL DEFAULT 100,
            group_key VARCHAR(128),
            attempts INTEGER NOT NULL DEFAULT 0,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            lease_owner VARCHAR(128),
            lease_expires_at TIMESTAMPTZ,
            run_after TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_job_attempts CHECK (attempts >= 0 AND max_attempts >= 1),
            CONSTRAINT ck_job_lease CHECK (
                state <> 'leased' OR (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
            )
        )
        """
    )
    op.execute("CREATE INDEX ix_job_claimable ON job (priority, created_at) WHERE state = 'queued'")
    op.execute("CREATE INDEX ix_job_leased_expiry ON job (lease_expires_at) WHERE state = 'leased'")
    op.execute(
        "CREATE INDEX ix_job_group_state ON job (group_key, state) WHERE group_key IS NOT NULL"
    )

    op.execute(
        r"""
        CREATE TABLE audit_event (
            id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            action VARCHAR(64) NOT NULL
                CONSTRAINT ck_audit_action_format CHECK (action ~ '^[a-z_]+(\.[a-z_]+)+$'),
            entity_type VARCHAR(64) NOT NULL,
            entity_id VARCHAR(128) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    op.execute("CREATE INDEX ix_audit_entity ON audit_event (entity_type, entity_id, id)")
    op.execute("CREATE INDEX ix_audit_occurred_at ON audit_event (occurred_at)")
    op.execute(
        """
        CREATE FUNCTION audit_event_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_event is append-only' USING ERRCODE = '55000';
        END $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_update_delete
            BEFORE UPDATE OR DELETE ON audit_event
            FOR EACH ROW EXECUTE FUNCTION audit_event_append_only()
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_event_no_truncate
            BEFORE TRUNCATE ON audit_event
            FOR EACH STATEMENT EXECUTE FUNCTION audit_event_append_only()
        """
    )

    op.execute(
        """
        CREATE TABLE worker_heartbeat (
            worker_id VARCHAR(128) PRIMARY KEY,
            hostname VARCHAR(255) NOT NULL,
            pid INTEGER NOT NULL,
            git_sha VARCHAR(40) NOT NULL,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            current_job_id UUID
        )
        """
    )
    op.execute("CREATE INDEX ix_worker_heartbeat_last_seen ON worker_heartbeat (last_seen_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS worker_heartbeat")
    op.execute("DROP TABLE IF EXISTS audit_event")
    op.execute("DROP FUNCTION IF EXISTS audit_event_append_only()")
    op.execute("DROP TABLE IF EXISTS job")
