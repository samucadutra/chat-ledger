"""Intake: matters, content-addressed blobs and collections.

Revision ID: 0002_intake
Revises: 0001_foundation
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0002_intake"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE matter (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name VARCHAR(80) NOT NULL
                CONSTRAINT ck_matter_name_len CHECK (char_length(btrim(name)) BETWEEN 3 AND 80),
            name_key VARCHAR(80) GENERATED ALWAYS AS (lower(btrim(name))) STORED,
            description VARCHAR(500),
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )
    op.execute("CREATE UNIQUE INDEX uq_matter_name_key ON matter (name_key)")
    op.execute("CREATE INDEX ix_matter_created_at ON matter (created_at DESC)")

    op.execute(
        """
        CREATE TABLE blob (
            sha256 CHAR(64) PRIMARY KEY
                CONSTRAINT ck_blob_sha256_hex CHECK (sha256 ~ '^[0-9a-f]{64}$'),
            size_bytes BIGINT NOT NULL,
            storage_path TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE collection (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id UUID NOT NULL
                CONSTRAINT fk_collection_matter REFERENCES matter(id) ON DELETE RESTRICT,
            blob_sha256 CHAR(64) NOT NULL
                CONSTRAINT fk_collection_blob REFERENCES blob(sha256) ON DELETE RESTRICT,
            original_filename VARCHAR(255) NOT NULL,
            size_bytes BIGINT NOT NULL,
            source VARCHAR(16) NOT NULL
                CONSTRAINT ck_collection_source CHECK (source IN ('upload','generator')),
            entry_count INTEGER NOT NULL,
            conversation_count INTEGER NOT NULL,
            export_date_from DATE,
            export_date_to DATE,
            root_prefix VARCHAR(255) NOT NULL DEFAULT '',
            added_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT ck_collection_counts CHECK (
                entry_count >= 0 AND conversation_count >= 0 AND size_bytes > 0
            ),
            CONSTRAINT ck_collection_dates CHECK (
                export_date_from IS NULL OR export_date_to >= export_date_from
            )
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_collection_matter_blob ON collection (matter_id, blob_sha256)"
    )
    op.execute("CREATE INDEX ix_collection_matter_added ON collection (matter_id, added_at)")
    op.execute("CREATE INDEX ix_collection_blob ON collection (blob_sha256)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS collection")
    op.execute("DROP TABLE IF EXISTS blob")
    op.execute("DROP TABLE IF EXISTS matter")
