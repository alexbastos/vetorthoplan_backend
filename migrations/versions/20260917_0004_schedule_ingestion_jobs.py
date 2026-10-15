"""Schedule durable image ingestion jobs.

Revision ID: 20260917_0004
Revises: 20260917_0003
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0004"
down_revision: str | None = "20260917_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_ingestion_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('QUEUED')", name="ck_image_ingestion_jobs_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_image_ingestion_jobs_attempts_nonnegative"),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["clinical_cases.id"],
            name="fk_image_ingestion_jobs_case_id_clinical_cases",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["image_uploads.id"],
            name="fk_image_ingestion_jobs_upload_id_image_uploads",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_ingestion_jobs"),
        sa.UniqueConstraint("image_id", name="uq_image_ingestion_jobs_image_id"),
        sa.UniqueConstraint("upload_id", name="uq_image_ingestion_jobs_upload_id"),
    )
    op.create_index(
        "ix_image_ingestion_jobs_status_created_at",
        "image_ingestion_jobs",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_image_ingestion_jobs_tenant_id",
        "image_ingestion_jobs",
        ["tenant_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_image_ingestion_jobs_tenant_id", table_name="image_ingestion_jobs")
    op.drop_index(
        "ix_image_ingestion_jobs_status_created_at",
        table_name="image_ingestion_jobs",
    )
    op.drop_table("image_ingestion_jobs")
