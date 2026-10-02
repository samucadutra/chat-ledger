"""Synthetic export generations (F03).

Revision ID: 0003_generation
Revises: 0002_intake
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003_generation"
down_revision: str | None = "0002_intake"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE generation (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            matter_id UUID NOT NULL
                CONSTRAINT fk_generation_matter REFERENCES matter(id) ON DELETE RESTRICT,
            seed BIGINT NOT NULL
                CONSTRAINT ck_generation_seed CHECK (seed BETWEEN 0 AND 2147483647),
            preset VARCHAR(8) NOT NULL
                CONSTRAINT ck_generation_preset
                CHECK (preset IN ('small','medium','large','custom')),
            profile VARCHAR(8) NOT NULL
                CONSTRAINT ck_generation_profile CHECK (profile IN ('clean','default','stress')),
            messages INTEGER NOT NULL,
            conversations INTEGER NOT NULL,
            overlap_of_collection_id UUID
                CONSTRAINT fk_generation_overlap_collection REFERENCES collection(id)
                ON DELETE RESTRICT,
            overlap_days_pct SMALLINT NOT NULL DEFAULT 30
                CONSTRAINT ck_generation_overlap_pct CHECK (overlap_days_pct BETWEEN 1 AND 100),
            job_id UUID
                CONSTRAINT fk_generation_job REFERENCES job(id) ON DELETE SET NULL,
            state VARCHAR(10) NOT NULL DEFAULT 'queued'
                CONSTRAINT ck_generation_state
                CHECK (state IN ('queued','running','done','failed')),
            progress_messages INTEGER NOT NULL DEFAULT 0,
            collection_id UUID
                CONSTRAINT fk_generation_collection REFERENCES collection(id)
                ON DELETE RESTRICT,
            ground_truth_sha256 CHAR(64),
            error_code VARCHAR(64),
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
            CONSTRAINT ck_generation_messages CHECK (
                messages BETWEEN 1000 AND 1000000 AND conversations BETWEEN 1 AND 5000
            ),
            CONSTRAINT ck_generation_done_collection CHECK (
                state <> 'done' OR collection_id IS NOT NULL
            )
        )
        """
    )
    op.execute(
        "CREATE INDEX ix_generation_matter_created ON generation (matter_id, created_at DESC)"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_generation_collection ON generation (collection_id) "
        "WHERE collection_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS generation")
