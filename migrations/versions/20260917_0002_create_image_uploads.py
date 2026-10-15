"""Create image upload sessions.

Revision ID: 20260917_0002
Revises: 20260915_0001
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260917_0002"
down_revision: str | None = "20260915_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "image_uploads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("image_id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("case_id", sa.Uuid(), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('DICOM', 'PNG', 'JPEG')", name="ck_image_uploads_kind"),
        sa.CheckConstraint(
            "status IN ('PENDING_UPLOAD')",
            name="ck_image_uploads_status",
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 104857600",
            name="ck_image_uploads_size_range",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["clinical_cases.id"],
            name="fk_image_uploads_case_id_clinical_cases",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_uploads"),
        sa.UniqueConstraint("image_id", name="uq_image_uploads_image_id"),
        sa.UniqueConstraint("object_key", name="uq_image_uploads_object_key"),
    )
    op.create_index(
        "ix_image_uploads_tenant_case",
        "image_uploads",
        ["tenant_id", "case_id"],
    )
    op.create_index("ix_image_uploads_expires_at", "image_uploads", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_image_uploads_expires_at", table_name="image_uploads")
    op.drop_index("ix_image_uploads_tenant_case", table_name="image_uploads")
    op.drop_table("image_uploads")
