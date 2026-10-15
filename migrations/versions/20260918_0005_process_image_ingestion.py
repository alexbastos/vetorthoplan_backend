"""Process image ingestion jobs and expose image state.

Revision ID: 20260918_0005
Revises: 20260917_0004
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260918_0005"
down_revision: str | None = "20260917_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("image_uploads", sa.Column("detected_media_type", sa.String(64)))
    op.add_column("image_uploads", sa.Column("width_px", sa.Integer()))
    op.add_column("image_uploads", sa.Column("height_px", sa.Integer()))
    op.add_column("image_uploads", sa.Column("rejection_code", sa.String(64)))
    op.add_column("image_uploads", sa.Column("processed_at", sa.DateTime(timezone=True)))
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD', 'QUARANTINED', 'PROCESSING', 'READY', 'REJECTED')",
    )

    op.add_column("image_ingestion_jobs", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("image_ingestion_jobs", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.add_column("image_ingestion_jobs", sa.Column("error_code", sa.String(64)))
    op.drop_constraint(
        "ck_image_ingestion_jobs_status",
        "image_ingestion_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_ingestion_jobs_status",
        "image_ingestion_jobs",
        "status IN ('QUEUED', 'PROCESSING', 'SUCCEEDED', 'REJECTED', 'FAILED')",
    )


def downgrade() -> None:
    op.execute(
        "UPDATE image_ingestion_jobs SET status = 'QUEUED', started_at = NULL, "
        "finished_at = NULL, error_code = NULL WHERE status <> 'QUEUED'"
    )
    op.drop_constraint(
        "ck_image_ingestion_jobs_status",
        "image_ingestion_jobs",
        type_="check",
    )
    op.create_check_constraint(
        "ck_image_ingestion_jobs_status",
        "image_ingestion_jobs",
        "status IN ('QUEUED')",
    )
    op.drop_column("image_ingestion_jobs", "error_code")
    op.drop_column("image_ingestion_jobs", "finished_at")
    op.drop_column("image_ingestion_jobs", "started_at")

    op.execute(
        "UPDATE image_uploads SET status = 'QUARANTINED', detected_media_type = NULL, "
        "width_px = NULL, height_px = NULL, rejection_code = NULL, processed_at = NULL "
        "WHERE status IN ('PROCESSING', 'READY', 'REJECTED')"
    )
    op.drop_constraint("ck_image_uploads_status", "image_uploads", type_="check")
    op.create_check_constraint(
        "ck_image_uploads_status",
        "image_uploads",
        "status IN ('PENDING_UPLOAD', 'QUARANTINED')",
    )
    op.drop_column("image_uploads", "processed_at")
    op.drop_column("image_uploads", "rejection_code")
    op.drop_column("image_uploads", "height_px")
    op.drop_column("image_uploads", "width_px")
    op.drop_column("image_uploads", "detected_media_type")
